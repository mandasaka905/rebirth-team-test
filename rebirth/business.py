"""Conditional business observations; no demand forecasts or causal claims."""
from decimal import Decimal
from .domain import ValidationError, amount, day, identifier, integer, money


def validate_periods(periods, as_of, sources):
    if not isinstance(periods, list) or len(periods) > 60 or not all(isinstance(p, dict) for p in periods):
        raise ValidationError("经营期间必须为对象列表，最多60期")
    ordered = sorted(periods, key=lambda p: p.get("start", ""))
    previous, seen = None, set()
    for p in ordered:
        try:
            identifier(p["id"])
            if "scope_id" in p or "count_basis" in p:
                identifier(p.get("scope_id"))
                if p.get("count_basis") not in ("person_visits", "unique_people"):
                    raise ValidationError("经营期间需声明有效的范围和计数口径")
            if p["id"] in seen:
                raise ValidationError("经营期间ID重复")
            seen.add(p["id"])
            if not day(p["start"]) <= day(p["end"]) <= day(as_of):
                raise ValidationError("期间日期不可倒置或晚于底账日期")
            if previous and day(p["start"]) <= day(previous):
                raise ValidationError("经营期间不能重叠")
            previous = p["end"]
            for k in ("revenue", "goods_cost", "operating_cost"):
                if p.get(k) is not None:
                    money(p[k])
            for k in ("visits", "buyers", "returning_buyers"):
                if p.get(k) is not None:
                    integer(p[k], k)
            if p.get("buyers") is not None and p.get("visits") is not None and p["buyers"] > p["visits"]:
                raise ValidationError("成交人次不能超过到店人次")
            if p.get("returning_buyers") is not None and p.get("buyers") is not None and p["returning_buyers"] > p["buyers"]:
                raise ValidationError("老客成交人次不能超过成交人次")
            if p["source_id"] not in sources:
                raise ValidationError("期间引用未知来源")
        except (KeyError, TypeError) as exc:
            raise ValidationError("经营期间结构不完整") from exc
    return ordered


def diagnostics(ledger, args=None):
    rows = []
    for p in sorted(ledger.get("operating_periods", []), key=lambda p: p["end"]):
        days = (day(p["end"]) - day(p["start"])).days + 1
        contribution = None if any(p.get(k) is None for k in ("revenue", "goods_cost", "operating_cost")) else money(p["revenue"]) - money(p["goods_cost"]) - money(p["operating_cost"])
        rows.append({**p, "days": days, "contribution": amount(contribution) if contribution is not None else None,
            "revenue_per_day": str(round(money(p["revenue"])/days, 2)) if p.get("revenue") is not None else None,
            "contribution_per_day": str(round(contribution/days, 2)) if contribution is not None else None,
            "visits_per_day": str(round(Decimal(p["visits"])/days, 2)) if p.get("visits") is not None else None,
            "conversion": str(round(Decimal(p["buyers"])/p["visits"], 4)) if p.get("buyers") is not None and p.get("visits") else None,
            "returning_share": str(round(Decimal(p["returning_buyers"])/p["buyers"], 4)) if p.get("returning_buyers") is not None and p.get("buyers") else None})
    findings = []
    comparison_status = "needs_two_periods"
    if len(rows) >= 2:
        old, new = rows[-2:]
        old_scope = (old.get("scope_id", "shop_all"), old.get("count_basis", "person_visits"))
        new_scope = (new.get("scope_id", "shop_all"), new.get("count_basis", "person_visits"))
        comparison_status = "comparable" if old_scope == new_scope else "scope_mismatch"
        for field, title, owner, question in (
            ("revenue_per_day", "日均营业额", "customer", "营业时间、商品结构或转化是否变化？不能只归因于电商。"),
            ("visits_per_day", "日均到店人次", "customer", "闭店、统计口径或周边客流是否变化？"),
            ("conversion", "到店成交比例", "customer", "顾客未成交时提到价格、尺码、品质还是其他原因？"),
            ("returning_share", "老客成交占比", "customer", "占比不是流失率；需要客户分组与自愿回访证据。"),
            ("contribution_per_day", "日均经营贡献", "cash", "请核对商品成本、房租、人工和折扣；这不是税后净利润。")):
            if comparison_status == "comparable" and old[field] is not None and new[field] is not None and Decimal(new[field]) < Decimal(old[field]):
                findings.append({"metric": field, "title": title+"较前期下降", "before": old[field], "after": new[field], "owner": owner, "question": question})
    from .planning import assess_models
    from .accounting import reconcile
    from .cohorts import analyze_cohorts
    return {"cohorts": analyze_cohorts(ledger), "models": assess_models(ledger), "accounts": reconcile(ledger), "periods": rows, "findings": findings, "needs_two_periods": len(rows) < 2, "comparison_status": comparison_status,
        "note": ("最近两期的经营范围或计数口径不同，保留各期数据，不输出升降比较。" if comparison_status == "scope_mismatch" else "只比较最近两期，金额和计数按天归一；未声明标签的旧记录沿用全店人次口径，仍须人工核实。")+"季节和营业天数仍可能不同。经营贡献=营业额-商品成本-已录经营费用，不是税后净利润；不推断原因。"}


