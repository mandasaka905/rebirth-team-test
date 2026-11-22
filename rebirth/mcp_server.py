"""Read-only MCP adapter for the existing proposal evaluator."""

import hashlib
import json
import os
import secrets

from .domain import validate_ledger
from .tools import evaluate


def evaluate_constraints(ledger: dict, proposal: dict) -> dict:
    """核验单份经营方案的预算、库存、工时与现金底线；保留未知成本。

    ledger 必须符合经营底账契约，proposal 必须符合方案契约。
    情景计算不是销量预测或执行授权；不同方案不能叠加执行。
    """
    payload = json.dumps({"ledger": ledger, "proposal": proposal}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > 1_000_000:
        raise ValueError("经营底账与方案合计不得超过1MB")
    result = evaluate(validate_ledger(ledger), {"proposal": proposal})
    return {"tool_version": "1.0.0", "input_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "evaluation": result, "execution_authorized": False}


def create_server():
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("rebirth-constraint-check", host=os.getenv("MCP_HOST", "127.0.0.1"),
                     port=int(os.getenv("PORT", "8000")), stateless_http=True,
                     json_response=True, max_request_body_size=1_100_000)
    server.tool(name="evaluate_proposal_constraints")(evaluate_constraints)
    return server


def create_app():
    app = create_server().streamable_http_app()
    token = os.getenv('REBIRTH_MCP_TOKEN', '')
    if os.getenv('MCP_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost') and not token:
        raise RuntimeError('对外监听必须设置 REBIRTH_MCP_TOKEN')
    if token:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse

        class BearerGuard(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                actual = request.headers.get('authorization', '')
                if not secrets.compare_digest(actual.encode(), ('Bearer ' + token).encode()):
                    return JSONResponse({'error': 'unauthorized'}, status_code=401)
                return await call_next(request)

        app.add_middleware(BearerGuard)
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host=os.getenv('MCP_HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8000')))
