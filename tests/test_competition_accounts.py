import unittest
import test_registration as registration

class CompetitionAccountsTest(unittest.TestCase):
    call=registration.RegistrationTest.call
    signup=registration.RegistrationTest.signup
    identity=registration.RegistrationTest.identity
    tearDown=registration.RegistrationTest.tearDown
    def setUp(self):
        registration.RegistrationTest.setUp(self);self.gateway.first_admin=True
    def test_only_first_registration_becomes_admin(self):
        a=self.identity(self.signup('owner'));b=self.identity(self.signup('member'))
        self.assertEqual(self.call('/api/session',cookie=a[0])['body']['user']['role'],'admin')
        self.assertEqual(self.call('/api/session',cookie=b[0])['body']['user']['role'],'member')
        self.assertEqual(self.call('/api/admin/users',cookie=b[0],account=b[1])['status'],403)
        rows=self.call('/api/admin/users',cookie=a[0],account=a[1])['body']['users']
        self.assertEqual(len(rows),2);self.assertNotIn('password',str(rows));self.assertNotIn('salt',str(rows))
    def test_disable_revokes_sessions_and_enable_preserves_records(self):
        a=self.identity(self.signup('owner'));b=self.identity(self.signup('member'))
        self.assertEqual(self.call('/api/admin/status',dict(id=b[1],disabled=True),cookie=a[0],account=a[1])['status'],200)
        self.assertEqual(self.call('/api/session',cookie=b[0])['status'],401)
        self.assertEqual(self.call('/api/login',dict(username='member',password='synthetic-register-password'))['status'],401)
        self.assertEqual(self.call('/api/admin/status',dict(id=a[1],disabled=True),cookie=a[0],account=a[1])['status'],400)
        self.assertEqual(self.call('/api/admin/status',dict(id=b[1],disabled=False),cookie=a[0],account=a[1])['status'],200)
        self.assertEqual(self.call('/api/login',dict(username='member',password='synthetic-register-password'))['status'],200)
    def test_password_requires_old_password_and_revokes_all_sessions(self):
        a=self.identity(self.signup('owner'));new='a-new-synthetic-password'
        body=dict(current='wrong',password=new,password_confirm=new)
        self.assertEqual(self.call('/api/account/password',body,cookie=a[0],account=a[1])['status'],400)
        body['current']='synthetic-register-password'
        self.assertEqual(self.call('/api/account/password',body,cookie=a[0],account=a[1])['status'],200)
        self.assertEqual(self.call('/api/session',cookie=a[0])['status'],401)
        self.assertEqual(self.call('/api/login',dict(username='owner',password=new))['status'],200)
    def test_cloud_requires_explicit_gateway_opt_in(self):
        a=self.identity(self.signup('owner'))
        self.assertFalse(self.gateway.allow_cloud)
        self.assertEqual(self.call('/api/runs',dict(mode='agentarts',merchant_id='try_a',cloud_data_consent=True),cookie=a[0],account=a[1])['status'],403)

if __name__=='__main__':unittest.main()
