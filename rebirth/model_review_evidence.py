"""Each model review must cite this role's actual calculation of its version."""
from .domain import ValidationError
from .preflight import redact_context

def same_calculation_input(expected,actual):
    fields=('model','supply_requirements')
    return redact_context({k:expected.get(k) for k in fields})==redact_context({k:actual.get(k) for k in fields})

def validate(reviews,drafts,observations):
    expected={(d['id'],d['version']) for d in drafts};seen=set()
    for r in reviews:
        key=(r.get('draft_id'),r.get('version'))
        if key not in expected or key in seen:raise ValidationError('模式复核版本不存在或重复')
        seen.add(key)
        allowed={o['evidence_id'] for o in observations if o.get('tool')=='model_draft_evaluate' and 'value' in o
                 and o.get('arguments',{}).get('draft',{}).get('id')==key[0]
                 and o['arguments']['draft'].get('version')==key[1]
                 and same_calculation_input(next(d for d in drafts if (d['id'],d['version'])==key),o['arguments']['draft'])}
        if not set(r.get('evidence_ids',[]))&allowed:raise ValidationError('模式复核须引用本角色本阶段对该精确草案版本的计算证据')
    if seen!=expected:raise ValidationError('模式复核须覆盖全部当前草案版本')
