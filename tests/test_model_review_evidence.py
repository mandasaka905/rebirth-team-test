import unittest
from rebirth.model_review_evidence import validate
from rebirth.domain import ValidationError

class ModelReviewEvidenceTests(unittest.TestCase):
    def test_exact_role_phase_observations_required(self):
        drafts=[{'id':'d','version':2}];r=[{'draft_id':'d','version':2,'evidence_ids':['e1']}]
        obs=[{'evidence_id':'e1','tool':'model_draft_evaluate','arguments':{'draft':drafts[0]},'value':{}}]
        validate(r,drafts,obs)
        for bad in ([],[{**obs[0],'tool':'inventory_analyze'}],[{**obs[0],'arguments':{'draft':{'id':'d','version':1}}}]):
            with self.assertRaises(ValidationError):validate(r,drafts,bad)
    def test_missing_or_duplicate_reviews_rejected(self):
        with self.assertRaises(ValidationError):validate([], [{'id':'d','version':1}],[])
    def test_same_version_cannot_substitute_other_cost_but_redaction_is_expected(self):
        from copy import deepcopy
        d={'id':'d','version':1,'model':{'unit_cost':'40.00','source_note':'合成来源'},'supply_requirements':[]}
        observed=deepcopy(d);observed['model']['source_note']='原说明留存本机'
        r=[{'draft_id':'d','version':1,'evidence_ids':['e1']}]
        obs=[{'evidence_id':'e1','tool':'model_draft_evaluate','arguments':{'draft':observed},'value':{}}]
        validate(r,[d],obs)
        observed['model']['unit_cost']='0.00'
        with self.assertRaises(ValidationError):validate(r,[d],obs)
