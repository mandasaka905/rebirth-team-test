"""Produce auditable structural metrics and a separate semantic review worksheet."""
from pathlib import Path
from collections import Counter
import csv,json,argparse

def summarize(report):
 events=report.get('events',[]);byid={e['id']:e for e in events};positions={e['id']:i for i,e in enumerate(events)}
 completed=set();claims=[]
 for event in events:
  if event['kind']!='agent_result':continue
  role=event['actor'];phase=event['data']['phase'];completed.add((role,phase));result=event['data']['result']
  entries=[]
  if result.get('assessment'):entries.append(('assessment',result['assessment']['conclusion'],result['assessment'].get('evidence_ids',[])))
  citations={c['claim']:c for c in (result.get('assessment') or {}).get('knowledge_citations',[])}
  entries += [('knowledge_citation',c['claim'],[c['evidence_id']]) for c in citations.values()]
  entries += [('objection',o['reason'],o.get('evidence_ids',[])) for o in result.get('objections',[])]
  for kind,text,refs in entries:
   valid=bool(refs) and all(r in byid and byid[r]['kind']=='tool_result' and positions[r]<positions[event['id']] and byid[r]['actor']==role and byid[r]['data'].get('phase')==phase for r in refs)
   citation=citations.get(text) if kind=='knowledge_citation' else None
   matches=[d for ref in refs if ref in byid for d in byid[ref]['data'].get('value',{}).get('matches',[])]
   excerpt_present=any(d.get('id')==citation['document_id'] and citation['supporting_text'] in d.get('content','') for d in matches) if citation else None
   claims.append({'event_id':event['id'],'role':role,'phase':phase,'kind':kind,'claim':text,'evidence_ids':refs,'same_role_prior_phase_refs_valid':valid,'evidence':[{ 'id':r,**byid[r]['data']} for r in refs if r in byid and byid[r]['kind']=='tool_result'],'semantic_judgment':None,'quoted_support':citation.get('supporting_text') if citation else None,'scope_limit':citation.get('scope_limit') if citation else None,'excerpt_present':excerpt_present})
 expected={(r,p) for r in ('inventory','customer','cash') for p in ('investigate','propose','review')}
 failed=report.get('status') in ('failed','cancelled','running','interrupted')
 proposals=[] if failed else (report.get('result') or {}).get('proposals',[])
 required=('items','upfront_cost','weekly_hours','stop_conditions','rationale','evidence_ids')
 return {'run_id':report.get('run_id'),'mode':report.get('mode'),'status':report.get('status'),'structural_metrics_only':True,'specialist_phases_completed':len(completed&expected),'specialist_phases_expected':9,'missing_specialist_phases':[{'role':r,'phase':p} for r,p in sorted(expected-completed)],'agent_output_rejections':sum(e['kind']=='agent_output_rejected' for e in events),'tool_errors':sum(e['kind']=='tool_error' for e in events),'final_proposals':len(proposals),'proposal_required_fields_present':sum(all(k in p['proposal'] and p['proposal'][k] is not None for k in required) for p in proposals),'claim_count':len(claims),'claims_with_valid_reference_scope':sum(c['same_role_prior_phase_refs_valid'] for c in claims),'semantic_support_rate':None,'risk_identification_rate':None,'merchant_outcome':None,'claims':claims,'notice':'结构完整性、引用作用域检查不等于建议正确率；语义支持和已知风险识别须按同一案例人工逐项评审，不能由工具风险命中数代替。'}

def write(report,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);value=summarize(report)
 (folder/'evaluation.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 with (folder/'claim-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['event_id','role','phase','kind','claim','evidence_ids','same_role_prior_phase_refs_valid','evidence','quoted_support','scope_limit','excerpt_present','semantic_judgment','reason','reviewer']
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for c in value['claims']:w.writerow({**c,'evidence_ids':json.dumps(c['evidence_ids']), 'evidence':json.dumps(c['evidence'],ensure_ascii=False)})
 (folder/'评审方法.txt').write_text('逐条阅读主张和实际引用证据。semantic_judgment填写 supported（支持）、partial（部分支持）、unsupported（不支持）、unclear（不能判断），并写原因。不要改写原始主张。至少分别检查数字是否一致、条件是否遗漏、是否把假设写成事实、是否夸大适用范围。风险识别须使用冻结案例的预定风险清单，逐项定位模型实际识别的语句；不直接把工具检查计为模型识别。建议两名评审独立填写，再记录分歧。未评审项不计入正确率；失败样本仍保留。',encoding='utf-8-sig')
 return value
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=write(json.loads(a.report.read_text(encoding='utf-8')),a.output);print(json.dumps({k:v[k] for k in ('status','specialist_phases_completed','claim_count','claims_with_valid_reference_scope','semantic_support_rate')}))
