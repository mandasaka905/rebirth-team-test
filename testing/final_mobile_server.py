from pathlib import Path
import json,sys
from http.server import ThreadingHTTPServer
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from rebirth.hosted import Gateway
from rebirth.store import Store
D=R/'testing/final-mobile-sandbox';D.mkdir(exist_ok=True)
g=Gateway(D,'http://127.0.0.1:0',local_preview=True,registration_open=False,seed_examples=False,allow_cloud=False,config_path=R/'config/hosted-no-cloud.json')
username='freeze_mobile_qa';password='Freeze-Mobile-20261121!'
uid=g.accounts.create(username,password)
store=Store(g.accounts.folder/'shops'/uid/'business.sqlite3')
l=json.loads((R/'team-delivery/逆势重生-队友双击专用版-20261121-v8/录制资料/店铺基础资料_供验收程序使用.json').read_text(encoding='utf-8'))
l['name']='冻结验收店（构造资料）';store.put_ledger(l)
s=ThreadingHTTPServer(('127.0.0.1',0),g.handler());g.host='127.0.0.1:'+str(s.server_port);g.origin='http://'+g.host
(R/'testing/final-mobile-server.json').write_text(json.dumps({'origin':g.origin,'username':username,'test_account':True,'cloud_enabled':False}),encoding='utf-8')
print(g.origin,flush=True)
try:s.serve_forever()
finally:s.server_close()
