"""Competition entry: account-isolated website and explicitly confirmed AgentArts calls."""
from pathlib import Path
import argparse,json,os,sys
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.agentarts-deps'))
def main():
    from rebirth.local_credentials import read_keys
    from rebirth.hosted import Gateway
    parser=argparse.ArgumentParser()
    parser.add_argument('--keys-file',type=Path,default=Path.home()/'OneDrive/Desktop/密钥.txt')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args();keys=read_keys(args.keys_file);os.environ.update(keys)
    try:
        data=ROOT/'var/competition'
        gateway=Gateway(data,'http://127.0.0.1:0',local_preview=True,registration_open=True,
            demo_only=False,seed_examples=False,first_admin=True,allow_cloud=True,config_path=ROOT/'config/agentarts.managed.local.json')
        server=ThreadingHTTPServer(('127.0.0.1',args.port),gateway.handler())
        gateway.host='127.0.0.1:'+str(server.server_port);gateway.origin='http://'+gateway.host
        (data/'server.json').write_text(json.dumps({'url':gateway.origin,'registration_open':True,'cloud_configured':True}),encoding='utf-8')
        print(json.dumps({'url':gateway.origin,'notice':'First registered account is administrator. Cloud analysis requires explicit confirmation.'}),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:
        for name in keys:os.environ.pop(name,None)
if __name__=='__main__':main()
