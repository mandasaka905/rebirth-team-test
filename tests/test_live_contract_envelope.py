import unittest
from unittest.mock import patch
from rebirth.providers import AgentArtsProvider
from rebirth.control import RunControl


class EnvelopeTests(unittest.TestCase):
    def capture(self, role, phase, proposals=None, instruction_override=None, models=None, observations=None):
        provider = AgentArtsProvider.__new__(AgentArtsProvider)
        provider.config = {'agents': {role: {'url':'wss://example.invalid/runtime/ws',
                          'token_env':'TEST_CONTRACT_KEY', 'auth_header':'Authorization','transport':'managed_ws'}}}
        provider.control = RunControl()
        provider.sessions = {}
        provider.instruction_override = instruction_override
        context = {'run_id':'synthetic', 'role':role,'phase':phase,'collaboration_protocol':2,
                   'ledger':{'business_models':models or []},'observations':observations if observations is not None else [{'evidence_id':'e42','value':{}}], 'proposals':proposals or []}
        captured = []
        def fake(url, token, session, envelope, control, **kwargs):
            captured.append(envelope)
            return {'action':'final','result':{}}
        with patch.dict('os.environ', {'TEST_CONTRACT_KEY':'synthetic-only'}), patch('rebirth.managed_ws.invoke',side_effect=fake):
            provider.step(context)
        return captured[0]

    def test_primary_example_matches_specialist_enforced_fields(self):
        for phase, fields in [('investigate',['assessment']),('review',['assessment','proposal_reviews']),
                              ('revise',['assessment','revision_responses'])]:
            envelope=self.capture('inventory',phase)
            for field in fields:self.assertIn(field,envelope['output_contract']['final_action']['result'])
            self.assertEqual(envelope['stage_requirements']['current_evidence_ids'],['e42'])

    def test_coordinator_example_has_tasks_instead_of_legacy_only_roles(self):
        envelope=self.capture('coordinator','coordinate')
        self.assertIn('coordination_tasks',envelope['output_contract']['final_action']['result'])

    def test_existing_stock_does_not_require_new_purchase_terms(self):
        envelope=self.capture('inventory','review',[{'id':'clearance','version':2,'items':[{'receipt_date':'2026-11-08'}]}])
        stage=envelope['stage_requirements']
        self.assertFalse(stage['proposal_scope'][0]['supplier_terms_required_for_this_plan'])
        self.assertIn('不是采购到货日',stage['field_meanings']['items[].receipt_date'])
        self.assertIn('未付采购欠款',stage['instructions'])

    def test_new_procurement_keeps_supply_checks_and_single_identity_has_same_scope(self):
        p={'id':'replenishment','version':1,'procurements':[{'supply_id':'offer1'}]}
        multi=self.capture('cash','review',[p])
        single=self.capture('cash','review',[p],instruction_override='综合单智能体')
        self.assertTrue(multi['stage_requirements']['proposal_scope'][0]['supplier_terms_required_for_this_plan'])
        self.assertEqual(multi['stage_requirements']['proposal_scope'],single['stage_requirements']['proposal_scope'])
        self.assertEqual(multi['stage_requirements']['field_meanings'],single['stage_requirements']['field_meanings'])

    def test_no_model_archive_is_not_a_prerequisite_for_ordinary_candidates(self):
        stage=self.capture('inventory','propose')['stage_requirements']
        self.assertFalse(stage['business_model_linkage']['model_refs_required'])
        self.assertIn('model_refs=[]',stage['business_model_linkage']['when_no_models'])
        self.assertIn('缩减了哪些具体动作',stage['instructions'])

    def test_existing_models_still_require_exact_version(self):
        stage=self.capture('cash','review',models=[{'id':'offline_retail','version':3}])['stage_requirements']
        self.assertTrue(stage['business_model_linkage']['model_refs_required'])
        self.assertEqual(stage['business_model_linkage']['existing_versions'],[{'id':'offline_retail','version':3}])

    def test_retrieved_citation_ids_are_phase_local_and_not_host_written_claims(self):
        obs=[{'evidence_id':'e9','tool':'knowledge_search','value':{'matches':[{'id':'external_doc','content':'核实付款时序。'}]}},
             {'evidence_id':'e10','tool':'cash_baseline','value':{}}]
        envelope=self.capture('cash','investigate',observations=obs)
        self.assertEqual(envelope['stage_requirements']['retrieved_knowledge'],[{'evidence_id':'e9','document_ids':['external_doc']}])
        self.assertEqual(envelope['output_contract']['final_action']['result']['assessment']['knowledge_citations'],[])
        self.assertIn('不强凑引用',envelope['stage_requirements']['instructions'])
        other=self.capture('cash','investigate')
        self.assertNotIn('retrieved_knowledge',other['stage_requirements'])


if __name__=='__main__':unittest.main()
