"""Single local task slot with real progress, cancellation and explicit cloud consent."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4
from time import monotonic
import re
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
        resume=data.get('resume_run')
        if resume is not None and (not isinstance(resume,str) or not re.fullmatch('[a-f0-9]{32}',resume)):
            raise ValidationError('请选择未完成的分析记录')
        calls = data.get("max_calls", 64)
        if type(calls) is not int or not 1 <= calls <= 96:
            raise ValidationError("每次任务调用上限须为1到96")
        rounds=data.get('max_rounds',0 if mode=='agentarts' else 2)
        if type(rounds) is not int or not 0<=rounds<=2:raise ValidationError('补充讨论次数应为0至2次')
        control = RunControl(max_calls=calls,max_seconds=600 if mode == "agentarts" else 180)
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
        engine = Engine(self.store, provider, control=control, max_rounds=0 if mode == "manual" else rounds)
        job = {"id": uuid4().hex, "merchant": merchant, "mode": mode, "engine": engine, "control": control, "state": "running", "result": None, "started": monotonic()}
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
                job["result"] = engine.execute(merchant, draft=data.get("draft") if mode == "manual" else None, parent_run=data.get("parent_run"),resume_run=data.get("resume_run"))
                job["state"] = "completed"
            except Exception as exc:
                job["state"] = "cancelled" if control.cancel.is_set() else "failed"
                job["error"] = str(exc)[:1000]
                run = getattr(engine, "run_id", None)
                if run:
                    job["result"] = self.store.result(merchant, run)
            finally:
                job['finished'] = monotonic()
                self.shared_lock.release()
        self.pool.submit(work)
        return {"job_id": job["id"], "merchant_id": merchant, "mode": mode}

    def get(self, merchant, job_id):
        job = self.entries.get(job_id)
        if not job or job["merchant"] != merchant:
            raise ValidationError("未找到该店铺任务；服务重启后请查看分析历史")
        run = getattr(job["engine"], "run_id", None)
        events = self.store.events(merchant, run) if run else []
        latest={}
        for event in events:
            if event['kind']=='phase_started':latest[event['actor']]=[event,False]
            elif event['kind']=='agent_result' and event['actor'] in latest and event['data'].get('phase')==latest[event['actor']][0]['data'].get('phase'):
                latest[event['actor']][1]=True
        active=[{'role':role,'phase':row[0]['data'].get('phase')} for role,row in latest.items() if not row[1]]
        progress={**active[-1],'output_recorded':False,'active_roles':active} if active else None
        if not progress and latest:
            event=list(latest.values())[-1][0]
            progress={'role':event['actor'],'phase':event['data'].get('phase'),'output_recorded':True,'active_roles':[]}
        return {"job_id": job_id, "state": job["state"], "mode": job["mode"], "run_id": run,
            "elapsed_seconds": max(0, round(job.get('finished', monotonic()) - job['started'])),
            "progress": progress,
            "event_count": len(events), "last_event": {k: events[-1][k] for k in ("actor", "kind")} if events else None,
            "usage": job["control"].status(), "result": job["result"], "error": job.get("error")}

    def cancel(self, merchant, job_id):
        job = self.entries.get(job_id)
        if not job or job["merchant"] != merchant:
            raise ValidationError("未找到该店铺任务")
        if job["state"] != "running":
            raise ValidationError("任务已结束")
        job["control"].cancel.set()
        return {"state": "cancelling", "notice": "已请求停止后续调用；在途请求须等待响应或连接超时，已发生的云费用不能撤销"}
