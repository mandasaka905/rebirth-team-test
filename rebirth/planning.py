"""Explicit business hypotheses and bounded discrete portfolio search; no forecasting."""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
from itertools import combinations
from .domain import ValidationError, amount, day, identifier, integer, money, nonempty, validate_proposal


MODEL_TEXT = ("name", "customer_segment", "customer_problem", "value_proposition", "channel",
              "fulfilment", "revenue_method", "key_resources", "required_skills", "available_skills", "source_note")


def validate_models(raw):
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValidationError("经营模式最多20个")
    ids = set()
    for m in raw:
        if not isinstance(m, dict):
            raise ValidationError("经营模式必须为对象")
        identifier(m.get("id"))
        if m["id"] in ids:
            raise ValidationError("经营模式ID重复")
        ids.add(m["id"])
        m.setdefault("version", 1)
        integer(m["version"], "经营模式版本", 1000000)
        if not m["version"]: raise ValidationError("经营模式版本须大于0")
        for k in MODEL_TEXT:
            nonempty(m.get(k), k)
        if m.get("status") not in ("current", "candidate"):
            raise ValidationError("经营模式状态无效")
        integer(m.get("period_days"), "测算期间天数", 366)
        if not m["period_days"]:
            raise ValidationError("测算天数须大于0")
        for k in ("unit_revenue", "unit_cost", "fixed_cost", "investment"):
            if m.get(k) is not None:
                money(m[k])
        if m.get("assumed_orders") is not None:
            integer(m["assumed_orders"], "假设订单数")
        integer(m.get("weekly_hours"), "每周工时", 168)
        if type(m.get("costs_confirmed")) is not bool:
            raise ValidationError("费用确认必须为布尔值")
        from .model_economics import validate as validate_unit_cost
        validate_unit_cost(m)
        nonempty(m.get("demand_evidence"), "需求证据或明确写待核实")
    return raw


def assess_models(ledger):
    rows = []
    for m in ledger.get("business_models", []):
        unit = None if m.get("unit_revenue") is None or m.get("unit_cost") is None else money(m["unit_revenue"]) - money(m["unit_cost"])
        fixed = money(m["fixed_cost"]) if m.get("fixed_cost") is not None else None
        break_even = int((fixed/unit).to_integral_value(rounding=ROUND_CEILING)) if unit is not None and unit > 0 and fixed is not None else None
        profit = None if m.get("assumed_orders") is None or unit is None or fixed is None else unit*m["assumed_orders"]-fixed
        missing = sorted(set(m["required_skills"].splitlines())-set(m["available_skills"].splitlines()))
        issues = []
        if any(m.get(k) is None for k in ("unit_revenue", "unit_cost", "fixed_cost", "investment")):
            issues.append("存在未知收入或成本，缺失不补零")
        if unit is not None and unit <= 0:
            issues.append("单位贡献不为正，增加订单也不能覆盖固定费用")
        if missing:
            issues.append("能力尚待补齐："+"、".join(missing))
        if m["weekly_hours"] > ledger["weekly_available_hours"]:
            issues.append("每周工时超过店主可投入时间")
        if m.get("investment") is not None and money(m["investment"]) > money(ledger["max_trial_budget"]):
            issues.append("初始投入超过店铺试验预算")
        if not m["costs_confirmed"]:
            issues.append("成本未核实，不能据此判断可持续")
        if profit is not None and profit < 0:
            issues.append("在当前明示订单假设下无法覆盖本期成本")
        rows.append({"model": deepcopy(m), "unit_contribution": amount(unit) if unit is not None else None, "break_even_orders": break_even,
                     "assumed_period_contribution": amount(profit) if profit is not None else None,
                     "investment_payback_periods": str((money(m["investment"])/profit).quantize(Decimal(".01"))) if profit and profit > 0 and m.get("investment") is not None else None,
                     "missing_skills": missing, "issues": issues,
                     "unknowns": ["订单量与需求证据仍需实地验证", "回收期不包含资金时序、税费和未填成本，不等于现金可承受性"]})
    return {"models": rows, "notice": "比较客户、价值、渠道、履约、能力及单位经济；所有订单是假设，不对经营可持续性作保证。"}


