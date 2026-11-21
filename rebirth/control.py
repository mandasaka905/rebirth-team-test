"""Per-task request/text/time bounds, not a provider billing guarantee."""
from threading import Event, Lock
from time import monotonic
from pathlib import Path
from datetime import datetime, timezone
import json
import os


class RunCancelled(RuntimeError):
    pass


class LimitExceeded(RuntimeError):
    pass


class RunControl:
    def __init__(self, *, max_calls=64, max_input_bytes=2000000, max_output_bytes=300000, max_seconds=180, cancel=None, journal_path=None):
        self.max_calls, self.max_input_bytes, self.max_output_bytes = max_calls, max_input_bytes, max_output_bytes
        self.max_seconds, self.cancel = max_seconds, cancel or Event()
        self.started, self.lock = monotonic(), Lock()
        self.calls = self.input_bytes = self.output_bytes = 0
        self.journal_path = Path(journal_path) if journal_path is not None else None
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            # A new task must not reset an existing task's usage record.
            with self.journal_path.open('x', encoding='utf-8') as f:
                json.dump(self._snapshot('initialized'), f, ensure_ascii=False)

    def _snapshot(self, event):
        return {**self.status(), 'owner_pid':os.getpid(), 'event':event,
                'updated_at':datetime.now(timezone.utc).isoformat(),
                'billing_notice':'请求计数包含发送前预留及可能在途请求，不是平台已计费次数或账单。'}

    def _persist(self, event):
        if self.journal_path:
            tmp = self.journal_path.with_suffix(self.journal_path.suffix+'.tmp')
            with tmp.open('w',encoding='utf-8') as f:
                json.dump(self._snapshot(event),f,ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp,self.journal_path)

    def check(self):
        if self.cancel.is_set():
            raise RunCancelled("任务已取消；已发出的云请求不能撤销，后续请求不会继续")
        if monotonic() - self.started > self.max_seconds:
            raise LimitExceeded("达到任务总时长上限")

    def reserve(self, size):
        self.check()
        with self.lock:
            if self.calls >= self.max_calls or self.input_bytes + size > self.max_input_bytes:
                raise LimitExceeded("达到调用次数或累计输入文本上限")
            self.calls += 1
            self.input_bytes += size
            self._persist('reserved_before_send')

    def receive(self, size):
        with self.lock:
            self.output_bytes += size
            self._persist('received')
            if self.output_bytes > self.max_output_bytes:
                raise LimitExceeded("达到累计输出文本上限")
        self.check()

    def status(self):
        return {"calls": self.calls, "input_bytes": self.input_bytes, "output_bytes": self.output_bytes,
            "max_calls": self.max_calls, "max_input_bytes": self.max_input_bytes, "max_output_bytes": self.max_output_bytes,
            "max_seconds": self.max_seconds, "notice": "次数和文本字节上限不是精确Token或人民币额度；取消不能追回已发生费用，云端仍须单独设额度。"}
