import unittest,tempfile,base64,io
from rebirth.accounts import Accounts
from rebirth.merchant_network import Community
class NetworkTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.a=Accounts(self.tmp.name);self.c=Community(self.a)
  self.users=[{'id':self.a.create('owner'+str(i),'long-test-password'),'role':'member'} for i in range(3)]
 def tearDown(self):self.tmp.cleanup()
 def test_profile_and_avatar(self):
  from PIL import Image
  stream=io.BytesIO();Image.new('RGB',(30,30),'red').save(stream,'PNG')
  self.c.post(self.users[0],{'op':'profile','nickname':'街角老板','bio':'杂货','avatar':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
  p=self.c.profile(self.users[0]['id']);self.assertEqual(p['nickname'],'街角老板');self.assertTrue(p['avatar'].startswith('data:image/jpeg'));self.assertNotIn('name',p)
  with self.assertRaises(ValueError):self.c.post(self.users[0],{'op':'profile','nickname':'张','avatar':'data:image/svg+xml;base64,xxx'})
 def test_help_close_and_ownership(self):
  p=self.c.post(self.users[0],{'op':'publish','title':'库存周转','body':'如何小批清理','category':'库存周转'})['id']
  r=self.c.post(self.users[1],{'op':'reply','post':p,'body':'先核对成本再试一批'})['id']
  with self.assertRaises(ValueError):self.c.post(self.users[1],{'op':'solve','post':p,'solved':True})
  self.c.post(self.users[0],{'op':'helpful','post':p,'reply':r});self.c.post(self.users[0],{'op':'solve','post':p,'solved':True})
  d=self.c.get(self.users[2],{'view':['post'],'id':[p]});self.assertEqual(d['post']['solved'],1);self.assertEqual(d['replies'][0]['helpful'],1)
  self.c.post(self.users[2],{'op':'report','kind':'reply','target':r,'reason':'需要核对'})
  with self.assertRaises(ValueError):self.c.post(self.users[2],{'op':'hide','kind':'post','target':p})
  self.c.post(self.users[0],{'op':'hide','kind':'post','target':p});self.assertEqual(self.c.get(self.users[1],{})['posts'],[])
 def test_private_messages_and_block(self):
  a,b,c=self.users
  m=self.c.post(a,{'op':'message','peer':b['id'],'body':'私下交流'})['id']
  self.assertEqual(self.c.get(c,{'view':['inbox']})['conversations'],[])
  self.assertEqual(self.c.get(c,{'view':['thread'],'peer':[b['id']]})['messages'],[])
  self.assertEqual(len(self.c.get(b,{'view':['thread'],'peer':[a['id']]})['messages']),1)
  with self.assertRaises(ValueError):self.c.post(c,{'op':'report','kind':'message','target':m,'reason':'越权'})
  self.c.post(b,{'op':'block','target':a['id'],'blocked':True})
  with self.assertRaises(ValueError):self.c.post(a,{'op':'message','peer':b['id'],'body':'再次'})
  self.c.post(b,{'op':'block','target':a['id'],'blocked':False});self.c.post(a,{'op':'message','peer':b['id'],'body':'已恢复'})
 def test_reports_access_and_rate_limit(self):
  with self.assertRaises(ValueError):self.c.get(self.users[0],{'view':['reports']})
  for i in range(10):self.c.post(self.users[0],{'op':'publish','title':str(i),'body':'提问','category':'记账工具'})
  with self.assertRaises(ValueError):self.c.post(self.users[0],{'op':'publish','title':'超额','body':'提问','category':'记账工具'})
if __name__=='__main__':unittest.main()
