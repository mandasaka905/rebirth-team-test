"""Observed outcomes are separate from hypothetical proposals and forecasts."""

from copy import deepcopy
from datetime import timedelta, date
from decimal import Decimal

from .domain import ValidationError, amount, day, identifier, integer, money, nonempty


def validate_feedback(raw, proposal, snapshot):
    if not isinstance(raw, dict):
        raise ValidationError("反馈必须是对象")
    data = deepcopy(raw)
    try:
        identifier(data["id"])
        identifier(data["run_id"])
        if data["proposal_id"] != proposal["id"] or type(data["proposal_version"]) is not int or data["proposal_version"] != proposal["version"]:
            raise ValidationError("反馈必须指向任务中保留的精确方案版本")
        if type(data["synthetic"]) is not bool or data["synthetic"] != snapshot["synthetic"]:
            raise ValidationError("反馈的合成标记必须与该任务底账一致")
        if not day(proposal["spend_date"]) <= day(data["period_start"]) <= day(data["period_end"]) <= day(snapshot["as_of"]) + timedelta(days=30):
            raise ValidationError("反馈期间必须位于方案支出日至底账后30天内")
        if data["period_start"] != proposal["spend_date"]:
            raise ValidationError("反馈需从方案支出日开始累计记录，不能漏掉前期费用")
        if not data["synthetic"] and day(data["period_end"]) > date.today():
            raise ValidationError("真实反馈不可填写未来日期；虚构验收只能使用合成店铺")
        nonempty(data["source_note"], "反馈来源说明")
        money(data["fixed_spend"])
        if proposal.get("procurements"):
            money(data.get("procurement_paid"))
            money(data.get("procurement_expense"))
            if money(data["procurement_expense"])>money(data["procurement_paid"]):raise ValidationError("本简化现金口径中采购运费等费用不能超过采购实付")
            if not isinstance(data.get("items"),list):raise ValidationError("反馈items必须为列表")
            for item in data["items"]:
                if not isinstance(item,dict):raise ValidationError("反馈商品须为对象")
                if item.get("actual_goods_cost") is not None: money(item["actual_goods_cost"])
        integer(data["hours_spent"], "实际总工时", 744)
        if type(data["costs_confirmed"]) is not bool:
            raise ValidationError("反馈费用确认标记必须为布尔值")
        if not isinstance(data["items"], list):
            raise ValidationError("反馈items必须为列表")
        planned = {p["sku"]: p for p in proposal["items"]}
        seen = set()
        for item in data["items"]:
            sku = item["sku"]
            if not isinstance(sku, str) or sku not in planned or sku in seen:
                raise ValidationError("反馈商品不存在或重复")
            seen.add(sku)
            integer(item["units_sold"], "实际销售件数")
            integer(item["units_returned"], "退货件数")
            item.setdefault("units_returned_resellable", 0 if item["units_returned"] == 0 else None)
            integer(item["units_returned_resellable"], "可再次销售退回件数")
            if item["units_returned"] > item["units_sold"] or item["units_sold"] > planned[sku]["quantity"]:
                raise ValidationError("退货不能超过销售，试验销售不能超出该方案商品范围")
            if item["units_returned_resellable"] > item["units_returned"]:
                raise ValidationError("可再次销售件数不能超过退回件数")
            for field in ("cash_received", "refund_paid", "variable_spend"):
                money(item[field])
            if money(item["refund_paid"]) > money(item["cash_received"]):
                raise ValidationError("退款不得超过本次试验收款；跨期退款需单独核对")
            if item["units_sold"] == 0 and (money(item["cash_received"]) or money(item["refund_paid"])):
                raise ValidationError("未发生销售的商品不能录入销售收款或退款")
        if seen != set(planned):
            raise ValidationError("必须逐项记录全部试验商品，零销量也要明确录入")
        if not isinstance(data["observations"], list) or not all(isinstance(x, str) and x.strip() for x in data["observations"]):
            raise ValidationError("observations必须是文字观察列表")
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"反馈结构不完整：{exc}") from exc
    return data


