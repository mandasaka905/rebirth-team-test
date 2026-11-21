"""Offline delivery checks; does not read credentials or call cloud APIs."""
from pathlib import Path
from html.parser import HTMLParser
import json

class _Assets(HTMLParser):
    def __init__(self):
        super().__init__(); self.paths=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='script' and a.get('src'): self.paths.append(a['src'])
        if tag=='link' and a.get('rel') in ('stylesheet','icon') and a.get('href'): self.paths.append(a['href'])

def check_files(root):
    root=Path(root); missing=[]; invalid=[]; checked=set()
    required=['config/contracts.json','dist/index.html','dist/login.html','dist/register.html']
    required += ['agentarts/prompts/'+r+'.md' for r in ('coordinator','inventory','customer','cash')]
    for rel in required:
        checked.add(rel)
        if not (root/rel).is_file(): missing.append(rel)
    contracts=root/'config/contracts.json'
    if contracts.is_file():
        try:
            data=json.loads(contracts.read_text(encoding='utf-8-sig'))
            if not isinstance(data.get('proposal_example'),dict): invalid.append('config/contracts.json')
        except (ValueError,OSError): invalid.append('config/contracts.json')
    for html in (root/'dist').glob('*.html'):
        parser=_Assets(); parser.feed(html.read_text(encoding='utf-8-sig'))
        for url in parser.paths:
            if url.startswith(('https:','http:','data:','//')): continue
            rel='dist/'+url.split('?',1)[0].lstrip('/')
            checked.add(rel)
            if not (root/rel).is_file(): missing.append(rel)
    return {'passed':not missing and not invalid,'checked_files':len(checked),'missing':sorted(set(missing)),'invalid':invalid,'network_calls':0}
