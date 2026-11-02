"""Deterministic calculations. LLMs never own financial arithmetic."""

from datetime import timedelta
from decimal import Decimal

from .domain import ValidationError, amount, day, money, validate_proposal
from .readiness import questions
from .business import diagnostics


ZERO = Decimal(0)


def inventory(ledger, args):
    as_of = day(ledger["as_of"])
    rows = []
    from .supply import analyze
    from .operating_imports import stale_sales
    stale=stale_sales(ledger)
    for p in ledger["products"]:
        age = (as_of - day(p["received_on"])).days
        rows.append({"sku": p["sku"], "stock": p["stock"], "sales_30d": p["sales_30d"],
                     "age_days": age, "size_complete": p["size_complete"],
                     "slow_moving": age >= 90 and p["stock"] > p["sales_30d"] * 2,
                     "unit_cost": p["unit_cost"], "unit_price": p["unit_price"],
                     "source_id": p["source_id"], "sales_window_stale":p["sku"] in stale,
                     "field_sources":{k:ledger.get("field_sources",{}).get("products/"+p["sku"]+"/"+k,p["source_id"]) for k in ("stock","sales_30d","unit_cost","unit_price","size_complete")}})
    return {"supply": analyze(ledger), "products": rows, "policy": "积压筛查规则：入库至少90天且库存大于近30天销量的2倍。不是滞销因果结论。",
            "complete": ledger["completeness"]["inventory_complete"]}


def customers(ledger, args):
    return {"observations": ledger["customer_signals"],
            "unresolved": [] if ledger["customer_signals"] else ["缺少真实客户反馈，不能推定购买意愿"],
            "note": "观察只支持提出假设，不能直接换算未来销量；synthetic来源不是市场证据。"}


def cash_baseline(ledger, args):
    horizon = day(ledger["as_of"]) + timedelta(days=30)
    overdue = [o for o in ledger["obligations"] if day(o["date"]) < day(ledger["as_of"])]
    obligations = sum((money(o["amount"]) for o in ledger["obligations"] if day(o["date"]) <= horizon), ZERO)
    spendable = money(ledger["cash_balance"]) - money(ledger["reserve_floor"]) - obligations
    from .accounting import reconcile
    account_warnings = reconcile(ledger)["warnings"] if "accounts" in ledger else []
    return {"account_warnings": account_warnings, "cash_balance": ledger["cash_balance"], "reserve_floor": ledger["reserve_floor"],
            "obligations_30d_including_overdue": amount(obligations),
            "conservative_budget_ceiling": amount(max(ZERO, min(spendable, money(ledger["max_trial_budget"])))),
            "overdue_ids": [o["id"] for o in overdue],
            "complete": ledger["completeness"]["obligations_complete"] and ledger["completeness"]["receivables_complete"] and not account_warnings,
            "note": "保守上限不计未来回款；仍须检查逐日现金。逾期未付款于首日计入。"}


