import unittest
from copy import deepcopy
from rebirth.knowledge_claims import validate
from rebirth.domain import ValidationError


class KnowledgeClaimsTests(unittest.TestCase):
    def setUp(self):
        self.obs=[{'evidence_id':'e1','tool':'knowledge_search','value':{'matches':[
            {'id':'guide','content':'未来销售不能当作已经到手的现金。'}]}}]
        self.claim={'claim':'先检查房租付款日','document_id':'guide','supporting_text':'未来销售不能当作已经到手的现金',
                    'evidence_id':'e1','scope_limit':'不能证明本店未来成交量'}
    def test_exact_returned_excerpt_accepted_without_semantic_verdict(self):
        validate([self.claim],self.obs);validate([],self.obs)
        # This check deliberately does not pretend to grade semantic entailment.
        c=deepcopy(self.claim);c['claim']='语义仍需人工核对';validate([c],self.obs)
    def test_fabricated_evidence_document_and_excerpt_rejected(self):
        for k,v in [('evidence_id','peer_phase'),('document_id','unretrieved'),('supporting_text','保证下周赚钱'),('scope_limit','')]:
            c=deepcopy(self.claim);c[k]=v
            with self.assertRaises(ValidationError):validate([c],self.obs)
    def test_other_tools_cannot_be_used_as_knowledge_search(self):
        self.obs[0]['tool']='inventory_analyze'
        with self.assertRaises(ValidationError):validate([self.claim],self.obs)