def combine(ledger, selected):
    """Only sum explicitly compatible commitments. Never double-count assumed demand silently."""
    proposals = [e["proposal"] for e in selected]
    if len({p["spend_date"] for p in proposals}) != 1:
        raise ValidationError("当前组合仅支持同一天发生固定投入；请先统一支出时点")
    items = {}
    orders = {}
    for proposal in proposals:
        for order in proposal.get("procurements", []):
            key = (order["offer_id"], order["order_date"])
            if key in orders:
                orders[key]["quantity"] += order["quantity"]
                orders[key]["shipping_batches"] += order.get("shipping_batches",1)
            else: orders[key] = {**deepcopy(order),"shipping_batches":order.get("shipping_batches",1)}
    for p in proposals:
        for item in p["items"]:
            old = items.get(item["sku"])
            if old and any(old.get(k) != item.get(k) for k in ("price", "variable_cash_cost", "receipt_date", "sale_date")):
                raise ValidationError("同一SKU的价格、单件费用或回款日不同，不能合并为一笔假设")
            if old:
                old["quantity"] += item["quantity"]
            else:
                items[item["sku"]] = deepcopy(item)
    p = {"id": "portfolio_draft", "version": 1, "owner": "cash", "title": "经约束筛选的组合假设",
         "upfront_cost": amount(sum((money(p["upfront_cost"]) for p in proposals), Decimal(0))),
         "other_cost": amount(sum((money(p["other_cost"]) for p in proposals), Decimal(0))),
         "spend_date": proposals[0]["spend_date"], "weekly_hours": sum(p["weekly_hours"] for p in proposals),
         "sales_assumption": "merchant_estimate", "costs_confirmed": all(p["costs_confirmed"] for p in proposals),
         "procurements": list(orders.values()), "items": list(items.values()), "rationale": "对已声明彼此兼容、需求不重复的候选组合进行有界枚举；仍需交叉复核",
         "model_refs": list({(r["id"],r["version"]):deepcopy(r) for p in proposals for r in p.get("model_refs", [])}.values()),
         "evidence_ids": list(dict.fromkeys(e for p in proposals for e in p["evidence_ids"])),
         "assumptions": ["组合销量不重复由商户确认，系统没有预测增量需求", "投入与工时相加，不假设共享费用优惠"],
         "stop_conditions": ["达到试验预算或现金底线时停止新增投入"]}
    return validate_proposal(p)


def optimize(ledger, entries, *, independent=False, objective="contribution", budget=None):
    from .tools import evaluate
    if not entries or len(entries) > 10:
        raise ValidationError("每次选择1到10个候选，最多检查1023个组合")
    if objective not in ("contribution", "cash_floor"):
        raise ValidationError("筛选目标无效")
    keys = [identifier(e.get("key")) for e in entries]
    if len(set(keys)) != len(keys):
        raise ValidationError("候选代号重复")
    cap = money(ledger["max_trial_budget"] if budget is None else budget)
    if cap > money(ledger["max_trial_budget"]):
        raise ValidationError("组合预算不可超过店铺上限")
    for e in entries:
        deps = e.get("requires", [])
        if not isinstance(deps, list) or not set(deps) <= set(keys) or e["key"] in deps:
            raise ValidationError("依赖必须指向本次其他候选")
        if not isinstance(e.get("exclusive_group", ""), str):
            raise ValidationError("互斥组应为文本")
    base = {"id": "no_action", "version": 1, "owner": "cash", "title": "暂不新增投入",
            "upfront_cost": "0.00", "other_cost": "0.00", "spend_date": ledger["as_of"], "weekly_hours": 0,
            "sales_assumption": "merchant_estimate", "costs_confirmed": True, "items": [],
            "rationale": "无增量行动对照，不代表原经营模式可以持续", "evidence_ids": ["local_baseline"],
            "assumptions": [], "stop_conditions": ["先核对必要付款"]}
    ev = evaluate(ledger, {"proposal": base})
    feasible = [{"keys": [], "proposal": base, "evaluation": ev}] if ev["constraint_pass"] else []
    rejected, checked = [], 0
    for n in range(1, len(entries)+1):
        for chosen in combinations(entries, n):
            checked += 1
            chosen_keys = {e["key"] for e in chosen}
            groups = [e.get("exclusive_group") for e in chosen if e.get("exclusive_group")]
            why = None
            if n > 1 and not independent:
                why = "尚未确认组合需求不重复，仅比较单项"
            elif len(groups) != len(set(groups)):
                why = "同一互斥组不可同时选择"
            elif len({e["proposal"]["id"] for e in chosen}) != n:
                why = "同一方案的不同任务或版本不能叠加投入"
            elif any(not set(e.get("requires", [])) <= chosen_keys for e in chosen):
                why = "前置依赖未入选"
            elif any(e.get("objections") for e in chosen):
                why = "原候选仍有未解决异议"
            try:
                if why:
                    raise ValidationError(why)
                p = combine(ledger, chosen)
                v = evaluate(ledger, {"proposal": p})
                if v["trial_cash_commitment"] is None:
                    raise ValidationError("采购费用未知，不能参与组合预算筛选")
                if money(v["trial_cash_commitment"]) > cap:
                    raise ValidationError("组合支出超过本次筛选预算")
                if not v["constraint_pass"]:
                    raise ValidationError("、".join(c["code"] for c in v["checks"]))
                if v["gross_profit_after_declared_trial_costs"] is None:
                    raise ValidationError("缺少商品成本，不能用于贡献目标排序")
                feasible.append({"keys": sorted(chosen_keys), "proposal": p, "evaluation": v})
            except ValidationError as exc:
                if len(rejected) < 30:
                    rejected.append({"keys": sorted(chosen_keys), "reason": str(exc)})
    def score(r):
        v = r["evaluation"]
        profit = money(v["gross_profit_after_declared_trial_costs"], negative=True)
        floor = money(v["scenarios"][0]["minimum_cash_before_receipts"], negative=True)
        return (profit, floor, -money(v["trial_cash_commitment"])) if objective == "contribution" else (floor, profit, -money(v["trial_cash_commitment"]))
    feasible.sort(key=score, reverse=True)
    return {"objective": objective, "budget": amount(cap), "checked": checked, "feasible_count": len(feasible),
            "best": feasible[0] if feasible else None, "alternatives": feasible[:10], "rejected": rejected,
            "notice": "仅对选中的固定数量候选做离散组合预算选择，不搜索所有商业模式、价格或销量。可选暂不投入；排名不是收益预测或执行批准。"}

