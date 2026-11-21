"""Reproducible supplement cycle, explicitly constructed and locally calculated."""
from pathlib import Path
from copy import deepcopy
import json,sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider
from rebirth.tools import evaluate

def run(folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 case=json.loads((R/'testing/public-retail/cases.json').read_text(encoding='utf-8'))[0]
 ledger=deepcopy(case['ledger']);p=deepcopy(case['initial_proposal']);p.pop('evidence_ids',None)
 ledger['candidate_for_review']=p
 sku=p['items'][0]['sku'];next(x for x in ledger['products'] if x['sku']==sku)['unit_cost']=None
 store=Store(folder/'business.sqlite3');store.put_ledger(ledger)
 before=Engine(store,RuleProvider(),max_rounds=0).execute(ledger['merchant_id'])
 initial=evaluate(before['ledger_snapshot'],{'proposal':p})
 audit=store.answer(ledger['merchant_id'],[{'question_id':'unit_cost_'+sku,'value':'30.00','source_note':'构造验收案例：假设采购凭证核对后单价为30元，非真实商户凭证。'}])
 after=Engine(store,RuleProvider(),max_rounds=0).execute(ledger['merchant_id'])
 updated=evaluate(after['ledger_snapshot'],{'proposal':p})
 assert initial['gross_profit_after_declared_trial_costs'] is None
 assert updated['gross_profit_after_declared_trial_costs'] is not None
 assert initial['trial_cash_commitment']==updated['trial_cash_commitment']
 assert next(x for x in before['ledger_snapshot']['products'] if x['sku']==sku)['unit_cost'] is None
 assert next(x for x in after['ledger_snapshot']['products'] if x['sku']==sku)['unit_cost']=='30.00'
 assert after['ledger_snapshot']['synthetic'] is True
 summary={'execution':'constructed_local_rule_cycle','cloud_calls':0,'merchant_feedback':False,'before_run':before['run_id'],'after_run':after['run_id'],'sku':sku,'supplement':audit['accepted'],'before':initial,'after':updated,'old_snapshot_preserved':True,'assertions_passed':6,'interpretation':'补成本后才能计算该明示方案毛利；已付现货成本不再次扣现金。其余未知和演示属性保持，不代表需求已被验证或经营收益已发生。'}
 for name,value in [('before-report',before),('after-report',after),('comparison',summary)]:
  (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 return summary
if __name__=='__main__':
 out=R/'testing/supplement-cycle'/__import__('uuid').uuid4().hex
 s=run(out);print(json.dumps({'output':str(out),'passed':s['assertions_passed'],'cloud_calls':0,'before_profit':s['before']['gross_profit_after_declared_trial_costs'],'after_profit':s['after']['gross_profit_after_declared_trial_costs']}))
