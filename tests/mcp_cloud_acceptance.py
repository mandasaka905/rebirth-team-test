"""Read private local credentials and verify real cloud MCP calls."""
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
KEY = json.loads((ROOT / 'config/mcp-inbound.local.json').read_text())['api_key']
BASE = 'https://defaultgw-gmytsnryg4.cn-southwest-2.huaweicloud-agentarts.com/runtimes/rebirth-constraint-mcp/invocations'


def run(url):
    with httpx.Client(trust_env=False, timeout=90) as client:
        headers = {'Authorization': 'Bearer ' + KEY, 'Accept': 'application/json, text/event-stream',
                   'X-Hw-Agentarts-Session-Id': 'mcp-cloud-acceptance-v3'}
        def rpc(method, params=None):
            response = client.post(url, headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})
            response.raise_for_status()
            body = response.json()
            assert 'error' not in body, body.get('error')
            return body['result']
        rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'rebirth-acceptance', 'version': '1'}})
        listing = rpc('tools/list')
        assert 'evaluate_proposal_constraints' in [x['name'] for x in listing['tools']]
        ledger = json.loads((ROOT / 'examples/merchant.synthetic.json').read_text(encoding='utf-8'))
        proposal = json.loads((ROOT / 'config/contracts.json').read_text(encoding='utf-8'))['proposal_example']
        proposal['items'][0]['variable_cash_cost'] = '400.00'
        result = rpc('tools/call', {'name': 'evaluate_proposal_constraints', 'arguments': {'ledger': ledger, 'proposal': proposal}})
        assert not result.get('isError')
        value = result.get('structuredContent') or json.loads(result['content'][0]['text'])
        assert 'BUDGET_EXCEEDED' in {x['code'] for x in value['evaluation']['checks']}
        invalid = rpc('tools/call', {'name': 'evaluate_proposal_constraints', 'arguments': {'ledger': {}, 'proposal': proposal}})
        assert invalid.get('isError')
        anonymous = client.post(url, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, headers={'Accept': 'application/json, text/event-stream'})
        assert anonymous.status_code in (401, 403)
        record = {'url': url, 'handshake': 'pass', 'discovery': 'pass', 'budget_breach': 'pass',
                  'invalid_input': 'pass', 'unauthorized': 'pass', 'sample_result': value,
                  'managed_agent_binding': 'not_verified'}
        (ROOT / 'testing/mcp-cloud-acceptance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Cloud MCP acceptance passed; managed agent binding not yet verified.')


if __name__ == '__main__':
    import sys
    run(BASE + ('/mcp' if '--suffix' in sys.argv else '') + '?endpoint=Latest')
