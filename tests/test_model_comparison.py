from pathlib import Path
from copy import deepcopy
import importlib.util,unittest
from rebirth.domain import ValidationError
from rebirth.planning import validate_models
from rebirth.tools import dispatch
from rebirth.model_comparison import for_report

spec=importlib.util.spec_from_file_location('model_fixture',Path(__file__).resolve().parents[1]/'testing/model-reconstruction/build_case.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class ModelComparisonTests(unittest.TestCase):
    def setUp(self):self.ledger,self.args,self.revised=fixture.fixture()
    def compare(self,args=None):return dispatch(self.ledger,'business_model_compare',args or self.args)
    def test_structural_changes_unknown_cost_and_tradeoffs_are_preserved(self):
        r=self.compare();self.assertEqual(len(r['rows']),3);self.assertIsNone(r['selected_winner'])
        pickup,delivery=r['rows'][1:]
        self.assertIn('channel',{x['field'] for x in pickup['structural_field_changes']})
        self.assertEqual(pickup['assessment']['unit_contribution'],'27.00')
        self.assertEqual(pickup['scenarios'][2]['period_contribution'],'480.00')
        self.assertIsNone(delivery['assessment']['unit_contribution']);self.assertIsNone(delivery['scenarios'][2]['period_contribution'])
        self.assertTrue(any('工时' in x for x in delivery['blockers']));self.assertFalse(r['scope_confirmed'])
    def test_revision_is_compared_in_place_not_added_as_another_alternative(self):
        r=self.compare({**self.args,'drafts':[self.args['drafts'][0],self.revised]})
        self.assertFalse(r['rows'][2]['blockers']);self.assertEqual(r['rows'][2]['draft_version'],2)
        with self.assertRaises(ValidationError):self.compare({**self.args,'drafts':[self.args['drafts'][1],self.revised]})
    def test_period_mismatch_does_not_rank_and_old_baseline_rejected(self):
        a=deepcopy(self.args);a['drafts'][0]['model']['period_days']=30
        self.assertFalse(self.compare(a)['same_period'])
        a['baseline_ref']['version']=999
        with self.assertRaises(ValidationError):self.compare(a)
    def test_costs_unknown_mismatch_and_false_confirmation_rejected(self):
        for kind in ('unknown','sum','confirm','duplicate'):
            m=deepcopy(self.args['drafts'][0]['model'])
            if kind=='unknown':m['unit_cost_components'][0]['amount']=None
            if kind=='sum':m['unit_cost']='40.99'
            if kind=='confirm':m['costs_confirmed']=True
            if kind=='duplicate':m['unit_cost_components'][1]['id']='goods'
            with self.assertRaises(ValidationError):validate_models([m])
    def test_numeric_only_change_not_claimed_as_structural_innovation(self):
        a=deepcopy(self.args);a['drafts']=[a['drafts'][0]];a['drafts'][0]['model']=deepcopy(self.ledger['business_models'][0]);a['drafts'][0]['model']['status']='candidate';a['drafts'][0]['model']['fixed_cost']='50.00'
        r=self.compare(a)['rows'][1];self.assertEqual(r['structural_field_changes'],[])
        self.assertTrue(any('结构字段未改变' in x for x in r['warnings']))
    def test_automatic_report_does_not_invent_missing_baseline(self):
        self.assertIsNone(for_report(self.ledger,[]));self.ledger['business_models']=[]
        self.assertEqual(for_report(self.ledger,self.args['drafts'])['rows'],[])
    def test_real_engine_includes_comparison_without_changing_saved_models(self):
        import tempfile
        from rebirth.store import Store
        from rebirth.engine import Engine
        from rebirth.providers import RuleProvider
        with tempfile.TemporaryDirectory() as folder:
            s=Store(Path(folder)/'model.sqlite3');s.put_ledger(self.ledger);original=s.ledger(self.ledger['merchant_id'])
            r=Engine(s,RuleProvider(),max_rounds=0).execute(self.ledger['merchant_id'])
            self.assertTrue(r['result']['model_comparison']['rows'])
            self.assertIsNone(r['result']['model_comparison']['selected_winner'])
            self.assertEqual(original,s.ledger(self.ledger['merchant_id']))
