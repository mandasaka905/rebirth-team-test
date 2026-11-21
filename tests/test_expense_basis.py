from copy import deepcopy
import unittest
from test_core import proposal
from rebirth.domain import validate_proposal,ValidationError


class ExpenseBasisTests(unittest.TestCase):
    def good(self):
        p=proposal();p.update(upfront_cost='80.00',other_cost='0.00',costs_confirmed=False,
            expense_breakdown=[dict(id='print',label='少量宣传单',quantity=20,unit_cost='2.00',amount='40.00',basis='构造假设，不是报价',basis_kind='assumption'),
                               dict(id='bags',label='小批包装',quantity=20,unit_cost='2.00',amount='40.00',basis='构造假设，不是报价',basis_kind='assumption')])
        return p
    def test_breakdown_is_checked_without_changing_legacy_contract(self):
        validate_proposal(self.good());validate_proposal(proposal())
    def test_mismatch_duplicate_or_fake_confirmation_rejected(self):
        for change in ('total','quantity','duplicate','confirmation'):
            p=self.good()
            if change=='total':p['upfront_cost']='79.00'
            if change=='quantity':p['expense_breakdown'][0]['quantity']=21
            if change=='duplicate':p['expense_breakdown'][1]['id']='print'
            if change=='confirmation':p['costs_confirmed']=True
            with self.assertRaises(ValidationError):validate_proposal(p)


if __name__=='__main__':unittest.main()
