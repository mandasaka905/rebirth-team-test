"""Manual source-linked journal with atomic CSV batches; never silently posts to balances."""
import csv
from io import StringIO
from decimal import Decimal
from .domain import ValidationError, identifier, integer, money, amount, day, nonempty

CATEGORIES = {"sale", "refund", "purchase", "rent", "other", "owner", "loan"}


def validate_accounts(data, ledger):
    if not isinstance(data, dict):
        raise ValidationError("账簿应为对象")
    opening = data.get("opening")
    if opening is not None:
        if not isinstance(opening, dict):
            raise ValidationError("期初应为对象")
        if day(opening.get("date")) > day(ledger["as_of"]):
            raise ValidationError("期初日期晚于底账")
        money(opening.get("balance"))
        nonempty(opening.get("source_note"), "期初来源")
    seen_refs, seen = set(), set()
    purchases, cash = data.get("purchases", []), data.get("cash_entries", [])
    for kind, rows in (("purchase", purchases), ("cash", cash)):
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValidationError("每类账簿最多1000笔")
        for r in rows:
            if not isinstance(r, dict):
                raise ValidationError("账簿行必须为对象")
            identifier(r.get("id"))
            if r["id"] in seen:
                raise ValidationError("账簿ID重复")
            seen.add(r["id"])
            nonempty(r.get("external_ref"), "原始单据号")
            ref = (kind, r["external_ref"])
            if ref in seen_refs:
                raise ValidationError("同类原始单据号重复，整批未保存")
            seen_refs.add(ref)
            nonempty(r.get("source_note"), "账簿来源")
            if day(r.get("date")) > day(ledger["as_of"]):
                raise ValidationError("流水日期不可晚于底账")
            if opening and day(r["date"]) < day(opening["date"]):
                raise ValidationError("流水早于期初日期，请调整期初范围")
            if kind == "purchase":
                if r.get("sku") not in {p["sku"] for p in ledger["products"]}:
                    raise ValidationError("采购SKU尚未在商品资料登记")
                integer(r.get("quantity"), "采购件数")
                if not r["quantity"]:
                    raise ValidationError("采购件数应大于0")
                money(r.get("unit_cost")); money(r.get("other_cost"))
                nonempty(r.get("supplier"), "供应方或匿名代号")
                if day(r.get("due_date")) < day(r["date"]):
                    raise ValidationError("采购到期日早于单据日")
            else:
                if r.get("direction") not in ("in", "out") or r.get("category") not in CATEGORIES:
                    raise ValidationError("流水方向或类别无效")
                if money(r.get("amount")) <= 0:
                    raise ValidationError("流水金额须大于0")
                if r["category"] in ("refund", "purchase", "rent") and r["direction"] != "out":
                    raise ValidationError("退款、采购付款和租金应为支出")
                if r["category"] == "sale" and r["direction"] != "in":
                    raise ValidationError("销售收款应为收入")
    purchase_map = {r["id"]: r for r in purchases}
    for c in cash:
        if c.get("purchase_id") and (c["category"] != "purchase" or c["purchase_id"] not in purchase_map):
            raise ValidationError("采购关联必须指向本账簿的采购单且类别为purchase")
    for p in purchases:
        total = money(p["unit_cost"])*p["quantity"]+money(p["other_cost"])
        paid = sum((money(c["amount"]) for c in cash if c.get("purchase_id") == p["id"]), Decimal(0))
        if paid > total:
            raise ValidationError("关联采购付款超过采购总额；请先核对退款或录入错误")
    return data


def reconcile(ledger):
    data = ledger.get("accounts", {})
    purchases, cash = data.get("purchases", []), data.get("cash_entries", [])
    incoming = sum((money(c["amount"]) for c in cash if c["direction"] == "in"), Decimal(0))
    outgoing = sum((money(c["amount"]) for c in cash if c["direction"] == "out"), Decimal(0))
    opening = data.get("opening")
    closing = money(opening["balance"])+incoming-outgoing if opening else None
    warnings = []
    if closing is None:
        warnings.append("未填写期初现金，不能对账")
    elif closing != money(ledger["cash_balance"]):
        warnings.append("流水推算余额与当前底账不一致；不要重复计入，请核对后人工更新")
    rows = []
    for p in purchases:
        total = money(p["unit_cost"])*p["quantity"]+money(p["other_cost"])
        paid = sum((money(c["amount"]) for c in cash if c.get("purchase_id") == p["id"]), Decimal(0))
        unpaid = total-paid
        obligation = next((o for o in ledger["obligations"] if o["id"] == p.get("obligation_id")), None)
        matched = unpaid == 0 or (obligation is not None and money(obligation["amount"]) == unpaid and obligation["date"] == p["due_date"])
        if not matched:
            warnings.append("采购单"+p["external_ref"]+"的未付款尚未与底账应付款匹配，当前情景可能漏算")
        rows.append({**p, "total": amount(total), "paid": amount(paid), "unpaid": amount(unpaid), "obligation_matched": matched})
    net_sale = sum((money(c["amount"]) * (1 if c["direction"] == "in" else -1) for c in cash if c["category"] in ("sale", "refund")), Decimal(0))
    return {"opening": opening, "cash_entries": cash, "purchases": rows, "incoming": amount(incoming),
            "outgoing": amount(outgoing), "closing": amount(closing) if closing is not None else None,
            "balance_difference": amount(closing-money(ledger["cash_balance"])) if closing is not None else None,
            "net_sale_cash": amount(net_sale), "warnings": warnings,
            "notice": "账簿用于核对，绝不自动加减底账现金、库存或费用。采购付款不是当期售出成本；销售收款不等于收入确认或净利润。"}


def parse_csv(text, kind):
    if kind not in ("cash_entries", "purchases") or not isinstance(text, str) or len(text) > 500000:
        raise ValidationError("请选择有效CSV类型，最多50万字")
    fields = {"cash_entries": ["id", "date", "direction", "category", "amount", "external_ref", "purchase_id", "source_note"],
              "purchases": ["id", "date", "sku", "quantity", "unit_cost", "other_cost", "due_date", "supplier", "external_ref", "obligation_id", "source_note"]}[kind]
    reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    chinese={"cash_entries":["记录编号","日期","收支方向","款项类型","金额","原始单据号","关联采购编号","来源说明"],
             "purchases":["采购编号","日期","商品编号","数量","采购单价","其他成本","付款到期日","供应方","原始单据号","关联待付款编号","来源说明"]}[kind]
    aliases=dict(zip(chinese,fields))
    if reader.fieldnames:reader.fieldnames=[aliases.get(x.strip(),x.strip()) for x in reader.fieldnames]
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) != set(fields):
        raise ValidationError("CSV列名须完整且不重复："+",".join(fields))
    rows = []
    for line, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValidationError("CSV第"+str(line)+"行列数不一致")
        row = {k: v.strip() for k, v in row.items()}
        if kind=='cash_entries':
            row['direction']={'收入':'in','支出':'out'}.get(row['direction'],row['direction'])
            row['category']={'销售':'sale','退款':'refund','采购':'purchase','房租':'rent','其他':'other','店主往来':'owner','借还款':'loan'}.get(row['category'],row['category'])
        if kind == "purchases":
            try:
                row["quantity"] = int(row["quantity"])
            except ValueError:
                raise ValidationError("CSV采购件数须为整数") from None
        rows.append(row)
        if len(rows) > 500:
            raise ValidationError("单批最多500行，全部未保存")
    if not rows:
        raise ValidationError("CSV无记录")
    return rows

