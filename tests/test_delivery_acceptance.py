import shutil,tempfile,unittest
from pathlib import Path
from rebirth.delivery import check_files
ROOT=Path(__file__).resolve().parents[1]
class DeliveryChecks(unittest.TestCase):
 def test_current_assets_and_contracts_exist(self):
  result=check_files(ROOT);self.assertTrue(result['passed'],result);self.assertEqual(result['network_calls'],0)
 def test_incomplete_archive_names_missing_contract_and_asset(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'dist').mkdir();(root/'dist/index.html').write_text('<script src="/core.js"></script>')
   result=check_files(root);self.assertFalse(result['passed']);self.assertIn('config/contracts.json',result['missing']);self.assertIn('dist/core.js',result['missing'])
 def test_broken_contract_is_rejected_without_contents(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'config').mkdir();(root/'config/contracts.json').write_text('not json')
   result=check_files(root);self.assertEqual(result['invalid'],['config/contracts.json']);self.assertNotIn('not json',str(result))
