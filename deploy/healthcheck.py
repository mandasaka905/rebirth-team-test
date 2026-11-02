"""Readiness check over the loopback upstream, with the configured canonical Host."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
origin=os.environ.get('REBIRTH_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL') or 'https://'+os.environ.get('RAILWAY_PUBLIC_DOMAIN','')
host=urlsplit(origin).netloc
if not host:raise SystemExit(1)
request=Request('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',headers={'Host':host})
with urlopen(request,timeout=4) as response:
    if json.load(response).get('status')!='ok':raise SystemExit(1)
