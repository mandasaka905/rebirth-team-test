from copy import deepcopy
import unittest
from rebirth.action_basis import basis,merchant_followups


class ActionBasisTests(unittest.TestCase):
    def report(self):
        return {'run_id':'run_a','events':[
            {'id':'e1','kind':'tool_result','actor':'cash','data':{'tool':'proposal_evaluate','arguments':{'proposal':{'id':'p','version':1}}}},
            {'id':'e2','kind':'tool_result','actor':'cash','data':{'tool':'proposal_evaluate','arguments':{'proposal':{'id':'p','version':2}}}},
            {'id':'e3','kind':'agent_result','actor':'cash','data':{'phase':'review','result':{'proposal_reviews':[
                {'proposal_id':'p','version':1,'reason':'旧版超预算','evidence_ids':['e1']},
                {'proposal_id':'p','version':2,'reason':'新版需求仍待核对','evidence_ids':['e2','fake']}]}}},
            {'id':'e4','kind':'coordination_plan','actor':'coordinator','data':{
                'requirements':[{'id':'old','proposal_id':'p','version':1},{'id':'new','proposal_id':'p','version':2}],
                'tasks':[{'requirement_id':rid,'assignee':'customer','disposition':'ask_merchant','action':'补需求记录','acceptance':'有日期与来源'} for rid in ('old','new')]}}
        ]}
    def test_exact_version_and_real_role_evidence_only(self):
        b=basis(self.report(),{'proposal':{'id':'p','version':2}},'cash')
        self.assertEqual(b['evidence_ids'],['e2']);self.assertEqual(b['reasons'],['新版需求仍待核对'])
        self.assertNotIn('e1',b['evidence_ids']);self.assertEqual(b['source_run'],'run_a')
    def test_only_current_version_followups_are_copied(self):
        r=self.report();old=deepcopy(r)
        tasks=merchant_followups(r,{'proposal':{'id':'p','version':2}})
        self.assertEqual([t['requirement_id'] for t in tasks],['new']);self.assertEqual(r,old)
        self.assertEqual(merchant_followups(r,None),[])
    def test_missing_evidence_is_not_fabricated(self):
        b=basis({'run_id':'empty','events':[]},None,'cash')
        self.assertEqual(b['evidence_ids'],[]);self.assertEqual(b['reasons'],[]);self.assertIn('暂无',b['notice'])
