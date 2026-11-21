import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import urllib.error
import test_core
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider
from rebirth.domain import ValidationError,validate_ledger
from rebirth.tools import evaluate,dispatch
from rebirth.planning import combine
from rebirth.supply import analyze
from rebirth.feedback import validate_feedback,summarize_feedback
from rebirth.knowledge import BUILTINS,search
from rebirth.server import make_handler

ROOT=Path(__file__).resolve().parent.parent

def fixture():
    l=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'));l.pop('accounts',None)
    for p in l['products']:
        if p['sku']=='COAT_02':p.update(stock=2,sales_30d=30)
    l['supply_options']=[{'id':'supplier_a','sku':'COAT_02','supplier':'合成供货方','lead_days':4,'payment_days':0,'min_qty':3,'capacity':20,'unit_cost':'90.00','shipping_cost':'10.00','returnable':True,'return_days':7,'return_policy':'合成条件：须验货，不保证退款','confirmed':True,'checked_on':l['as_of'],'source_note':'全部合成供应条件'}]
    return l

def proposal():
    return {'id':'restock','version':1,'owner':'inventory','title':'合成小批量补货','spend_date':'2026-10-25','upfront_cost':'0.00','other_cost':'0.00','weekly_hours':1,'sales_assumption':'merchant_estimate','costs_confirmed':True,'model_refs':[{'id':'current','version':1}],
            'items':[{'sku':'COAT_02','quantity':5,'price':'139.00','variable_cash_cost':'0.00','sale_date':'2026-10-29','receipt_date':'2026-10-30'}],
            'procurements':[{'offer_id':'supplier_a','order_date':'2026-10-25','quantity':3}], 'rationale':'合成条件检验','evidence_ids':['test_evidence'],'assumptions':['销量仅是假设'],'stop_conditions':['供应延迟停止']}

