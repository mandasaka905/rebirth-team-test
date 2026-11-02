"""Append-only local workflow extensions. Legacy runs and feedback stay intact."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from uuid import uuid4
from .domain import ValidationError, day, identifier, money, nonempty, validate_ledger
from .feedback import validate_feedback, summarize_feedback
from .knowledge import BUILTINS


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class LocalWorkflows:
    def investigations(self, merchant, as_of=None):
        self.ledger(merchant)
        with self.connect() as db:
            rows = db.execute("SELECT data FROM investigations WHERE merchant=? ORDER BY created_at,id", (merchant,)).fetchall()
        values = [json.loads(r[0]) for r in rows]
        return [v for v in values if as_of is None or day(v["checked_on"]) <= day(as_of)]

    def save_investigation(self, merchant, raw):
        ledger = self.ledger(merchant)
        if not isinstance(raw, dict):
            raise ValidationError("调查记录必须是对象")
        data = {k: raw.get(k) for k in ("hypothesis", "supporting", "counter", "next_check", "source_note", "status", "owner", "checked_on")}
        for k in ("hypothesis", "next_check", "source_note"):
            nonempty(data[k], k)
        for k in ("supporting", "counter"):
            if not isinstance(data[k], str):
                raise ValidationError("支持与反例必须是文字，可明确填写暂无")
        if data["owner"] not in ("inventory", "customer", "cash") or data["status"] not in ("unverified", "supported", "conflicted", "undetermined"):
            raise ValidationError("调查角色或状态无效")
        if day(data["checked_on"]) > day(ledger["as_of"]):
            raise ValidationError("调查核对日不可晚于底账日期")
        if data["status"] == "supported" and not data["supporting"].strip():
            raise ValidationError("有支持证据时必须填写证据；不代表已证明因果")
        if data["status"] == "conflicted" and not data["counter"].strip():
            raise ValidationError("有反例时必须填写反例")
        data["id"] = raw.get("id") or "inv_" + uuid4().hex[:16]
        identifier(data["id"])
        data["synthetic"] = ledger["synthetic"]
        with self.connect() as db:
            db.execute("INSERT INTO investigations VALUES (?,?,?,?) ON CONFLICT(merchant,id) DO UPDATE SET data=excluded.data", (merchant, data["id"], dump(data), datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT INTO investigation_events(merchant,id,data,created_at) VALUES (?,?,?,?)", (merchant, data["id"], dump(data), datetime.now(timezone.utc).isoformat()))
        return data

    def knowledge(self, merchant):
        self.ledger(merchant)
        with self.connect() as db:
            rows = db.execute("SELECT data FROM knowledge_documents WHERE merchant=? ORDER BY created_at,id", (merchant,)).fetchall()
        return deepcopy(BUILTINS) + [json.loads(r[0]) for r in rows]

    def add_knowledge(self, merchant, data):
        self.ledger(merchant)
        if not isinstance(data, dict):
            raise ValidationError("资料必须是对象")
        doc = {k: nonempty(data.get(k), k) for k in ("title", "content", "source")}
        if len(doc["title"]) > 160 or len(doc["source"]) > 2000:
            raise ValidationError("资料标题或来源过长")
        doc["id"] = "doc_" + uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO knowledge_documents VALUES (?,?,?,?)", (merchant, doc["id"], dump(doc), datetime.now(timezone.utc).isoformat()))
        return doc

    def put_period(self, merchant, raw):
        data = self.ledger(merchant)
        if not isinstance(raw, dict):
            raise ValidationError("经营期间必须是对象")
        p = deepcopy(raw)
        source = nonempty(p.pop("source_note", None), "期间来源说明")
        sid = "period_" + uuid4().hex[:16]
        data["sources"][sid] = source
        p["id"] = p.get("id") or "period_" + uuid4().hex[:16]
        p["source_id"] = sid
        data["operating_periods"] = [x for x in data.get("operating_periods", []) if x["id"] != p["id"]] + [p]
        return self.put_ledger(data)

    def feedback_journal(self, merchant):
        identifier(merchant)
        with self.connect() as db:
            original = db.execute("SELECT data,summary,created_at FROM feedback WHERE merchant=?", (merchant,)).fetchall()
            updates = db.execute("SELECT data,summary,created_at FROM feedback_updates WHERE merchant=?", (merchant,)).fetchall()
        entries = [{"data": json.loads(r[0]), "summary": json.loads(r[1]), "created_at": r[2]} for r in [*original, *updates]]
        return sorted(entries, key=lambda x: (x["data"]["period_end"], x["created_at"]))

    def latest_feedback(self, merchant, *, as_of=None, synthetic=None, limit=5):
        entries = self.feedback_journal(merchant)
        latest = {}
        for e in entries:
            d = e["data"]
            if as_of is not None and day(d["period_end"]) > day(as_of):
                continue
            if synthetic is not None and d["synthetic"] != synthetic:
                continue
            latest[(d["run_id"], d["proposal_id"], d["proposal_version"])] = e
        return [e["summary"] for e in sorted(latest.values(), key=lambda x: (x["data"]["period_end"], x["created_at"]), reverse=True)[:max(1,min(int(limit),50))]]

    def advance_feedback(self, merchant, raw):
        if not isinstance(raw, dict) or raw.get("operation") not in ("checkpoint", "correction"):
            raise ValidationError("请选择新检查点或更正")
        row = self.check(merchant, raw.get("run_id"))
        if row["status"] in ("running", "failed", "cancelled", "interrupted"):
            raise ValidationError("任务未完成")
        result, snapshot = json.loads(row["result"]), json.loads(row["snapshot"])
        proposal = next((x["proposal"] for x in result.get("proposals", []) if x["proposal"]["id"] == raw.get("proposal_id")), None)
        if not proposal:
            raise ValidationError("未找到方案")
        data = validate_feedback(raw, proposal, snapshot)
        nonempty(data.get("change_reason"), "本次记录或更正原因")
        group = [e for e in self.feedback_journal(merchant) if e["data"]["run_id"] == data["run_id"] and e["data"]["proposal_id"] == data["proposal_id"] and e["data"]["proposal_version"] == data["proposal_version"]]
        current = group[-1]["summary"] if group else None
        if not current or data.get("supersedes_id") != current["feedback_id"]:
            raise ValidationError("记录已变化，请刷新并基于最新检查点填写")
        previous = next(e["data"] for e in self.feedback_journal(merchant) if e["data"]["id"] == current["feedback_id"])
        if data["operation"] == "correction":
            if data["period_end"] != previous["period_end"]:
                raise ValidationError("更正保持截止日不变；延长期间请用新检查点")
        else:
            if day(data["period_end"]) <= day(previous["period_end"]):
                raise ValidationError("新检查点的截止日必须晚于上一期")
            for key in (("fixed_spend", "hours_spent", "procurement_paid") if proposal.get("procurements") else ("fixed_spend", "hours_spent")):
                if money(data[key]) < money(previous[key]):
                    raise ValidationError("累计支出或工时不能减少；录错请更正")
            old_items = {x["sku"]: x for x in previous["items"]}
            for x in data["items"]:
                for key in ("units_sold", "units_returned", "units_returned_resellable", "cash_received", "refund_paid", "variable_spend"):
                    if money(x[key]) < money(old_items[x["sku"]].get(key, 0)):
                        raise ValidationError("新检查点须填从开始日累计值，不能减少；录错请更正")
        summary = summarize_feedback(data, proposal, snapshot)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM feedback WHERE merchant=? AND id=?", (merchant, data["id"])).fetchone() or db.execute("SELECT 1 FROM feedback_updates WHERE merchant=? AND id=?", (merchant, data["id"])).fetchone():
                raise ValidationError("反馈ID已有记录，不能复用")
            used = db.execute("SELECT 1 FROM feedback_updates WHERE merchant=? AND supersedes=?", (merchant, data["supersedes_id"])).fetchone()
            if used:
                raise ValidationError("上一记录已有后续版本，请刷新")
            db.execute("INSERT INTO feedback_updates VALUES (?,?,?,?,?,?)", (merchant, data["id"], data["supersedes_id"], dump(data), dump(summary), datetime.now(timezone.utc).isoformat()))
        return summary

    def experiments(self, merchant):
        self.ledger(merchant)
        with self.connect() as db:
            rows = db.execute("SELECT data FROM experiments WHERE merchant=? ORDER BY created_at DESC", (merchant,)).fetchall()
        values = [json.loads(r[0]) for r in rows]
        for e in values:
            feedback = next((x for x in self.latest_feedback(merchant, limit=50) if x["run_id"] == e["run_id"] and x["proposal_id"] == e["proposal_id"] and x["proposal_version"] == e["proposal_version"]), None)
            e["review_alerts"] = []
            if feedback and money(feedback["actual_trial_spend"]) >= money(e["stop_budget"]):
                e["review_alerts"].append("累计试验支出已达到登记停止预算；请人工停止新增投入并核对，不自动执行经营动作")
            if day(e["end_date"]) < datetime.now().date() and e["status"] == "active":
                e["review_alerts"].append("已超过登记截止日，请复盘或更新状态")
        return values

    def save_experiment(self, merchant, raw):
        if not isinstance(raw, dict) or raw.get("acknowledged") is not True:
            raise ValidationError("请确认只是登记计划，不会自动联系顾客或执行交易")
        report = self.result(merchant, raw.get("run_id"))
        entry = next((x for x in (report.get("result") or {}).get("proposals", []) if x["proposal"]["id"] == raw.get("proposal_id") and x["proposal"]["version"] == raw.get("proposal_version")), None)
        if not entry:
            raise ValidationError("方案版本不存在")
        with self.connect() as db:
            existing = db.execute("SELECT 1 FROM experiments WHERE merchant=? AND id=?", (merchant, "trial_" + report["run_id"] + "_" + entry["proposal"]["id"])).fetchone()
        closing = bool(existing) and raw.get("status") in ("paused", "stopped", "completed")
        if not closing and (report["ledger_changed"] or report.get("context_changed") or not entry["evaluation"]["constraint_pass"] or entry.get("objections")):
            raise ValidationError("资料已变化或仍有硬约束、异议，不能登记为可开展试验")
        snapshot = json.loads(self.check(merchant, report["run_id"])["snapshot"])
        if not closing and not snapshot["synthetic"] and (not snapshot["merchant_confirmed"] or not all(snapshot["completeness"].values()) or not entry["proposal"]["costs_confirmed"]):
            raise ValidationError("真实资料需先确认账目完整及方案费用")
        data = {k: raw.get(k) for k in ("run_id", "proposal_id", "proposal_version", "hypothesis", "success_metric", "end_date", "stop_budget", "status", "source_note")}
        for k in ("hypothesis", "success_metric", "source_note"):
            nonempty(data[k], k)
        if data["status"] not in ("planned", "active", "paused", "stopped", "completed"):
            raise ValidationError("试验状态无效")
        p = entry["proposal"]
        if not day(p["spend_date"]) <= day(data["end_date"]) <= day(snapshot["as_of"]) + timedelta(days=30):
            raise ValidationError("试验截止日须在方案支出日至底账后30天内")
        if money(data["stop_budget"]) > money(snapshot["max_trial_budget"]):
            raise ValidationError("停止预算不可超过商户试验投入上限")
        if not closing and money(data["stop_budget"]) < money(entry["evaluation"]["trial_cash_commitment"]):
            raise ValidationError("停止预算小于方案申报支出，请先修改方案")
        from .linkage import resolve
        data["model_refs"] = deepcopy(p.get("model_refs", []))
        data["model_snapshots"] = resolve(snapshot, p) if p.get("model_refs") else []
        data["synthetic"] = snapshot["synthetic"]
        data["id"] = "trial_" + data["run_id"] + "_" + data["proposal_id"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT data FROM experiments WHERE merchant=?", (merchant,)).fetchall()
            old = next((json.loads(x[0]) for x in active if json.loads(x[0])["id"] == data["id"]), None)
            if old and old["status"] in ("stopped", "completed") and data["status"] in ("planned", "active"):
                raise ValidationError("已停止或复盘的试验不直接重复投入；请先建新方案并复核")
            if data["status"] == "active" and any(json.loads(x[0])["status"] == "active" and json.loads(x[0])["id"] != data["id"] for x in active):
                raise ValidationError("当前已有开展中的试验；先暂停或完成，避免叠加预算和库存")
            db.execute("INSERT INTO experiments VALUES (?,?,?,?) ON CONFLICT(merchant,id) DO UPDATE SET data=excluded.data", (merchant, data["id"], dump(data), datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT INTO experiment_events(merchant,id,data,created_at) VALUES (?,?,?,?)", (merchant, data["id"], dump(data), datetime.now(timezone.utc).isoformat()))
        return data

    def export_bundle(self, merchant):
        with self.connect() as db:
            runs = db.execute("SELECT * FROM runs WHERE merchant=?", (merchant,)).fetchall()
            events = db.execute("SELECT * FROM events WHERE merchant=? ORDER BY seq", (merchant,)).fetchall()
            trials = db.execute("SELECT data FROM experiment_events WHERE merchant=? ORDER BY seq", (merchant,)).fetchall()
            investigations = db.execute("SELECT data FROM investigation_events WHERE merchant=? ORDER BY seq", (merchant,)).fetchall()
        return {"format": "rebirth-local-export-v1", "notice": "包含经营敏感资料，只下载到本机，勿公开上传；密钥和连接配置不在导出中",
            "workbench_history": self.records(merchant), "ledger": self.ledger(merchant), "knowledge": self.knowledge(merchant), "runs": [dict(r) for r in runs],
            "events": [dict(r) for r in events], "feedback_journal": self.feedback_journal(merchant),
            "experiment_events": [json.loads(r[0]) for r in trials], "investigation_events": [json.loads(r[0]) for r in investigations]}
