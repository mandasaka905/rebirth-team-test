from pathlib import Path
import sqlite3,json
from datetime import datetime,timezone
root=Path(__file__).resolve().parent
lines=['任务只读排查 UTC '+datetime.now(timezone.utc).isoformat(),'不读取密钥配置，不导出底账、模型正文或客户资料。']
allowed_actor={'coordinator','inventory','customer','cash','host','system','merchant'}
for db in (root/'data/shops').glob('*/business.sqlite3'):
 try:
  c=sqlite3.connect('file:'+db.resolve().as_posix()+'?mode=ro',uri=True,timeout=2);c.row_factory=sqlite3.Row
  runs=c.execute('select id,mode,status,created_at from runs order by rowid desc limit 2').fetchall()
  for r in runs:
   lines.append(json.dumps(dict(r),ensure_ascii=False))
   rows=c.execute('select actor,kind,created_at,data from events where run=? order by seq desc limit 15',(r['id'],)).fetchall()
   for e in reversed(rows):
    d=json.loads(e['data']);phase=d.get('phase');phase=phase if phase in ('investigate','propose','review','revise','coordinate','design') else None
    kind=e['kind'] if str(e['kind']).replace('_','').isalnum() and len(e['kind'])<50 else 'other'
    lines.append(json.dumps({'actor':e['actor'] if e['actor'] in allowed_actor else 'other','kind':kind,'phase':phase,'at':e['created_at']},ensure_ascii=False))
  c.close()
 except Exception as e:lines.append('读取失败 '+type(e).__name__)
if len(lines)==2:lines.append('本目录未找到任务。请将两个排查文件放在录制包根目录，和runtime、data同级。')
out=root/'任务排查结果.txt';out.write_text('\n'.join(lines),encoding='utf-8');print('已生成任务排查结果.txt；过30秒再运行一次可比较事件时间是否推进。')
