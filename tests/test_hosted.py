import http.client
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from io import BytesIO
from http.server import ThreadingHTTPServer

from rebirth.hosted import Gateway


class HostedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.gateway=Gateway(cls.tmp.name,'http://127.0.0.1:0',local_preview=True)
        cls.a=cls.gateway.accounts.create('test_a','synthetic-test-password-a')
        cls.b=cls.gateway.accounts.create('test_b','synthetic-test-password-b')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),cls.gateway.handler())
        cls.port=cls.server.server_port;cls.gateway.host=f'127.0.0.1:{cls.port}';cls.gateway.origin='http://'+cls.gateway.host
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        for handler in cls.gateway.handlers.values():
            # No model calls in this test; all executors complete on their own.
            pass
        cls.tmp.cleanup()

    def request(self,path,body=None,cookie=None,account=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        hdr={'Host':self.gateway.host}
        if body is not None:hdr.update({'Origin':self.gateway.origin,'Content-Type':'application/json'})
        if cookie:hdr['Cookie']=cookie
        if account:hdr['X-Rebirth-Account']=account
        hdr.update(headers or {})
        conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,hdr)
        response=conn.getresponse();raw=response.read();status=response.status;out_headers=dict(response.getheaders());conn.close()
        value=json.loads(raw) if 'application/json' in out_headers.get('Content-Type','') else raw.decode('utf-8-sig')
        return status,value,out_headers

    def login(self,name='test_a',password='synthetic-test-password-a'):
        status,_,headers=self.request('/api/login',{'username':name,'password':password});self.assertEqual(status,200)
        return headers['Set-Cookie'].split(';')[0]

    def test_no_unauthenticated_business_access(self):
        for path in ['/api/merchants','/api/merchants/x/export','/api/tools','/api/preflight']:
            self.assertEqual(self.request(path)[0],401,path)
        status,_,headers=self.request('/workbench');self.assertEqual(status,303);self.assertEqual(headers['Location'],'/login')
        for path in ['/config/hosted-no-cloud.json','/../accounts.sqlite3','/shops','/api/register']:
            self.assertIn(self.request(path)[0],(401,404))

    def test_same_account_shares_records_across_connections_but_other_account_cannot(self):
        a=self.login();b=self.login('test_b','synthetic-test-password-b')
        status,example,_=self.request('/api/example',cookie=a,account=self.a);self.assertEqual(status,200)
        example['merchant_id']='shared_id';example['name']='Private shop A'
        self.assertEqual(self.request('/api/ledgers',example,a,self.a)[0],201)
        self.assertEqual(self.request('/api/merchants/shared_id',cookie=a,account=self.a)[1]['name'],'Private shop A')
        self.assertEqual(self.request('/api/merchants/shared_id',cookie=b,account=self.b)[0],404)
        self.assertNotIn('Private shop A',json.dumps(self.request('/api/merchants',cookie=b,account=self.b)[1]))
        example['name']='Private shop B';self.assertEqual(self.request('/api/ledgers',example,b,self.b)[0],201)
        self.assertEqual(self.request('/api/merchants/shared_id',cookie=a,account=self.a)[1]['name'],'Private shop A')
        self.assertEqual(self.request('/api/merchants/shared_id',cookie=b,account=self.b)[1]['name'],'Private shop B')

    def test_old_tab_cannot_write_into_switched_account(self):
        b=self.login('test_b','synthetic-test-password-b')
        status,body,_=self.request('/api/ledgers',{'merchant_id':'bad'},b,self.a)
        self.assertEqual(status,409);self.assertTrue(body['account_changed'])
        self.assertEqual(self.request('/api/merchants',cookie=b)[0],409)

    def test_boundary_checks_reject_cross_site_missing_origin_and_spoofed_host(self):
        a=self.login()
        self.assertEqual(self.request('/api/logout',{},a,headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/logout',{},a,headers={'Origin':''})[0],403)
        self.assertEqual(self.request('/api/session',cookie=a,headers={'Host':'evil.example','X-Forwarded-Host':self.gateway.host})[0],403)
        self.assertEqual(self.request('/api/session',cookie=a,headers={'Sec-Fetch-Site':'cross-site'})[0],403)

    def test_logout_invalidates_only_that_device_session(self):
        a=self.login();other=self.login()
        status,_,headers=self.request('/api/logout',{},a);self.assertEqual(status,200);self.assertIn('Max-Age=0',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/session',cookie=a)[0],401)
        self.assertEqual(self.request('/api/session',cookie=other)[0],200)

    def test_persistent_sessions_and_password_reset_revocation(self):
        self.gateway.accounts.create('reset_test','synthetic-reset-password')
        cookie=self.login('reset_test','synthetic-reset-password');token=cookie.split('=',1)[1]
        from rebirth.accounts import Accounts
        reopened=Accounts(self.tmp.name);self.assertIsNotNone(reopened.user(token))
        reopened.reset_password('reset_test','new-synthetic-reset-password')
        self.assertIsNone(reopened.user(token))

    def test_invalid_logins_limited_and_do_not_reveal_account_existence(self):
        responses=[self.request('/api/login',{'username':'unknown_user','password':'wrong'}) for _ in range(11)]
        self.assertEqual(responses[0][0],401);self.assertEqual(responses[0][1]['error'],'账号或密码不正确')
        self.assertEqual(responses[-1][0],429)

    def test_workbench_initializes_account_before_first_application_request(self):
        a=self.login();status,html,_=self.request('/workbench',cookie=a)
        self.assertEqual(status,200);self.assertEqual(html.count('src="/auth-client.js"'),1)
        self.assertLess(html.index('/auth-client.js'),html.index('/app.js'))
        self.assertIn(self.a,html);self.assertNotIn(self.b,html)
        self.assertNotIn('password',json.dumps(self.request('/api/session',cookie=a)[1]))

    def test_backup_keeps_account_data_but_cannot_revive_login_sessions(self):
        from rebirth.hosted_backup import backup_all
        from rebirth.accounts import Accounts
        a=self.login();token=a.split('=',1)[1]
        with tempfile.TemporaryDirectory() as parent:
            out=Path(parent)/'snapshot';result=backup_all(self.tmp.name,out)
            self.assertTrue(result['sessions_revoked_in_backup'])
            restored=Accounts(out);self.assertIsNone(restored.user(token))
            self.assertIsNotNone(self.gateway.accounts.user(token))
            with restored.connect() as db:self.assertIsNotNone(db.execute('SELECT id FROM users WHERE id=?',(self.a,)).fetchone())
        with self.assertRaises(ValueError):backup_all(self.tmp.name,Path(self.tmp.name)/'nested')

    def test_cloud_call_remains_disabled_for_signed_in_account(self):
        a=self.login();status,_,_=self.request('/api/runs',{'mode':'agentarts','merchant_id':'x','cloud_data_consent':True},a,self.a)
        self.assertEqual(status,403)

    def test_production_requires_https_and_host_scoped_secure_cookie(self):
        with self.assertRaises(ValueError):Gateway(self.tmp.name,'http://example.com')
        with self.assertRaises(ValueError):Gateway(self.tmp.name,'https://example.com/path')
        self.assertEqual(Gateway(self.tmp.name,'https://example.com').cookie_name,'__Host-rebirth')

    def test_production_wsgi_login_cookie_and_private_api(self):
        gateway=Gateway(self.tmp.name,'https://shop.example.com')
        app=gateway.wsgi()
        def call(path,body=None,cookie='',account=''):
            raw=json.dumps(body).encode() if body is not None else b''
            environ={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'HTTP_HOST':'shop.example.com','HTTP_ORIGIN':'https://shop.example.com','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':BytesIO(raw),'HTTP_COOKIE':cookie,'HTTP_X_REBIRTH_ACCOUNT':account}
            result={}
            payload=b''.join(app(environ,lambda status,headers:result.update(status=status,headers=dict(headers))))
            return result,json.loads(payload)
        result,_=call('/api/login',{'username':'test_a','password':'synthetic-test-password-a'})
        self.assertTrue(result['status'].startswith('200'))
        cookie=result['headers']['Set-Cookie'];self.assertIn('__Host-rebirth=',cookie);self.assertIn('; Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertTrue(call('/api/merchants')[0]['status'].startswith('401'))
        self.assertTrue(call('/api/merchants',cookie=cookie.split(';')[0],account=self.a)[0]['status'].startswith('200'))


if __name__=='__main__':unittest.main()
