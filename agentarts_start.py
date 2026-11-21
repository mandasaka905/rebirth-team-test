"""Loopback-only website using the user's local key file; no credential GUI."""
from pathlib import Path
from http.server import ThreadingHTTPServer
import argparse
import json
import os
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.agentarts-deps'))


def make_site(store,config):
    from rebirth.server import make_handler
    base=make_handler(store,config,allow_cloud=True)
    class Handler(base):
        def asset(self,path):
            if path=='/workbench':
                value=(ROOT/'dist/index.html').read_text(encoding='utf-8-sig')
                value=value.replace('</head>','<link rel="stylesheet" href="/desk-theme.css"><script src="/desk-theme.js" defer></script></head>')
                data=value.encode('utf-8');mime='text/html; charset=utf-8'
            else:
                files={'/':('index.html','text/html; charset=utf-8')}
                for name in ('homepage.css','desk-theme.css'):files['/'+name]=(name,'text/css; charset=utf-8')
                for name in ('homepage.js','desk-theme.js'):files['/'+name]=(name,'text/javascript; charset=utf-8')
                for name in ('summer-street.png','summer-street-mobile.png','shop-interior-v1.png','tree-shadow.svg','wordmark.svg'):
                    files['/preview-assets/'+name]=('assets/'+name,'image/svg+xml' if name.endswith('.svg') else 'image/png')
                if path not in files:return super().asset(path)
                name,mime=files[path];data=(ROOT/'design-preview/dist'/name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data);return True
    return Handler


def main():
    from rebirth.local_credentials import read_keys
    from rebirth.onboarding import PracticeStore,seed_practice
    parser=argparse.ArgumentParser();parser.add_argument('--keys-file',type=Path,required=True)
    parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
    names=[]
    try:
        keys=read_keys(args.keys_file);names=list(keys);os.environ.update(keys)
        config=ROOT/'config/agentarts.managed.local.json'
        store=PracticeStore(ROOT/'var/agentarts-practice/business.sqlite3');seed_practice(store,ROOT)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),make_site(store,config))
        url='http://127.0.0.1:'+str(server.server_port)
        (ROOT/'var/agentarts-practice/server.json').write_text(json.dumps({'url':url,'cloud_allowed':True,'synthetic_only':True}),encoding='utf-8')
        print(json.dumps({'url':url,'cloud_allowed':True,'notice':'Only explicit web tasks call AgentArts; no automatic analysis'},ensure_ascii=True),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:
        for name in names:os.environ.pop(name,None)


if __name__=='__main__':main()
