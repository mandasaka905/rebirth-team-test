"""Supply commitments share the proposal stock, margin, budget and cash calculation."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from .domain import ValidationError, identifier, integer, money, amount, nonempty, day

ZERO = Decimal(0)

def validate_offers(rows, ledger):
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValidationError("供应条件最多100条")
    seen = set(); skus = {p["sku"] for p in ledger["products"]}
    for r in rows:
        if not isinstance(r, dict): raise ValidationError("供应条件须为对象")
        identifier(r.get("id")); identifier(r.get("sku"))
        if r["id"] in seen or r["sku"] not in skus: raise ValidationError("供应条件代号重复或商品不存在")
        seen.add(r["id"])
        for k in ("supplier", "source_note", "return_policy"): nonempty(r.get(k), k)
        if day(r.get("checked_on")) > day(ledger["as_of"]): raise ValidationError("供应核对日期不可晚于底账")
        for k in ("lead_days", "payment_days", "min_qty", "capacity", "return_days"):
            if r.get(k) is not None: integer(r[k], k, 1000000 if k in ("min_qty", "capacity") else 366)
        if r.get("min_qty") is not None and r.get("capacity") is not None and r["min_qty"] > r["capacity"]:
            raise ValidationError("起订量不可超过可供数量")
        for k in ("unit_cost", "shipping_cost"):
            if r.get(k) is not None: money(r[k])
        if type(r.get("confirmed")) is not bool or type(r.get("returnable")) not in (bool,type(None)):
            raise ValidationError("须明确供应核实状态，退货可行性可为未知")
    return rows


def analyze(ledger):
    offers = ledger.get("supply_options", [])
    rows=[]
    for p in ledger["products"]:
        options=[deepcopy(o) for o in offers if o["sku"]==p["sku"]]
        days=None if not p["sales_30d"] else str((Decimal(p["stock"])*30/Decimal(p["sales_30d"])).quantize(Decimal('.1')))
        risks=[]
        for o in options:
            if o.get("lead_days") is not None and p["sales_30d"]*o["lead_days"] > p["stock"]*30:
                risks.append(o["id"])
        rows.append({"sku":p["sku"],"coverage_days_at_past_rate":days,"lead_time_risk_offers":risks,"offers":options})
    return {"products":rows,"notice":"覆盖天数仅按近30天历史平均速度作对照，不预测需求；供应日期、数量和退货条件须商户核实。退货或议价所得不计入确定回款。"}


def validate_orders(orders):
    if not isinstance(orders,list) or len(orders)>30: raise ValidationError("方案补货最多30行")
    used=set()
    for x in orders:
        if not isinstance(x,dict): raise ValidationError("补货行须为对象")
        identifier(x.get("offer_id")); day(x.get("order_date")); integer(x.get("quantity"),"补货数量")
        if not x["quantity"]: raise ValidationError("补货数量须大于0")
        integer(x.get("shipping_batches",1),"运费计费批次")
        if not 1<=x.get("shipping_batches",1)<=x["quantity"]:raise ValidationError("运费批次须为1到补货件数之间的整数")
        key=(x["offer_id"],x["order_date"])
        if key in used: raise ValidationError("同一供应条件同日补货不可重复，请合并数量")
        used.add(key)
    return orders


def plan(ledger, proposal):
    start=day(ledger["as_of"]); end=start+timedelta(days=30)
    offers={x["id"]:x for x in ledger.get("supply_options",[])}
    products={x["sku"]:x for x in ledger["products"]}
    lines=[]; checks=[]; unknowns=[]; committed=ZERO; used={}
    for order in validate_orders(proposal.get("procurements",[])):
        o=offers.get(order["offer_id"])
        if o is None: raise ValidationError("补货引用不存在的供应条件")
        date=day(order["order_date"]);qty=order["quantity"];batches=order.get("shipping_batches",1)
        if not day(proposal["spend_date"])<=date<=end: raise ValidationError("下单日须在方案开始日至30天范围内")
        used[o["id"]]=used.get(o["id"],0)+qty
        if o.get("min_qty") is not None and qty<o["min_qty"]*batches: checks.append({"code":"SUPPLY_MINIMUM","sku":o["sku"],"detail":"未达到起订量"})
        if o.get("capacity") is not None and used[o["id"]]>o["capacity"]: checks.append({"code":"SUPPLY_CAPACITY","sku":o["sku"],"detail":"累计补货超过核实可供数量"})
        absent=[k for k in ("lead_days","payment_days","min_qty","capacity","unit_cost","shipping_cost") if o.get(k) is None]
        if absent or not o["confirmed"]: unknowns.append(o["id"]+"供应条件未核实或缺失："+",".join(absent))
        arrival=None if o.get("lead_days") is None else date+timedelta(days=o["lead_days"])
        payment=None if o.get("payment_days") is None else date+timedelta(days=o["payment_days"])
        if (arrival and arrival>end) or (payment and payment>end): checks.append({"code":"SUPPLY_OUTSIDE_HORIZON","detail":"到货或全额付款超出30天，须缩小本轮方案而非漏算"})
        goods=None if o.get("unit_cost") is None else money(o["unit_cost"])*qty
        shipping=None if o.get("shipping_cost") is None else money(o["shipping_cost"])*batches
        total=None if goods is None or shipping is None else goods+shipping
        if total is not None: committed+=total
        review_on=max([day(i.get("sale_date",i["receipt_date"])) for i in proposal["items"] if i["sku"]==o["sku"]] or [date])
        deadline=arrival+timedelta(days=o["return_days"]) if arrival and o.get("return_days") is not None else None
        return_status="not_allowed" if o.get("returnable") is False else "unknown" if o.get("returnable") is None or deadline is None else "outside_window" if review_on>deadline else "within_window_needs_check"
        lines.append({"return_deadline":deadline.isoformat() if deadline else None,"return_review_status":return_status,"return_review_date":review_on.isoformat(),
                      "return_check_note":"只核对申报退换时限；质量、包装、扣费与对方确认仍需人工核实，不计入退货预期回款", "offer_id":o["id"],"sku":o["sku"],"quantity":qty,"order_date":date.isoformat(),"arrival_date":arrival.isoformat() if arrival else None,
                      "payment_date":payment.isoformat() if payment else None,"unit_cost":o.get("unit_cost"),"shipping_batches":batches,"shipping_cost":amount(shipping) if shipping is not None else None,"cash_cost":amount(total) if total is not None else None,
                      "returnable":o.get("returnable"),"return_days":o.get("return_days"),"return_policy":o["return_policy"],"source_note":o["source_note"]})
    costs={}; ending=[]
    for item in proposal["items"]:
        sku=item["sku"]
        if sku not in products: continue
        p=products[sku]; sale=day(item.get("sale_date",item["receipt_date"]))
        if not day(proposal["spend_date"])<=sale<=end: raise ValidationError("交付日须在方案开始日至30天内")
        lots=[l for l in lines if l["sku"]==sku and l["arrival_date"] and day(l["arrival_date"])<=sale]
        available=p["stock"]+sum(l["quantity"] for l in lots)
        if item["quantity"]>available:
            checks.append({"code":"STOCK_EXCEEDED","sku":sku,"detail":"在交付日前到货数量不足"})
        remaining=item["quantity"]; old=min(remaining,p["stock"]);remaining-=old
        value=None if old and p["unit_cost"] is None else money(p["unit_cost"] or '0')*old
        for l in sorted(lots,key=lambda l:l["arrival_date"]):
            take=min(remaining,l["quantity"]);remaining-=take
            if take and (l["unit_cost"] is None or value is None): value=None
            elif take: value+=money(l["unit_cost"])*take
        if remaining: value=None
        costs[sku]=value
        ending.append({"sku":sku,"opening":p["stock"],"ordered":sum(l["quantity"] for l in lines if l["sku"]==sku),"available_on_delivery":available,"declared_sold":item["quantity"],"remaining_on_delivery":available-item["quantity"]})
    for sku in sorted({l["sku"] for l in lines}-{r["sku"] for r in ending}):
        product=products[sku];ordered=sum(l["quantity"] for l in lines if l["sku"]==sku)
        available=product["stock"]+sum(l["quantity"] for l in lines if l["sku"]==sku and l["arrival_date"] and day(l["arrival_date"])<=end)
        ending.append({"sku":sku,"opening":product["stock"],"ordered":ordered,"available_on_delivery":available,"declared_sold":0,"remaining_on_delivery":available,"availability_date":end.isoformat()})
    return {"lines":lines,"checks":checks,"unknowns":unknowns,"cash_commitment":amount(committed),"sold_costs":costs,"stock_path":ending,
            "costs_complete":all(l["cash_cost"] is not None for l in lines),"notice":"到货按供应条件计算，成本采用现货优先的FIFO假设；采购全额和运费即使零销量也付款，未售新货不重复扣作已售成本；不自动下单或登记真实入库。"}


def rule_restock(ledger,evidence_ids,prior=None):
    """A disclosed historical-rate rehearsal, not a demand forecast or purchase order."""
    from decimal import ROUND_CEILING
    from .tools import cash_baseline
    budget=money(cash_baseline(ledger,{})["conservative_budget_ceiling"])
    start=day(ledger["as_of"])
    for o in ledger.get("supply_options",[]):
        if not o["confirmed"] or any(o.get(k) is None for k in ("lead_days","payment_days","min_qty","capacity","unit_cost","shipping_cost")):continue
        p=next(p for p in ledger["products"] if p["sku"]==o["sku"])
        if p["size_complete"] is not True or not p["sales_30d"] or p["stock"]*30>=p["sales_30d"]*o["lead_days"]:continue
        qty=max(1,o["min_qty"],int((Decimal(p["sales_30d"])*7/30).to_integral_value(rounding=ROUND_CEILING)))
        if qty>o["capacity"] or qty*money(o["unit_cost"])+money(o["shipping_cost"])>budget:continue
        arrival=start+timedelta(days=o["lead_days"]); receipt=arrival+timedelta(days=1)
        if receipt>start+timedelta(days=30) or o["payment_days"]>30 or p["unit_price"] is None:continue
        return {"id":"inventory_restock","version":prior["version"]+1 if prior else 1,"owner":"inventory","title":"小批量补货与到货核验（规则假设）",
                "spend_date":ledger["as_of"],"upfront_cost":"0.00","other_cost":"0.00","weekly_hours":min(2,ledger["weekly_available_hours"]),
                "sales_assumption":"unverified","costs_confirmed":False,"model_refs":[],
                "procurements":[{"offer_id":o["id"],"quantity":qty,"order_date":ledger["as_of"]}],
                "items":[{"sku":p["sku"],"quantity":qty,"price":p["unit_price"],"variable_cash_cost":"0.00","sale_date":arrival.isoformat(),"receipt_date":receipt.isoformat()}],
                "rationale":"历史平均速度下现货覆盖短于供应周期，仅生成待验证的小批量假设；不是预测。零额活动费仍待人工核实。",
                "evidence_ids":evidence_ids,"assumptions":["拟销量参照7天历史平均并满足起订，不是实际需求","费用及履约需再核实，退货回款不纳入资金"],
                "stop_conditions":["供应延迟、需求不足或现金底线触及即停止新增投入"]}
    return None
