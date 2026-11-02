"""Aggregate fixed-cohort repeat purchase; no personal identifiers or permanent churn claims."""
from decimal import Decimal
from .domain import ValidationError, identifier, day, integer, nonempty


def signature(r):
    return (r["definition"], r["base_size"], r["baseline_start"], r["baseline_end"])


def prevent_redefinition(previous, updated):
    old = {r["cohort_id"]:signature(r) for r in previous.get("customer_cohorts", [])}
    if any(r["cohort_id"] in old and signature(r) != old[r["cohort_id"]] for r in updated.get("customer_cohorts", [])):
        raise ValidationError("固定客群的定义或分母不可改写，请另建客群代号")


def validate_cohorts(rows, as_of):
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValidationError("固定客群观察最多200条")
    groups, ids, windows = {}, set(), {}
    for r in rows:
        if not isinstance(r, dict):
            raise ValidationError("客群观察必须为对象")
        identifier(r.get("id"));identifier(r.get("cohort_id"))
        if r["id"] in ids:
            raise ValidationError("客群观察ID重复")
        ids.add(r["id"])
        for k in ("label", "definition", "source_note"):
            nonempty(r.get(k), k)
        integer(r.get("base_size"), "基准客群去重人数")
        if not r["base_size"]:
            raise ValidationError("基准客群人数须大于0")
        if not day(r.get("baseline_start")) <= day(r.get("baseline_end")) < day(r.get("start")) <= day(r.get("end")) <= day(as_of):
            raise ValidationError("客群观察须晚于基准期且不晚于底账日")
        for k in ("membership_confirmed", "observation_complete"):
            if type(r.get(k)) is not bool:
                raise ValidationError("客群分母和观察完整性需明确布尔确认")
        if r.get("retained") is not None:
            integer(r["retained"], "同一客群本窗复购去重人数", r["base_size"])
        elif r["observation_complete"]:
            raise ValidationError("完整观察须填明确复购人数；未知不可补0")
        signature = (r["definition"], r["base_size"], r["baseline_start"], r["baseline_end"])
        if r["cohort_id"] in groups and groups[r["cohort_id"]] != signature:
            raise ValidationError("同一固定客群的定义、基准期和分母不得改变；请另建客群")
        groups[r["cohort_id"]] = signature
        for a,b in windows.setdefault(r["cohort_id"], []):
            if day(r["start"]) <= day(b) and day(a) <= day(r["end"]):
                raise ValidationError("同一客群的观察窗不可重叠；录错请更正原条目")
        windows[r["cohort_id"]].append((r["start"],r["end"]))
    return rows


def analyze_cohorts(ledger):
    output, findings = [], []
    for r in sorted(ledger.get("customer_cohorts", []), key=lambda r:r["end"]):
        known = r["membership_confirmed"] and r["observation_complete"] and r.get("retained") is not None
        retained = r["retained"] if known else None
        output.append({**r, "days": (day(r["end"])-day(r["start"])).days+1,
                       "retention": str((Decimal(retained)/r["base_size"]).quantize(Decimal(".0001"))) if known else None,
                       "not_repeated": r["base_size"]-retained if known else None,
                       "not_repeated_rate": str((Decimal(r["base_size"]-retained)/r["base_size"]).quantize(Decimal(".0001"))) if known else None})
    for cid in sorted({r["cohort_id"] for r in output}):
        rows = [r for r in output if r["cohort_id"] == cid]
        if len(rows) < 2:
            continue
        a,b = rows[-2:]
        if a["days"] != b["days"]:
            findings.append({"cohort_id":cid, "kind":"incomparable", "statement":"观察窗长度不同，不直接比较复购率"})
        elif a["retention"] is None or b["retention"] is None:
            findings.append({"cohort_id":cid, "kind":"insufficient", "statement":"固定客群或观察尚未核实，不把未知当流失"})
        else:
            change = Decimal(b["retention"])-Decimal(a["retention"])
            findings.append({"cohort_id":cid, "kind":"decline" if change < 0 else "not_declined",
                             "before":a["retention"],"after":b["retention"],"change":str(change),
                             "statement":"同一固定客群、相同时长观察窗的复购比例"+("下降，需调查未复购原因" if change < 0 else "未下降，仍需检查样本与季节差异")})
    return {"windows":output,"findings":findings,
            "notice":"只使用匿名汇总及固定基准客群。未复购指本观察窗没有复购，不代表永久流失；来源与成员一致性由商户核实，不证明原因。"}