def summarize_feedback(data, proposal, snapshot):
    products = {p["sku"]: p for p in snapshot["products"]}
    planned = {p["sku"]: p for p in proposal["items"]}
    gross, refunds, variable, cost = (Decimal(0) for _ in range(4))
    missing_cost = False
    units, returns, planned_revenue = 0, 0, Decimal(0)
    for item in data["items"]:
        sku = item["sku"]
        units += item["units_sold"]
        returns += item["units_returned"]
        gross += money(item["cash_received"])
        refunds += money(item["refund_paid"])
        variable += money(item["variable_spend"])
        if proposal.get("procurements"):
            if item.get("actual_goods_cost") is None: missing_cost=True
            else: cost+=money(item["actual_goods_cost"])
        elif products[sku]["unit_cost"] is None:
            missing_cost = True
        else:
            cost += money(products[sku]["unit_cost"]) * (item["units_sold"]-item["units_returned_resellable"])
        planned_revenue += money(planned[sku]["price"]) * planned[sku]["quantity"]
    net = gross - refunds
    expenses = money(data["fixed_spend"]) + variable
    procurement_paid = money(data.get("procurement_paid", "0")) if proposal.get("procurements") else Decimal(0)
    procurement_expense = money(data.get("procurement_expense", "0")) if proposal.get("procurements") else Decimal(0)
    expenses += procurement_expense
    spending = expenses + procurement_paid - procurement_expense
    unknowns = []
    if not data["costs_confirmed"]:
        unknowns.append("实际费用尚未核实")
    if missing_cost:
        unknowns.append("部分商品采购成本缺失")
    if data["synthetic"]:
        unknowns.append("合成反馈不能作为真实经营效果")
    planned_qty = sum(x["quantity"] for x in proposal["items"])
    questions = []
    if units < planned_qty:
        questions.append({"owner": "customer", "question": "未成交的原因是什么？请补充接触人数、购买反馈或执行差异。"})
    if returns:
        questions.append({"owner": "inventory", "question": "退货是否与尺码、质量或商品描述有关？需要核实原因及退回商品状态。"})
    planned_spend=money(proposal["upfront_cost"])+money(proposal["other_cost"])+sum((money(x["variable_cash_cost"])*x["quantity"] for x in proposal["items"]),Decimal(0))
    if proposal.get("procurements"):
        from .supply import plan
        planned_supply=plan(snapshot,proposal)
        planned_spend=planned_spend+money(planned_supply["cash_commitment"]) if planned_supply["costs_complete"] else None
    if planned_spend is None:unknowns.append("原方案采购费用未核实，无法判断是否超支")
    if planned_spend is not None and spending > planned_spend:
        questions.append({"owner": "cash", "question": "实际费用超过原计划，增加项及付款日期是什么？"})
    if not missing_cost and net - cost - expenses < 0:
        questions.append({"owner": "cash", "question": "试验毛利贡献为负，需检查折扣、退款、费用和执行条件，不能仅凭回款判断成功。"})
    return {"feedback_id": data["id"], "run_id": data["run_id"], "proposal_id": proposal["id"],
            "proposal_version": proposal["version"], "owner": proposal["owner"],
            "period_end": data["period_end"], "synthetic": data["synthetic"],
            "units_sold": units, "units_returned": returns, "net_units": units-returns,
            "gross_cash_received": amount(gross), "refund_paid": amount(refunds),
            "net_cash_received": amount(net), "actual_trial_spend": amount(spending),
            "trial_net_cash": amount(net-spending),
            "procurement_paid": amount(procurement_paid), "procurement_expense": amount(procurement_expense), "trial_margin_contribution": None if missing_cost else amount(net-cost-expenses),
            "declared_sales_revenue": amount(planned_revenue), "receipt_gap_vs_declared": amount(net-planned_revenue),
            "unknowns": unknowns, "follow_up_questions": questions,
            "observations": data["observations"], "hours_spent": data["hours_spent"],
            "interpretation": "仅描述该次试验收支，不证明行动导致了收入变化，不自动调整当前底账、库存或模型。现货反馈仅核实可再次销售的退货冲回商品成本；补货方案须填写实际已售成本（含退货调整），采购实付及其中运费期间费用分开，未售采购不重复扣作毛利成本；本简化口径不处理采购费用赊欠与税额。"}
