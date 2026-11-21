import json,tempfile,unittest
from pathlib import Path
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider,ProviderError
from rebirth.domain import ValidationError
ROOT=Path(__file__).resolve().parents[1]
class ResumeTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'business.sqlite3')
  self.l=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'));self.m=self.l['merchant_id'];self.s.put_ledger(self.l)
  class Fail(RuleProvider):
   def step(self,c):
    if c['role']=='coordinator':raise ProviderError('synthetic network failure')
    return super().step(c)
  self.engine=Engine(self.s,Fail(),max_rounds=0)
  with self.assertRaises(ProviderError):self.engine.execute(self.m)
  self.run=self.engine.run_id
 def tearDown(self):self.tmp.cleanup()
 def test_resume_reuses_only_validated_matching_checkpoints(self):
  class Count(RuleProvider):
   def __init__(self):self.calls=[]
   def step(self,c):self.calls.append((c['role'],c['phase']));return super().step(c)
  p=Count();r=Engine(self.s,p,max_rounds=0).execute(self.m,resume_run=self.run)
  self.assertEqual(p.calls,[('coordinator','coordinate')]);self.assertEqual(r['run_id'],self.run)
  self.assertNotIn(r['status'],('failed','running'));self.assertEqual(sum(e['kind']=='task_resumed' for e in r['events']),1)
  with self.assertRaises(ValidationError):Engine(self.s,p).execute(self.m,resume_run=self.run)
 def test_changed_ledger_blocks_continuation_before_provider_call(self):
  l=self.s.ledger(self.m);l['cash_balance']='11999.00';self.s.put_ledger(l)
  with self.assertRaisesRegex(ValidationError,'资料或依据已改变'):Engine(self.s,RuleProvider()).execute(self.m,resume_run=self.run)
  self.assertEqual(self.s.check(self.m,self.run)['status'],'failed')
 def test_wrong_merchant_or_provider_cannot_continue(self):
  other={**self.l,'merchant_id':'other'};self.s.put_ledger(other)
  with self.assertRaises(ValidationError):Engine(self.s,RuleProvider()).execute('other',resume_run=self.run)
  p=RuleProvider();p.mode='agentarts'
  with self.assertRaises(ValidationError):Engine(self.s,p).execute(self.m,resume_run=self.run)
 def test_changed_evidence_blocks_before_any_more_model_calls(self):
  self.s.add_knowledge(self.m,{'title':'新资料','content':'虚构补充资料，原分析完成后新增','source':'合成'})
  class Never(RuleProvider):
   def step(self,c):raise AssertionError('provider must not be called')
  with self.assertRaisesRegex(ValidationError,'资料或依据已改变'):Engine(self.s,Never()).execute(self.m,resume_run=self.run)
 def test_three_continuations_are_the_limit(self):
  self.s.event(self.m,self.run,'coordinator','task_resumed',{'attempt':1,'previous_usage':{}})
  self.s.event(self.m,self.run,'coordinator','task_resumed',{'attempt':2,'previous_usage':{}})
  self.s.event(self.m,self.run,'coordinator','task_resumed',{'attempt':3,'previous_usage':{}})
  with self.assertRaisesRegex(ValidationError,'续接3次'):Engine(self.s,RuleProvider()).execute(self.m,resume_run=self.run)
if __name__=='__main__':unittest.main()
