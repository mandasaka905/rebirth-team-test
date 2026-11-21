"""Reproducible local checks. This is not a model accuracy benchmark."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import json,sys,hashlib
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from rebirth.tools import dispatch
from rebirth.readiness import questions
from rebirth.domain import ValidationError,validate_proposal
from rebirth.knowledge_claims import validate as citation_validate

cases=json.loads((root/'testing/public-retail/cases.json').read_text(encoding='utf-8'))
rows=[]
for c in cases:
    actual=dispatch(c['ledger'],'proposal_evaluate',{'proposal':c['initial_proposal']})
    codes={x['code'] for x in actual['checks']};rubric=c['rubric']
    ok=set(rubric['required_initial_checks'])==codes
    ok=ok and all(any(part in item for item in actual['unknowns']) for part in rubric['required_unknown_fragments'])
    ok=ok and not actual['eligible_for_merchant_review']
    rows.append({'id':c['id'],'title':c['title'],'passed':ok,'expected_checks':rubric['required_initial_checks'],
                 'actual_checks':sorted(codes),'actual_unknowns':actual['unknowns'],'evaluation':actual})

l=deepcopy(cases[0]['ledger']);p=deepcopy(cases[0]['initial_proposal'])
for label,cost,expected in [('预算正好用完','1500.00',False),('超出预算一分钱','1500.01',True)]:
    candidate=deepcopy(p);candidate['upfront_cost']=cost;candidate['other_cost']='0.00'
    value=dispatch(l,'proposal_evaluate',{'proposal':candidate});codes={x['code'] for x in value['checks']}
    rows.append({'id':'B'+str(len(rows)+1),'title':label,'passed':('BUDGET_EXCEEDED' in codes)==expected,'actual_checks':sorted(codes)})
stock=deepcopy(l);stock['products'][0]['size_complete']=False
value=dispatch(stock,'proposal_evaluate',{'proposal':p})
rows.append({'id':'B10','title':'有库存但规格不满足','passed':any(c['code']=='SIZE_EVIDENCE_REQUIRED' for c in value['checks'])})
demand=deepcopy(l);demand['customer_signals']=[]
rows.append({'id':'B11','title':'没有顾客观察时保留追问','passed':any(q['id']=='customer_observation' for q in questions(demand)['questions'])})

fixture=json.loads((root/'testing/explainable-case/case-and-evidence.json').read_text(encoding='utf-8'))
for i,kind in enumerate(('sum','confirmation'),12):
    bad=deepcopy(fixture['after'])
    if kind=='sum':bad['expense_breakdown'][0]['amount']='39.99'
    else:bad['costs_confirmed']=True
    rejected=False
    try:validate_proposal(bad)
    except ValidationError:rejected=True
    rows.append({'id':'B'+str(i),'title':'费用明细不一致被拒绝' if kind=='sum' else '假设费用不能标为已核实','passed':rejected})
for i,kind in enumerate(('record','excerpt'),14):
    claim={'claim':'先核查付款','document_id':'g','supporting_text':'核对付款','evidence_id':'e1','scope_limit':'不预测收益'}
    obs=[{'evidence_id':'e1','tool':'knowledge_search','value':{'matches':[{'id':'g','content':'核对付款日期'}]}}]
    claim['evidence_id' if kind=='record' else 'supporting_text']='不存在的记录或文本'
    rejected=False
    try:citation_validate([claim],obs)
    except ValidationError:rejected=True
    rows.append({'id':'B'+str(i),'title':'虚构检索记录被拒绝' if kind=='record' else '检索内容中没有的摘录被拒绝','passed':rejected})

result={'checked_at':datetime.now(timezone.utc).isoformat(),'kind':'local_deterministic_checks_not_ai_accuracy',
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'cloud_calls':0,'rows':rows,
        'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('rebirth/tools.py','rebirth/expense_basis.py','rebirth/knowledge_claims.py')},
        'limits':['构造案例不代表真实商户成效','通过率不是AI问答准确率','引用校验不判断语义是否充分支持主张','未据此比较多智能体与单智能体优劣']}
out=Path(__file__).resolve().parent
(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
table=['# 固定案例核对结果','','本表验证本地计算与校验逻辑，不作为大模型准确率或真实经营效果。','','|编号|核对内容|结果|','|---|---|---|']
table += [f"|{r['id']}|{r['title']}|{'通过' if r['passed'] else '失败'}|" for r in rows]
table += ['',f"共{result['total']}项，{result['passed']}项通过。未调用付费模型。",'', '复现命令：`python testing/competition-evaluation/run_checks.py`。完整输入见既有cases.json，实际结果及代码哈希见results.json。']
(out/'固定案例核对结果.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ('kind','passed','total','cloud_calls')}))
if result['passed']!=result['total']:raise SystemExit(1)