class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.l=fixture();self.m=self.l['merchant_id'];self.store.put_ledger(self.l)
    def tearDown(self):self.tmp.cleanup()
    def report(self):return Engine(self.store,RuleProvider()).execute(self.m)
    def decision(self,r):
        d=r['result']['model_drafts'][0]
        return {'run_id':r['run_id'],'draft_id':d['id'],'version':d['version'],'confirmed':True,'source_note':'合成商户审阅','decision':'accept'}
    def csv(self,kind='inventory'):
        return {'kind':kind,'csv':'sku,name,stock,sales_30d,received_on,unit_cost,unit_price,size_complete,source_note\nNEW_S,新款S码,3,0,2026-10-20,,119.00,,合成盘点\n','source_note':'合成批次','replace_existing':False,'confirm_sales_window':False}
    def commit(self,raw):
        p=self.store.operating_import(self.m,raw);return self.store.operating_import(self.m,{**raw,'confirmed':True,'preview_digest':p['preview_digest']},True)

    def test_arrival_fifo_and_zero_sales_full_purchase_cash(self):
        r=evaluate(self.l,{'proposal':proposal()})
        self.assertTrue(r['constraint_pass']);self.assertEqual(r['known_stock_cost'],'430.00');self.assertEqual(r['gross_profit_after_declared_trial_costs'],'255.00')
        self.assertEqual(r['trial_cash_commitment'],'280.00');self.assertEqual(r['scenarios'][0]['days'][0]['outflow'],'280.00')
        self.assertEqual(r['procurement']['lines'][0]['arrival_date'],'2026-10-29');self.assertEqual(r['procurement']['stock_path'][0]['remaining_on_delivery'],0)
    def test_unsold_procurement_is_not_double_expensed(self):
        p=proposal();p['procurements'][0]['quantity']=6;p['items'][0]['quantity']=3
        r=evaluate(self.l,{'proposal':p});self.assertEqual(r['trial_cash_commitment'],'550.00');self.assertEqual(r['known_stock_cost'],'250.00');self.assertEqual(r['gross_profit_after_declared_trial_costs'],'157.00')
        self.assertEqual(r['procurement']['stock_path'][0]['remaining_on_delivery'],5)
    def test_delivery_before_arrival_cannot_use_future_goods(self):
        p=proposal();p['items'][0]['sale_date']='2026-10-28';r=evaluate(self.l,{'proposal':p});self.assertIn('STOCK_EXCEEDED',[x['code'] for x in r['checks']])
    def test_minimum_capacity_and_unknown_conditions(self):
        p=proposal();p['procurements'][0]['quantity']=1
        self.assertIn('SUPPLY_MINIMUM',[x['code'] for x in evaluate(self.l,{'proposal':p})['checks']])
        p['procurements'][0]['quantity']=21
        self.assertIn('SUPPLY_CAPACITY',[x['code'] for x in evaluate(self.l,{'proposal':p})['checks']])
        self.l['supply_options'][0]['unit_cost']=None
        r=evaluate(self.l,{'proposal':proposal()});self.assertIsNone(r['trial_cash_commitment']);self.assertIsNone(r['gross_profit_after_declared_trial_costs']);self.assertFalse(r['constraint_pass']);self.assertIsNone(r['scenarios'][0]['minimum_cash_before_receipts']);self.assertIsNone(r['scenarios'][0]['days'][0]['closing'])
    def test_unknown_or_duplicate_order_never_accepted(self):
        p=proposal();p['procurements'][0]['offer_id']='missing'
        with self.assertRaises(ValidationError):evaluate(self.l,{'proposal':p})
        p=proposal();p['procurements']*=2
        with self.assertRaises(ValidationError):evaluate(self.l,{'proposal':p})
    def test_purchase_budget_and_horizon_hard_constraints(self):
        self.l['max_trial_budget']='200.00'
        self.assertIn('BUDGET_EXCEEDED',[x['code'] for x in evaluate(self.l,{'proposal':proposal()})['checks']])
        self.l['supply_options'][0]['payment_days']=31
        self.assertIn('SUPPLY_OUTSIDE_HORIZON',[x['code'] for x in evaluate(self.l,{'proposal':proposal()})['checks']])
    def test_return_window_checks_do_not_fabricate_cash_refunds(self):
        p=proposal();r=evaluate(self.l,{'proposal':p});line=r['procurement']['lines'][0]
        self.assertEqual(line['return_deadline'],'2026-11-05');self.assertEqual(line['return_review_status'],'within_window_needs_check')
        p['items'][0]['sale_date']='2026-11-06';p['items'][0]['receipt_date']='2026-11-06'
        line=evaluate(self.l,{'proposal':p})['procurement']['lines'][0];self.assertEqual(line['return_review_status'],'outside_window')
        self.l['supply_options'][0]['returnable']=None
        line=evaluate(self.l,{'proposal':p})['procurement']['lines'][0];self.assertEqual(line['return_review_status'],'unknown')

    def test_historical_cover_is_labeled_not_forecast(self):
        r=analyze(self.l)['products'][1];self.assertEqual(r['coverage_days_at_past_rate'],'2.0');self.assertEqual(r['lead_time_risk_offers'],['supplier_a'])
    def test_portfolio_aggregates_orders_and_supply_capacity(self):
        p=proposal();q=deepcopy(p);q['id']='second'
        combined=combine(self.l,[{'proposal':p},{'proposal':q}]);self.assertEqual(combined['procurements'][0]['quantity'],6)
        self.l['supply_options'][0]['capacity']=5
        self.assertIn('SUPPLY_CAPACITY',[x['code'] for x in evaluate(self.l,{'proposal':combined})['checks']])
    def test_actual_procurement_cash_and_margin_are_distinct(self):
        p=proposal();f={'id':'f1','run_id':'r1','proposal_id':'restock','proposal_version':1,'synthetic':True,'period_start':'2026-10-25','period_end':'2026-10-30','source_note':'合成实际观察','fixed_spend':'0.00','procurement_paid':'280.00','procurement_expense':'10.00','hours_spent':1,'costs_confirmed':True,'observations':[],
        'items':[{'sku':'COAT_02','units_sold':5,'units_returned':0,'units_returned_resellable':0,'cash_received':'695.00','refund_paid':'0.00','variable_spend':'0.00','actual_goods_cost':'430.00'}]}
        f=validate_feedback(f,p,self.l);r=summarize_feedback(f,p,self.l);self.assertEqual(r['trial_net_cash'],'415.00');self.assertEqual(r['trial_margin_contribution'],'255.00');self.assertFalse(any('超过原计划' in q['question'] for q in r['follow_up_questions']))
        f['items'][0]['actual_goods_cost']=None;self.assertIsNone(summarize_feedback(f,p,self.l)['trial_margin_contribution'])
        f['procurement_expense']='281.00'
        with self.assertRaises(ValidationError):validate_feedback(f,p,self.l)
        f['procurement_expense']='10.00'
        for bad in (None,'bad',['bad']):
            with self.subTest(items=bad):
                broken=deepcopy(f);broken['items']=bad
                with self.assertRaises(ValidationError):validate_feedback(broken,p,self.l)
    def test_model_proposal_three_distinct_reviews_and_manual_adoption(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('禁止云调用')):r=self.report()
        d=r['result']['model_drafts'][0];self.assertEqual({x['from'] for x in d['reviews']},{'inventory','customer','cash'});self.assertEqual(len({x['reason'] for x in d['reviews']}),3)
        before=deepcopy(self.store.ledger(self.m));saved=self.store.mode_decision(self.m,self.decision(r));after=saved['ledger']
        self.assertEqual(len(after['business_models']),len(before['business_models'])+1);self.assertEqual(before['business_models'],after['business_models'][:-1]);self.assertIsNone(after['business_models'][-1]['investment']);self.assertFalse(after['business_models'][-1]['costs_confirmed']);self.assertIn('origin',after['business_models'][-1])
        again=self.report();customer=[p['proposal'] for p in again['result']['proposals'] if p['proposal']['owner']=='customer'];self.assertTrue(customer);self.assertEqual(customer[0]['model_refs'][0]['id'],after['business_models'][-1]['id'])
    def test_model_cannot_save_without_confirmation_or_with_hard_violation(self):
        r=self.report();raw=self.decision(r);raw['confirmed']=False
        with self.assertRaises(ValidationError):self.store.mode_decision(self.m,raw)
        raw=self.decision(r);raw['model']=deepcopy(r['result']['model_drafts'][0]['model']);raw['model']['investment']='99999.00'
        with self.assertRaises(ValidationError):self.store.mode_decision(self.m,raw)
        self.assertEqual(self.store.records(self.m,'mode_decision'),[])
    def test_model_rejection_keeps_ledger_and_original(self):
        r=self.report();before=self.store.ledger(self.m);raw=self.decision(r);raw['decision']='reject';self.store.mode_decision(self.m,raw)
        self.assertEqual(before,self.store.ledger(self.m));self.assertEqual(self.store.records(self.m,'mode_decision')[0]['data']['original']['id'],raw['draft_id'])
        with self.assertRaises(ValidationError):self.store.mode_decision(self.m,raw)
    def test_stale_model_context_is_rejected(self):
        r=self.report();self.store.add_knowledge(self.m,{'title':'新资料','content':'合成变化','source':'合成'})
        with self.assertRaises(ValidationError):self.store.mode_decision(self.m,self.decision(r))
    def test_model_output_cannot_forge_role_version_or_evidence(self):
        from rebirth.model_drafts import rule_draft
        run,ledger=self.store.new_run(self.m,'rules');e=self.store.event(self.m,run,'customer','tool_result',{'tool':'customer_evidence','value':{}})
        d=rule_draft(ledger,[e]);engine=Engine(self.store,RuleProvider())
        engine.validate_result(self.m,run,'customer','propose',{'model_drafts':[d]},[])
        with self.assertRaises(ValidationError):engine.validate_result(self.m,run,'cash','propose',{'model_drafts':[d]},[])
        d['evidence_ids']=['foreign']
        with self.assertRaises(ValidationError):engine.validate_result(self.m,run,'customer','propose',{'model_drafts':[d]},[])
        d['evidence_ids']=[e];d['version']=3
        with self.assertRaises(ValidationError):engine.validate_result(self.m,run,'customer','propose',{'model_drafts':[d]},[])
    def test_duplicate_model_dependencies_cannot_understate_stock(self):
        from rebirth.model_drafts import rule_draft,assess_draft
        d=rule_draft(self.l,['e1']);d['supply_requirements']*=2
        with self.assertRaises(ValidationError):assess_draft(self.l,d)

    def test_inventory_import_unknowns_preview_and_duplicate_batch(self):
        raw=self.csv();p=self.store.operating_import(self.m,raw);self.assertFalse(p['committed']);self.assertEqual(len(self.store.ledger(self.m)['products']),3)
        self.commit(raw);new=self.store.ledger(self.m)['products'][-1];self.assertEqual(new['sku'],'NEW_S');self.assertIsNone(new['unit_cost']);self.assertIsNone(new['size_complete'])
        with self.assertRaises(ValidationError):self.commit(raw)
    def test_inventory_existing_requires_explicit_replacement(self):
        raw=self.csv();raw['csv']=raw['csv'].replace('NEW_S','COAT_02')
        with self.assertRaises(ValidationError):self.commit(raw)
        raw['replace_existing']=True;self.commit(raw);p=next(p for p in self.store.ledger(self.m)['products'] if p['sku']=='COAT_02');self.assertEqual(p['stock'],3)
    def test_malformed_import_is_atomic_and_stale_preview_rejected(self):
        raw=self.csv();raw['csv']+='BAD,残缺\n';before=self.store.ledger(self.m)
        with self.assertRaises(ValidationError):self.commit(raw)
        self.assertEqual(before,self.store.ledger(self.m))
        raw=self.csv();p=self.store.operating_import(self.m,raw);updated=deepcopy(before);updated['goal']='合成修改';self.store.put_ledger(updated)
        with self.assertRaises(ValidationError):self.store.operating_import(self.m,{**raw,'confirmed':True,'preview_digest':p['preview_digest']},True)
    def test_sales_import_preserves_cash_stock_and_deduplicates(self):
        raw=self.csv('sales');raw.update(csv='id,date,sku,quantity,revenue,goods_cost,source_note\nS1,2026-10-24,COAT_02,4,556.00,,合成收银\n',confirm_sales_window=True)
        self.commit(raw);l=self.store.ledger(self.m);p=next(p for p in l['products'] if p['sku']=='COAT_02');self.assertEqual(p['sales_30d'],4);self.assertEqual(p['stock'],2);self.assertEqual(l['cash_balance'],self.l['cash_balance']);self.assertIsNone(l['sales_records'][0]['goods_cost'])
        raw['source_note']='尝试复用单号'
        with self.assertRaises(ValidationError):self.commit(raw)
    def test_sales_incomplete_or_future_window_is_not_zeroed(self):
        raw={'kind':'sales','csv':'id,date,sku,quantity,revenue,goods_cost,source_note\nS1,2026-10-26,COAT_02,1,139.00,80.00,合成\n','source_note':'合成','confirm_sales_window':False}
        with self.assertRaises(ValidationError):self.commit(raw)
        raw['confirm_sales_window']=True
        with self.assertRaises(ValidationError):self.commit(raw)
    def test_reference_library_sources_scope_and_retrieval(self):
        refs=[d for d in BUILTINS if d.get('kind')=='primary_source_summary'];self.assertEqual(len(refs),6)
        for d in refs:self.assertTrue(d['url'].startswith('https://'));self.assertTrue(d['scope']);self.assertEqual(d['checked_on'],'2026-10-26')
        self.assertTrue(any(d.get('url') for d in search(BUILTINS,'供应商 交付 起订')['matches']))

class CompletionApiTests(unittest.TestCase):
    request=test_core.ApiTests.request
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'api.sqlite3');self.handler=make_handler(self.store,'missing.json');self.l=fixture();self.m=self.l['merchant_id'];self.store.put_ledger(self.l)
    def tearDown(self):self.tmp.cleanup()
    def test_new_asset_and_api_preview_rejection(self):
        self.assertTrue(self.request('/completion.js',raw=True)[1]);self.assertIn('inventory',self.request('/api/operating-templates')['templates'])
        root='/api/merchants/'+self.m
        self.request(root+'/supply-options',{'offers':self.l['supply_options'],'source_note':'合成API确认'})
        self.assertEqual(len(self.request(root+'/workbench')['supply']['products']),3)
        with self.assertRaises(urllib.error.HTTPError):self.request(root+'/operating-import',{'kind':'sales','csv':'bad'})
        with self.assertRaises(urllib.error.HTTPError):self.request(root+'/mode-decision',{'run_id':'foreign'})

if __name__=='__main__':unittest.main()
