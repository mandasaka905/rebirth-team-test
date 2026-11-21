import json
from pathlib import Path
import unittest
from rebirth.tools import dispatch

ROOT = Path(__file__).resolve().parents[1]/'testing/public-retail'


class PublicCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['id']: c for c in json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))}

    def evaluate(self, key):
        c = self.cases[key]
        return dispatch(c['ledger'], 'proposal_evaluate', {'proposal': c['initial_proposal']})

    def test_cash_is_reconciled_independently(self):
        # Zero sales: starting balance - trial expense - known rent.
        for key, expected in [('C01', '2700.00'), ('C02', '0.00'), ('C03', '200.00'), ('C07', '0.00')]:
            self.assertEqual(self.evaluate(key)['scenarios'][0]['minimum_cash_before_receipts'], expected)

    def test_unknown_cost_never_becomes_profit(self):
        self.assertIsNone(self.evaluate('C05')['gross_profit_after_declared_trial_costs'])

    def test_source_currency_and_scenarios_remain_separate(self):
        summary = json.loads((ROOT/'public-summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['counts']['rows'], 541909)
        for c in self.cases.values():
            self.assertTrue(c['ledger']['synthetic'])
            self.assertFalse(c['ledger']['merchant_confirmed'])
            self.assertEqual(c['kind'], 'constructed_cny_scenario')
            self.assertFalse(c['rubric']['real_merchant_outcome'])
            self.assertEqual(c['ledger']['products'][0]['unit_price'], '70.00')


if __name__ == '__main__':
    unittest.main()
