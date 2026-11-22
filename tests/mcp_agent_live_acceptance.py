"""Explicit live synthetic AgentArts -> application MCP bridge -> AgentArts test."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.agentarts-deps'))
from rebirth.local_credentials import read_keys
from rebirth.providers import AgentArtsProvider
from rebirth.control import RunControl
from rebirth.tools import dispatch

if not os.environ.get('AGENTARTS_CASH_KEY'):
    os.environ.update(read_keys(ROOT / 'config/AgentArts密钥.local.txt', roles=('cash',)))
os.environ['REBIRTH_MCP_CREDENTIAL_FILE'] = str(ROOT / 'config/mcp-inbound.local.json')
ledger = json.loads((ROOT / 'examples/merchant.synthetic.json').read_text(encoding='utf-8'))
proposal = json.loads((ROOT / 'config/contracts.json').read_text(encoding='utf-8'))['proposal_example']
proposal['items'][0]['variable_cash_cost'] = '400.00'
instruction = '''这是合成数据的MCP调用验收。只审查context.proposals中的方案。
必须请求proposal_evaluate工具核验，不修改参数，不生成新方案。
工具由应用通过云端MCP实际执行。收到结果后必须引用本次evidence_id，指出BUDGET_EXCEEDED及预算原因，
保留未知事项，不将计算通过当作执行许可。最终返回action=final,result含notes和objections。
只输出单个JSON对象，不做其他任务。'''
provider = AgentArtsProvider(ROOT / 'config/agentarts.managed.local.json', required_roles=('cash',),
    instruction_override=instruction, control=RunControl(max_calls=5, max_input_bytes=500000,
        max_output_bytes=500000, max_seconds=400))
context = {'run_id': 'mcp-proof-' + uuid4().hex, 'role': 'cash', 'phase': 'review',
    'ledger': ledger, 'tools': {'proposal_evaluate': '核验当前完整方案', 'cash_baseline': '读取现金约束'},
    'proposals': [proposal], 'reviews': [], 'observations': []}
events = []
for step in range(5):
    action = provider.step(context)
    events.append({'kind': 'agent_action', 'action': action})
    print('Agent action:', action.get('action'), action.get('name', ''), flush=True)
    if action.get('action') == 'final':
        serialized = json.dumps(action, ensure_ascii=False)
        remote = [o for o in context['observations'] if o['value'].get('_mcp')]
        assert remote, 'Agent did not request MCP evaluation'
        assert any(o['evidence_id'] in serialized for o in remote), 'Conclusion did not cite MCP evidence'
        assert 'BUDGET_EXCEEDED' in serialized or '预算' in serialized, 'Budget issue absent from conclusion'
        output = {'passed': True, 'integration': 'application-side MCP bridge, not native Managed Agents binding',
                  'run_id': context['run_id'], 'events': events, 'observations': context['observations']}
        (ROOT / 'testing/mcp-agent-live-acceptance.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Agent -> cloud MCP -> cited conclusion: PASS', flush=True)
        break
    assert action.get('action') == 'tool'
    name, args = action['name'], action['arguments']
    assert name in ('proposal_evaluate', 'cash_baseline'), 'Unexpected tool requested'
    value = dispatch(ledger, name, args)
    context['observations'].append({'tool': name, 'arguments': args, 'value': value, 'evidence_id': 'mcp-evidence-' + str(step)})
else:
    raise AssertionError('Agent did not finish within bounded calls')
