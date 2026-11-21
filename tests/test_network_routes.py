import unittest,tempfile,json
from rebirth.hosted import Gateway
import test_registration as reg
class NetworkRoutesTest(unittest.TestCase):
 call=reg.RegistrationTest.call
 signup=reg.RegistrationTest.signup
 identity=reg.RegistrationTest.identity
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.gateway=Gateway(self.temp.name,'https://test.example.com',registration_open=True,first_admin=True);base=self.gateway.wsgi()
  def app(env,start):
   if '?' in env['PATH_INFO']:env['PATH_INFO'],env['QUERY_STRING']=env['PATH_INFO'].split('?',1)
   return base(env,start)
  self.app=app
 def tearDown(self):self.temp.cleanup()
 def test_routes_privacy_and_mutual_help(self):
  a=self.identity(self.signup('alice'));b=self.identity(self.signup('bob'));c=self.identity(self.signup('carol'))
  def send(identity,body):return self.call('/api/community',body,cookie=identity[0],account=identity[1])
  def get(identity,q):return self.call('/api/community?'+q,cookie=identity[0],account=identity[1])
  self.assertEqual(self.call('/api/community')['status'],401)
  self.assertEqual(send(a,{'op':'profile','nickname':'小林','bio':'经营小店','avatar':''})['status'],200)
  p=send(a,{'op':'publish','title':'库存积压','body':'求小批量试做建议','category':'库存周转'})['body']['id']
  r=send(b,{'op':'reply','post':p,'body':'先盘点，留足必要现金再试'})['body']['id']
  self.assertEqual(get(c,'view=post&id='+p)['body']['replies'][0]['author']['nickname'],'小店经营者')
  self.assertEqual(send(c,{'op':'solve','post':p,'solved':True})['status'],400)
  send(a,{'op':'helpful','post':p,'reply':r});send(a,{'op':'solve','post':p,'solved':True})
  send(b,{'op':'message','peer':a[1],'body':'私下交流内容'})
  self.assertEqual(get(c,'view=inbox')['body']['conversations'],[])
  self.assertEqual(len(get(a,'view=thread&peer='+b[1])['body']['messages']),1)
  send(a,{'op':'block','target':b[1],'blocked':True})
  self.assertEqual(send(b,{'op':'message','peer':a[1],'body':'禁止继续'})['status'],400)
  self.assertEqual(self.call('/api/community',{'op':'publish'},cookie=a[0],account=b[1])['status'],409)
  self.assertEqual(self.call('/api/community',{'op':'publish'},cookie=a[0],account=a[1],origin='https://other.example')['status'],403)
  html=self.call('/account',cookie=a[0])['body'];self.assertIn('编辑资料',html);self.assertIn('/community',html)
if __name__=='__main__':unittest.main()
