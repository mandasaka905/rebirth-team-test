import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('evaluation',Path(__file__).resolve().parents[1]/'testing/evaluate_agent_output.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OutputEvaluation(unittest.TestCase):
 def fixture(self):
  return {'status':'failed','events':[{'id':'e1','kind':'tool_result','actor':'cash','data':{'phase':'review','value':{}}},{'id':'e2','kind':'agent_result','actor':'cash','data':{'phase':'review','result':{'assessment':{'conclusion':'测试主张','evidence_ids':['e1']}}}}],'result':{'proposals':[{}]}}
 def test_failure_keeps_partial_progress_but_no_valid_final_or_accuracy(self):
  r=m.summarize(self.fixture());self.assertEqual(r['specialist_phases_completed'],1);self.assertEqual(r['final_proposals'],0);self.assertIsNone(r['semantic_support_rate']);self.assertIsNone(r['risk_identification_rate'])
 def test_cross_role_and_future_reference_do_not_pass(self):
  r=self.fixture();r['events'][0]['actor']='inventory';self.assertEqual(m.summarize(r)['claims_with_valid_reference_scope'],0)
  r=self.fixture();r['events'].reverse();self.assertEqual(m.summarize(r)['claims_with_valid_reference_scope'],0)
 def test_repeated_phase_does_not_inflate_phase_coverage(self):
  r=self.fixture();r['events'].append({**r['events'][1],'id':'e3'});self.assertEqual(m.summarize(r)['specialist_phases_completed'],1)
