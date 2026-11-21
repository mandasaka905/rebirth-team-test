import unittest,tempfile,json
from pathlib import Path
from copy import deepcopy
from rebirth.store import Store
from rebirth.community import industry_check
from rebirth.domain import ValidationError
from rebirth.engine import Engine
from rebirth.providers import RuleProvider
ROOT=Path(__file__).resolve().parent.parent
class CommunityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'c.db';self.s=Store(self.path);self.l=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'));self.m=self.l['merchant_id'];self.s.put_ledger(self.l);other=deepcopy(self.l);other['merchant_id']='recipient';self.s.put_ledger(other)
 def tearDown(self):self.tmp.cleanup()
 def resource(self,**kw):
  return self.s.save_resource(self.m,{'title':'闲置货架','unit':'台','condition':'当面核对状态，不含运输','area':'测试街区','owner_alias':'合成甲店','source_note':'合成记录','quantity':3,'available_from':'2026-10-30','available_until':'2026-11-30','directory_consent':True,**kw})
 def transfer(self,r,**kw):return self.s.mutual_transfer(self.m,{'listing_id':r['data']['listing_id'],'recipient':'recipient','quantity':2,'occurred_on':'2026-10-31','source_note':'合成提供方记录','owner_confirmed':True,**kw})
 def receipt(self,t,**kw):return self.s.mutual_receipt('recipient',{'transfer_id':t['id'],'decision':'confirmed','source_note':'合成接收方记录','confirmed':True,**kw})
 def test_retail_cash_guard_and_historical_days(self):
  r=industry_check({'industry':'retail','observed_on':'2026-10-31','source_note':'合成','values':dict(stock='10',sold='3',unit_cost='20',price='30',restock='4',cash='100',reserve='50',due='10')});self.assertEqual(r['metrics'][0]['value'],'200.00');self.assertEqual(r['metrics'][1]['value'],'100.00');self.assertTrue(r['warnings']);self.assertEqual(len(r['tasks']),3)
 def test_food_fractional_loss_and_expiry(self):
  r=industry_check({'industry':'food','observed_on':'2026-10-31','source_note':'合成','values':dict(batch='10.50',waste='0.50',daily_use='3',unit_cost='10',shelf_days='2',orders='20',margin='5',fixed='60')});self.assertEqual(r['metrics'][0]['value'],'5.00');self.assertEqual(r['metrics'][1]['value'],'3.33');self.assertEqual(r['metrics'][2]['value'],'40.00');self.assertTrue(r['warnings'])
 def test_repair_capacity_rework_and_cost(self):
  r=industry_check({'industry':'repair','observed_on':'2026-10-31','source_note':'合成','values':dict(queue='10',minutes_job='90',minutes_day='240',price='80',material='20',sample='7',rework='1')});self.assertEqual(r['metrics'][0]['value'],'2.00');self.assertEqual(r['metrics'][1]['value'],'5.00');self.assertEqual(r['metrics'][3]['value'],'14.29')
 def test_unknowns_are_not_zero_and_invalid_units_rejected(self):
  r=industry_check({'industry':'retail','observed_on':'2026-10-31','source_note':'合成','values':{}});self.assertTrue(all(x['value'] is None for x in r['metrics']));self.assertTrue(r['warnings'])
  with self.assertRaises(ValidationError):industry_check({'industry':'retail','observed_on':'2026-10-31','source_note':'合成','values':{'stock':'1.50'}})
  with self.assertRaises(ValidationError):industry_check({'industry':'food','observed_on':'2026-10-31','source_note':'合成','values':{'batch':'1','waste':'2'}})
 def test_case_freezes_baseline_and_persists_history(self):
  c=self.s.impact_start(self.m,{'metric':'stock_value','scope':'同一三类商品','goal':'看清积压','baseline_date':'2026-10-01','baseline_value':'1000','source_note':'合成盘点','confirmed':True})
  raw={'case_id':c['id'],'observed_on':'2026-10-31','value':'900','source_note':'合成观察','actions':'合成行动','external_factors':'季节因素尚不清楚','extra_spend':'0','extra_minutes':60,'status':'observed','previous_id':None,'same_scope_confirmed':True}
  o=self.s.impact_observe(self.m,raw);self.assertEqual(Store(self.path).community_home(self.m)['cases'][0]['difference'],'-100.00')
  with self.assertRaises(ValidationError):self.s.impact_observe(self.m,raw)
  self.s.impact_observe(self.m,{**raw,'previous_id':o['id'],'value':'950','status':'stopped'})
  c=self.s.community_home(self.m)['cases'][0];self.assertEqual(c['data']['baseline_value'],'1000.00');self.assertEqual(len(c['history']),2);self.assertEqual(c['elapsed_days'],30)
 def test_case_scope_confirmation_and_ownership(self):
  with self.assertRaises(ValidationError):self.s.impact_start(self.m,{'confirmed':False})
  c=self.s.impact_start(self.m,{'metric':'checking_time','scope':'同一份核对表','goal':'简化核对','baseline_date':'2026-10-31','baseline_value':'20','source_note':'计时','confirmed':True})
  with self.assertRaises(ValidationError):self.s.impact_observe('recipient',{'case_id':c['id']})
  with self.assertRaises(ValidationError):self.s.impact_observe(self.m,{'case_id':c['id'],'same_scope_confirmed':False})
 def test_directory_consent_and_owner_version_guards(self):
  with self.assertRaises(ValidationError):self.resource(directory_consent=False)
  r=self.resource()
  with self.assertRaises(ValidationError):self.s.save_resource('recipient',{**r['data'],'expected_record_id':r['id']})
  with self.assertRaises(ValidationError):self.resource(listing_id=r['data']['listing_id'],expected_record_id='wrong')
 def test_mutual_confirmation_is_independent_and_quantity_is_deducted_once(self):
  r=self.resource();t=self.transfer(r);self.assertEqual(self.s.resource_directory(self.m)[0]['remaining'],3)
  with self.assertRaises(ValidationError):self.s.mutual_receipt(self.m,{'transfer_id':t['id'],'decision':'confirmed','confirmed':True,'source_note':'提供方不能代接收方'})
  self.receipt(t);self.assertEqual(Store(self.path).resource_directory(self.m)[0]['remaining'],1)
  with self.assertRaises(ValidationError):self.receipt(t)
  with self.assertRaises(ValidationError):self.transfer(r)
  self.assertEqual(self.s.ledger(self.m),self.l)
 def test_pending_blocks_double_booking_and_cancellation_releases(self):
  r=self.resource();t=self.transfer(r)
  with self.assertRaises(ValidationError):self.transfer(r,quantity=1)
  with self.assertRaises(ValidationError):self.resource(listing_id=r['data']['listing_id'],expected_record_id=r['id'])
  self.s.mutual_receipt(self.m,{'transfer_id':t['id'],'decision':'cancelled','source_note':'合成取消','confirmed':True});self.assertFalse(self.s.resource_directory(self.m)[0]['pending']);self.transfer(r,quantity=1)
 def test_decline_does_not_count_and_unit_cannot_rewrite_history(self):
  r=self.resource();t=self.transfer(r);self.receipt(t,decision='declined');self.assertEqual(self.s.resource_directory(self.m)[0]['remaining'],3)
  with self.assertRaises(ValidationError):self.resource(listing_id=r['data']['listing_id'],expected_record_id=r['id'],unit='件')
 def test_real_and_synthetic_directories_are_separated(self):
  self.resource();real=deepcopy(self.l);real.update(merchant_id='real_shop',synthetic=False);self.s.put_ledger(real);self.assertEqual(self.s.resource_directory('real_shop'),[])
  r=self.s.resource_directory(self.m)[0]
  with self.assertRaises(ValidationError):self.transfer({'data':r['data']},recipient='real_shop')
 def test_handover_requires_current_agenda_and_does_not_confirm_original_ledger(self):
  with self.assertRaises(ValidationError):self.s.support_handover(self.m,{'merchant_reviewed':False})
  r=Engine(self.s,RuleProvider()).execute(self.m);p=self.s.agenda_preview(self.m,{'run_id':r['run_id'],'start_date':self.l['as_of'],'days':7,'daily_minutes':30});saved=self.s.save_agenda(self.m,{**p['request'],'fingerprint':p['fingerprint'],'confirmed':True,'expected_current_id':None})
  old=self.s.ledger(self.m);h=self.s.support_handover(self.m,{'agenda_id':saved['id'],'operator_role':'companion','helper_alias':'志愿者A（合成）','notes':'只核对交接','next_check_on':'2026-11-01','help_minutes':15,'merchant_reviewed':True});self.assertEqual(self.s.ledger(self.m),old);self.assertTrue(h['data']['merchant_reviewed']);self.assertTrue(any(x['kind']=='support_handover' for x in self.s.export_bundle(self.m)['workbench_history']))
if __name__=='__main__':unittest.main()
