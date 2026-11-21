from io import BytesIO
from pathlib import Path
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from rebirth.hosted import Gateway


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.gateway=Gateway(self.temp.name,'https://test.example.com',registration_open=True,demo_only=True)
        self.app=self.gateway.wsgi()

    def tearDown(self):self.temp.cleanup()

    def call(self,path,body=None,cookie='',account='',origin='https://test.example.com'):
        raw=json.dumps(body).encode() if body is not None else b''
        env={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'HTTP_HOST':'test.example.com','HTTP_ORIGIN':origin,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':BytesIO(raw),'HTTP_COOKIE':cookie,'HTTP_X_REBIRTH_ACCOUNT':account}
        response={};payload=b''.join(self.app(env,lambda status,headers:response.update(status=int(status.split()[0]),headers=dict(headers))))
        response['body']=json.loads(payload) if response['headers'].get('Content-Type','').startswith('application/json') else payload.decode()
        return response

    def signup(self,name):
        return self.call('/api/register',dict(username=name,password='synthetic-register-password',password_confirm='synthetic-register-password',test_consent=True))

    def identity(self,response):
        cookie=response['headers']['Set-Cookie'].split(';')[0]
        return cookie,self.call('/api/session',cookie=cookie)['body']['user']['id']

    def test_register_automatically_logs_in_and_creates_separate_practice_shops(self):
        settings=self.call('/api/public-settings');self.assertEqual(settings['status'],200);self.assertTrue(settings['body']['registration_open'])
        a=self.signup('student_a');self.assertEqual(a['status'],200)
        cookie,uid=self.identity(a)
        shops=self.call('/api/merchants',cookie=cookie,account=uid)
        self.assertEqual(len(shops['body']['merchants']),2)
        self.assertTrue(all(x['synthetic'] for x in shops['body']['merchants']))
        self.assertEqual(self.call('/api/merchants/try_a',cookie=cookie,account=uid)['status'],200)
        self.assertIn('Secure',a['headers']['Set-Cookie']);self.assertNotIn('password',json.dumps(a['body']))

    def test_two_registered_accounts_cannot_read_each_others_edits(self):
        a=self.identity(self.signup('alice'));b=self.identity(self.signup('bob'))
        ledger=self.call('/api/merchants/try_a',cookie=a[0],account=a[1])['body'];ledger['name']='Alice private edit'
        self.assertEqual(self.call('/api/ledgers',ledger,cookie=a[0],account=a[1])['status'],201)
        self.assertNotEqual(self.call('/api/merchants/try_a',cookie=b[0],account=b[1])['body']['name'],'Alice private edit')
        self.assertEqual(self.call('/api/merchants/try_a',cookie=b[0],account=a[1])['status'],409)

    def test_invalid_confirmation_or_consent_does_not_create_account(self):
        for changes in [dict(password_confirm='different'),dict(test_consent=False),dict(password='short',password_confirm='short')]:
            body=dict(username='student',password='synthetic-register-password',password_confirm='synthetic-register-password',test_consent=True);body.update(changes)
            self.assertEqual(self.call('/api/register',body)['status'],400)
        with self.gateway.accounts.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)

    def test_registration_can_be_closed_and_cross_site_creation_is_rejected(self):
        body=dict(username='student',password='synthetic-register-password',password_confirm='synthetic-register-password',test_consent=True)
        self.assertEqual(self.call('/api/register',body,origin='https://evil.example')['status'],403)
        self.gateway.registration_open=False
        self.assertEqual(self.call('/api/register',body)['status'],403)

    def test_duplicate_name_case_and_maximum_accounts(self):
        self.gateway.registration_limit=1
        self.assertEqual(self.signup('student')['status'],200)
        self.assertEqual(self.signup('STUDENT')['status'],400)
        self.assertEqual(self.signup('another_student')['status'],400)
        with self.gateway.accounts.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)

    def test_registration_capacity_is_atomic(self):
        def create(name):
            try:return self.gateway.accounts.create(name,'synthetic-concurrent-password',limit=1)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(create,['first','second']))
        self.assertEqual(sum(x is not None for x in results),1)

    def test_demo_station_rejects_real_ledger_and_never_enables_cloud(self):
        cookie,uid=self.identity(self.signup('student'))
        ledger=self.call('/api/merchants/try_a',cookie=cookie,account=uid)['body'];ledger['synthetic']=False
        self.assertEqual(self.call('/api/ledgers',ledger,cookie=cookie,account=uid)['status'],400)
        self.assertEqual(self.call('/api/runs',dict(mode='agentarts',merchant_id='try_a',cloud_data_consent=True),cookie=cookie,account=uid)['status'],403)

    def test_restart_retains_login_and_practice_edits(self):
        cookie,uid=self.identity(self.signup('student'))
        ledger=self.call('/api/merchants/try_a',cookie=cookie,account=uid)['body'];ledger['goal']='synthetic saved goal'
        self.call('/api/ledgers',ledger,cookie=cookie,account=uid)
        self.gateway=Gateway(self.temp.name,'https://test.example.com',registration_open=True,demo_only=True);self.app=self.gateway.wsgi()
        self.assertEqual(self.call('/api/merchants/try_a',cookie=cookie,account=uid)['body']['goal'],'synthetic saved goal')

    def test_registration_rate_limit_covers_failed_attempts(self):
        self.signup('student')
        for _ in range(9):self.signup('student')
        self.assertEqual(self.signup('student')['status'],429)


if __name__=='__main__':unittest.main()
