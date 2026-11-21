"""Check citation provenance and excerpt presence, not semantic correctness."""
from .domain import ValidationError, nonempty


def validate(citations, observations):
    if not isinstance(citations,list) or len(citations)>6:
        raise ValidationError('知识引用须为至多6项的列表')
    searches={o['evidence_id']:o['value'] for o in observations if o.get('tool')=='knowledge_search' and 'value' in o}
    for c in citations:
        if not isinstance(c,dict):raise ValidationError('知识引用须有主张、资料编号、摘录和适用边界')
        for key in ('claim','document_id','supporting_text','evidence_id','scope_limit'):
            nonempty(c.get(key),'知识引用'+key)
            if len(c[key])>1000:raise ValidationError('知识引用说明过长')
        result=searches.get(c['evidence_id'])
        if result is None:raise ValidationError('知识引用必须来自本角色本阶段实际检索记录')
        doc=next((d for d in result.get('matches',[]) if d['id']==c['document_id']),None)
        if not doc or c['supporting_text'] not in doc['content']:
            raise ValidationError('引用的资料或摘录未在对应检索结果中出现')
