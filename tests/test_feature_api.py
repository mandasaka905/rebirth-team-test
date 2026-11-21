import json
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
import test_core
from rebirth.server import make_handler
from rebirth.store import Store


class FeatureApiTests(unittest.TestCase):
    request = test_core.ApiTests.request

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"features.sqlite3")
        self.handler=make_handler(self.store,"missing.json")
        self.request('/api/ledgers',test_core.ledger())

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_assets_are_allowed_and_credentials_not_served(self):
        for asset in ('/features.js','/features.css'):
            head,body=self.request(asset,raw=True)
            self.assertIn(b'Content-Security-Policy',head)
            self.assertTrue(body)
        with self.assertRaises(urllib.error.HTTPError):self.request('/config.local.json')

    def test_period_and_knowledge_api_are_persistent(self):
        self.request('/api/merchants/sample_clothing/periods',{'start':'2026-10-01','end':'2026-10-20','revenue':'100.00','source_note':'合成API记录'})
        self.assertEqual(len(self.request('/api/merchants/sample_clothing/diagnostics')['periods']),1)
        self.request('/api/merchants/sample_clothing/knowledge',{'title':'绛紫资料','content':'绛紫词条为合成测试','source':'合成'})
        found=self.request('/api/merchants/sample_clothing/knowledge-search',{'query':'绛紫'})
        self.assertEqual(found['matches'][0]['title'],'绛紫资料')

    def test_social_api_routes_persist_support_and_report_local_only(self):
        from datetime import date
        today=date.today().isoformat()
        base='/api/merchants/sample_clothing/'
        created=self.request(base+'support-request',dict(category='digital',problem='合成不会使用',goal='合成先学一个操作',availability='合成周末',requested_on=today,next_on=today,local_consent=True,aggregate_consent=False))
        home=self.request(base+'social')
        self.assertEqual(home['cases'][0]['id'],created['id'])
        self.assertEqual(home['summary']['participating_shops'],0)
        self.assertIn('social',self.request(base+'community'))
        for asset in ('/social.js','/social.css'):
            _,body=self.request(asset,raw=True)
            self.assertTrue(body)

    def test_preflight_and_outbound_preview_have_no_credentials(self):
        value=self.request('/api/preflight')
        self.assertFalse(value['can_request_cloud'])
        preview=self.request('/api/merchants/sample_clothing/outbound-preview')
        self.assertIn('经营金额',preview['notice'])
        self.assertEqual(preview['preview']['ledger']['name'],'匿名实体小店')

    def test_legacy_cloud_endpoint_cannot_bypass_per_task_consent(self):
        self.handler=make_handler(self.store,'missing.json',allow_cloud=True)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/runs',{'merchant_id':'sample_clothing','mode':'agentarts'})
        self.assertEqual(error.exception.code,400)

    def test_complete_acceptance_fixture_can_be_imported(self):
        value=self.request('/api/acceptance-example')
        self.request('/api/ledgers',value)
        report=self.request('/api/merchants/'+value['merchant_id']+'/diagnostics')
        self.assertEqual(len(report['periods']),2)
        self.assertTrue(value['synthetic'])

    def test_export_and_import_copy_do_not_overwrite_or_import_execution_claims(self):
        bundle=self.request('/api/merchants/sample_clothing/export')
        imported=self.request('/api/merchants/local/import-copy',bundle)
        self.assertNotEqual(imported['merchant_id'],'sample_clothing')
        self.assertTrue(imported['synthetic'])
        self.assertEqual(self.request('/api/merchants/'+imported['merchant_id']+'/runs')['runs'],[])

    def test_job_polling_and_cloud_guard(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/jobs',{'merchant_id':'sample_clothing','mode':'agentarts','cloud_data_consent':True})
        job=self.request('/api/jobs',{'merchant_id':'sample_clothing','mode':'rules'})
        path='/api/merchants/sample_clothing/jobs/'+job['job_id']
        deadline=time.monotonic()+20
        value=self.request(path)
        while value['state']=='running' and time.monotonic()<deadline:
            time.sleep(.03);value=self.request(path)
        self.assertEqual(value['state'],'completed')
        self.assertEqual(value['result']['mode'],'rules')
        self.assertGreater(value['event_count'],0)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/merchants/other/jobs/'+job['job_id'])


if __name__=='__main__':unittest.main()
