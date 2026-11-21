"""Summarize both arms, preserving failures; semantic judgments remain reviewable."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from rebirth.tools import dispatch


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def review_arm(folder,manifest,case):
    metrics=json.loads((folder/'metrics.json').read_text(encoding='utf-8'))
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    assert metrics['manifest_sha256']==digest(manifest),'condition manifest differs'
    assert digest(report['ledger_snapshot'])==manifest['ledger_sha256'],'input differs'
    assert metrics['source_unchanged'],'code changed'
    if metrics['usage']['calls'] is None:
        assert metrics['status']=='interrupted' and metrics['usage'].get('exact') is False
    else:
        assert metrics['usage']['calls']<=manifest['budget_per_arm']['max_calls']
    assert metrics['resumptions']==0
    events=report['events']
    by_id={e['id']:e for e in events}
    completed=[{'role':e['actor'],'phase':e['data']['phase'],'event_id':e['id']}
               for e in events if e['kind']=='agent_result']
    finals=report.get('result') or {}
    failure=report['status'] in ('failed','cancelled','interrupted','running')
    proposals=[]
    for item in [] if failure else finals.get('proposals',[]):
        p=item['proposal']
        value=dispatch(report['ledger_snapshot'],'proposal_evaluate',{'proposal':p})
        assert value==item['evaluation'],'saved final calculation does not reproduce'
        proposals.append({'proposal':p,'checks':value['checks'],'unknowns':value['unknowns'],
            'declared_revenue':value['declared_revenue'],
            'conditional_contribution':value['gross_profit_after_declared_trial_costs'],
            'conditional_incremental_cash':value['incremental_cash_under_declared_sales'],
            'zero_sales_minimum_cash':value['scenarios'][0]['minimum_cash_before_receipts'],
            'objections':item['objections']})
    claims=[]
    for e in events:
        if e['kind']!='agent_result':continue
        result=e['data']['result']
        if result.get('assessment'):
            a=result['assessment']
            assert all(ref in by_id and by_id[ref]['kind']=='tool_result' for ref in a['evidence_ids'])
            claims.append({'role':e['actor'],'phase':e['data']['phase'],'event_id':e['id'],
                'claim':a['conclusion'],'evidence_ids':a['evidence_ids'],
                'missing_data':a['missing_data'],'assumptions':a['assumptions'],'limits':a['limits']})
        for o in result.get('objections',[]):
            claims.append({'role':e['actor'],'phase':e['data']['phase'],'event_id':e['id'],
                          'claim':o['reason'],'request':o['request'],'evidence_ids':o['evidence_ids'],
                          'proposal_id':o['proposal_id'],'version':o['version']})
    return {'arm':folder.name,'status':report['status'],'error_type':metrics['error_type'],
        'elapsed_seconds':metrics['elapsed_seconds'],'usage':metrics['usage'],
        'token_usage':metrics['token_usage'],'cost_cny':metrics['cost_cny'],
        'agent_output_rejections':metrics['agent_output_rejections'],'tool_errors':metrics['tool_errors'],
        'completed_phases':completed,'failure_message':finals.get('error_message') if failure else None,
        'last_completed_phase':completed[-1] if completed else None,
        'final_proposals':None if failure else proposals,
        'material_revisions':None if failure else finals.get('collaboration',{}).get('material_revisions'),
        'readiness':None if failure else finals.get('action_readiness'),
        'claim_review_queue':claims,
        'event_counts':dict(Counter(e['kind'] for e in events)),
        'files_sha256':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
                        for name in ('report.json','metrics.json')}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('pair',type=Path)
    args=parser.parse_args()
    manifest=json.loads((args.pair/'manifest.json').read_text(encoding='utf-8'))
    case=json.loads((args.pair/'case.json').read_text(encoding='utf-8'))
    assert digest(case)==manifest['case_sha256']
    baseline=dispatch(case['ledger'],'proposal_evaluate',{'proposal':case['initial_proposal']})
    assert set(case['rubric']['required_initial_checks']) <= {c['code'] for c in baseline['checks']}
    arms=[review_arm(args.pair/name,manifest,case) for name in manifest['order']]
    result={'purpose':manifest['purpose'],'case':case['id'],'initial_checks':baseline['checks'],
            'arms':arms,'verdict':'no_general_superiority_claim','human_review_status':'pending',
            'scope':'同端点一次配对编排预试验；失败时无最终结果，不将空风险列表视为安全。'}
    (args.pair/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# C02同端点编排预试验结果','',
           '一次配对试验，不代表普遍优劣，也不证明真实经营成效。',
           '','|核对项|单身份|多角色|','|---|---|---|']
    rows=[('最终状态',lambda r:r['status']),('错误类型',lambda r:r['error_type'] or '无'),
          ('宿主请求数',lambda r:r['usage']['calls'] if r['usage']['calls'] is not None else '未知，已完成下界'+str(r['usage'].get('completed_request_lower_bound'))),
          ('耗时（秒）',lambda r:r['elapsed_seconds'] if r['elapsed_seconds'] is not None else '准确停止时刻未知'),
          ('输出被要求纠正次数',lambda r:r['agent_output_rejections']),('工具错误数',lambda r:r['tool_errors']),
          ('完整阶段数',lambda r:len(r['completed_phases'])),
          ('最终候选数',lambda r:'未形成最终结果' if r['final_proposals'] is None else len(r['final_proposals'])),
          ('实际安排修改数',lambda r:'未完成验收' if r['material_revisions'] is None else r['material_revisions']),
          ('实际Token / 人民币费用',lambda r:'未知 / 未核账单')]
    for label,fn in rows:lines.append('|'+label+'|'+'|'.join(str(fn(r)) for r in arms)+'|')
    for r in arms:
        lines+=['','## '+{'single':'单身份','multi':'多角色'}[r['arm']],'']
        if r['failure_message']:lines.append('未完成原因：'+r['failure_message'])
        lines.append('完成阶段：'+('；'.join(x['role']+'/'+x['phase'] for x in r['completed_phases']) or '无'))
        if r['final_proposals'] is None:
            lines.append('没有经过完整最终审查的方案。中途提出的判断与依据保留在review.json，不能按零风险计分。')
        for item in r['final_proposals'] or []:
            p=item['proposal']
            contribution='未知' if item['conditional_contribution'] is None else item['conditional_contribution']+'元'
            cash='未知' if item['conditional_incremental_cash'] is None else item['conditional_incremental_cash']+'元'
            lines+=['',f"候选：{p['title']}，v{p['version']}。前期投入{p['upfront_cost']}元，零销量最低现金{item['zero_sales_minimum_cash']}元。",
                    f"按声明销量计算的贡献：{contribution}；增量现金：{cash}。数字依赖假设和资料，不是实际结果。",
                    '剩余宿主问题：'+('；'.join(x['code'] for x in item['checks']) or '无'),
                    '仍待核实：'+('；'.join(item['unknowns']) or '工具没有列出'),
                    '仍有异议：'+str(len(item['objections']))+'项。']
    lines+=['','## 仍要逐条看什么','',
            'review.json保留各阶段专业主张、补证问题、依据编号和全部最终异议，等待队员逐条核对。重点看是否理解回款日、是否对现货错误要求采购资料、是否把销量假设当成交事实、是否把现金足够误当经济划算。程序没有靠关键词判定这些主张正确。',
            '', '两组共用同端点，源码和输入哈希已核对；实际云端解析版本与采样参数未独立读取。两组提示词组织、记忆和并发不同，不能把本轮差异只归因于角色数量。']
    (args.pair/'结果说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'review_written':str(args.pair/'结果说明.md'),
                      'statuses':{r['arm']:r['status'] for r in arms}},ensure_ascii=True))


if __name__=='__main__':main()
