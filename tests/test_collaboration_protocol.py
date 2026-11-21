from copy import deepcopy
import unittest
from test_core import ledger, proposal
from rebirth.domain import ValidationError
from rebirth.tools import dispatch
from rebirth.collaboration_protocol import validate, rule_contract, requirements


class ProtocolTests(unittest.TestCase):
    def test_assigned_foreign_evidence_response_cannot_edit_foreign_plan(self):
        self.setUp();other=deepcopy(self.p);other.update(id='foreign',owner='customer')
        rows=[{'proposal_id':'foreign','coordination_tasks':[{'requirement_id':'assigned','assignee':'inventory'}]}]
        result=rule_contract({**self.context,'phase':'revise'}, {})
        response={'proposal_id':'foreign','previous_version':other['version'],'status':'needs_data','reason':'需要店主提供需求证据','requirement_ids':['assigned'],'evidence_ids':['e1']}
        result['revision_responses'].append(response)
        validate('inventory','revise',result,self.obs,[self.p,other],rows,[])
        for change in ({'status':'modified'},{'requirement_ids':['not_assigned']},{'previous_version':999}):
            bad=deepcopy(result);bad['revision_responses'][-1].update(change)
            with self.assertRaises(ValidationError):validate('inventory','revise',bad,self.obs,[self.p,other],rows,[])
    def setUp(self):
        self.p = proposal()
        self.p['owner'] = 'inventory'
        self.obs = [{'evidence_id': 'e1', 'tool': 'inventory_analyze', 'arguments': {},
                     'value': dispatch(ledger(), 'inventory_analyze', {})},
                    {'evidence_id': 'e2', 'tool': 'proposal_evaluate', 'arguments': {'proposal': self.p},
                     'value': dispatch(ledger(), 'proposal_evaluate', {'proposal': self.p})}]
        self.context = {'role': 'inventory', 'phase': 'review', 'observations': self.obs, 'proposals': [self.p], 'reviews': []}
        self.good = rule_contract(self.context, {})

    def check(self, result, phase='review', prior=()):
        validate('inventory', phase, result, self.obs, [self.p], prior, [])

    def test_structured_role_contract_accepts_real_evidence(self):
        self.check(self.good)

    def test_knowledge_claims_are_checked_by_actual_phase_validator(self):
        self.obs.append({'evidence_id':'e3','tool':'knowledge_search','value':{'matches':[{'id':'g','content':'库存不等于可售数量'}]}})
        r=deepcopy(self.good);r['assessment']['knowledge_citations']=[{'claim':'核查可售数量','document_id':'g',
            'supporting_text':'库存不等于可售数量','evidence_id':'e3','scope_limit':'不能证明本店会成交'}]
        self.check(r)
        r['assessment']['knowledge_citations'][0]['supporting_text']='保证全部卖出'
        with self.assertRaises(ValidationError):self.check(r)

    def test_unreviewed_candidate_can_be_calculated_but_not_submitted_as_evidenced(self):
        from rebirth.domain import validate_proposal
        p = deepcopy(self.p)
        p.pop('evidence_ids')
        value = dispatch(ledger(), 'proposal_evaluate', {'proposal': p})
        self.assertIn('checks', value)
        with self.assertRaises(ValidationError): validate_proposal(p)
        self.assertNotIn('evidence_ids', p)

    def test_missing_or_wrong_role_and_ungrounded_claim_rejected(self):
        for mutate in (lambda r:r.pop('assessment'),
                       lambda r:r['assessment'].update(perspective='cash'),
                       lambda r:r['assessment'].update(evidence_ids=['peer-or-fabricated']),
                       lambda r:r['assessment'].update(assumptions=[]),
                       lambda r:r['assessment'].update(limits=[])):
            r = deepcopy(self.good)
            mutate(r)
            with self.assertRaises(ValidationError): self.check(r)

    def test_missing_reviews_and_wrong_version_rejected(self):
        for mutate in (lambda r:r.update(proposal_reviews=[]),
                       lambda r:r['proposal_reviews'][0].update(version=999),
                       lambda r:r['proposal_reviews'][0].update(evidence_ids=['e1'])):
            r = deepcopy(self.good); mutate(r)
            with self.assertRaises(ValidationError): self.check(r)

    def test_previous_objection_cannot_disappear(self):
        previous = [{'proposal_id': self.p['id'], 'objections': [{'id': 'old-objection', 'from': 'inventory'}]}]
        with self.assertRaisesRegex(ValidationError, '静默消失'): self.check(self.good, prior=previous)

    def test_pass_cannot_retain_objection(self):
        r = deepcopy(self.good)
        r['proposal_reviews'][0]['status'] = 'pass'
        r['objections'] = [{'topic': 'inventory', 'severity': 'blocking', 'acceptance': '核实库存',
                            'evidence_ids': ['e2'], 'proposal_id': self.p['id']}]
        with self.assertRaisesRegex(ValidationError, '一边通过'): self.check(r)

    def test_task_coverage_owner_and_completion_conditions(self):
        rows = [{'proposal_id': self.p['id'], 'version': 1, 'owner': 'inventory', 'objections': [],
                 'tool_checks': {'checks': [{'code': 'STOCK_EXCEEDED'}], 'unknowns': []}}]
        req = requirements(rows)
        result = rule_contract({'role': 'coordinator', 'phase': 'coordinate', 'observations': [], 'coordination_requirements': req}, {})
        validate('coordinator', 'coordinate', result, [], [self.p], rows, req)
        for mutate in (lambda r:r.update(coordination_tasks=[]),
                       lambda r:r['coordination_tasks'][0].update(assignee='cash'),
                       lambda r:r['coordination_tasks'][0].update(acceptance='')):
            r=deepcopy(result);mutate(r)
            with self.assertRaises(ValidationError):validate('coordinator','coordinate',r,[],[self.p],rows,req)

    def test_revision_must_address_each_owned_candidate(self):
        r = rule_contract({**self.context, 'phase': 'revise'}, {})
        self.check(r, phase='revise')
        r['revision_responses'][0]['status'] = 'modified'
        with self.assertRaisesRegex(ValidationError, '实际安排变化'):self.check(r, phase='revise')

    def test_separate_task_responses_for_one_plan_preserve_coverage_and_unknowns(self):
        prior=[{'proposal_id':self.p['id'],'coordination_tasks':[{'assignee':'inventory','requirement_id':'plan-task'}]},
               {'proposal_id':None,'coordination_tasks':[{'assignee':'inventory','requirement_id':'shop-data'}]}]
        context={**self.context,'phase':'revise','reviews':prior}
        result=rule_contract(context,{})
        after=deepcopy(self.p);after.update(version=2,upfront_cost='10.00')
        result['proposals']=[after]
        result['revision_responses'][0]['status']='modified'
        self.check(result,phase='revise',prior=prior)
        broken=deepcopy(result);broken['revision_responses'][-1]['status']='modified'
        with self.assertRaisesRegex(ValidationError,'全店补证'):self.check(broken,phase='revise',prior=prior)
        broken=deepcopy(result);broken['revision_responses'][-1]['requirement_ids']=['plan-task']
        with self.assertRaises(ValidationError):self.check(broken,phase='revise',prior=prior)

    def test_no_proposal_missing_data_still_has_assignment(self):
        req = requirements([{'proposal_id':None,'version':None,'owner':'cash','objections':[],
                             'questions':[{'question':'请核实应付账款'}]}])
        result = rule_contract({'role':'coordinator','phase':'coordinate','observations':[], 'coordination_requirements':req}, {})
        self.assertEqual(result['coordination_tasks'][0]['disposition'], 'ask_merchant')
        self.assertEqual(result['coordination_tasks'][0]['assignee'], 'cash')


if __name__ == '__main__': unittest.main()
