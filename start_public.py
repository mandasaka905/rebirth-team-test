from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Timer
import webbrowser
from rebirth.hosted import Gateway
root=Path(__file__).resolve().parent
g=Gateway(root/'var/public','http://127.0.0.1:0',local_preview=True,registration_open=True,seed_examples=False,first_admin=False,allow_cloud=False,config_path=root/'config/hosted-no-cloud.json')
s=ThreadingHTTPServer(('127.0.0.1',0),g.handler());g.host='127.0.0.1:'+str(s.server_port);g.origin='http://'+g.host
print(g.origin,flush=True)
Timer(1,lambda:webbrowser.open(g.origin)).start()
try:s.serve_forever()
except KeyboardInterrupt:pass
finally:s.server_close()
