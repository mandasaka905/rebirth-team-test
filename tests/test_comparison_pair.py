import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]/'testing/public-retail'
sys.path.insert(0,str(HERE))
import run_comparison_pair as pair


class ComparisonGuardTests(unittest.TestCase):
    def test_shared_endpoint_really_matches_without_mutating_production(self):
        config={'agents':{r:{'url':r,'token_env':r+'_KEY'} for r in pair.ROLES},'allowed_hosts':['example.invalid']}
        frozen=json.dumps(config,sort_keys=True)
        shared=pair.shared_config(config)
        self.assertTrue(all(x==shared['agents']['coordinator'] for x in shared['agents'].values()))
        self.assertEqual(json.dumps(config,sort_keys=True),frozen)
        shared['agents']['cash']['url']='changed'
        self.assertEqual(shared['agents']['inventory']['url'],'coordinator')

    def test_code_changes_stop_before_creating_arm_or_calling_models(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pair,'source_hashes',return_value={'file':'new'}):
            root=Path(temp)
            with self.assertRaisesRegex(ValueError,'源码已改变'):
                pair.execute_arm(root,'single',{},root/'none',{'source_hashes':{'file':'old'}},cloud=True)
            self.assertFalse((root/'single').exists())

    def test_case_changes_stop_before_calling_models(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pair,'source_hashes',return_value={}):
            root=Path(temp)
            with self.assertRaisesRegex(ValueError,'案例已改变'):
                pair.execute_arm(root,'multi',{'id':'changed'},root/'none',
                    {'source_hashes':{},'case_sha256':pair.digest({'id':'original'})},cloud=True)
            self.assertFalse((root/'multi').exists())

    def test_single_identity_gets_specialist_knowledge_and_self_review(self):
        prompt=pair.integrated_instruction()
        self.assertIn('同一个综合经营分析智能体',prompt)
        for text in ('商品与供应链','现金流','customer_retention','costs_confirmed','自行','自查'):
            self.assertIn(text,prompt)
        self.assertIn('单个tool或final',prompt)

    def test_cloud_requires_explicit_paid_flag_before_any_directory_creation(self):
        with patch.object(sys,'argv',['pair','--cloud']), patch.object(pair.Path,'mkdir') as mkdir:
            with self.assertRaises(SystemExit) as caught:pair.main()
            self.assertEqual(caught.exception.code,2)
            mkdir.assert_not_called()


if __name__=='__main__':unittest.main()
