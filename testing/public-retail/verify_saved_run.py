"""Read-only recomputation of a saved engineering run; never contacts models."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rebirth.tools import dispatch


def inspect(folder):
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    metrics = json.loads((folder/'metrics.json').read_text(encoding='utf-8'))
    events, result = report['events'], report['result']
    ledger = report['ledger_snapshot']
    assert report['status'] == result['status']
    assert report['status'] not in ('failed', 'cancelled', 'running')
    by_id = {e['id']: e for e in events}
    assert len(by_id) == len(events), 'duplicate event id'
    tool_ids = {e['id'] for e in events if e['kind'] == 'tool_result'}
    for e in events:
        if e['kind'] != 'agent_result':
            continue
        value = e['data']['result']
        entries = [value.get('assessment')] + value.get('proposal_reviews', []) + value.get('revision_responses', [])
        for entry in filter(None, entries):
            assert entry['evidence_ids'] and set(entry['evidence_ids']) <= tool_ids, 'missing tool evidence'
    perspectives = {a['role'] for a in result['collaboration']['role_assessments'] if a['phase'] == 'investigate'}
    assert perspectives == {'cash', 'customer', 'inventory'}
    checked = []
    for item in result['proposals']:
        p, saved = item['proposal'], item['evaluation']
        actual = dispatch(ledger, 'proposal_evaluate', {'proposal': p})
        assert {k:v for k,v in actual.items() if k!='cash_cost_breakdown'} == {k:v for k,v in saved.items() if k!='cash_cost_breakdown'}, 'saved calculation no longer reproduces'
        reviews = [r for r in result['collaboration']['proposal_reviews']
                   if (r['proposal_id'], r['version']) == (p['id'], p['version'])]
        assert {r['role'] for r in reviews} == {'cash', 'customer', 'inventory'}, 'incomplete final review'
        ready = next(r for r in result['action_readiness'] if r['proposal_id'] == p['id'])
        assert not ready['automatic_execution']
        if item['objections'] or actual['checks']:
            assert ready['state'] == 'hold'
        declared = sum(Decimal(i['price'])*i['quantity'] for i in p['items'])
        assert declared == Decimal(actual['declared_revenue'])
        checked.append({'proposal_id': p['id'], 'version': p['version'], 'spend_date': p['spend_date'],
            'upfront_cost': p['upfront_cost'], 'constraint_pass': actual['constraint_pass'],
            'checks': [c['code'] for c in actual['checks']], 'unknowns': actual['unknowns'],
            'declared_revenue': actual['declared_revenue'],
            'gross_profit_after_declared_trial_costs': actual['gross_profit_after_declared_trial_costs'],
            'incremental_cash_under_declared_sales': actual['incremental_cash_under_declared_sales'],
            'scenarios': [{k:v for k,v in s.items() if k != 'days'} for s in actual['scenarios']],
            'action_state': ready['state'],
            'reviews': [{'role': r['role'], 'event_id': r['event_id'], 'status': r['status'],
                         'responses': r.get('responses', [])} for r in reviews],
            'remaining_objections': item['objections']})
    revisions = []
    for e in events:
        if e['kind'] != 'proposal_revision':
            continue
        before, after = e['data']['before'], e['data']['after']
        a = dispatch(ledger, 'proposal_evaluate', {'proposal': before})
        b = dispatch(ledger, 'proposal_evaluate', {'proposal': after})
        revisions.append({'event_id': e['id'], 'actor': e['actor'],
            'before': {'upfront_cost': before['upfront_cost'], 'spend_date': before['spend_date'],
                       'checks': [x['code'] for x in a['checks']]},
            'after': {'upfront_cost': after['upfront_cost'], 'spend_date': after['spend_date'],
                      'checks': [x['code'] for x in b['checks']]}})
    return {'run_id': report['run_id'], 'case': metrics.get('case'), 'status': report['status'],
        'metrics_missing_fields': [k for k in ('case','cumulative_usage','token_usage','cost_cny','revision_round_limit') if k not in metrics],
        'network_calls_by_verifier': 0, 'paid_calls_by_verifier': 0,
        'cumulative_host_requests': metrics.get('cumulative_usage'),
        'token_usage': metrics.get('token_usage'), 'cost_cny': metrics.get('cost_cny'),
        'failures_retained': [{'event_id': e['id'], **e['data']} for e in events if e['kind'] == 'run_failed'],
        'resumptions': sum(e['kind'] == 'task_resumed' for e in events),
        'host_revalidation': [e['data'] for e in events if e['kind'] == 'returned_output_revalidated'],
        'revision_round_limit': metrics.get('revision_round_limit'), 'revisions': revisions,
        'proposals': checked,
        'saved_files_sha256': {n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ('report.json', 'metrics.json')},
        'scope': 'engineering_acceptance_not_formal_comparison',
        'human_review': ['证据支持的语义是否准确，不能仅凭引用存在认定正确',
                        '现货清货没有采购，部分供应条款追问可能多余，须人工评审',
                        '成本、需求与商户意愿不能从构造数据证明',
                        '实际Token和费用须以华为云账单为准']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = inspect(args.folder)
    if args.output:
        args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'verified': True, 'run_id': value['run_id'], 'status': value['status'],
                      'network_calls': 0, 'proposals_recomputed': len(value['proposals'])}))
