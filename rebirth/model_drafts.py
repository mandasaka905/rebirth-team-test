"""New business models remain drafts until reviewed and explicitly accepted by a merchant."""
from copy import deepcopy
from .domain import ValidationError, identifier, integer, nonempty, money
from .planning import validate_models, assess_models


def validate_draft(d):
    if not isinstance(d,dict): raise ValidationError("模式草案须为对象")
    identifier(d.get("id"));integer(d.get("version"),"草案版本",1000000)
    if not d["version"] or d.get("owner")!="customer": raise ValidationError("模式草案由客户与经营方式角色负责，版本须为正数")
    model=deepcopy(d.get("model"));validate_models([model])
    if model["status"]!="candidate": raise ValidationError("智能体只能提交候选模式，不能修改现状")
    for k in ("rationale","validation_plan"): nonempty(d.get(k),k)
    for k in ("assumptions","supply_requirements","evidence_ids"):
        if not isinstance(d.get(k),list): raise ValidationError(k+"须为列表")
    if not d["assumptions"] or not all(isinstance(x,str) and x.strip() for x in d["assumptions"]): raise ValidationError("模式必须声明待验证假设")
    seen_skus=set()
    for r in d["supply_requirements"]:
        if not isinstance(r,dict): raise ValidationError("商品依赖须为对象")
        identifier(r.get("sku"));integer(r.get("quantity"),"所需件数")
        if r["sku"] in seen_skus:raise ValidationError("同一模式的商品依赖不能重复，请合并数量")
        seen_skus.add(r["sku"])
        if not r["quantity"]: raise ValidationError("所需商品数量须大于0")
        if r.get("offer_id"):identifier(r["offer_id"])
    return d


def assess_draft(ledger,draft):
    d=validate_draft(deepcopy(draft));m=d["model"]
    assessed=assess_models({**ledger,"business_models":[m]})["models"][0]
    blockers=[];warnings=list(assessed["issues"])
    if m["weekly_hours"]>ledger["weekly_available_hours"]:blockers.append("每周工时超过店主可用时间")
    if m.get("investment") is not None and money(m["investment"])>money(ledger["max_trial_budget"]):blockers.append("初始投入超过预算")
    if assessed["unit_contribution"] is not None and money(assessed["unit_contribution"],negative=True)<=0:blockers.append("单位贡献非正，先修改模式")
    products={p["sku"]:p for p in ledger["products"]};offers={o["id"]:o for o in ledger.get("supply_options",[])}
    for r in d["supply_requirements"]:
        p=products.get(r["sku"])
        if p is None: blockers.append("所需商品不存在："+r["sku"]);continue
        if r["quantity"]>p["stock"]:
            o=offers.get(r.get("offer_id"))
            if not o or o["sku"]!=r["sku"]:blockers.append("现货不足且未关联同商品供应条件："+r["sku"])
            elif not o["confirmed"] or any(o.get(k) is None for k in ("lead_days","payment_days","capacity","min_qty","unit_cost","shipping_cost")):blockers.append("补货供应条件尚未核实："+r["sku"])
            elif r["quantity"]-p["stock"]>o["capacity"]:blockers.append("所需补货超出供应能力："+r["sku"])
            else:warnings.append("依赖补货："+r["sku"]+"；到货、起订量与现金必须在具体行动方案中重算")
    if not d["supply_requirements"]:warnings.append("尚未明确商品依赖，进入行动前须补齐")
    warnings.append("模式订单数是假设；入库不代表可执行，仍须具体方案现金与库存复核")
    stock_facts=[r["sku"]+"：需要"+str(r["quantity"])+"件，现货"+str(products.get(r["sku"],{}).get("stock","未知"))+"件" for r in d["supply_requirements"]]
    perspectives={"inventory":stock_facts+[x for x in blockers+warnings if any(k in x for k in ("商品","补货","供应","库存"))] or ["核对现货、尺码及交付条件；需要补货时在行动方案中验证到货"],
                  "cash":[x for x in blockers+warnings if any(k in x for k in ("贡献","成本","费用","预算","投入","订单"))] or ["本模式仍需逐日现金与必要付款核算"],
                  "customer":["需求证据仍是待验证线索："+m["demand_evidence"],"验证安排："+d["validation_plan"]]+[x for x in blockers+warnings if "能力" in x or "工时" in x]}
    return {"perspectives":perspectives,"draft_id":d["id"],"version":d["version"],"assessment":assessed,"blockers":list(dict.fromkeys(blockers)),"warnings":list(dict.fromkeys(warnings))}


def rule_draft(ledger,evidence_ids,prior=None):
    if not ledger.get("customer_signals") or not ledger["products"]: return None
    current=next((m for m in ledger.get("business_models",[]) if m["status"]=="current"),None)
    product=next((p for p in ledger["products"] if p["stock"] and p["size_complete"] is True),ledger["products"][0])
    m={"id":"mode_exploration","version":1,"status":"candidate","name":"预约到店与小范围需求核验（规则草案）",
       "customer_segment":current["customer_segment"] if current else "已有反馈涉及的客户，具体客群待核实",
       "customer_problem":"购买时间、尺码或服务需求是否不匹配，待访谈核实",
       "value_proposition":"先核实需求和可用商品，再安排小范围预约试穿",
       "channel":"仅对已自愿咨询的客户提供预约入口；不自动联系客户",
       "fulfilment":"确认款式尺码、交付时间和售后条件后到店交付",
       "revenue_method":"成交后按件销售；未核实前不视为已有订单",
       "key_resources":"现有门店、商品、店主可用时间",
       "required_skills":"接待\n库存核对\n预约协调","available_skills":current["available_skills"] if current else "待核实",
       "demand_evidence":"原始客户观察仅支持提出假设，不能证明购买意愿或成交",
       "source_note":"本地透明模板，非大模型；证据见草案关联工具结果",
       "period_days":30,"unit_revenue":product["unit_price"],"unit_cost":product["unit_cost"],"fixed_cost":None,"investment":None,
       "assumed_orders":None,"weekly_hours":min(4,ledger["weekly_available_hours"]),"costs_confirmed":False}
    return {"id":"customer_mode","version":prior["version"]+1 if prior else 1,"owner":"customer","model":m,
            "rationale":"依据已录客户观察提出一个可否决的模式假设，先核实服务障碍而非强制上电商",
            "assumptions":["预约意愿尚未验证","额外费用与所需能力待店主核实"],
            "supply_requirements":[{"sku":product["sku"],"quantity":min(2,product["stock"]) or 1,"offer_id":""}],
            "validation_plan":"先核实客户拒绝原因、愿意到店时间及款式尺码；限额试验后比较同口径结果",
            "evidence_ids":list(evidence_ids)}
