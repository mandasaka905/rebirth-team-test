"""Explicit model versions and immutable proposal/model/trial lineage."""
from copy import deepcopy
from .domain import ValidationError, identifier, integer


def normalize_versions(previous, updated):
    old = {m["id"]: m for m in previous.get("business_models", [])}
    for m in updated.get("business_models", []):
        before = old.get(m["id"])
        if before is None:
            m.setdefault("version", 1)
            continue
        version = before.get("version", 1)
        if m.get("version", 1) != version:
            raise ValidationError("经营模式版本已变化，请刷新后再编辑")
        changed = {k:v for k,v in m.items() if k != "version"} != {k:v for k,v in before.items() if k != "version"}
        m["version"] = version + int(changed)
    return updated


def validate_refs(refs):
    if not isinstance(refs, list) or len(refs) > 20:
        raise ValidationError("模式关联必须是最多20项的列表")
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValidationError("模式关联应为对象")
        identifier(ref.get("id"));integer(ref.get("version"), "模式版本", 1000000)
        if not ref["version"] or ref["id"] in seen:
            raise ValidationError("模式版本须为正数，同一模式不能重复关联")
        seen.add(ref["id"])
    return refs


def resolve(ledger, proposal):
    refs = validate_refs(proposal.get("model_refs", []))
    models = ledger.get("business_models", [])
    if models and not refs:
        raise ValidationError("店铺已有经营模式，请明确关联方案对应的模式版本")
    result = []
    for ref in refs:
        model = next((m for m in models if m["id"] == ref["id"] and m.get("version", 1) == ref["version"]), None)
        if model is None:
            raise ValidationError("关联模式不存在或版本已过期，请重新选择")
        result.append({**deepcopy(model), "version": model.get("version", 1)})
    return result


def default_refs(ledger, role):
    models = ledger.get("business_models", [])
    preferred = next((m for m in (list(reversed(models)) if role=="customer" else models) if m["status"] == ("candidate" if role == "customer" else "current")), None)
    chosen = preferred or (models[0] if models else None)
    return [{"id": chosen["id"], "version": chosen.get("version", 1)}] if chosen else []

