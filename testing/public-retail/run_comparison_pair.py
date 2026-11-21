"""One frozen, bounded paired pilot. Default is offline; never resumes failures."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'.agentarts-deps')]
from rebirth.control import RunControl
from rebirth.engine import Engine
from rebirth.providers import AgentArtsProvider, RuleProvider
from rebirth.store import Store
from run_benchmark import SINGLE_INSTRUCTION

ROLES = ('coordinator', 'inventory', 'customer', 'cash')
BUDGET = {'max_calls':64, 'max_input_bytes':4000000, 'max_output_bytes':300000, 'max_seconds':1800}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_hashes():
    files = sorted((ROOT/'rebirth').glob('*.py')) + sorted((ROOT/'agentarts/prompts').glob('*.md'))
    files += [ROOT/'config/contracts.json', HERE/'run_benchmark.py', Path(__file__).resolve()]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def integrated_instruction():
    # Give the single identity the same specialist business knowledge, retaining
    # each distinct paragraph once instead of a deliberately weak short prompt.
    paragraphs, seen = [], set()
    for role in ROLES:
        text = (ROOT/'agentarts/prompts'/f'{role}.md').read_text(encoding='utf-8')
        for paragraph in text.split('\n\n'):
            paragraph = paragraph.strip()
            if paragraph and paragraph not in seen:
                seen.add(paragraph)
                paragraphs.append(paragraph)
    return SINGLE_INSTRUCTION + '''\n\n下面是四种任务的业务参考，均由你这个综合身份使用。
参考中的角色名称只表示当前任务视角，不创建独立智能体或隔离记忆。
以开头的综合身份和宿主当前phase/role为准，使用全部可见先前结果进行自查。
参考的输出例子以本次output_contract中的协议2完整契约为准。\n\n''' + '\n\n'.join(paragraphs)


def shared_config(config):
    endpoint = deepcopy(config['agents']['coordinator'])
    return {**config, 'agents':{role:deepcopy(endpoint) for role in ROLES}}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def execute_arm(pair, strategy, case, config_file, manifest, *, cloud=False):
    if source_hashes() != manifest['source_hashes']:
        raise ValueError('冻结后源码已改变，不得把修改前后运行混成同一组对照')
    if digest(case) != manifest['case_sha256']:
        raise ValueError('冻结后案例已改变')
    if digest(json.loads(config_file.read_text(encoding='utf-8'))) != manifest['config_sha256']:
        raise ValueError('冻结后接入配置已改变')
    if hashlib.sha256((pair/'single-instruction.txt').read_bytes()).hexdigest() != manifest['single_instruction_sha256']:
        raise ValueError('冻结后单身份业务说明已改变')
    arm = pair/strategy
    arm.mkdir()  # Deliberately refuse overwriting or silently retrying an arm.
    control = RunControl(**manifest['budget_per_arm'],journal_path=arm/'usage-checkpoint.json')
    if cloud:
        provider = AgentArtsProvider(config_file, control=control,
            instruction_override=(pair/'single-instruction.txt').read_text(encoding='utf-8') if strategy == 'single' else None)
        original = provider.step
        def traced(context):
            print('pilot_step', strategy, context['role'], context['phase'], control.status()['calls']+1, flush=True)
            value = original(context)
            with (arm/'actions.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'role':context['role'], 'phase':context['phase'],
                    'allowed_refs':[o['evidence_id'] for o in context['observations'] if 'value' in o],
                    'feedback_errors':[p.get('error') for p in context['protocol_feedback']],
                    'action':value},ensure_ascii=False)+'\n')
            return value
        provider.step = traced
    else:
        provider = RuleProvider()
    store = Store(arm/'business.sqlite3')
    store.put_ledger(case['ledger'])
    engine = Engine(store,provider,control=control,max_rounds=manifest['revision_round_limit'],
                    single_identity=strategy == 'single')
    started = time.monotonic()
    error = None
    try:
        report = engine.execute(case['ledger']['merchant_id'])
    except Exception as exc:
        error = type(exc).__name__
        report = store.result(case['ledger']['merchant_id'],engine.run_id)
    frozen = source_hashes() == manifest['source_hashes']
    result = report.get('result') or {}
    metrics = {'strategy':strategy,'case':case['id'], 'manifest_sha256':digest(manifest),
        'execution':'cloud' if cloud else 'offline_rule_protocol_check',
        'elapsed_seconds':round(time.monotonic()-started,3),'error_type':error,
        'source_unchanged':frozen,'status':report['status'],'usage':control.status(),
        'token_usage':None,'cost_cny':None,'resumptions':0,'automatic_retry':False,
        'proposals':len(result.get('proposals',[])),
        'agent_output_rejections':sum(e['kind']=='agent_output_rejected' for e in report['events']),
        'tool_errors':sum(e['kind']=='tool_error' for e in report['events']),
        'collaboration':result.get('collaboration'),
        'notice':'一次同端点编排预试验；请求字节不是Token或费用，不作统计优劣或真实经营改善结论。'}
    write_json(arm/'report.json',report)
    write_json(arm/'metrics.json',metrics)
    print(json.dumps({'arm_finished':strategy,'status':report['status'],'error_type':error,
                      'requests':control.status()['calls']}),flush=True)
    if not frozen:
        raise ValueError('运行期间源码改变，本组不能用于冻结对照')
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case',choices=[f'C0{i}' for i in range(1,8)],default='C02')
    parser.add_argument('--cloud',action='store_true')
    parser.add_argument('--confirm-paid-calls',action='store_true')
    parser.add_argument('--config',type=Path)
    args = parser.parse_args()
    if args.cloud and (not args.confirm_paid_calls or not args.config):
        parser.error('云端预试验须提供配置并显式确认付费调用；本程序不读取桌面密钥')
    case = next(c for c in json.loads((HERE/'cases.json').read_text(encoding='utf-8')) if c['id']==args.case)
    config = shared_config(json.loads(args.config.read_text(encoding='utf-8-sig'))) if args.cloud else None
    instruction = integrated_instruction()
    manifest = {'purpose':'same_endpoint_orchestration_pilot_not_formal_comparison',
        'created_at':datetime.now(timezone.utc).isoformat(),'case':case['id'],
        'case_sha256':digest(case),'ledger_sha256':digest(case['ledger']),'rubric_sha256':digest(case['rubric']),
        'source_hashes':source_hashes(),'budget_per_arm':BUDGET,'revision_round_limit':1,
        'order':['single','multi'], 'repetitions_per_arm':1,
        'both_arms_use_same_endpoint':True, 'config_sha256':digest(config),
        'single_instruction_sha256':hashlib.sha256(instruction.encode()).hexdigest(),
        'model_from_prior_setup':'rebirth-maas / deepseek-v4.1-flash',
        'resolved_model_and_sampling_independently_observed':False,
        'single_identity':'综合身份、顺序执行相同分阶段协议、可读全部前序结果、可自查和修订',
        'multi_identity':'专业角色独立工作记忆、阶段屏障共享、阶段内并行',
        'limitations':['一次、一个构造案例，不能用于统计优劣',
                       '单身份仍遵循相同宿主分阶段协议，不代表所有单智能体实现',
                       '同端点控制模型接入差异，不是四个生产端点的运行对照',
                       '共享端点不能观测实际解析模型版本与平台采样参数，未假称独立核实',
                       '两组专业提示词组织方式和执行并发不同；字节预算相同不等于同Token或同费用']}
    pair = HERE/'paired-runs'/uuid4().hex
    pair.mkdir(parents=True)
    write_json(pair/'manifest.json',manifest)
    write_json(pair/'case.json',case)
    write_json(pair/'endpoints.json',config)
    (pair/'single-instruction.txt').write_bytes(instruction.encode('utf-8'))
    print(json.dumps({'pair_folder':str(pair),'cloud':args.cloud,'total_request_ceiling':2*BUDGET['max_calls']}),flush=True)
    rows=[]
    for strategy in manifest['order']:
        rows.append(execute_arm(pair,strategy,case,pair/'endpoints.json',manifest,cloud=args.cloud))
    write_json(pair/'summary.json',{'manifest_sha256':digest(manifest),'arms':[
        {k:v for k,v in row.items() if k!='collaboration'} for row in rows],
        'total_host_requests':sum(r['usage']['calls'] for r in rows),'comparison_verdict':'human_review_pending'})
    print(json.dumps({'pair_completed':str(pair),'cloud':args.cloud}),flush=True)


if __name__ == '__main__':
    main()
