import unittest,tempfile,json
from pathlib import Path
from rebirth.hosted import Gateway
from rebirth.operating_imports import parse
import test_registration as reg
ROOT=Path(__file__).resolve().parents[1]
class MerchantEntryTests(unittest.TestCase):
 call=reg.RegistrationTest.call
 signup=reg.RegistrationTest.signup
 identity=reg.RegistrationTest.identity
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.gateway=Gateway(self.temp.name,'https://test.example.com',registration_open=True,first_admin=True);self.app=self.gateway.wsgi()
 def tearDown(self):self.temp.cleanup()
 def test_new_account_has_no_fake_shop_and_real_records_are_private(self):
  a=self.identity(self.signup('owner'));b=self.identity(self.signup('another'))
  self.assertEqual(self.call('/api/merchants',cookie=a[0],account=a[1])['body']['merchants'],[])
  l=json.loads((ROOT/'examples/merchant.synthetic.json').read_text(encoding='utf-8'));l.update(merchant_id='actual_entry_test',name='接口验收专用店',synthetic=False,products=[])
  l['completeness']['inventory_complete']=False
  self.assertEqual(self.call('/api/ledgers',l,cookie=a[0],account=a[1])['status'],201)
  self.assertFalse(self.call('/api/merchants/actual_entry_test',cookie=a[0],account=a[1])['body']['synthetic'])
  self.assertEqual(self.call('/api/merchants',cookie=b[0],account=b[1])['body']['merchants'],[])
  csv='商品编号,商品名称,库存数量,近30天销量,入库日期,采购单价,销售单价,尺码齐全\nA001,验收专用商品,7,2,2026-10-01,8.50,12.00,是\n'
  raw=dict(kind='inventory',csv=csv,source_note='隔离验收资料，不是真实经营记录',replace_existing=False,confirm_sales_window=False)
  route='/api/merchants/actual_entry_test/'
  preview=self.call(route+'operating-preview',raw,cookie=a[0],account=a[1]);self.assertEqual(preview['status'],201,preview)
  saved=self.call(route+'operating-import',{**raw,'confirmed':True,'preview_digest':preview['body']['preview_digest']},cookie=a[0],account=a[1]);self.assertEqual(saved['status'],201,saved)
  l=self.call(route.rstrip('/'),cookie=a[0],account=a[1])['body'];self.assertEqual(l['products'][0]['stock'],7);self.assertFalse(l['synthetic'])
 def test_cover_is_public_and_registration_is_after_workbench_entry(self):
  r=self.call('/');self.assertEqual(r['status'],200)
  for section in ['top','story','journey','collaboration','begin']:self.assertIn('id="'+section+'"',r['body'])
  gate=self.call('/workbench');self.assertEqual(gate['status'],303);self.assertEqual(gate['headers']['Location'],'/register')
 def test_chinese_cash_columns_preserve_money_and_direction(self):
  from rebirth.accounting import parse_csv
  text='记录编号,日期,收支方向,款项类型,金额,原始单据号,关联采购编号,来源说明\nC01,2026-11-02,支出,房租,800.25,SRC-01,,隔离验收\n'
  row=parse_csv(text,'cash_entries')[0]
  self.assertEqual(row['direction'],'out');self.assertEqual(row['category'],'rent');self.assertEqual(row['amount'],'800.25')
 def test_column_alias_duplicates_are_rejected(self):
  from rebirth.domain import ValidationError
  with self.assertRaises(ValidationError):parse('sku,商品编号\nA001,A002\n','inventory')
if __name__=='__main__':unittest.main()

