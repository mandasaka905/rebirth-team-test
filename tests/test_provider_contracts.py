import unittest
from rebirth.provider_contracts import clarify
from rebirth.tool_batch import expand


class RequestContractTests(unittest.TestCase):
    def test_revision_slots_separate_global_and_cross_owner_tasks(self):
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        clarify(e,{'role':'customer','phase':'revise','proposals':[{'id':'own','owner':'customer','version':1},{'id':'other','owner':'inventory','version':2}],
            'reviews':[{'proposal_id':None,'coordination_tasks':[{'requirement_id':'global','assignee':'customer'}]},
                       {'proposal_id':'other','coordination_tasks':[{'requirement_id':'cross','assignee':'customer'}]}]})
        self.assertEqual(e['stage_requirements']['global_evidence_task_ids'],['global'])
        self.assertEqual(e['stage_requirements']['revision_response_slots'][1],{'proposal_id':'other','previous_version':2,'may_modify':False,'assigned_requirement_ids':['cross']})
    def test_failed_batch_recovers_one_missing_tool_without_running_it(self):
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        c={'role':'cash','phase':'review','proposals':[{'id':'p','version':2}],
           'observations':[{'tool':'read_tools','error':'calls缺失'}]}
        clarify(e,c)
        self.assertNotIn('batch_tool_action',e['output_contract'])
        self.assertEqual(e['output_contract']['single_tool_recovery_example']['name'],'cash_baseline')
        c['observations'].append({'tool':'cash_baseline','value':{}})
        clarify(e,c)
        self.assertEqual(e['output_contract']['single_tool_recovery_example']['arguments']['proposal'],{'id':'p','version':2})
    def test_batch_example_is_executable_and_stage_rules_explicit(self):
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        clarify(e,{'phase':'propose'})
        action=e['output_contract']['batch_tool_action']
        self.assertEqual([n for n,a in expand(action['name'],action['arguments'])],['inventory_analyze','data_readiness'])
        self.assertIn('proposals=[]',e['stage_requirements']['instructions'])
        self.assertIn('版本恰为原版加1',e['stage_requirements']['instructions'])
    def test_completed_review_and_coordinator_do_not_request_redundant_reads(self):
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        clarify(e,{'role':'cash','phase':'review','proposals':[{'id':'p','version':2}],
                   'observations':[{'tool':'proposal_evaluate','arguments':{'proposal':{'id':'p','version':2}},'value':{}}]})
        self.assertIn('直接返回',e['stage_requirements']['next_action_hint'])
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        clarify(e,{'role':'coordinator','phase':'coordinate'})
        self.assertFalse(e['stage_requirements']['fresh_tool_required'])
    def test_coordinator_receives_exact_slots_without_host_decisions(self):
        e={'output_contract':{},'stage_requirements':{'instructions':''}}
        clarify(e,{'role':'coordinator','coordination_requirements':[{'id':'req_a'},{'id':'req_b'}]})
        self.assertEqual(e['stage_requirements']['coordination_slot_ids'],['req_a','req_b'])
        self.assertEqual(e['stage_requirements']['coordination_task_count'],2)
        self.assertNotIn('coordination_tasks',e['stage_requirements'])
