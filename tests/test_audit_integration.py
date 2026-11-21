"""Cross-feature contracts: saving, provenance, time windows and combined purchasing."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from rebirth.store import Store
from rebirth.planning import combine
from rebirth.tools import evaluate,inventory
from rebirth.readiness import questions,apply_answers
from rebirth.domain import ValidationError
import hashlib,json
from test_completion import fixture,proposal

class AuditIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'audit.sqlite3');self.l=fixture();self.m=self.l['merchant_id'];self.store.put_ledger(self.l)
    def tearDown(self):self.tmp.cleanup()
    def import_sales(self):
        raw={'kind':'sales','csv':'id,date,sku,quantity,revenue,goods_cost,source_note\nAUDIT1,2026-10-24,COAT_02,4,556.00,,逐行收银小票依据\n','source_note':'销售导入批次依据','confirm_sales_window':True}
        p=self.store.operating_import(self.m,raw);self.store.operating_import(self.m,{**raw,'confirmed':True,'preview_digest':p['preview_digest']},True)
    def test_combined_orders_do_not_invent_shipping_discount(self):
        p=proposal();p['items'][0]['quantity']=2;q=deepcopy(p);q['id']='second_order'
        combined=combine(self.l,[{'proposal':p},{'proposal':q}]);r=evaluate(self.l,{'proposal':combined})
        self.assertEqual(r['trial_cash_commitment'],'560.00')
    def test_sales_import_does_not_relabel_inventory_cost_source(self):
        self.import_sales();l=self.store.ledger(self.m);old=next(p for p in self.l['products'] if p['sku']=='COAT_02');now=next(p for p in l['products'] if p['sku']=='COAT_02')
        self.assertEqual(now['source_id'],old['source_id']);sid=l['field_sources']['products/COAT_02/sales_30d'];self.assertIn('逐行收银小票依据',l['sources'][sid])
    def test_general_edit_keeps_sections_not_rendered_by_old_editor(self):
        self.import_sales();l=self.store.ledger(self.m)
        basic={k:deepcopy(v) for k,v in l.items() if k in fixture() and k!='supply_options'};basic['goal']='仅修改店铺目标'
        self.store.put_ledger(basic);saved=self.store.ledger(self.m)
        self.assertEqual(saved.get('supply_options'),l['supply_options']);self.assertEqual(saved.get('sales_records'),l['sales_records'])
    def test_rolling_date_requires_rechecking_imported_sales_window(self):
        self.import_sales();l=self.store.ledger(self.m);l['as_of']='2026-10-26';self.store.put_ledger(l)
        pending=questions(self.store.ledger(self.m))['questions']
        self.assertTrue(any(q['path']==['products','COAT_02','sales_30d'] for q in pending))

    def test_original_supplier_and_sales_sources_survive_inventory_replacement(self):
        self.import_sales();l=self.store.ledger(self.m)
        raw={'kind':'inventory','csv':'sku,name,stock,sales_30d,received_on,unit_cost,unit_price,size_complete,source_note\nCOAT_02,外套,3,2,2026-06-01,82.00,139.00,true,新采购单核对\n','source_note':'盘点替换','replace_existing':True}
        p=self.store.operating_import(self.m,raw);self.store.operating_import(self.m,{**raw,'confirmed':True,'preview_digest':p['preview_digest']},True)
        l=self.store.ledger(self.m);row=next(p for p in inventory(l,{})['products'] if p['sku']=='COAT_02')
        self.assertIn('新采购单核对',l['sources'][row['field_sources']['unit_cost']]);self.assertIn('stock_fixture',l['sources']);self.assertEqual(len(l['sales_records']),1)
    def test_stale_editor_cannot_overwrite_new_import(self):
        before=self.store.ledger(self.m);token=hashlib.sha256(json.dumps(before,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.import_sales();edited=deepcopy(before);edited['goal']='旧页面修改';edited['_expected_digest']=token
        with self.assertRaises(ValidationError):self.store.put_ledger(edited)
        self.assertEqual(len(self.store.ledger(self.m)['sales_records']),1)
    def test_current_editor_digest_accepts_unicode_and_keeps_provenance(self):
        before=self.store.ledger(self.m);edited=deepcopy(before);edited['goal']='中文目标变更'
        edited['_expected_digest']=hashlib.sha256(json.dumps(before,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        saved=self.store.put_ledger(edited);self.assertEqual(saved['goal'],'中文目标变更');self.assertNotIn('_expected_digest',saved)
    def test_current_window_can_be_reconfirmed_without_faking_zero(self):
        self.import_sales();l=self.store.ledger(self.m);l['as_of']='2026-10-26';self.store.put_ledger(l)
        l=self.store.ledger(self.m);q=next(q for q in questions(l)['questions'] if q['id']=='sales_window_COAT_02')
        self.assertEqual(q['value_type'],'integer')
        self.assertIn('SALES_WINDOW_STALE',[c['code'] for c in evaluate(l,{'proposal':{**proposal(),'spend_date':'2026-10-26','procurements':[]}})['checks']])
        updated,audit=apply_answers(l,[{'question_id':q['id'],'value':4,'source_note':'核对当前30天，仍为4件'}]);self.store.put_ledger(updated)
        self.assertFalse(any(q['id']=='sales_window_COAT_02' for q in questions(updated)['questions']))
        self.assertEqual(updated['sales_windows']['COAT_02']['end'],'2026-10-26');self.assertEqual(updated['products'][1]['sales_30d'],4)
    def test_separate_skus_keep_their_own_sales_windows(self):
        self.import_sales();l=self.store.ledger(self.m);l['as_of']='2026-10-26';self.store.put_ledger(l)
        raw={'kind':'sales','csv':'id,date,sku,quantity,revenue,goods_cost,source_note\nA2,2026-10-25,KNIT_03,1,119.00,70.00,针织小票\n','source_note':'第二商品','confirm_sales_window':True}
        p=self.store.operating_import(self.m,raw);self.store.operating_import(self.m,{**raw,'confirmed':True,'preview_digest':p['preview_digest']},True)
        l=self.store.ledger(self.m);self.assertEqual(l['sales_windows']['COAT_02']['end'],'2026-10-25');self.assertEqual(l['sales_windows']['KNIT_03']['end'],'2026-10-26')
    def test_zero_batches_and_minimum_per_batch_are_not_bypassed(self):
        p=proposal();p['procurements'][0]['shipping_batches']=0
        with self.assertRaises(ValidationError):evaluate(self.l,{'proposal':p})
        p['procurements'][0]['shipping_batches']=2
        self.assertIn('SUPPLY_MINIMUM',[c['code'] for c in evaluate(self.l,{'proposal':p})['checks']])
    def test_purchased_but_unsold_goods_are_visible_in_stock_path(self):
        p=proposal();p['items']=[];r=evaluate(self.l,{'proposal':p})
        row=r['procurement']['stock_path'][0];self.assertEqual(row['ordered'],3);self.assertEqual(row['declared_sold'],0);self.assertEqual(row['remaining_on_delivery'],5)

if __name__=='__main__':unittest.main()
