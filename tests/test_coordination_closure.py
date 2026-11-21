import unittest
from copy import deepcopy
from rebirth.coordination_closure import close


class ClosureTests(unittest.TestCase):
    def test_archive_preserves_missing_data_and_never_requests_more_revision(self):
        reviews=[{'proposal_id':'p','version':2,'owner':'inventory',
                  'objections':[{'id':'ob1','request':'核对真实询问','acceptance':'有日期与来源','from':'customer','severity':'needs_data'}],
                  'tool_checks':{'checks':[{'code':'BUDGET_EXCEEDED'}],'unknowns':['费用未知']}}]
        original=deepcopy(reviews);r=close(reviews)
        self.assertEqual(r['revise_roles'],[]);self.assertEqual(len(r['coordination_tasks']),3)
        self.assertEqual(r['source'],'host_archive_of_validated_reviews');self.assertEqual(reviews,original)
        self.assertTrue(any(t['action']=='核对真实询问' and t['assignee']=='customer' for t in r['coordination_tasks']))
        self.assertTrue(any(t['disposition']=='retain_unresolved' for t in r['coordination_tasks']))
    def test_empty_requirements_do_not_invent_tasks(self):
        self.assertEqual(close([])['coordination_tasks'],[])
    def test_replay_does_not_inflate_revision_or_resolved_constraint_counts(self):
        from rebirth.collaboration import summarize
        e={'kind':'revision_effect','data':{'proposal_id':'p','before_version':1,'after_version':2,
           'material_change':True,'resolved_checks':['BUDGET_EXCEEDED']}}
        result=summarize([e,deepcopy(e),deepcopy(e)])
        self.assertEqual(result['material_revisions'],1);self.assertEqual(result['resolved_check_count'],1)
        self.assertEqual(result['replayed_revision_events'],2)
