import json
from pathlib import Path
import unittest

from rebirth.domain import ValidationError, validate_ledger
from rebirth.mcp_server import evaluate_constraints
from rebirth.tools import evaluate

ROOT = Path(__file__).resolve().parents[1]


class MCPAdapterTests(unittest.TestCase):
    def setUp(self):
        self.ledger = json.loads((ROOT / 'examples/merchant.synthetic.json').read_text(encoding='utf-8'))
        self.proposal = json.loads((ROOT / 'config/contracts.json').read_text(encoding='utf-8'))['proposal_example']

    def test_same_calculations_and_no_execution_authority(self):
        result = evaluate_constraints(self.ledger, self.proposal)
        self.assertEqual(result['evaluation'], evaluate(validate_ledger(self.ledger), {'proposal': self.proposal}))
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(len(result['input_sha256']), 64)

    def test_excess_budget_is_rejected(self):
        self.proposal['items'][0]['variable_cash_cost'] = '400.00'
        result = evaluate_constraints(self.ledger, self.proposal)['evaluation']
        self.assertIn('BUDGET_EXCEEDED', {x['code'] for x in result['checks']})
        self.assertFalse(result['constraint_pass'])

    def test_unknown_cost_stays_unknown(self):
        used = {item['sku'] for item in self.proposal['items']}
        for product in self.ledger['products']:
            if product['sku'] in used:
                product['unit_cost'] = None
        result = evaluate_constraints(self.ledger, self.proposal)['evaluation']
        self.assertIsNone(result['gross_profit_after_declared_trial_costs'])
        self.assertTrue(result['unknowns'])
        self.assertFalse(result['eligible_for_merchant_review'])

    def test_invalid_ledger_is_not_calculated(self):
        with self.assertRaises(ValidationError):
            evaluate_constraints({}, self.proposal)

    def test_digest_changes_with_input(self):
        first = evaluate_constraints(self.ledger, self.proposal)['input_sha256']
        self.ledger['name'] += '变更'
        self.assertNotEqual(first, evaluate_constraints(self.ledger, self.proposal)['input_sha256'])
