"""One explicit cloud probe. Read local secrets internally; print only safe outcome."""
from pathlib import Path
import json
import os
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.agentarts-deps'))


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--keys-file',type=Path,default=ROOT/'config/AgentArts密钥.local.txt')
    parser.add_argument('--diagnostic',action='store_true')
    parser.add_argument('--role',choices=('coordinator','inventory','customer','cash'),default='coordinator')
    args=parser.parse_args()
    from rebirth.local_credentials import read_keys
    from rebirth.control import RunControl,LimitExceeded,RunCancelled
    from rebirth.providers import AgentArtsProvider,ProviderError
    role=args.role
    names=[]
    try:
        keys=read_keys(args.keys_file,roles=(role,))
        names=list(keys)
        os.environ.update(keys)
        provider=AgentArtsProvider(ROOT/'config/agentarts.managed.local.json',required_roles=(role,),
            control=RunControl(max_calls=1,max_input_bytes=20000,max_output_bytes=300000,max_seconds=70))
        if args.diagnostic:
            seen=set()
            def observe(frame):
                body=frame.get('body') or {};payload=frame.get('payload') or {}
                event=body.get('event_type') if isinstance(body,dict) else None
                if isinstance(payload,dict):event=event or payload.get('event_type')
                signature=(frame.get('response_kind'),frame.get('type'),event,bool(frame.get('is_final')))
                if signature in seen and not frame.get('is_final'):return
                seen.add(signature)
                summary={'kind':signature,'frame_keys':list(frame),'body_keys':list(body) if isinstance(body,dict) else [],'status':frame.get('status')}
                if frame.get('is_final') or event in ('chat.final','chat.done'):
                    result=body.get('result') if isinstance(body,dict) else None
                    summary['result_type']=type(result).__name__
                    summary['result_keys']=list(result) if isinstance(result,dict) else []
                    content=result.get('content') if isinstance(result,dict) else None
                    if event=='chat.final' and isinstance(body,dict):content=body.get('delta')
                    summary['content_type']=type(content).__name__
                    preview=json.dumps(content,ensure_ascii=True)[:1600]
                    for secret in keys.values():preview=preview.replace(secret,'[REDACTED]')
                    summary['test_content_preview']=preview
                print(json.dumps(summary,ensure_ascii=True),flush=True)
            provider.frame_observer=observe
        result=provider.step({'run_id':'connection-test-'+uuid4().hex,'role':role,'phase':'coordinate',
            'ledger':{},'tools':{},'proposals':[],'reviews':[], 'test_only':True,
            'request':'只测试连接。不得展开经营分析，不调用工具。只返回一个final动作，result包含revise_roles空列表和notes字符串列表。'})
        final=result.get('action')=='final' and isinstance(result.get('result'),dict)
        tool=result.get('action')=='tool' and isinstance(result.get('name'),str) and isinstance(result.get('arguments'),dict)
        print(json.dumps({'role':role,'connected':True,'valid_final_action':final,'valid_tool_action':tool,
            'notice':'仅验证该角色接口；完整业务尚未验收'},ensure_ascii=True))
        return 0 if final or tool else 2
    except (ProviderError,LimitExceeded,RunCancelled,ValueError) as exc:
        print(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=True));return 1
    except Exception:
        print(json.dumps({'status':'failed','error':'检查程序发生异常；原始内容未输出'},ensure_ascii=True));return 1
    finally:
        for name in names:os.environ.pop(name,None)


if __name__=='__main__':raise SystemExit(main())
