"""Observable revision evidence; no claims about model reasoning or causality."""
from .tools import dispatch


def revision_effect(ledger, before, after, reviews):
    ignored = {'version', 'evidence_ids', 'id', 'owner'}
    fields = sorted(k for k in set(before or {}) | set(after)
                    if k not in ignored and (before or {}).get(k) != after.get(k))
    operational = {'upfront_cost', 'other_cost', 'spend_date', 'weekly_hours',
                   'items', 'procurements', 'model_refs', 'stop_conditions'}
    operational_fields = [k for k in fields if k in operational]
    old = dispatch(ledger, 'proposal_evaluate', {'proposal': before}) if before else None
    new = dispatch(ledger, 'proposal_evaluate', {'proposal': after})
    codes = lambda value: sorted({c['code'] for c in value['checks']}) if value else []
    old_codes, new_codes = codes(old), codes(new)
    objections = [o for r in reviews if r['proposal_id'] == after['id']
                  and before and r['version'] == before['version']
                  for o in r.get('objections', [])]
    return {'proposal_id': after['id'], 'before_version': before['version'] if before else None,
            'after_version': after['version'], 'changed_fields': fields,
            'material_change': bool(operational_fields), 'operational_fields': operational_fields,
            'objections': objections,
            'before_checks': old_codes, 'after_checks': new_codes,
            'resolved_checks': sorted(set(old_codes) - set(new_codes)),
            'introduced_checks': sorted(set(new_codes) - set(old_codes)),
            'remaining_unknowns': new['unknowns'],
            'notice': '字段变化和约束重算不证明经营收益，也不自动证明异议已解决。'}


def summarize(events):
    changes=[];seen=set();replayed=0
    for event in events:
        if event['kind']!='revision_effect':continue
        change=event['data'];key=(change['proposal_id'],change['before_version'],change['after_version'])
        if key in seen:
            replayed+=1;continue
        seen.add(key);changes.append(change)
    assessments = [{'role': e['actor'], 'phase': e['data']['phase'], 'event_id': e['id'],
                    **e['data']['result']['assessment']} for e in events
                   if e['kind'] == 'agent_result' and e['data']['result'].get('assessment')]
    plans = [{'event_id': e['id'], **e['data']} for e in events if e['kind'] == 'coordination_plan']
    reviews = [{'role': e['actor'], 'event_id': e['id'], **r} for e in events if e['kind'] == 'agent_result'
               for r in e['data']['result'].get('proposal_reviews', [])]
    responses = [{'role': e['actor'], 'event_id': e['id'], **r} for e in events if e['kind'] == 'agent_result'
                 for r in e['data']['result'].get('revision_responses', [])]
    return {'revisions': changes,
            'role_assessments': assessments, 'coordination_plans': plans,
            'proposal_reviews': reviews, 'revision_responses': responses,
            'material_revisions': sum(bool(x['material_change']) for x in changes),
            'unchanged_revisions': sum(not x['material_change'] for x in changes),
            'resolved_check_count': sum(len(x['resolved_checks']) for x in changes),
            'replayed_revision_events':replayed,
            'comparison_status': 'not_evaluated',
            'notice': '未进行同预算单智能体对照，不据此声称多智能体更优。'}


def action_readiness(evaluated):
    """A review gate, never automatic business approval or a profit prediction."""
    rows = []
    for item in evaluated:
        p, e = item['proposal'], item['evaluation']
        objections = item.get('objections', [])
        state = 'hold' if e['checks'] or objections else 'verify' if e['unknowns'] else 'reviewable'
        rows.append({'proposal_id': p['id'], 'version': p['version'], 'state': state,
                     'label': {'hold': '暂缓投入，先处理风险或异议', 'verify': '先补证据，再决定是否投入',
                               'reviewable': '可供商户审阅的小范围试验候选'}[state],
                     'checks': e['checks'], 'unknowns': e['unknowns'], 'objections': objections,
                     'stop_conditions': p['stop_conditions'], 'automatic_execution': False})
    return rows