STRATEGIES = [
    {"id": "inventory", "title": "存量商品小范围调整", "owner": "inventory", "requirements": "成本、尺码、库存明确；先调查再决定折价", "risk": "折价可能损伤毛利，不能只看回款"},
    {"id": "appointment", "title": "下班后预约试衣", "owner": "customer", "requirements": "实际预约线索、可投入时间和可试穿商品", "risk": "询问不等于预约或成交"},
    {"id": "display", "title": "线下陈列对照试验", "owner": "inventory", "requirements": "小批商品、两种陈列方式、同口径观察", "risk": "时间段客流差异不是陈列效果"},
    {"id": "return_visit", "title": "自愿老客需求回访", "owner": "customer", "requirements": "顾客同意联系，先收集需求；不自动发送营销", "risk": "不得收集不必要的个人信息或承诺销量"},
    {"id": "online", "title": "线上展示、线下核验交付", "owner": "customer", "requirements": "明确渠道费用、履约时间和实际咨询线索", "risk": "不连接销售平台；需核实费用、退货和合规条件"},
    {"id": "livestream", "title": "直播渠道小范围可行性核查", "owner": "customer", "requirements": "先核实运营能力、平台成本、退货和履约", "risk": "仅将明示成本填入情景，不预测流量、转化或默认推荐投入"},
]


def compare_candidates(entries):
    rows = []
    for e in entries:
        p, v = e["proposal"], e["evaluation"]
        rows.append({"id": p["id"], "title": p["title"], "version": p["version"], "spend": v["trial_cash_commitment"],
            "hours": p["weekly_hours"], "cash_floor": v["scenarios"][0]["minimum_cash_before_receipts"],
            "contribution": v["gross_profit_after_declared_trial_costs"], "hard_pass": v["constraint_pass"] and not e.get("objections"),
            "unknowns": len(v["unknowns"]), "dominated_by": []})
    def values(r):
        return (-money(r["spend"]), -Decimal(r["hours"]), money(r["cash_floor"], negative=True), money(r["contribution"], negative=True))
    for a in rows:
        if not a["hard_pass"] or a["contribution"] is None:
            continue
        for b in rows:
            if a is b or not b["hard_pass"] or b["contribution"] is None:
                continue
            if all(x >= y for x, y in zip(values(b), values(a))) and any(x > y for x, y in zip(values(b), values(a))):
                a["dominated_by"].append(b["id"]+"@v"+str(b["version"]))
    return {"rows": rows, "note": "仅在这组明示假设候选中比较投入、工时、零销量最低现金和申报贡献；非支配不是全局最优或执行推荐。备选不能叠加。"}
