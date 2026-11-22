"""Run with requirements-mcp installed. Starts an isolated local MCP server."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = {**os.environ, 'PORT': str(port), 'MCP_HOST': '127.0.0.1', 'REBIRTH_MCP_TOKEN': token}
    process = subprocess.Popen([sys.executable, '-m', 'rebirth.mcp_server'], cwd=ROOT,
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}/mcp'
    try:
        async with httpx.AsyncClient(trust_env=False) as anonymous:
            for _ in range(100):
                try:
                    response = await anonymous.post(url, json={})
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(.1)
            else:
                raise RuntimeError('MCP server did not start')
            assert response.status_code == 401
        async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, trust_env=False) as client:
            async with streamable_http_client(url, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    assert [t.name for t in listing.tools] == ['evaluate_proposal_constraints']
                    ledger = json.loads((ROOT / 'examples/merchant.synthetic.json').read_text(encoding='utf-8'))
                    proposal = json.loads((ROOT / 'config/contracts.json').read_text(encoding='utf-8'))['proposal_example']
                    proposal['items'][0]['variable_cash_cost'] = '400.00'
                    result = await session.call_tool('evaluate_proposal_constraints', {'ledger': ledger, 'proposal': proposal})
                    assert not result.isError
                    data = result.structuredContent or json.loads(result.content[0].text)
                    assert 'BUDGET_EXCEEDED' in {c['code'] for c in data['evaluation']['checks']}
                    invalid = await session.call_tool('evaluate_proposal_constraints', {'ledger': {}, 'proposal': proposal})
                    assert invalid.isError
                    print(json.dumps({'transport': 'streamable-http', 'sdk_handshake': 'pass', 'discovery': 'pass',
                                      'real_budget_calculation': 'pass', 'invalid_arguments': 'pass',
                                      'unauthorized_request': 'pass', 'cloud_agent_call': 'not_tested'}, ensure_ascii=False))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    asyncio.run(main())
