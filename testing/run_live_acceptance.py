"""Single bounded cloud acceptance; saves failure instead of retrying or resuming."""
from pathlib import Path
from uuid import uuid4
import argparse,hashlib,importlib.util,json,sys,time
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R),str(R/'.agentarts-deps')]
from rebirth.control import RunControl
from rebirth.engine import Engine
from rebirth.store import Store
from rebirth.providers import AgentArtsProvider

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package',type=Path,required=True);ap.add_argument('--max-rounds',type=int,choices=[0,1],default=0);ap.add_argument('--confirm-paid-calls',action='store_true');args=ap.parse_args()
 if not args.confirm_paid_calls:ap.error('requires explicit consent for one bounded cloud run')
 out=R/'testing/optimization-live'/uuid4().hex;out.mkdir(parents=True)
 spec=importlib.util.spec_from_file_location('local_cloud_loader',args.package/'录制配置.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 config,enabled=module.load_cloud(args.package)
 if not enabled:raise SystemExit('cloud configuration is missing')
 case=next(c for c in json.loads((R/'testing/public-retail/cases.json').read_text(encoding='utf-8')) if c['id']=='C02')
 control=RunControl(max_calls=40,max_input_bytes=2000000,max_output_bytes=300000,max_seconds=600,journal_path=out/'usage.json')
 provider=AgentArtsProvider(config,control=control);original=provider.step
 def step(context):
  print(json.dumps({'role':context['role'],'phase':context['phase'],'reserved_calls':control.status()['calls']}),flush=True)
  return original(context)
 provider.step=step
 files=list((R/'rebirth').glob('*.py'))+list((R/'agentarts/prompts').glob('*.md'))+[R/'config/contracts.json']
 hashes={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 (out/'manifest.json').write_text(json.dumps({'case':'C02','execution':'live_cloud','source_sha256':hashes,'budget':control.status(),'max_revision_rounds':args.max_rounds,'model_parameters':'not_verified_from_console','single_vs_multi_comparison':False},indent=2),encoding='utf-8')
 store=Store(out/'business.sqlite3');store.put_ledger(case['ledger']);engine=Engine(store,provider,control=control,max_rounds=args.max_rounds)
 start=time.monotonic();error=None;report=None
 try:report=engine.execute(case['ledger']['merchant_id'])
 except Exception as exc:
  error=type(exc).__name__
  if getattr(engine,'run_id',None):report=store.result(case['ledger']['merchant_id'],engine.run_id)
 if report:(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 result=(report or {}).get('result') or {}
 summary={'execution':'live_cloud','status':(report or {}).get('status','not_started'),'error_type':error,'message':result.get('error_message'),'elapsed_seconds':round(time.monotonic()-start,2),'usage':control.status(),'token_usage':None,'cost_cny':None,'automatic_retries':0,'case':'C02','output_folder':str(out),'source_unchanged':all(hashlib.sha256(f.read_bytes()).hexdigest()==hashes[str(f.relative_to(R))] for f in files)}
 (out/'metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=True),flush=True)
 if error:raise SystemExit(1)
if __name__=='__main__':main()
