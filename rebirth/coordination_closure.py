"""Archive remaining requirements after revisions end. No new agent judgment."""
from .collaboration_protocol import requirements


def close(reviews):
    remaining=requirements(reviews);tasks=[]
    for r in remaining:
        details=r['details'];kind=r['kind'];assignee=r['owner']
        if kind=='objection':
            action=details.get('request',details.get('reason','核对未解决质询'))
            acceptance=details.get('acceptance','补齐来源并重新复核，不把归档当作解除异议。');assignee=details.get('from',assignee)
            disposition='ask_merchant' if details.get('severity')=='needs_data' else 'retain_unresolved'
        elif kind=='missing_data':
            parts=[d.get('question',str(d)) if isinstance(d,dict) else str(d) for d in details]
            action='核对并补齐：'+'；'.join(parts)
            conditions=[d.get('completion_condition','') for d in details if isinstance(d,dict)]
            acceptance='；'.join(c for c in conditions if c) or '提供有日期和来源的记录，再重新核查对应方案版本。'
            disposition='ask_merchant'
        else:
            action='继续保留硬约束问题：'+'、'.join(d['code'] for d in details)
            acceptance='修改实际条件并重新计算；本次归档不解除硬约束。'
            disposition='retain_unresolved'
        tasks.append({'requirement_id':r['id'],'assignee':assignee,'disposition':disposition,
                      'action':action,'acceptance':acceptance})
    return {'coordination_tasks':tasks,'revise_roles':[],
            'source':'host_archive_of_validated_reviews',
            'notice':'修订轮数已用完，由程序逐项归档已有质询与工具缺口；没有新增智能体判断。'}
