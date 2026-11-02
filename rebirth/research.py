"""Frozen experiment scopes, typed exits and descriptive target/baseline comparisons."""
from datetime import date
from decimal import Decimal
from .domain import ValidationError, day, money, amount, integer, nonempty, identifier

METRICS = {"revenue_per_day": "日均销售额", "contribution_per_day": "日均商品及经营贡献", "conversion": "到店成交比例"}
COUNT_BASES = ("person_visits", "unique_people")


def threshold(value, metric):
    result = money(value, negative=metric == "contribution_per_day")
    if metric == "conversion" and result > 1:
        raise ValidationError("成交比例使用0到1")
    return result


def window(raw, start, end):
    if day(start) > day(end):
        raise ValidationError("观察开始日期不可晚于截止日")
    for k in ("revenue", "goods_cost", "expenses"):
        money(raw.get(k))
    for k in ("visits", "buyers"):
        integer(raw.get(k), k)
    if raw["buyers"] > raw["visits"]:
        raise ValidationError("成交计数不可多于到店计数")
    nonempty(raw.get("source_note"), "观察来源")
    days = (day(end)-day(start)).days+1
    return {"days": days, "revenue_per_day": money(raw["revenue"])/days,
            "contribution_per_day": (money(raw["revenue"])-money(raw["goods_cost"])-money(raw["expenses"]))/days,
            "conversion": Decimal(raw["buyers"])/raw["visits"] if raw["visits"] else None}


def validate_exits(rules):
    if not isinstance(rules, list) or len(rules) > 6:
        raise ValidationError("结构化退出条件最多6条")
    ids = set()
    for r in rules:
        if not isinstance(r, dict):
            raise ValidationError("退出条件须为对象")
        identifier(r.get("id"))
        if r["id"] in ids:
            raise ValidationError("退出条件ID重复")
        ids.add(r["id"])
        if r.get("metric") not in (*METRICS, "trial_spend", "closing_cash") or r.get("op") not in ("lte", "gte"):
            raise ValidationError("退出指标或比较方式不受支持")
        threshold(r.get("value"), r["metric"])
        nonempty(r.get("description"), "退出条件说明")
    return rules


def check_scope(design, observation):
    if not design.get("scope_id"):
        return False  # Old records remain readable, but cannot claim a verified comparison.
    if observation.get("scope_id") != design["scope_id"] or observation.get("count_basis") != design["count_basis"]:
        raise ValidationError("基准或观察的经营范围、计数口径与冻结设计不一致")
    return True


def validate_design(d, trial, ledger, *, draft=False):
    if not isinstance(d, dict) or d.get("metric") not in METRICS:
        raise ValidationError("请选择受支持的评价指标")
    for k in ("hypothesis", "intervention", "comparison_method", "confounders", "stop_rule", "source_note", "scope_description"):
        nonempty(d.get(k), k)
    identifier(d.get("scope_id"))
    if d.get("count_basis") not in COUNT_BASES:
        raise ValidationError("需声明按人次或去重人数计数")
    if not draft and d.get("scope_confirmed") is not True:
        raise ValidationError("请人工确认基准与观察属于同一范围和计数口径")
    integer(d.get("min_days"), "最少观察天数", 30)
    integer(d.get("min_visits"), "最少到店计数")
    if d["min_days"] < 1 or (d["metric"] == "conversion" and d["min_visits"] < 1):
        raise ValidationError("需声明有效观察天数；转化率需声明最低到店计数")
    threshold(d.get("target_value"), d["metric"])
    if not day(d.get("observe_start")) >= day(trial["spend_date"]):
        raise ValidationError("观察开始不可早于方案支出日")
    if not day(d["observe_start"]) <= day(d.get("observe_end")) <= day(trial["end_date"]):
        raise ValidationError("观察期间须在试验截止日以内")
    if d["min_days"] > (day(d["observe_end"])-day(d["observe_start"])).days+1:
        raise ValidationError("最少观察天数超过设计观察期")
    baseline = d.get("baseline")
    if not isinstance(baseline, dict):
        raise ValidationError("请填写基准期同口径记录")
    if day(baseline.get("end")) >= day(d["observe_start"]) or day(baseline["end"]) > day(ledger["as_of"]):
        raise ValidationError("基准期须早于试验且不晚于底账日")
    check_scope(d, baseline)
    window(baseline, baseline.get("start"), baseline["end"])
    validate_exits(d.get("exit_rules", []))
    return d


