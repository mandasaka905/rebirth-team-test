"""Managed Agents protocol; credentials stay in headers and permissions are never auto-granted."""
import json
from time import monotonic, time
from urllib.parse import urlsplit
from uuid import uuid4


def connection_error(exc):
    """Report bounded diagnostics, never exception text, headers, bodies, or keys."""
    import ssl
    import socket
    status=getattr(getattr(exc,'response',None),'status_code',None)
    if isinstance(status,int):
        hints={401:'网关鉴权未通过，需核对该运行时绑定的入站调用密钥；这不是模型推理报错',
            403:'网关拒绝访问，需检查运行时权限或访问限制',
            404:'运行时路径未找到，需核对运行时名称和访问地址',
            429:'网关限流或额度限制',502:'网关暂时无法连接后端运行时',503:'运行时暂不可用'}
        return f'WebSocket握手失败（HTTP {status}）：'+hints.get(status,'网关未接受升级连接')+'；未自动重试'
    if isinstance(exc,ssl.SSLCertVerificationError):return 'TLS证书校验未通过；未关闭安全校验'
    if isinstance(exc,ssl.SSLError):return 'TLS加密握手失败；尚未进入API Key鉴权'
    if isinstance(exc,socket.gaierror):return '域名解析失败；尚未进入API Key鉴权'
    if isinstance(exc,TimeoutError):return '连接超时；不能据此判断API Key是否有效'
    if isinstance(exc,UnicodeError):return '请求头包含不能发送的字符，请检查复制内容是否混入中文说明'
    if isinstance(exc,OSError):return '网络连接失败；尚未确认API Key是否有效'
    return '连接阶段失败（'+type(exc).__name__+'）；未显示原始响应或密钥'


def invoke(url, token, session, envelope, control, *, connector=None, observer=None):
    from .providers import ProviderError, extract_action
    if connector is None:
        try:
            from websockets.sync.client import connect
        except ImportError:
            raise ProviderError('请先安装 requirements-agentarts.txt，尚未发送云请求') from None
        connector = connect
    parts = urlsplit(url)
    if parts.scheme != 'wss':
        raise ProviderError('Managed Agents须使用加密wss连接，不通过明文ws发送密钥')
    query = json.dumps(envelope, ensure_ascii=False)
    request = json.dumps({'request_id':uuid4().hex, 'channel_id':'officeclaw',
        'session_id':'session_default', 'chat_id':session, 'req_method':'chat.send',
        'params':{'query':query, 'mode':'agent.plan', 'interactive_ask':False},
        'metadata':{'user_id':session}, 'is_stream':True, 'timestamp':time()}, ensure_ascii=False)
    control.reserve(len(request.encode('utf-8')))
    headers = {'Authorization':'Bearer '+token, 'x-hw-agentarts-session-id':session,
        'X-HW-AgentArts-Claw-User-Id':session, 'X-HW-AgentGateway-Chat-Id':session}
    deadline = monotonic()+180
    wire_bytes=0
    streamed_bytes=0
    def count_final(value):
        # Final content commonly repeats all deltas. Charge only the extra bytes.
        size=len((value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)).encode('utf-8'))
        control.receive(max(0,size-streamed_bytes))
        return extract_action(value)
    def receive(ws):
        nonlocal wire_bytes
        while True:
            control.check()
            if monotonic() >= deadline:
                raise ProviderError('Managed Agents响应超时；未自动重试')
            try:
                raw=ws.recv(timeout=min(1, max(0.01, deadline-monotonic())))
                break
            except TimeoutError:
                continue
        if not isinstance(raw, (str, bytes)):
            raise ProviderError('Managed Agents返回了不支持的消息')
        wire_bytes+=len(raw.encode('utf-8')) if isinstance(raw,str) else len(raw)
        if wire_bytes>8*1024*1024:
            raise ProviderError('平台传输消息超过8MB，已停止接收；这不是API Key错误')
        control.check()
        try: frame=json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProviderError('Managed Agents返回的消息不是有效JSON') from None
        if not isinstance(frame,dict): raise ProviderError('Managed Agents消息结构不正确')
        if observer is not None:observer(frame)
        if frame.get('response_kind')=='e2a.error' or frame.get('status') in ('failed','error'):
            raise ProviderError('Managed Agents执行失败；未记录可能包含敏感内容的原始消息')
        if frame.get('tag')=='TOOL_PERMISSION' and frame.get('decision')=='ASK':
            raise ProviderError('云端请求工具授权；已中止，未自动授权')
        return frame
    try:
        ws=connector(url, additional_headers=headers, origin='https://'+parts.netloc,
            compression=None, open_timeout=40, close_timeout=2, max_size=4194304, proxy=None)
    except Exception as exc:
        raise ProviderError(connection_error(exc)) from None
    try:
        while True:
            frame=receive(ws)
            if frame.get('type')=='event' and frame.get('event')=='connection.ack': break
        ws.send(request)
        fragments=[]
        while True:
            frame=receive(ws)
            body=frame.get('body') or {}
            payload=frame.get('payload') or {}
            if not isinstance(body,dict) or not isinstance(payload,dict):
                raise ProviderError('Managed Agents消息体格式错误')
            if frame.get('is_final'):
                if frame.get('status') not in (None,'succeeded'):
                    raise ProviderError('Managed Agents未成功完成')
                return count_final((body.get('result') or {}).get('content',''))
            event=body.get('event_type','chat.delta') if frame.get('response_kind') else payload.get('event_type')
            if event=='chat.ask_user_question':
                raise ProviderError('云端需要人工补充信息；已中止，未代选答案')
            if event=='chat.error': raise ProviderError('Managed Agents执行失败')
            if event=='chat.final':
                # Current Managed Agents can send a terminal chunk with delta,
                # rather than an e2a.complete result or legacy payload.content.
                value=body.get('delta') if frame.get('response_kind') else payload.get('content')
                if isinstance(value,dict) and 'content' in value:value=value['content']
                if value is None or value=='':value=''.join(fragments)
                return count_final(value)
            if event=='chat.delta':
                delta=body.get('delta') if frame.get('response_kind') else payload.get('content')
                if isinstance(delta,dict):delta=delta.get('content')
                if isinstance(delta,str):
                    size=len(delta.encode('utf-8'));control.receive(size);streamed_bytes+=size
                    fragments.append(delta)
            if event=='chat.done' or frame.get('is_complete') or frame.get('type')=='done':
                return extract_action(''.join(fragments))
    except ProviderError:
        raise
    except Exception as exc:
        from .control import LimitExceeded, RunCancelled
        if isinstance(exc,(LimitExceeded,RunCancelled)): raise
        raise ProviderError('Managed Agents通信中断或响应格式错误；未自动重试') from None
    finally:
        try: ws.close()
        except Exception: pass
