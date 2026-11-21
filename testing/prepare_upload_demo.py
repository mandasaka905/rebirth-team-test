from pathlib import Path
import zipfile,xml.etree.ElementTree as ET,io,collections,json
from datetime import datetime,timedelta
r=Path('outputs/rebirth');ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
with zipfile.ZipFile(r/'testing/public-retail/raw/online-retail.zip') as z:b=z.read(next(n for n in z.namelist() if n.endswith('.xlsx')))
rows=collections.defaultdict(list);names={}
with zipfile.ZipFile(io.BytesIO(b)) as z:
 strings=[]
 for _,n in ET.iterparse(z.open('xl/sharedStrings.xml'),events=('end',)):
  if n.tag==ns+'si':strings.append(''.join(x.text or '' for x in n.iter(ns+'t')));n.clear()
 for _,n in ET.iterparse(z.open('xl/worksheets/sheet1.xml'),events=('end',)):
  if n.tag!=ns+'row':continue
  v={}
  for c in n:
   t=c.find(ns+'v')
   if t is not None:v[''.join(x for x in c.attrib['r'] if x.isalpha())]=strings[int(t.text)] if c.attrib.get('t')=='s' else t.text
  number=int(n.attrib['r']);n.clear()
  try:
   d=(datetime(1899,12,30)+timedelta(days=float(v['E']))).date().isoformat();q=int(v['D']);p=v['F'];sku=v['B']
   if d<'2011-11-10' or d>'2011-12-09':continue
   if not sku.isdigit():continue
   float(p)
   rows[sku].append({'xlsx_row':number,'invoice':v['A'],'sku':sku,'description':v.get('C',''),'date':d,'quantity':q,'unit_price_gbp':p,'cancelled':v['A'].upper().startswith('C')})
   names[sku]=v.get('C','')
  except (KeyError,ValueError):pass
candidates=[(s,sum(x['quantity'] for x in v),len(v),names[s]) for s,v in rows.items() if 2<=sum(x['quantity'] for x in v)<=12 and len(v)<=10]
(r/'testing/upload-demo-candidates.json').write_text(json.dumps({'candidates':candidates,'rows':rows},ensure_ascii=False),encoding='utf-8')
print(candidates[:35])