def evaluate_design(design, measurement, trial, ledger):
    if not measurement:
        return {"status": "awaiting_observation", "label": "尚无观察", "next_action": "按预先声明的口径收集记录，不预填效果"}
    end = measurement["end"]
    if not day(design["observe_start"]) <= day(end) <= day(design["observe_end"]):
        raise ValidationError("测量截止日超出设计期间")
    if not ledger["synthetic"] and day(end) > date.today():
        raise ValidationError("真实观察不能填写未来结果")
    scope_ok = check_scope(design, measurement) and check_scope(design, design["baseline"])
    current = window(measurement, design["observe_start"], end)
    baseline = window(design["baseline"], design["baseline"]["start"], design["baseline"]["end"])
    spend = money(measurement.get("trial_spend"))
    closing_cash = money(measurement.get("closing_cash"))
    value, before = current[design["metric"]], baseline[design["metric"]]
    sample_ok = current["days"] >= design["min_days"] and measurement["visits"] >= design["min_visits"]
    target_met = value >= threshold(design["target_value"], design["metric"]) if value is not None else None
    relation = ("improved" if value > before else "worse" if value < before else "unchanged") if scope_ok and value is not None and before is not None else "unknown"
    hits = []
    for rule in validate_exits(design.get("exit_rules", [])):
        metric = rule["metric"]
        actual = {"trial_spend":spend, "closing_cash":closing_cash}.get(metric) if metric not in METRICS else current[metric]
        if metric in METRICS and (not sample_ok or not scope_ok):
            continue
        bound = threshold(rule["value"], metric)
        if actual is not None and ((rule["op"] == "lte" and actual <= bound) or (rule["op"] == "gte" and actual >= bound)):
            hits.append({"id":rule["id"], "description":rule["description"], "actual":str(actual), "threshold":rule["value"]})
    status, action = "in_progress", "继续按同口径观察，不能提前宣布有效"
    if spend > money(trial["stop_budget"]) or (spend > 0 and spend == money(trial["stop_budget"])) or closing_cash < money(ledger["reserve_floor"]) or hits:
        status, action = "stop", "已触及预算、现金或冻结的结构化退出条件；人工停止新增投入并核对"
    elif not scope_ok:
        status, action = "incomparable", "旧设计未声明范围和计数口径；保留记录，不判定较基准改善"
    elif not sample_ok or value is None or before is None:
        status, action = "insufficient", "样本、观察时长或基准不足，先补证，不据此追加投入"
    elif day(end) < day(design["observe_end"]):
        pass
    elif target_met and relation == "improved":
        status, action = "target_met", "达到预设目标，观察值也高于基准；仍须核对混杂因素，不证明因果或自动扩大投入"
    elif target_met:
        status, action = "target_only", "虽达预设目标，但观察值"+("低于" if relation == "worse" else "等于")+"基准；不能据此称经营改善，请复核目标与假设"
    else:
        status, action = "revise", ("观察值高于基准但未达预设目标；" if relation == "improved" else "未达预设目标；")+"检查执行差异、需求和费用，勿事后降低目标"
    labels = {"stop":"触及退出线", "insufficient":"证据不足", "in_progress":"观察中",
              "target_met":"达标且观察值高于基准", "target_only":"达标但未较基准改善",
              "revise":"需要修订假设", "incomparable":"范围口径未核实"}
    return {"status":status, "label":labels[status], "metric":design["metric"],
            "baseline":str(before.quantize(Decimal(".0001"))) if before is not None else None,
            "actual":str(value.quantize(Decimal(".0001"))) if value is not None else None,
            "target":design["target_value"], "target_met":target_met, "baseline_relation":relation,
            "change":str((value-before).quantize(Decimal(".0001"))) if value is not None and before is not None else None,
            "scope_confirmed":scope_ok, "count_basis":design.get("count_basis"), "days":current["days"],
            "visits":measurement["visits"], "trial_spend":amount(spend), "rule_hits":hits,
            "next_action":action, "confounders":design["confounders"], "evaluation_version":"0.6",
            "notice":"同范围与口径由商户声明确认，程序检查标签一致但不能替代实地核实。前后比较不证明因果，文字规则不自动解释；仅执行已冻结的结构化条件。"}
