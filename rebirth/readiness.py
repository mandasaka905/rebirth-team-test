"""Deterministic missing-evidence questions and typed merchant answers."""

from copy import deepcopy
from datetime import timedelta

from .domain import ValidationError, identifier, integer, money, nonempty, validate_ledger, day


def questions(ledger):
    pending = []

    def add(qid, owner, path, kind, text, reason):
        pending.append({"id": qid, "owner": owner, "path": path, "value_type": kind,
                        "question": text, "reason": reason})

    from .operating_imports import stale_sales
    stale=stale_sales(ledger)
    for p in ledger["products"]:
        sku = p["sku"]
        if sku in stale:
            add("sales_window_"+sku,"inventory",["products",sku,"sales_30d"],"integer",
                f"{p['name']}（{sku}）请重新核对截至{ledger['as_of']}的最近30天净销售件数。",
                f"现有统计只截至{stale[sku]['end']}，不能当作当前30天数据；如确实相同仍请确认来源。")
        for field, label in (("unit_cost", "实际单位采购成本"), ("unit_price", "当前标价")):
            if p[field] is None:
                add(f"{field}_{sku}", "inventory", ["products", sku, field], "money",
                    f"{p['name']}（{sku}）的{label}是多少？", "缺失金额不能当成零，无法可靠比较毛利。")
        if p["size_complete"] is None:
            add(f"size_{sku}", "inventory", ["products", sku, "size_complete"], "boolean",
                f"{p['name']}（{sku}）是否具备目标顾客需要的尺码？",
                "缺少尺码证据时，不能把库存总件数当作可售数量。")
    if not ledger["customer_signals"]:
        add("customer_observation", "customer", ["customer_signals"], "observation",
            "最近顾客实际询问或拒绝购买过什么？请提供一条观察及来源。",
            "没有客户观察，不能替顾客编造购买需求。")
    for field, owner, label in (("inventory_complete", "inventory", "库存"),
                                ("obligations_complete", "cash", "未付采购款、房租等必要付款"),
                                ("receivables_complete", "cash", "待收款")):
        if not ledger["completeness"][field]:
            add(field, owner, ["completeness", field], "boolean",
                f"请先补齐记录，再确认{label}是否已完整录入。",
                "空记录不表示实际没有业务；不完整数据只能得到条件性计算。")
    if not ledger["merchant_confirmed"]:
        add("merchant_confirmation", "coordinator", ["merchant_confirmed"], "boolean",
            "请核对底账日期、资金、付款及经营约束，是否确认这些记录？",
            "分析条件需要由商户确认；确认不会把合成数据变为真实数据。")
    return {"questions": pending, "ready_for_analysis": not pending,
            "synthetic": ledger["synthetic"],
            "note": "资料齐全不表示经营方案已成立；问题仅覆盖本地已支持字段。"}


def apply_answers(ledger, entries):
    if not isinstance(entries, list) or not entries:
        raise ValidationError("answers必须为非空列表")
    updated = deepcopy(ledger)
    allowed = {q["id"]: q for q in questions(ledger)["questions"]}
    seen, audit = set(), []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValidationError("每条回答必须是对象")
        qid = entry.get("question_id")
        if not isinstance(qid, str) or qid not in allowed:
            raise ValidationError("问题不存在、已回答或已过期，请重新查询questions")
        if qid in seen:
            raise ValidationError("同批回答不可重复")
        seen.add(qid)
        q = allowed[qid]
        value = entry.get("value")
        source = nonempty(entry.get("source_note"), "回答的资料来源或核对说明")
        if q["value_type"] == "money":
            money(value)
        elif q["value_type"] == "integer":
            integer(value,"净销售件数")
        elif q["value_type"] == "boolean":
            if type(value) is not bool:
                raise ValidationError("确认项必须使用JSON布尔值true或false")
        else:
            nonempty(value, "客户观察")
        # A source records the field answered, not the provenance of every product field.
        from uuid import uuid4
        source_id = "answer_" + uuid4().hex[:20]
        updated["sources"][source_id] = source
        path = q["path"]
        if path[0] == "products":
            item = next(p for p in updated["products"] if p["sku"] == path[1])
            item[path[2]] = value
            if path[2]=="sales_30d":
                end=day(updated["as_of"])
                updated.setdefault("sales_windows",{})[path[1]]={"start":(end-timedelta(days=29)).isoformat(),"end":end.isoformat(),"source_id":source_id}
        elif path[0] == "customer_signals":
            updated["customer_signals"].append({"observation": value, "source_id": source_id})
        elif path[0] == "completeness":
            updated["completeness"][path[1]] = value
        else:
            updated[path[0]] = value
        updated.setdefault("field_sources", {})["/".join(path)] = source_id
        audit.append({"question_id": qid, "path": path, "value": value, "source_id": source_id})
    return validate_ledger(updated), audit
