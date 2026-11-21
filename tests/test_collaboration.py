from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
from test_core import ledger, proposal
from rebirth.collaboration import revision_effect, action_readiness
from rebirth.tools import dispatch
from rebirth.engine import Engine
from rebirth.store import Store
from rebirth.providers import SimulationProvider
from rebirth.control import RunControl


class CollaborationTests(unittest.TestCase):
    def test_final_archive_after_revision_does_not_request_another_coordinator_judgment(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'closure.sqlite3');l=ledger();store.put_ledger(l)
            report=Engine(store,SimulationProvider('conflict'),max_rounds=1,
                          control=RunControl(max_calls=120,max_input_bytes=10000000,max_output_bytes=1000000)).execute(l['merchant_id'])
            plans=[e for e in report['events'] if e['kind']=='coordination_plan']
            self.assertEqual(plans[0]['actor'],'coordinator');self.assertEqual(plans[-1]['actor'],'host')
            self.assertEqual(plans[-1]['data']['source'],'host_archive_of_validated_reviews')
            self.assertTrue(plans[-1]['data']['revision_budget_exhausted'])
            required={r['id'] for r in plans[-1]['data']['requirements']}
            self.assertEqual(required,{t['requirement_id'] for t in plans[-1]['data']['tasks']})
    def test_merchant_candidate_is_calculated_and_reviewed_without_fake_ai_authorship(self):
        from rebirth.providers import RuleProvider
        l = ledger()
        p = proposal()
        p.pop('evidence_ids')
        p.update(id='merchant_clearance', version=1, owner='inventory', upfront_cost='3000.00')
        l['candidate_for_review'] = p
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'business.sqlite3')
            store.put_ledger(l)
            report = Engine(store, RuleProvider(), max_rounds=0).execute(l['merchant_id'])
            candidate = next(e for e in report['events'] if e['kind'] == 'merchant_candidate')
            self.assertEqual(candidate['actor'], 'merchant')
            refs = candidate['data']['proposal']['evidence_ids']
            self.assertTrue(all(any(e['id'] == ref and e['kind'] == 'tool_result' for e in report['events']) for ref in refs))
            entry = next(p for p in report['result']['proposals'] if p['proposal']['id'] == 'merchant_clearance')
            self.assertIn('BUDGET_EXCEEDED', [c['code'] for c in entry['evaluation']['checks']])
            self.assertTrue(entry['objections'])

    def test_constraint_feedback_and_revision_trace_in_real_engine(self):
        class Capture(SimulationProvider):
            def __init__(self):
                super().__init__('conflict')
                self.contexts = []
            def step(self, context):
                if context['phase'] in ('coordinate', 'revise'):
                    self.contexts.append(deepcopy(context))
                return super().step(context)
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'business.sqlite3')
            l = ledger()
            store.put_ledger(l)
            provider = Capture()
            report = Engine(store, provider, control=RunControl(max_calls=120, max_input_bytes=10000000, max_output_bytes=1000000)).execute(l['merchant_id'])
            self.assertTrue(any(c['phase'] == 'revise' and
                any(r.get('tool_checks', {}).get('checks') for r in c['reviews']) for c in provider.contexts))
            self.assertGreater(report['result']['collaboration']['material_revisions'], 0)
            self.assertTrue(report['result']['action_readiness'])

    def test_title_rewrite_is_not_operational_change(self):
        before = proposal()
        after = deepcopy(before)
        after['title'] = '更吸引人的标题'
        self.assertFalse(revision_effect(ledger(), before, after, [])['material_change'])

    def test_unresolved_objection_blocks_action_even_if_calculation_passes(self):
        p = proposal()
        e = dispatch(ledger(), 'proposal_evaluate', {'proposal': p})
        rows = action_readiness([{'proposal': p, 'evaluation': e, 'objections': [{'reason': '需求证据不足'}]}])
        self.assertEqual(rows[0]['state'], 'hold')
        self.assertFalse(rows[0]['automatic_execution'])

    def test_version_and_evidence_are_not_material_revision(self):
        before = proposal()
        after = deepcopy(before)
        after.update(version=before['version'] + 1, evidence_ids=['another'])
        result = revision_effect(ledger(), before, after, [])
        self.assertFalse(result['material_change'])
        self.assertEqual(result['resolved_checks'], [])

    def test_budget_fix_is_recomputed_and_attributed(self):
        before = proposal()
        before['upfront_cost'] = '3000.00'
        after = deepcopy(before)
        after.update(upfront_cost='100.00', version=before['version'] + 1)
        objection = {'from': 'cash', 'reason': '超过可用试验资金', 'request': '降低前置投入'}
        result = revision_effect(ledger(), before, after,
            [{'proposal_id': before['id'], 'version': before['version'], 'objections': [objection]}])
        self.assertIn('BUDGET_EXCEEDED', result['resolved_checks'])
        self.assertIn('upfront_cost', result['changed_fields'])
        self.assertEqual(result['objections'], [objection])

    def test_regression_not_hidden(self):
        before = proposal()
        after = deepcopy(before)
        after['items'][0]['quantity'] = 100000
        result = revision_effect(ledger(), before, after, [])
        self.assertIn('STOCK_EXCEEDED', result['introduced_checks'])


if __name__ == '__main__':
    unittest.main()
