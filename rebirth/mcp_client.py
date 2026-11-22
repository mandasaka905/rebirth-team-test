"""Application-side MCP transport; credentials never enter model context."""
import json
import hashlib
from pathlib import Path
from .domain import ValidationError, validate_ledger

ENDPOINT = 'https://defaultgw-gmytsnryg4.cn-southwest-2.huaweicloud-agentarts.com/runtimes/rebirth-constraint-mcp/invocations?endpoint=Latest'


def evaluate_remote(ledger, proposal, credential_file):
    import httpx
    key = json.loads(Path(credential_file).read_text(encoding='utf-8'))['api_key']
    validate_ledger(ledger)
    payload = {'ledger': ledger, 'proposal': proposal}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    try:
        with httpx.Client(trust_env=False, timeout=90) as client:
            response = client.post(ENDPOINT, headers={'Authorization': 'Bearer ' + key,
                'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 1,
                'method': 'tools/call', 'params': {'name': 'evaluate_proposal_constraints', 'arguments': payload}})
            response.raise_for_status()
            result = response.json()['result']
            if result.get('isError'):
                raise ValidationError('云端MCP工具拒绝输入，未生成核验结果')
            value = result.get('structuredContent') or json.loads(result['content'][0]['text'])
            if value['input_sha256'] != digest:
                raise ValidationError('云端MCP输入摘要不匹配，拒绝引用结果')
            evaluation = value['evaluation']
            evaluation['_mcp'] = {'transport': 'streamable-http', 'input_sha256': digest,
                                   'tool_version': value['tool_version'], 'endpoint': ENDPOINT}
            return evaluation
    except (httpx.HTTPError, KeyError, ValueError):
        raise ValidationError('云端MCP调用未完成；未使用本地结果冒充云端返回') from None
