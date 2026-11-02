"""Local development API. No public listening, no cloud calls without explicit mode."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from .domain import ValidationError
from .engine import Engine
from .providers import AgentArtsProvider, ProviderError, RuleProvider
from .tools import TOOL_ARGS, dispatch
from .jobs import Jobs
from .http_features import get_route, post_route

ROOT = Path(__file__).resolve().parent.parent


def make_handler(store, config_path, *, allow_cloud=False):
    run_lock = Lock()
    jobs = Jobs(store, config_path, allow_cloud, shared_lock=run_lock)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Business records, URL query strings, and credentials never go to access logs.
            pass

        def reply(self, status, value):
            payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            try:
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # The client may refresh after a committed save. Keep the saved result;
                # do not attempt a second error response on the closed connection.
                return

        def asset(self, path):
            assets = {"/app-scene.png": ("../design-preview/dist/assets/shop-interior-v1.png", "image/png"),"/app-ui.js": ("app-ui.js", "text/javascript; charset=utf-8"),
                      "/app-ui.css": ("app-ui.css", "text/css; charset=utf-8"),"/": ("index.html", "text/html; charset=utf-8"),
                      "/social.js": ("social.js", "text/javascript; charset=utf-8"),
                      "/social.css": ("social.css", "text/css; charset=utf-8"),
                      "/community.js": ("community.js", "text/javascript; charset=utf-8"),
                      "/community.css": ("community.css", "text/css; charset=utf-8"),
                      "/agenda.js": ("agenda.js", "text/javascript; charset=utf-8"),
                      "/agenda.css": ("agenda.css", "text/css; charset=utf-8"),
                      "/app.css": ("app.css", "text/css; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/core.js": ("core.js", "text/javascript; charset=utf-8"),
                      "/features.js": ("features.js", "text/javascript; charset=utf-8"),
                      "/workbench.js": ("workbench.js", "text/javascript; charset=utf-8"),
                      "/completion.js": ("completion.js", "text/javascript; charset=utf-8"),
                      "/connections.js": ("connections.js", "text/javascript; charset=utf-8"),
                      "/features.css": ("features.css", "text/css; charset=utf-8"),
                      "/favicon.svg": ("favicon.svg", "image/svg+xml")}
            if path not in assets:
                return False
            filename, content_type = assets[path]
            try:
                payload = (ROOT / "dist" / filename).read_bytes()
            except OSError:
                self.reply(404, {"error": "界面文件缺失，请检查dist目录"})
                return True
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)
            return True

        def safe_local(self):
            expected_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in expected_hosts:
                self.reply(403, {"error": "仅接受本机Host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://"+h for h in expected_hosts}:
                self.reply(403, {"error": "不允许跨站访问本地经营数据"})
                return False
            return True

        def do_GET(self):
            if not self.safe_local():
                return
            path = urlsplit(self.path).path
            if self.asset(path):
                return
            parts = path.strip("/").split("/")
            try:
                if get_route(self, parts, store, jobs, config_path, allow_cloud):
                    return
                if parts == ["health"]:
                    self.reply(200, {"status": "ok", "cloud_connected": False, "notice": "本地服务，不代表AgentArts已连接"})
                elif parts == ["api", "tools"]:
                    self.reply(200, {"tools": TOOL_ARGS})
                elif parts == ["api", "merchants"]:
                    self.reply(200, {"merchants": store.merchants()})
                elif parts == ["api", "example"]:
                    self.reply(200, json.loads((ROOT / "examples" / "merchant.synthetic.json").read_text(encoding="utf-8")))
                elif len(parts) == 3 and parts[:2] == ["api", "merchants"]:
                    self.reply(200, store.ledger(parts[2]))
                elif len(parts) == 4 and parts[:2] == ["api", "merchants"] and parts[3] == "runs":
                    self.reply(200, {"runs": store.run_history(parts[2])})
                elif len(parts) == 4 and parts[:2] == ["api", "merchants"] and parts[3] == "questions":
                    self.reply(200, store.questions(parts[2]))
                elif len(parts) == 4 and parts[:2] == ["api", "merchants"] and parts[3] == "feedback":
                    self.reply(200, {"outcomes": store.feedback_history(parts[2])})
                elif len(parts) == 5 and parts[:2] == ["api", "merchants"] and parts[3] == "runs":
                    self.reply(200, store.result(parts[2], parts[4]))
                else:
                    self.reply(404, {"error": "接口不存在"})
            except ValidationError as exc:
                self.reply(404, {"error": str(exc)})

        def do_POST(self):
            if not self.safe_local():
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.reply(415, {"error": "仅接受application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    self.reply(413, {"error": "请求必须为1字节至1MB"})
                    return
                data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("非有限JSON数值")))
                if not isinstance(data, dict):
                    raise ValidationError("请求必须是JSON对象")
                parts = urlsplit(self.path).path.strip("/").split("/")
                if post_route(self, parts, data, store, jobs):
                    return
                if parts == ["api", "ledgers"]:
                    ledger = store.put_ledger(data)
                    self.reply(201, {"merchant_id": ledger["merchant_id"], "synthetic": ledger["synthetic"]})
                elif len(parts) == 4 and parts[:2] == ["api", "merchants"] and parts[3] == "answers":
                    self.reply(200, store.answer(parts[2], data.get("answers")))
                elif len(parts) == 4 and parts[:2] == ["api", "merchants"] and parts[3] == "feedback":
                    self.reply(201, store.record_feedback(parts[2], data))
                elif parts == ["api", "runs"]:
                    mode = data.get("mode")
                    if mode not in ("rules", "agentarts"):
                        raise ValidationError("必须显式选择rules或agentarts模式")
                    if mode == "agentarts" and not allow_cloud:
                        self.reply(403, {"error": "本地服务默认禁止云调用；当前仅支持rules，无需开通或付费"})
                        return
                    if mode == "agentarts" and data.get("cloud_data_consent") is not True:
                        raise ValidationError("真实云任务需要本次经营数据发送与计费确认")
                    if not run_lock.acquire(blocking=False):
                        self.reply(409, {"error": "另一个任务正在执行，请稍后再试"})
                        return
                    try:
                        provider = RuleProvider() if mode == "rules" else AgentArtsProvider(config_path)
                        result = Engine(store, provider).execute(data["merchant_id"])
                        self.reply(201, result)
                    finally:
                        run_lock.release()
                elif len(parts) == 4 and parts[:2] == ["api", "tools"]:
                    merchant, tool = parts[2], parts[3]
                    ledger = store.ledger(merchant)
                    self.reply(200, dispatch(ledger, tool, data, history=store.feedback_history(
                        merchant, as_of=ledger["as_of"], synthetic=ledger["synthetic"]), knowledge=store.knowledge(merchant)))
                else:
                    self.reply(404, {"error": "接口不存在"})
            except (ValueError, KeyError, TypeError, ValidationError) as exc:
                self.reply(400, {"error": str(exc)})
            except ProviderError as exc:
                self.reply(502, {"error": str(exc)})
            except Exception:
                self.reply(500, {"error": "服务内部错误；请检查本地任务记录"})

    return Handler


def serve(store, port, config_path, *, allow_cloud=False, open_browser=False):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, config_path, allow_cloud=allow_cloud))
    print(f"本地应用：http://127.0.0.1:{server.server_port}/（不调用云服务）", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
