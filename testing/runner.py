"""Loopback-only, no-install usability kit. Runs the real application and local APIs."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
import webbrowser
from datetime import datetime

PROJECT = Path(__file__).resolve().parents[1]
KIT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rebirth.server import make_handler
from seed import prepare

DATA = KIT/'data'
IDENTITY = hashlib.sha256(str(KIT.resolve()).encode()).hexdigest()[:20]


def handler(store, feedback):
    base = make_handler(store, PROJECT/'config/test-no-cloud.json', allow_cloud=False)
    class TestHandler(base):
        def asset(self, path):
            if path == '/test-info':
                self.reply(200, {'app':'rebirth-usability','identity':IDENTITY,'synthetic_only':True,'cloud':False})
                return True
            if path == '/test-feedback':
                try:
                    value = json.loads(feedback.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    value = {}
                self.reply(200, value)
                return True
            if path == '/test-guide':
                payload = (PROJECT/'testing/guide.html').read_bytes(); mime='text/html; charset=utf-8'
            elif path == '/test-guide.js':
                payload = (PROJECT/'testing/guide.js').read_bytes(); mime='text/javascript; charset=utf-8'
            elif path == '/test-scenarios.json':
                payload = (PROJECT/'testing/scenarios.json').read_bytes(); mime='application/json; charset=utf-8'
            elif path == '/test-kit.js':
                payload = (PROJECT/'testing/kit.js').read_bytes(); mime='text/javascript; charset=utf-8'
            elif path == '/test-kit.css':
                payload = (PROJECT/'testing/kit.css').read_bytes(); mime='text/css; charset=utf-8'
            elif path == '/workbench':
                html=(PROJECT/'dist/index.html').read_text(encoding='utf-8-sig')
                html=html.replace('</head>','<link rel="stylesheet" href="/desk-theme.css"><link rel="stylesheet" href="/test-kit.css"><script src="/desk-theme.js" defer></script><script src="/test-kit.js" defer></script></head>')
                payload=html.encode('utf-8');mime='text/html; charset=utf-8'
            else:
                assets={'/':('index.html','text/html; charset=utf-8'),'/homepage.css':('homepage.css','text/css; charset=utf-8'),'/homepage.js':('homepage.js','text/javascript; charset=utf-8'),'/desk-theme.css':('desk-theme.css','text/css; charset=utf-8'),'/desk-theme.js':('desk-theme.js','text/javascript; charset=utf-8')}
                for f in ['summer-street.png','summer-street-mobile.png','shop-interior-v1.png','tree-shadow.svg','wordmark.svg']:
                    assets['/preview-assets/'+f]=('assets/'+f,'image/svg+xml' if f.endswith('.svg') else 'image/png')
                if path not in assets:
                    return super().asset(path)
                filename,mime=assets[path];payload=(PROJECT/'design-preview/dist'/filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(payload)
            return True

        def do_POST(self):
            if urlsplit(self.path).path != '/test-feedback':
                return super().do_POST()
            if not self.safe_local():return
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('反馈格式不正确')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=100000:raise ValueError('反馈太长')
                value=json.loads(self.rfile.read(length))
                if not isinstance(value,dict) or value.get('schema')!='rebirth-usability-v1':raise ValueError('反馈格式不正确')
                feedback.parent.mkdir(parents=True,exist_ok=True)
                tmp=feedback.with_suffix('.tmp')
                tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
                os.replace(tmp,feedback)
                self.reply(200,{'saved':True})
            except (ValueError,TypeError,OSError) as error:
                self.reply(400,{'error':str(error)})
    return TestHandler


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        import socket
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def selfcheck():
    checks=[]
    required=['dist/index.html','dist/app-ui.js','dist/social.js','rebirth/server.py','examples/planning.synthetic.json','knowledge/reference_library.json','design-preview/dist/assets/summer-street.png','design-preview/dist/assets/shop-interior-v1.png','testing/guide.html','testing/guide.js']
    for relative in required:
        if not (PROJECT/relative).is_file():raise RuntimeError('缺少文件：'+relative)
    checks.append('页面、脚本、图片和样例文件齐全')
    with tempfile.TemporaryDirectory(prefix='rebirth-kit-',dir=DATA) as folder:
        store=prepare(Path(folder)/'check.sqlite3',PROJECT)
        server=LocalServer(('127.0.0.1',0),handler(store,Path(folder)/'feedback.json'))
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            for path in ['/','/workbench','/app-ui.js','/social.js','/test-guide','/test-guide.js','/preview-assets/summer-street.png','/health']:
                with urllib.request.urlopen(base+path,timeout=5) as response:
                    if response.status!=200:raise RuntimeError(path+'未正常返回')
            merchants=json.load(urllib.request.urlopen(base+'/api/merchants'))['merchants']
            assert len(merchants)==2 and all(m['synthetic'] for m in merchants)
            home=json.load(urllib.request.urlopen(base+'/api/merchants/try_b/community'))
            assert home['social']['cards'] and not home['social']['cards'][0]['owned']
            assert not json.load(urllib.request.urlopen(base+'/health'))['cloud_connected']
            checks.append('两家合成店铺、匿名经验和真实本机API正常，云调用关闭')
            from rebirth.engine import Engine
            from rebirth.providers import RuleProvider
            report=Engine(store,RuleProvider()).execute('try_a')
            preview=store.agenda_preview('try_a',dict(run_id=report['run_id'],start_date=store.ledger('try_a')['as_of'],days=7,daily_minutes=30))
            saved=store.save_agenda('try_a',{**preview['request'],'fingerprint':preview['fingerprint'],'confirmed':True,'expected_current_id':None})
            assert saved['id'] and store.agendas('try_a')['agendas']
            checks.append('本地分析→日程预览→保存→重读已走通')
            payload=json.dumps({'schema':'rebirth-usability-v1','notes':'自动自检，全部合成'}).encode()
            request=urllib.request.Request(base+'/test-feedback',data=payload,headers={'Content-Type':'application/json'})
            assert json.load(urllib.request.urlopen(request))['saved']
            assert json.load(urllib.request.urlopen(base+'/test-feedback'))['notes']=='自动自检，全部合成'
            checks.append('试用反馈能保存和重读')
        finally:
            server.shutdown();server.server_close();thread.join()
    return {'passed':True,'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'checks':checks,'scope':'自动自检验证启动与数据链路；界面是否顺手请按人工脚本试用。'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--selfcheck',action='store_true')
    parser.add_argument('--new-round',action='store_true')
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    DATA.mkdir(exist_ok=True)
    if args.selfcheck:
        result=selfcheck();print(json.dumps(result,ensure_ascii=False,indent=2))
        (DATA/'自动自检结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return
    info_file=DATA/'server.json'
    old=None
    try:
        old=json.loads(info_file.read_text(encoding='utf-8'))
        with urllib.request.urlopen('http://127.0.0.1:'+str(int(old['port']))+'/test-info',timeout=1) as r:
            live=json.load(r)
        if live.get('identity')==IDENTITY:
            if args.new_round:
                print('请先关闭上一次测试的后台窗口，再启动新一轮；旧数据不会删除。')
                return
            if not args.no_open:webbrowser.open('http://127.0.0.1:'+str(old['port'])+'/test-guide')
            print('本测试包已经运行，直接使用原窗口；没有启动第二份后台。')
            return
    except (OSError,ValueError,KeyError,TypeError):
        pass
    if args.new_round or not old or not isinstance(old.get('round'),str):
        round_id='round-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    else:
        round_id=old['round']
    if not round_id.startswith('round-') or any(x not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for x in round_id):
        raise RuntimeError('测试轮次目录无效')
    folder=DATA/round_id;folder.mkdir(exist_ok=True)
    store=prepare(folder/'practice.sqlite3',PROJECT)
    server=LocalServer(('127.0.0.1',args.port),handler(store,folder/'试用反馈.json'))
    info={'port':server.server_port,'round':round_id,'identity':IDENTITY}
    info_file.write_text(json.dumps(info),encoding='utf-8')
    (DATA/'打开测试指南.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=http://127.0.0.1:'+str(server.server_port)+'/test-guide"><p>请保持测试后台窗口运行。</p>',encoding='utf-8')
    print('逆势重生 · 电脑版可用性试用包',flush=True)
    print('测试指南：http://127.0.0.1:'+str(server.server_port)+'/test-guide',flush=True)
    print('网站首页：http://127.0.0.1:'+str(server.server_port)+'/',flush=True)
    print('仅使用合成练习数据，不需要付费模型。保持这个窗口开启。',flush=True)
    print('关闭后再次启动会保留本轮记录；新一轮入口会另存一份数据。',flush=True)
    if not args.no_open:webbrowser.open('http://127.0.0.1:'+str(server.server_port)+'/test-guide')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('测试包未能启动：'+str(error),flush=True)
        raise SystemExit(1)
