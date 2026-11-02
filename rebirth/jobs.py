"""Single local task slot with real progress, cancellation and explicit cloud consent."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4
from .control import RunControl
from .domain import ValidationError
from .engine import Engine
from .providers import RuleProvider, SimulationProvider, AgentArtsProvider
from .preflight import inspect_config


class Jobs:
    def __init__(self, store, config_path, allow_cloud=False, shared_lock=None):
        self.store, self.config_path, self.allow_cloud = store, config_path, allow_cloud
        self.pool, self.lock, self.entries = ThreadPoolExecutor(max_workers=1), Lock(), {}
        self.shared_lock = shared_lock or Lock()

    def start(self, data):
        merchant, mode = data.get("merchant_id"), data.get("mode")
        self.store.ledger(merchant)
        if mode not in ("rules", "simulation", "agentarts", "manual"):
            raise ValidationError("请选择本地规则、协议模拟或已配置的AgentArts")
        calls = data.get("max_calls", 64)
        if type(calls) is not int or not 1 <= calls <= 96:
            raise ValidationError("每次任务调用上限须为1到96")
        control = RunControl(max_calls=calls)
        if mode == "agentarts":
            ready = inspect_config(self.config_path, self.allow_cloud)
            if not ready["can_request_cloud"]:
                raise ValidationError("真实云调用未启用或配置不完整；请先完成接入预检")
            if data.get("cloud_data_consent") is not True:
                raise ValidationError("必须为本次任务确认向已配置云端发送经营数据及可能计费")
            provider = AgentArtsProvider(self.config_path, control=control)
        elif mode == "simulation":
            provider = SimulationProvider(data.get("simulation_case", "normal"), control)
        else:
            provider = RuleProvider()
            if mode == "manual":
                provider.mode = "manual"
                if not isinstance(data.get("draft"), dict) or not isinstance(data.get("parent_run"), str):
                    raise ValidationError("编辑方案缺少原任务和完整方案")
        engine = Engine(self.store, provider, control=control, max_rounds=0 if mode == "manual" else 2)
        job = {"id": uuid4().hex, "merchant": merchant, "mode": mode, "engine": engine, "control": control, "state": "running", "result": None}
        with self.lock:
            if any(j["state"] == "running" for j in self.entries.values()):
                raise ValidationError("已有任务执行中，请等待或取消")
            if not self.shared_lock.acquire(blocking=False):
                raise ValidationError("已有同步或异步任务执行中")
            if len(self.entries) >= 40:
                oldest = next((key for key, value in self.entries.items() if value["state"] != "running"), None)
                if oldest:
                    self.entries.pop(oldest)
            self.entries[job["id"]] = job
        def work():
            try:
                job["result"] = engine.execute(merchant, draft=data.get("draft") if mode == "manual" else None, parent_run=data.get("parent_run"))
                job["state"] = "completed"
            except Exception as exc:
                job["state"] = "cancelled" if control.cancel.is_set() else "failed"
                job["error"] = str(exc)[:1000]
                run = getattr(engine, "run_id", None)
                if run:
                    job["result"] = self.store.result(merchant, run)
            finally:
                self.shared_lock.release()
        self.pool.submit(work)
        return {"job_id": job["id"], "merchant_id": merchant, "mode": mode}

    def get(self, merchant, job_id):
        job = self.entries.get(job_id)
        if not job or job["merchant"] != merchant:
            raise ValidationError("未找到该店铺任务；服务重启后请查看分析历史")
        run = getattr(job["engine"], "run_id", None)
        events = self.store.events(merchant, run) if run else []
        return {"job_id": job_id, "state": job["state"], "mode": job["mode"], "run_id": run,
            "event_count": len(events), "last_event": {k: events[-1][k] for k in ("actor", "kind")} if events else None,
            "usage": job["control"].status(), "result": job["result"], "error": job.get("error")}

    def cancel(self, merchant, job_id):
        job = self.entries.get(job_id)
        if not job or job["merchant"] != merchant:
            raise ValidationError("未找到该店铺任务")
        if job["state"] != "running":
            raise ValidationError("任务已结束")
        job["control"].cancel.set()
        return {"state": "cancelling", "notice": "停止后续调用；正在进行的HTTP请求最多等待20秒，已发生的云费用不能撤销"}