def evaluate(ledger, args):
    p = validate_proposal(args["proposal"])
    products = {x["sku"]: x for x in ledger["products"]}
    start = day(ledger["as_of"])
    end = start + timedelta(days=30)
    spend = day(p["spend_date"])
    issues, unknowns = [], []
    from .linkage import resolve
    try:
        resolve(ledger, p)
    except ValidationError as exc:
        issues.append({"code": "MODEL_BINDING_REQUIRED", "detail": str(exc)})
    if "accounts" in ledger:
        from .accounting import reconcile
        for warning in reconcile(ledger)["warnings"]:
            unknowns.append(warning)
            issues.append({"code": "UNRECONCILED_ACCOUNTS", "detail": warning})
    if not start <= spend <= end:
        raise ValidationError("方案支出日必须位于底账日后30天内（含当天）")
    from .supply import plan
    supply = plan(ledger, p)
    issues.extend(supply["checks"]); unknowns.extend(supply["unknowns"])
    if not supply["costs_complete"] or supply["unknowns"]:
        issues.append({"code":"SUPPLY_DATA_REQUIRED", "detail":"供应条件或费用未知，补齐后再执行"})
    procurement_cost = money(supply["cash_commitment"])
    known_cost = ZERO
    revenue = ZERO
    variable = ZERO
    from .operating_imports import stale_sales
    stale=stale_sales(ledger)
    for item in p["items"]:
        sku = item["sku"]
        if sku in stale:
            issues.append({"code":"SALES_WINDOW_STALE","sku":sku,"detail":"近30天销量只截至"+stale[sku]["end"]+"，请重新核对"})
        receipt = day(item["receipt_date"])
        if not spend <= receipt <= end:
            raise ValidationError("方案回款日必须位于支出日至30天范围内")
        if sku not in products:
            issues.append({"code": "UNKNOWN_SKU", "sku": sku})
            continue
        stock = products[sku]
        if stock["size_complete"] is False:
            issues.append({"code": "SIZE_EVIDENCE_REQUIRED", "sku": sku})
        elif stock["size_complete"] is None:
            unknowns.append(f"{sku}尺码可用性未确认")
        if supply["sold_costs"].get(sku) is None:
            unknowns.append(f"{sku}采购成本缺失，无法计算完整毛利")
        else:
            known_cost += supply["sold_costs"][sku]
        revenue += money(item["price"]) * item["quantity"]
        variable += money(item["variable_cash_cost"]) * item["quantity"]
    if p["weekly_hours"] > ledger["weekly_available_hours"]:
        issues.append({"code": "WORKLOAD_EXCEEDED", "available": ledger["weekly_available_hours"]})
    upfront = money(p["upfront_cost"]) + money(p["other_cost"])
    # Full declared trial cash commitments must fit budget, not only advertising expense.
    committed_cost = upfront + variable + procurement_cost
    if committed_cost > money(ledger["max_trial_budget"]):
        issues.append({"code": "BUDGET_EXCEEDED", "limit": ledger["max_trial_budget"]})
    if p["sales_assumption"] != "observed":
        unknowns.append("销量尚未由真实成交验证；基准情景仅是商户假设")
    if not p["costs_confirmed"]:
        unknowns.append("活动及单件变动费用尚未核实，不能把零费用当作事实")
    if ledger["synthetic"]:
        unknowns.append("当前底账为合成测试数据，不代表真实商户经营结果")
    if not ledger["merchant_confirmed"]:
        unknowns.append("商户尚未确认经营底账和约束")
    for field, complete in ledger["completeness"].items():
        if not complete:
            unknowns.append(f"底账不完整：{field}")
    if not p["items"] or sum(i["quantity"] for i in p["items"]) == 0:
        unknowns.append("没有正数量商品试验，不能形成经营改善判断")
    daily = []
    # Income assumptions never make a cash-constrained plan silently pass.
    for factor_name, factor in (("zero_sales", ZERO), ("half_sales", Decimal("0.5")), ("declared_sales", Decimal(1))):
        balance = money(ledger["cash_balance"])
        minimum = balance
        breach = None
        points = []
        for n in range(31):
            current = start + timedelta(days=n)
            # Conservative convention: payments before receipts on the same day.
            due = sum((money(o["amount"]) for o in ledger["obligations"]
                       if day(o["date"]) == current or (n == 0 and day(o["date"]) < start)), ZERO)
            out = due + (upfront if current == spend else ZERO)
            out += sum((money(l["cash_cost"]) for l in supply["lines"] if l["payment_date"] == current.isoformat() and l["cash_cost"] is not None), ZERO)
            for item in p["items"]:
                if day(item["receipt_date"]) == current:
                    out += money(item["variable_cash_cost"]) * int(item["quantity"] * factor)
            before_receipts = balance - out
            minimum = min(minimum, before_receipts)
            if before_receipts < money(ledger["reserve_floor"]) and breach is None:
                breach = current.isoformat()
            # Known future receivables only; overdue receivables are uncertain and excluded.
            incoming = sum((money(o["amount"]) for o in ledger["receivables"] if day(o["date"]) == current), ZERO)
            incoming += sum((money(i["price"]) * int(i["quantity"] * factor) for i in p["items"]
                             if day(i["receipt_date"]) == current), ZERO)
            balance = before_receipts + incoming
            points.append({"date": current.isoformat(), "outflow": amount(out), "inflow": amount(incoming), "closing": amount(balance)})
        daily.append({"scenario": factor_name, "minimum_cash_before_receipts": amount(minimum),
                      "ending_cash": amount(balance), "first_reserve_breach": breach, "days": points})
    if daily[0]["first_reserve_breach"]:
        issues.append({"code": "CASH_RESERVE_BREACH_ZERO_SALES", "date": daily[0]["first_reserve_breach"]})
    if any(day(r["date"]) < start for r in ledger["receivables"]):
        unknowns.append("存在逾期应收款，未作为可用现金计入")
    if not supply["costs_complete"] or supply["unknowns"]:
        for scenario in daily:
            scenario.update(minimum_cash_before_receipts=None, ending_cash=None, cash_projection_complete=False)
            for point in scenario["days"]: point.update(outflow=None,closing=None)
    return {"proposal_id": p["id"], "checks": issues, "unknowns": list(dict.fromkeys(unknowns)),
            "constraint_pass": not issues, "eligible_for_merchant_review": not issues and not unknowns,
            "declared_revenue": amount(revenue), "known_stock_cost": amount(known_cost),
            "gross_profit_after_declared_trial_costs": None if not supply["costs_complete"] or any("采购成本缺失" in x for x in unknowns) else amount(revenue-known_cost-upfront-variable-sum((money(l["shipping_cost"]) for l in supply["lines"] if l["shipping_cost"] is not None), ZERO)),
            "incremental_cash_under_declared_sales": amount(revenue-committed_cost),
            "trial_cash_commitment": amount(committed_cost) if supply["costs_complete"] else None, "scenarios": daily,
            "procurement": {k:v for k,v in supply.items() if k != "sold_costs"},
            "definitions": ["已有库存采购款视为已支付：进入毛利成本，不再次列入方案现金支出。未付采购款必须在应付款中录入。",
                            "other_cost为预付额外现金费用；单件变动费用按成交回款日先付后收；补货按供应条件全额付款，不支持分期；运费作为期间费用，未售新货作为库存，不重复算已售成本。",
                            "零销量、半销量是敏感性情景，不是概率预测；半销量按每种商品件数向下取整。返回现金结果依赖录入的全部必要收支。",
                            "方案逐个评估，不能叠加执行；多项行动需合并为一份方案后重算。"]}


