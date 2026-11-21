"""Account profiles and opt-in merchant conversations; never reads tenant ledgers."""
import base64, io, secrets, time

CATEGORIES=('库存周转','获客经营','记账工具','资源互助','经验分享')
class Community:
 def __init__(self,accounts):
  self.accounts=accounts
  with accounts.connect() as db:db.executescript('''
   CREATE TABLE IF NOT EXISTS profiles(uid TEXT PRIMARY KEY,nickname TEXT NOT NULL,avatar TEXT NOT NULL DEFAULT '',bio TEXT NOT NULL DEFAULT '');
   CREATE TABLE IF NOT EXISTS help_posts(id TEXT PRIMARY KEY,uid TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,category TEXT NOT NULL,created INTEGER NOT NULL,solved INTEGER NOT NULL DEFAULT 0,hidden INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS help_replies(id TEXT PRIMARY KEY,post TEXT NOT NULL,uid TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL,helpful INTEGER NOT NULL DEFAULT 0,hidden INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,sender TEXT NOT NULL,recipient TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL,seen INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS blocks(uid TEXT NOT NULL,target TEXT NOT NULL,PRIMARY KEY(uid,target));
   CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,uid TEXT NOT NULL,kind TEXT NOT NULL,target TEXT NOT NULL,reason TEXT NOT NULL,created INTEGER NOT NULL);
  ''')
 @staticmethod
 def text(value,limit,required=True):
  if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()):raise ValueError('请填写有效文字，且不要超过字数限制')
  return value.strip()
 def profile(self,uid):
  with self.accounts.connect() as db:
   u=db.execute('SELECT id FROM users WHERE id=? AND disabled=0',(uid,)).fetchone()
   if not u:raise ValueError('对方账号不可用')
   p=db.execute('SELECT nickname,avatar,bio FROM profiles WHERE uid=?',(uid,)).fetchone()
   return {'id':uid,**(dict(p) if p else {'nickname':'小店经营者','avatar':'','bio':''})}
 def blocked(self,a,b):
  with self.accounts.connect() as db:return bool(db.execute('SELECT 1 FROM blocks WHERE (uid=? AND target=?) OR (uid=? AND target=?)',(a,b,b,a)).fetchone())
 def get(self,user,query):
  uid=user['id'];view=query.get('view',['feed'])[0]
  if view=='profile':return {'profile':self.profile(uid)}
  if view=='blocks':
   with self.accounts.connect() as db:ids=[r[0] for r in db.execute('SELECT target FROM blocks WHERE uid=?',(uid,))]
   return {'people':[self.profile(i) for i in ids]}
  if view=='inbox':
   with self.accounts.connect() as db:
    rows=[dict(r) for r in db.execute('SELECT * FROM messages WHERE sender=? OR recipient=? ORDER BY created DESC,rowid DESC LIMIT 500',(uid,uid))]
   peers={}
   for m in rows:
    other=m['recipient'] if m['sender']==uid else m['sender']
    if other not in peers:
     try:peers[other]={'person':self.profile(other),'last':m,'unread':0}
     except ValueError:continue
    if m['recipient']==uid and not m['seen'] and other in peers:peers[other]['unread']+=1
   return {'conversations':list(peers.values())}
  if view=='thread':
   other=query.get('peer',[''])[0];person=self.profile(other)
   with self.accounts.connect() as db:
    rows=[dict(r) for r in db.execute('SELECT * FROM (SELECT rowid,* FROM messages WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?) ORDER BY created DESC,rowid DESC LIMIT 100) ORDER BY created,rowid',(uid,other,other,uid))]
    db.execute('UPDATE messages SET seen=1 WHERE sender=? AND recipient=?',(other,uid))
   return {'person':person,'messages':rows,'blocked':self.blocked(uid,other)}
  if view=='reports':
   if user['role']!='admin':raise ValueError('仅管理员可以处理举报')
   with self.accounts.connect() as db:
    rows=[dict(r) for r in db.execute('SELECT * FROM reports ORDER BY created DESC LIMIT 100')]
    for row in rows:
     if row['kind'] in ('post','reply'):
      table='help_posts' if row['kind']=='post' else 'help_replies'
      item=db.execute(f'SELECT body,hidden FROM {table} WHERE id=?',(row['target'],)).fetchone();row['content']=dict(item) if item else None
     elif row['kind']=='message':
      item=db.execute('SELECT sender,recipient FROM messages WHERE id=?',(row['target'],)).fetchone();row['participants']=dict(item) if item else None
   return {'reports':rows}
  if view=='post':
   pid=query.get('id',[''])[0]
   with self.accounts.connect() as db:
    row=db.execute('SELECT p.* FROM help_posts p JOIN users u ON u.id=p.uid WHERE p.id=? AND p.hidden=0 AND u.disabled=0',(pid,)).fetchone()
    if not row:raise ValueError('这条求助已不可见')
    post=dict(row);replies=[dict(r) for r in db.execute('SELECT r.* FROM help_replies r JOIN users u ON u.id=r.uid WHERE r.post=? AND r.hidden=0 AND u.disabled=0 ORDER BY r.created,r.rowid LIMIT 200',(pid,))]
   post['author']=self.profile(post['uid'])
   for r in replies:r['author']=self.profile(r['uid'])
   return {'post':post,'replies':replies}
  with self.accounts.connect() as db:
   rows=[dict(r) for r in db.execute('SELECT p.*,(SELECT count(*) FROM help_replies r WHERE r.post=p.id AND hidden=0) AS replies FROM help_posts p JOIN users u ON u.id=p.uid WHERE p.hidden=0 AND u.disabled=0 ORDER BY p.created DESC,p.rowid DESC LIMIT 100')]
  for row in rows:row['author']=self.profile(row['uid'])
  return {'posts':rows,'categories':CATEGORIES}
 def post(self,user,b):
  uid=user['id'];op=b.get('op');now=int(time.time());item=secrets.token_hex(16)
  if op=='profile':
   nick=self.text(b.get('nickname'),24);bio=self.text(b.get('bio',''),120,False);avatar=b.get('avatar','')
   if not isinstance(avatar,str) or len(avatar)>300000:raise ValueError('头像过大，请选择较小的图片')
   if avatar:
    try:
     from PIL import Image
     if not avatar.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):raise ValueError()
     image=Image.open(io.BytesIO(base64.b64decode(avatar.split(',',1)[1],validate=True)))
     if image.width*image.height>4000000:raise ValueError()
     image.load();image=image.convert('RGB');image.thumbnail((256,256));out=io.BytesIO();image.save(out,format='JPEG',quality=85);avatar='data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
    except Exception:raise ValueError('请选择有效的PNG、JPEG或WebP头像') from None
   with self.accounts.connect() as db:db.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?,?)',(uid,nick,avatar,bio))
   return {'profile':self.profile(uid)}
  if op=='block':
   target=b.get('target');self.profile(target)
   if target==uid or not isinstance(b.get('blocked'),bool):raise ValueError('请选择其他经营者')
   with self.accounts.connect() as db:
    if b['blocked']:db.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(uid,target))
    else:db.execute('DELETE FROM blocks WHERE uid=? AND target=?',(uid,target))
   return {'ok':True}
  with self.accounts.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if op in ('publish','reply','message','report'):
    table={'publish':'help_posts','reply':'help_replies','message':'messages','report':'reports'}[op];field='sender' if op=='message' else 'uid'
    if db.execute(f'SELECT count(*) FROM {table} WHERE {field}=? AND created>?',(uid,now-60)).fetchone()[0]>=10:raise ValueError('发送太频繁，请稍后再试')
   if op=='publish':
    title=self.text(b.get('title'),60);body=self.text(b.get('body'),3000);category=b.get('category')
    if category not in CATEGORIES:raise ValueError('请选择求助类别')
    db.execute('INSERT INTO help_posts(id,uid,title,body,category,created) VALUES(?,?,?,?,?,?)',(item,uid,title,body,category,now))
   elif op in ('reply','solve','helpful'):
    pid=b.get('post');p=db.execute('SELECT * FROM help_posts WHERE id=? AND hidden=0',(pid,)).fetchone()
    if not p:raise ValueError('这条求助已不可见')
    if op=='reply':
     if self.blocked(uid,p['uid']):raise ValueError('当前无法与对方交流')
     db.execute('INSERT INTO help_replies(id,post,uid,body,created) VALUES(?,?,?,?,?)',(item,pid,uid,self.text(b.get('body'),2000),now))
    else:
     if p['uid']!=uid:raise ValueError('只有发起人可以确认帮助或解决状态')
     if op=='solve':db.execute('UPDATE help_posts SET solved=? WHERE id=?',(int(bool(b.get('solved'))),pid))
     else:db.execute('UPDATE help_replies SET helpful=1-helpful WHERE id=? AND post=? AND hidden=0',(b.get('reply'),pid))
   elif op=='message':
    other=b.get('peer');self.profile(other)
    if other==uid or self.blocked(uid,other):raise ValueError('当前无法与对方私信')
    db.execute('INSERT INTO messages(id,sender,recipient,body,created) VALUES(?,?,?,?,?)',(item,uid,other,self.text(b.get('body'),2000),now))
   elif op=='report':
    kind=b.get('kind');target=b.get('target');reason=self.text(b.get('reason'),300)
    table={'post':'help_posts','reply':'help_replies','message':'messages'}.get(kind)
    if not table:raise ValueError('请选择举报内容')
    row=db.execute(f'SELECT * FROM {table} WHERE id=?',(target,)).fetchone()
    if not row or (kind=='message' and uid not in (row['sender'],row['recipient'])):raise ValueError('内容不存在或无权访问')
    db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?)',(item,uid,kind,target,reason,now))
   elif op=='hide':
    table={'post':'help_posts','reply':'help_replies'}.get(b.get('kind'))
    if not table:raise ValueError('请选择内容')
    row=db.execute(f'SELECT uid FROM {table} WHERE id=?',(b.get('target'),)).fetchone()
    if not row or (row['uid']!=uid and user['role']!='admin'):raise ValueError('无权撤下这条内容')
    db.execute(f'UPDATE {table} SET hidden=1 WHERE id=?',(b.get('target'),))
   else:raise ValueError('操作不存在')
  return {'ok':True,'id':item}
