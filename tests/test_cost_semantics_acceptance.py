from copy import deepcopy
import unittest
from test_core import ledger,proposal
from rebirth.tools import evaluate
class CostSemanticsAcceptance(unittest.TestCase):
 def test_stock_cost_changes_profit_not_cash(self):
  l=ledger();p=proposal();sku=p['items'][0]['sku'];a=evaluate(l,{'proposal':p})
  product=next(x for x in l['products'] if x['sku']==sku);product['unit_cost']='99.00'
  b=evaluate(l,{'proposal':p})
  self.assertNotEqual(a['known_stock_cost'],b['known_stock_cost']);self.assertEqual(a['trial_cash_commitment'],b['trial_cash_commitment']);self.assertEqual(a['scenarios'],b['scenarios'])
 def test_extra_cash_changes_commitment(self):
  l=ledger();p=proposal();a=evaluate(l,{'proposal':p});p['items'][0]['variable_cash_cost']='10.00';b=evaluate(l,{'proposal':p})
  self.assertNotEqual(a['trial_cash_commitment'],b['trial_cash_commitment']);self.assertEqual(a['known_stock_cost'],b['known_stock_cost'])
 def test_unknown_stock_cost_keeps_cash_but_not_profit(self):
  l=ledger();p=proposal();sku=p['items'][0]['sku'];next(x for x in l['products'] if x['sku']==sku)['unit_cost']=None
  a=evaluate(l,{'proposal':p});self.assertIsNone(a['gross_profit_after_declared_trial_costs']);self.assertIsNotNone(a['trial_cash_commitment'])
 def test_breakdown_reconciles(self):
  from decimal import Decimal
  a=evaluate(ledger(),{'proposal':proposal()});b=a['cash_cost_breakdown']
  self.assertEqual(sum(Decimal(b[k]) for k in ('upfront_extra','variable_extra','new_procurement')),Decimal(a['trial_cash_commitment']))

 def test_unpaid_purchase_is_a_payment_not_second_trial_cost(self):
  from decimal import Decimal
  l=ledger();p=proposal();a=evaluate(l,{'proposal':p})
  l['obligations'].append({'id':'unpaid_goods','date':l['as_of'],'amount':'100.00','source_id':l['obligations'][0]['source_id']})
  b=evaluate(l,{'proposal':p})
  self.assertEqual(a['trial_cash_commitment'],b['trial_cash_commitment'])
  self.assertEqual(Decimal(a['scenarios'][0]['ending_cash'])-Decimal(b['scenarios'][0]['ending_cash']),Decimal('100.00'))