TOOLS = {"inventory_analyze": inventory, "customer_evidence": customers,
         "cash_baseline": cash_baseline, "proposal_evaluate": evaluate,
         "business_diagnostics": diagnostics,
         "data_readiness": lambda ledger, args: questions(ledger)}

TOOL_ARGS = {
    "inventory_analyze": {}, "customer_evidence": {}, "cash_baseline": {},
    "proposal_evaluate": {"proposal": "完整方案对象，见config/contracts.json"},
    "data_readiness": {}, "feedback_history": {},
    "business_diagnostics": {}, "knowledge_search": {"query": "本地资料检索词，最多200字"},
    "supply_analyze": {}, "model_draft_evaluate": {"draft":"完整模式草案"},
    "investigation_history": {}, "business_model_assess": {}, "accounts_reconcile": {}, "customer_retention": {},
}


def dispatch(ledger, name, args, *, history=(), knowledge=(), investigations=(), research=()):
    if not isinstance(args, dict):
        raise ValidationError("未知工具或参数类型错误")
    if name == "supply_analyze":
        from .supply import analyze
        return analyze(ledger)
    if name == "model_draft_evaluate":
        from .model_drafts import assess_draft
        return assess_draft(ledger, args.get("draft"))
    if name == "customer_retention":
        from .cohorts import analyze_cohorts
        return analyze_cohorts(ledger)
    if name == "business_model_assess":
        from .planning import assess_models
        return assess_models(ledger)
    if name == "accounts_reconcile":
        from .accounting import reconcile
        return reconcile(ledger)
    if name == "feedback_history":
        return {"experiment_reviews": list(research), "outcomes": list(history), "note": "仅该商户、相同合成标记、且结束日期不晚于当前底账的反馈；是观察，不能据此推定因果。"}
    if name == "knowledge_search":
        from .knowledge import search
        return search(knowledge, args.get("query"))
    if name == "investigation_history":
        return {"cards": list(investigations), "note": "人工记录的支持与反例，仅说明调查进度；有支持证据不等于证明因果。"}
    if name not in TOOLS:
        raise ValidationError("未知工具或参数类型错误")
    if name == "proposal_evaluate" and "proposal" not in args:
        raise ValidationError("缺少proposal")
    return TOOLS[name](ledger, args)
