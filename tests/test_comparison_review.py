import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'testing/public-retail'))
from review_comparison_pair import digest, review_arm


class ComparisonReviewTests(unittest.TestCase):
    def fixture(self, folder):
        ledger={'merchant_id':'synthetic'}
        manifest={'ledger_sha256':digest(ledger),'budget_per_arm':{'max_calls':64}}
        metrics={'manifest_sha256':digest(manifest),'source_unchanged':True,
            'usage':{'calls':3},'resumptions':0,'error_type':'ProviderError',
            'elapsed_seconds':12,'token_usage':None,'cost_cny':None,
            'agent_output_rejections':0,'tool_errors':0}
        report={'ledger_snapshot':ledger,'status':'failed','events':[],
            'result':{'status':'failed','error_message':'响应中断','proposals':[{'partial':True}]}}
        (folder/'metrics.json').write_text(json.dumps(metrics),encoding='utf-8')
        (folder/'report.json').write_text(json.dumps(report),encoding='utf-8')
        return manifest,report

    def test_failed_arm_has_no_final_quality_score_or_zero_risk_success(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            manifest,_=self.fixture(folder)
            value=review_arm(folder,manifest,{})
            self.assertIsNone(value['final_proposals'])
            self.assertIsNone(value['material_revisions'])
            self.assertEqual(value['error_type'],'ProviderError')
            self.assertEqual(value['failure_message'],'响应中断')
            self.assertIsNone(value['cost_cny'])

    def test_mismatched_inputs_rejected_before_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            manifest,report=self.fixture(folder)
            report['ledger_snapshot']['merchant_id']='different'
            (folder/'report.json').write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'input differs'):
                review_arm(folder,manifest,{})


if __name__=='__main__':unittest.main()
