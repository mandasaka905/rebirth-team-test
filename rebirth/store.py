"""SQLite event journal. All records are scoped to a merchant and immutable run."""

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import sqlite3
from uuid import uuid4

from .domain import ValidationError, identifier, validate_ledger
from .workflows import LocalWorkflows
from .workbench import Workbench
from .completion import CompletionWorkflows
from .agenda import AgendaWorkflows
from .community import CommunityWorkflows
from .social import SocialWorkflows


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store(SocialWorkflows, CommunityWorkflows, AgendaWorkflows, CompletionWorkflows, Workbench, LocalWorkflows):
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledgers'").fetchone() and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workbench_records'").fetchone():
                # Back up an existing pre-workbench database before additive migration, including WAL data.
                previous_version = "v05" if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='feedback_updates'").fetchone() else "v04"
                backup_path = Path(path).parent / "backups" / (Path(path).stem + "-before-" + previous_version + "-" + uuid4().hex[:12] + ".sqlite3")
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                target = sqlite3.connect(backup_path)
                try:
                    db.backup(target)
                finally:
                    target.close()
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workbench_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, merchant TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(merchant,id));
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS ledgers (
                    merchant TEXT PRIMARY KEY, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, merchant TEXT NOT NULL, mode TEXT NOT NULL,
                    snapshot TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL,
                    merchant TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
                    data TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_run ON events(merchant,run,seq);
                CREATE TABLE IF NOT EXISTS merchant_answers (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, merchant TEXT NOT NULL,
                    data TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    merchant TEXT NOT NULL, id TEXT NOT NULL, run TEXT NOT NULL,
                    proposal TEXT NOT NULL, version INTEGER NOT NULL,
                    period_end TEXT NOT NULL, synthetic INTEGER NOT NULL,
                    data TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(merchant,id), UNIQUE(merchant,run,proposal,version)
                );
                CREATE TABLE IF NOT EXISTS knowledge_documents (merchant TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(merchant,id));
                CREATE TABLE IF NOT EXISTS feedback_updates (merchant TEXT NOT NULL,id TEXT NOT NULL,supersedes TEXT NOT NULL,data TEXT NOT NULL,summary TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(merchant,id),UNIQUE(merchant,supersedes));
                CREATE TABLE IF NOT EXISTS experiments (merchant TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(merchant,id));
                CREATE TABLE IF NOT EXISTS experiment_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,merchant TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS investigations (merchant TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(merchant,id));
                CREATE TABLE IF NOT EXISTS investigation_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,merchant TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def put_ledger(self, data):
        if not isinstance(data,dict):raise ValidationError("经营底账必须为对象")
        data=deepcopy(data);expected=data.pop("_expected_digest",None)
        identifier(data.get("merchant_id"))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT data FROM ledgers WHERE merchant=?",(data["merchant_id"],)).fetchone()
            previous=json.loads(row[0]) if row else {}
            if expected is not None:
                actual=hashlib.sha256(json.dumps(previous,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
                if expected!=actual:raise ValidationError("底账已被其他操作更新，请刷新后重新编辑，未覆盖任何资料")
            if previous:
                if previous["synthetic"]!=data.get("synthetic"):raise ValidationError("同一店铺的合成标记不能更改；请另建真实资料店铺，不把示例改成真实成果")
                for key in ("operating_periods","business_models","accounts","customer_cohorts","supply_options","sales_records","sales_window","sales_windows","field_sources"):
                    if key not in data and key in previous:data[key]=deepcopy(previous[key])
                data["sources"]={**previous["sources"],**data.get("sources",{})}
            data=validate_ledger(data)
            from .linkage import normalize_versions
            data=normalize_versions(previous,data)
            from .cohorts import prevent_redefinition
            prevent_redefinition(previous,data)
            db.execute("INSERT INTO ledgers VALUES (?,?) ON CONFLICT(merchant) DO UPDATE SET data=excluded.data",(data["merchant_id"],dumps(data)))
        return data

    def ledger(self, merchant):
        identifier(merchant)
        with self.connect() as db:
            row = db.execute("SELECT data FROM ledgers WHERE merchant=?", (merchant,)).fetchone()
        if not row:
            raise ValidationError("未找到该商户底账")
        return json.loads(row[0])

    def merchants(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM ledgers ORDER BY merchant").fetchall()
        return [{k: ledger[k] for k in ("merchant_id", "name", "as_of", "synthetic")}
                for row in rows for ledger in [json.loads(row[0])]]

    def run_history(self, merchant, limit=20):
        self.ledger(merchant)
        with self.connect() as db:
            rows = db.execute("SELECT id,status,mode,created_at FROM runs WHERE merchant=? ORDER BY created_at DESC LIMIT ?",
                              (merchant, max(1, min(int(limit), 50)))).fetchall()
        return [dict(row) for row in rows]

    def questions(self, merchant):
        from .readiness import questions
        return questions(self.ledger(merchant))

    def answer(self, merchant, entries):
        from .readiness import apply_answers, questions
        identifier(merchant)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM ledgers WHERE merchant=?", (merchant,)).fetchone()
            if not row:
                raise ValidationError("未找到该商户底账")
            updated, audit = apply_answers(json.loads(row[0]), entries)
            db.execute("UPDATE ledgers SET data=? WHERE merchant=?", (dumps(updated), merchant))
            db.execute("INSERT INTO merchant_answers(merchant,data,created_at) VALUES (?,?,?)",
                       (merchant, dumps(audit), datetime.now(timezone.utc).isoformat()))
        return {"merchant_id": merchant, "accepted": audit, "readiness": questions(updated)}

    def record_feedback(self, merchant, raw):
        from .feedback import validate_feedback, summarize_feedback
        if not isinstance(raw, dict) or not isinstance(raw.get("run_id"), str):
            raise ValidationError("反馈缺少run_id")
        if raw.get("operation") is not None:
            raise ValidationError("检查点或更正请使用feedback-update接口")
        row = self.check(merchant, raw["run_id"])
        if row["status"] in ("running", "failed") or not row["result"]:
            raise ValidationError("只有已完成并保留方案的任务可以记录反馈")
        result = json.loads(row["result"])
        proposal = next((x["proposal"] for x in result.get("proposals", [])
                         if x["proposal"]["id"] == raw.get("proposal_id")), None)
        if not proposal:
            raise ValidationError("该任务不存在指定方案")
        snapshot = json.loads(row["snapshot"])
        data = validate_feedback(raw, proposal, snapshot)
        summary = summarize_feedback(data, proposal, snapshot)
        try:
            with self.connect() as db:
                if db.execute("SELECT 1 FROM feedback_updates WHERE merchant=? AND id=?", (merchant, data["id"])).fetchone():
                    raise ValidationError("反馈ID已有记录")
                db.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    merchant, data["id"], data["run_id"], data["proposal_id"], data["proposal_version"],
                    data["period_end"], int(data["synthetic"]), dumps(data), dumps(summary),
                    datetime.now(timezone.utc).isoformat()))
        except sqlite3.IntegrityError as exc:
            raise ValidationError("反馈ID或该方案版本已有反馈，不能重复入账；原始记录保留") from exc
        return summary

    def backup(self, destination):
        target_path = Path(destination)
        if target_path.exists():
            raise ValidationError("备份目标已存在，不覆盖原文件")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(target_path)
        try:
            with self.connect() as db:
                db.backup(target)
        finally:
            target.close()
        return {"saved": str(target_path.resolve()), "notice": "完整SQLite数据备份，不含连接配置或凭证；包含经营敏感资料，请只留本机"}

    def feedback_history(self, merchant, *, as_of=None, synthetic=None, limit=5):
        return self.latest_feedback(merchant, as_of=as_of, synthetic=synthetic, limit=limit)

    def legacy_feedback_history(self, merchant, *, as_of=None, synthetic=None, limit=5):
        identifier(merchant)
        clauses, params = ["merchant=?"], [merchant]
        if as_of is not None:
            from .domain import day
            day(as_of)
            clauses.append("period_end<=?")
            params.append(as_of)
        if synthetic is not None:
            clauses.append("synthetic=?")
            params.append(int(synthetic))
        params.append(max(1, min(int(limit), 50)))
        with self.connect() as db:
            rows = db.execute("SELECT summary FROM feedback WHERE "+" AND ".join(clauses)+
                              " ORDER BY period_end DESC,created_at DESC LIMIT ?", params).fetchall()
        return [json.loads(r[0]) for r in rows]

    def new_run(self, merchant, mode):
        snapshot = self.ledger(merchant)
        run = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (
                run, merchant, mode, dumps(snapshot), "running", None,
                datetime.now(timezone.utc).isoformat()))
        return run, snapshot

    def check(self, merchant, run):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND merchant=?", (run, merchant)).fetchone()
        if not row:
            raise ValidationError("未找到该商户的协作任务")
        return dict(row)

    def event(self, merchant, run, actor, kind, data):
        self.check(merchant, run)
        with self.connect() as db:
            cursor = db.execute("INSERT INTO events(run,merchant,actor,kind,data,created_at) VALUES (?,?,?,?,?,?)",
                (run, merchant, actor, kind, dumps(data), datetime.now(timezone.utc).isoformat()))
            return f"e{cursor.lastrowid}"

    def events(self, merchant, run):
        self.check(merchant, run)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE merchant=? AND run=? ORDER BY seq", (merchant, run)).fetchall()
        return [{"id": f"e{r['seq']}", "actor": r["actor"], "kind": r["kind"],
                 "data": json.loads(r["data"])} for r in rows]

    def finish(self, merchant, run, result):
        self.check(merchant, run)
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?, result=? WHERE id=? AND merchant=?",
                       (result["status"], dumps(result), run, merchant))

    def interrupt_orphaned_runs(self):
        """Called once when a hosted tenant is first opened by a new server process."""
        with self.connect() as db:
            rows = db.execute("SELECT id,merchant FROM runs WHERE status='running'").fetchall()
            for row in rows:
                result = {"status": "interrupted", "error_message": "服务进程已重新启动，分析未完成；已完成步骤保留，可确认后继续。"}
                db.execute("UPDATE runs SET status='interrupted',result=? WHERE id=? AND status='running'", (dumps(result),row["id"]))
                db.execute("INSERT INTO events(run,merchant,actor,kind,data,created_at) VALUES(?,?,?,?,?,?)",
                    (row["id"],row["merchant"],"host","run_interrupted",dumps({"reason":"server_restarted"}),datetime.now(timezone.utc).isoformat()))
        return len(rows)

    def result(self, merchant, run):
        row = self.check(merchant, run)
        snapshot = json.loads(row["snapshot"])
        events = self.events(merchant, run)
        contexts = {e["kind"]: e["data"] for e in events if e["kind"] in ("knowledge_snapshot", "investigation_snapshot", "history_snapshot")}
        changed = (contexts.get("knowledge_snapshot", {}).get("documents") != self.knowledge(merchant)
            or contexts.get("investigation_snapshot", {}).get("cards") != self.investigations(merchant, as_of=snapshot["as_of"])
            or contexts.get("history_snapshot", {}).get("outcomes") != self.feedback_history(merchant, as_of=snapshot["as_of"], synthetic=snapshot["synthetic"])
            or contexts.get("history_snapshot", {}).get("experiment_reviews", []) != self.research_evidence(merchant, snapshot["as_of"]))
        return {"run_id": run, "merchant_id": merchant, "mode": row["mode"],
                "ledger_snapshot": snapshot,
                "context_changed": changed,
                "ledger_changed": snapshot != self.ledger(merchant), "ledger_as_of": snapshot["as_of"],
                "status": row["status"], "result": json.loads(row["result"]) if row["result"] else None,
                "events": events}
