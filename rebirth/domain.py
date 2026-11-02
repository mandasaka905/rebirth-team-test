"""Validate business facts and proposals before an agent may use them."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re


class ValidationError(ValueError):
    pass


ROLES = ("coordinator", "inventory", "customer", "cash")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value):
        raise ValidationError("标识仅可包含1–64位字母、数字、下划线或连字符")
    return value


def money(value, *, negative=False):
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise ValidationError("金额必须为十进制字符串或整数，不接受浮点数")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError("金额无效") from exc
    if not number.is_finite() or abs(number) > Decimal("1000000000000"):
        raise ValidationError("金额必须是有限值且绝对值不超过一万亿元")
    if not negative and number < 0:
        raise ValidationError("金额不可为负")
    if number != number.quantize(Decimal("0.01")):
        raise ValidationError("金额最多两位小数")
    return number


def amount(value):
    return str(money(value, negative=True).quantize(Decimal("0.01")))


def integer(value, name, maximum=1000000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValidationError(f"{name}必须为0到{maximum}的整数")
    return value


def day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("日期必须为YYYY-MM-DD") from exc


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"缺少{name}")
    if len(value) > 10000:
        raise ValidationError(f"{name}过长")
    return value


def validate_ledger(raw):
    if not isinstance(raw, dict):
        raise ValidationError("经营底账必须是对象")
    data = deepcopy(raw)
    try:
        identifier(data["merchant_id"])
        nonempty(data["name"], "商户名称")
        as_of = day(data["as_of"])
        if data["currency"] != "CNY":
            raise ValidationError("首版仅支持人民币")
        if type(data["synthetic"]) is not bool:
            raise ValidationError("synthetic必须明确为true或false")
        for key in ("cash_balance", "reserve_floor", "max_trial_budget"):
            money(data[key])
        integer(data["weekly_available_hours"], "可用工作小时", 168)
        sources = data["sources"]
        if not isinstance(sources, dict) or not sources:
            raise ValidationError("必须提供数据来源")
        for key, value in sources.items():
            identifier(key)
            nonempty(value, "数据来源说明")
        nonempty(data["goal"], "经营目标")
        products = data["products"]
        if not isinstance(products, list):
            raise ValidationError("products必须为列表")
        seen = set()
        for p in products:
            identifier(p["sku"])
            if p["sku"] in seen:
                raise ValidationError("SKU重复")
            seen.add(p["sku"])
            nonempty(p["name"], "商品名称")
            integer(p["stock"], "库存")
            integer(p["sales_30d"], "近30天销量")
            if day(p["received_on"]) > as_of:
                raise ValidationError("入库日期不可晚于底账日期")
            for key in ("unit_cost", "unit_price"):
                if p[key] is not None:
                    money(p[key])
            if type(p["size_complete"]) not in (bool, type(None)):
                raise ValidationError("size_complete仅接受true、false或null")
            if p["source_id"] not in sources:
                raise ValidationError("商品引用未知来源")
        for key in ("obligations", "receivables"):
            if not isinstance(data[key], list):
                raise ValidationError(f"{key}必须为列表，缺失记录不等于零")
            seen_entries = set()
            for entry in data[key]:
                identifier(entry["id"])
                if entry["id"] in seen_entries:
                    raise ValidationError(f"{key}中id重复")
                seen_entries.add(entry["id"])
                day(entry["date"])
                money(entry["amount"])
                if entry["source_id"] not in sources:
                    raise ValidationError("收支记录引用未知来源")
        for signal in data["customer_signals"]:
            nonempty(signal["observation"], "客户观察")
            if signal["source_id"] not in sources:
                raise ValidationError("客户观察引用未知来源")
        for flag in ("obligations_complete", "receivables_complete", "inventory_complete"):
            if type(data["completeness"][flag]) is not bool:
                raise ValidationError("完整性标记必须是布尔值")
        if "sales_windows" in data:
            from .operating_imports import validate_windows
            validate_windows(data["sales_windows"],data)
        if "sales_records" in data:
            from .operating_imports import validate_sales
            validate_sales(data["sales_records"], data)
        if "supply_options" in data:
            from .supply import validate_offers
            validate_offers(data["supply_options"], data)
        if "business_models" in data:
            from .planning import validate_models
            validate_models(data["business_models"])
        if "customer_cohorts" in data:
            from .cohorts import validate_cohorts
            validate_cohorts(data["customer_cohorts"], data["as_of"])
        if "accounts" in data:
            from .accounting import validate_accounts
            validate_accounts(data["accounts"], data)
        if "field_sources" in data:
            if not isinstance(data["field_sources"], dict) or not all(
                isinstance(k, str) and isinstance(v, str) and v in sources for k, v in data["field_sources"].items()
            ):
                raise ValidationError("字段来源映射无效")
        if type(data["merchant_confirmed"]) is not bool:
            raise ValidationError("merchant_confirmed必须是布尔值")
        if "operating_periods" in data:
            from .business import validate_periods
            data["operating_periods"] = validate_periods(data["operating_periods"], data["as_of"], sources)
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"底账结构不完整：{exc}") from exc
    return data


def validate_proposal(raw):
    if not isinstance(raw, dict):
        raise ValidationError("方案必须为对象")
    p = deepcopy(raw)
    try:
        identifier(p["id"])
        integer(p.get("version"), "方案版本", 1000000)
        if not p["version"]: raise ValidationError("方案版本须大于0")
        nonempty(p["title"], "方案名称")
        if "model_refs" in p:
            from .linkage import validate_refs
            validate_refs(p["model_refs"])
        if p["owner"] not in ("inventory", "customer", "cash"):
            raise ValidationError("方案负责人必须是专业智能体")
        money(p["upfront_cost"])
        money(p["other_cost"])
        day(p["spend_date"])
        integer(p["weekly_hours"], "每周工作时间", 168)
        if p["sales_assumption"] not in ("unverified", "merchant_estimate", "observed"):
            raise ValidationError("销售假设标记无效")
        if type(p["costs_confirmed"]) is not bool:
            raise ValidationError("必须明确费用是否已经核实")
        if not isinstance(p["items"], list):
            raise ValidationError("items必须是列表")
        seen = set()
        for item in p["items"]:
            identifier(item["sku"])
            if item["sku"] in seen:
                raise ValidationError("同一方案的SKU不可重复，以免重复计算库存")
            seen.add(item["sku"])
            integer(item["quantity"], "试验商品数")
            money(item["price"])
            money(item["variable_cash_cost"])
            day(item["receipt_date"])
        from .supply import validate_orders
        validate_orders(p.get("procurements", []))
        for item in p["items"]:
            if "sale_date" in item: day(item["sale_date"])
        nonempty(p["rationale"], "提案依据")
        if not isinstance(p["evidence_ids"], list) or not p["evidence_ids"]:
            raise ValidationError("方案必须引用证据")
        if not isinstance(p["assumptions"], list) or not isinstance(p["stop_conditions"], list):
            raise ValidationError("方案必须提供假设和停止条件列表")
        if not p["stop_conditions"]:
            raise ValidationError("缺少停止条件")
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"方案结构不完整：{exc}") from exc
    return p
