import json,tempfile,unittest
from pathlib import Path
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider,ProviderError,ResponseFormatError,extract_action
ROOT=Path(__file__).resolve().parents[1]
class AgentCorrectionTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'business.sqlite3')
  self.ledger=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'));self.store.put_ledger(self.ledger)
  self.run,_=self.store.new_run(self.ledger['merchant_id'],'rules')
 def tearDown(self):self.tmp.cleanup()
 def invoke(self,provider,role='coordinator',phase='coordinate'):
  return Engine(self.store,provider).call(self.ledger['merchant_id'],self.run,self.ledger,role,phase)
 def test_output_format_is_corrected_with_feedback_and_audit(self):
  class P(RuleProvider):
   def __init__(self):self.calls=0
   def step(self,c):
    self.calls+=1
    if self.calls<=2:raise ResponseFormatError('invalid JSON')
    assert len(c['protocol_feedback'])==2
    return super().step(c)
  p=P();self.invoke(p);self.assertEqual(p.calls,3)
  self.assertEqual(sum(e['kind']=='agent_output_rejected' for e in self.store.events(self.ledger['merchant_id'],self.run)),2)
 def test_bad_evidence_is_not_accepted_and_must_be_corrected_by_agent(self):
  class P(RuleProvider):
   def __init__(self):self.calls=0
   def step(self,c):
    self.calls+=1
    if self.calls==1:return {'action':'final','result':{'notes':[{'statement':'bad','evidence_ids':['invented']} ]}}
    assert c['protocol_feedback'][0]['rejected_result']['notes'][0]['evidence_ids']==['invented']
    return super().step(c)
  p=P();result=self.invoke(p);self.assertNotIn('invented',json.dumps(result));self.assertEqual(p.calls,2)
 def test_network_failure_never_retries(self):
  class P(RuleProvider):
   def __init__(self):self.calls=0
   def step(self,c):self.calls+=1;raise ProviderError('network failed')
  p=P()
  with self.assertRaises(ProviderError):self.invoke(p)
  self.assertEqual(p.calls,1)
 def test_persistent_malformed_output_stops_after_three_calls(self):
  class P(RuleProvider):
   def __init__(self):self.calls=0
   def step(self,c):self.calls+=1;raise ResponseFormatError('invalid JSON')
  p=P()
  with self.assertRaises(ResponseFormatError):self.invoke(p)
  self.assertEqual(p.calls,3)
class ActionEnvelopeTest(unittest.TestCase):
 def test_short_explanation_and_one_complete_action_are_accepted(self):
  action={'action':'tool','name':'supply_analyze','arguments':{}}
  self.assertEqual(extract_action('先核对供应条件。\n\n'+json.dumps(action)),action)
 def test_multiple_or_quoted_actions_are_not_guessed(self):
  for value in ['解释 {"action":"tool"} {"action":"final"}', '解释 {"action":"tool"} 后续说明', '解释 [ {"action":"tool"} ]']:
   with self.assertRaises(ResponseFormatError):extract_action(value)
 def test_plain_code_fence_is_a_supported_envelope(self):
  self.assertEqual(extract_action('```\n{"action":"final","result":{}}\n```')['action'],'final')
if __name__=='__main__':unittest.main()
