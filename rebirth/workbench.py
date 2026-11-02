"""Persistent, source-linked planning records. Changes never silently post to the ledger."""
from copy import deepcopy
from datetime import datetime, timezone, date, timedelta
import json
from uuid import uuid4
from .domain import ValidationError, day, nonempty, validate_ledger, amount, money
from .planning import assess_models, optimize
from .accounting import reconcile, parse_csv
from .research import validate_design, evaluate_design


class Workbench:
    def records(self, merchant, kind=None):
        self.ledger(merchant)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM workbench_records WHERE merchant=? ORDER BY seq", (merchant,)).fetchall()
        return [{"id": r["id"], "kind": r["kind"], "data": json.loads(r["data"]), "created_at": r["created_at"]}
                for r in rows if kind is None or r["kind"] == kind]

    def append_record(self, merchant, kind, data):
        self.ledger(merchant)
        rid = "wb_" + uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",
                       (merchant, rid, kind, json.dumps(data, ensure_ascii=False, allow_nan=False), datetime.now(timezone.utc).isoformat()))
        return {"id": rid, "data": data}

    def save_section(self, merchant, section, value, source_note):
        if section not in ("business_models", "accounts", "customer_cohorts", "supply_options"):
            raise ValidationError("不支持的经营资料区")
        nonempty(source_note, "本次变更来源")
        old = self.ledger(merchant)
        updated = deepcopy(old); updated[section] = deepcopy(value)
        from .linkage import normalize_versions
        updated = normalize_versions(old, updated)
        updated = validate_ledger(updated)
        if section == "customer_cohorts":
            from .cohorts import signature
            previous = {r["cohort_id"]:signature(r) for r in old.get("customer_cohorts", [])}
            if any(r["cohort_id"] in previous and signature(r) != previous[r["cohort_id"]] for r in updated[section]):
                raise ValidationError("已保存固定客群的定义或分母不可改写；请另建客群代号")
        value = deepcopy(updated[section])
        raw = json.dumps(updated, ensure_ascii=False, allow_nan=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT data FROM ledgers WHERE merchant=?", (merchant,)).fetchone()
            if json.loads(current[0]) != old:
                raise ValidationError("底账同时被修改，请刷新后再保存")
            db.execute("UPDATE ledgers SET data=? WHERE merchant=?", (raw, merchant))
            change = {"section": section, "before": old.get(section), "after": value, "source_note": source_note}
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",
                       (merchant, "wb_"+uuid4().hex, "section_change", json.dumps(change, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return self.workbench(merchant)

    def import_accounts(self, merchant, raw, *, commit=False):
        ledger = self.ledger(merchant)
        kind = raw.get("kind")
        rows = parse_csv(raw.get("csv"), kind)
        accounts = deepcopy(ledger.get("accounts", {"purchases": [], "cash_entries": [], "opening": None}))
        accounts.setdefault(kind, []).extend(rows)
        checked = deepcopy(ledger); checked["accounts"] = accounts
        validate_ledger(checked)
        if commit:
            if raw.get("confirmed") is not True:
                raise ValidationError("请先预览并确认整批CSV")
            self.save_section(merchant, "accounts", accounts, nonempty(raw.get("source_note"), "导入来源"))
        return {"rows": rows, "committed": commit, "reconciliation": reconcile(checked),
                "notice": "整批校验与保存，重复ID或原单号拒绝；不自动更改底账余额、库存或应付款。"}

    def select_portfolio(self, merchant, raw):
        ledger = self.ledger(merchant)
        refs = raw.get("candidates")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 10:
            raise ValidationError("请选择1到10个候选")
        entries, used = [], set()
        for ref in refs:
            if not isinstance(ref, dict):
                raise ValidationError("候选引用无效")
            report = self.result(merchant, ref.get("run_id"))
            if report["ledger_changed"] or report["context_changed"] or (report["result"] or {}).get("status") in ("failed", "cancelled", "running", None):
                raise ValidationError("候选任务未完成或资料已变化，请先重新分析")
            row = next((x for x in report["result"].get("proposals", []) if x["proposal"]["id"] == ref.get("proposal_id") and x["proposal"]["version"] == ref.get("version")), None)
            if row is None:
                raise ValidationError("候选精确版本不存在")
            identity = (report["run_id"], row["proposal"]["id"], row["proposal"]["version"])
            if identity in used:
                raise ValidationError("同一方案版本不可重复入选")
            used.add(identity)
            entries.append({**deepcopy(row), "key": ref.get("key"), "requires": ref.get("requires", []), "exclusive_group": ref.get("exclusive_group", "")})
        if type(raw.get("independent", False)) is not bool:
            raise ValidationError("组合需求确认必须为布尔值")
        result = optimize(ledger, entries, independent=raw.get("independent", False), objective=raw.get("objective", "contribution"), budget=raw.get("budget"))
        saved = self.append_record(merchant, "portfolio", {"request": raw, "ledger_snapshot": ledger, "result": result})
        return {"record_id": saved["id"], **result}

    def research_context(self, merchant, as_of=None):
        ledger = self.ledger(merchant)
        records = self.records(merchant)
        trials = {t["id"]: t for t in self.experiments(merchant)}
        designs = [r for r in records if r["kind"] == "design"]
        output = []
        for r in designs:
            d = r["data"]
            if as_of and day(d["observe_start"]) > day(as_of):
                continue
            measures = [m for m in records if m["kind"] == "measurement" and m["data"]["design_id"] == r["id"]
                        and (not as_of or day(m["data"]["end"]) <= day(as_of))]
            trial = trials[d["trial_id"]]
            measurement = measures[-1]["data"] if measures else None
            # Use the frozen thresholds and ledger scope, not a later edited trial budget.
            assessment = evaluate_design(d, measurement, d["trial_snapshot"], d["ledger_snapshot"])
            output.append({"id": r["id"], "design": d, "measurement": measurement,
                           "measurement_id": measures[-1]["id"] if measures else None, "evaluation": assessment})
        return output

    def design_template(self, merchant, trial_id):
        ledger = self.ledger(merchant)
        trial = next((t for t in self.experiments(merchant) if t["id"] == trial_id), None)
        if not trial:
            raise ValidationError("试验不存在")
        report = self.result(merchant, trial["run_id"])
        p = next(x["proposal"] for x in report["result"]["proposals"] if x["proposal"]["id"] == trial["proposal_id"])
        baseline = next((x for x in reversed(sorted(ledger.get("operating_periods", []), key=lambda x:x["end"])) if day(x["end"]) < day(p["spend_date"])), None)
        start = day(p["spend_date"])
        b = {k: baseline.get(k) if baseline else None for k in ("revenue", "goods_cost", "visits", "buyers")}
        b.update({"start": baseline["start"] if baseline else (start-timedelta(days=7)).isoformat(),
                  "end": baseline["end"] if baseline else (start-timedelta(days=1)).isoformat(),
                  "expenses": baseline.get("operating_cost") if baseline else None,
                  "source_note": ledger["sources"].get(baseline.get("source_id"), "") if baseline else "", "scope_id":baseline.get("scope_id", "shop_all") if baseline else "shop_all", "count_basis":baseline.get("count_basis", "person_visits") if baseline else "person_visits"})
        return {"scope_id":b["scope_id"], "scope_description":"全店同口径经营；不能与单项SKU收款混比", "count_basis":b["count_basis"], "scope_confirmed":False, "exit_rules":[], "draft_ref":None,
                "trial_id": trial_id, "hypothesis": trial["hypothesis"], "intervention": p["title"],
                "metric": "revenue_per_day", "target_value": "", "min_days": 1, "min_visits": 1,
                "observe_start": p["spend_date"], "observe_end": trial["end_date"],
                "comparison_method": "前后同口径对比；记录营业时长和客流差异", "confounders": "季节、天气、客流、同期折扣及店主投入变化",
                "stop_rule": "达到登记预算或现金低于保留额时停止新增投入", "source_note": "", "baseline": b}

    def save_design(self, merchant, raw):
        trial_id = raw.get("trial_id")
        template = self.design_template(merchant, trial_id)
        ledger = self.ledger(merchant)
        trial = next(t for t in self.experiments(merchant) if t["id"] == trial_id)
        report = self.result(merchant, trial["run_id"])
        if report["ledger_changed"] or report["context_changed"]:
            raise ValidationError("资料已变化，请先建立新方案和试验")
        if trial["status"] != "planned" or any(r["data"].get("trial_id") == trial_id for r in self.records(merchant, "design")):
            raise ValidationError("仅能为尚未开展的试验预先登记一次评价设计，目标不可事后重写")
        if any(e["data"]["run_id"] == trial["run_id"] and e["data"]["proposal_id"] == trial["proposal_id"] for e in self.feedback_journal(merchant)):
            raise ValidationError("已有试验反馈，不能再称为预先设计；请建新试验")
        data = {k: raw.get(k) for k in template}
        p = next(x["proposal"] for x in report["result"]["proposals"] if x["proposal"]["id"] == trial["proposal_id"])
        frozen_trial = {**trial, "spend_date": p["spend_date"]}
        validate_design(data, frozen_trial, ledger)
        if not ledger["synthetic"] and day(data["observe_start"]) < date.today():
            raise ValidationError("真实预注册设计不可倒填过去的试验开始日")
        if raw.get("draft_ref"):
            original = self.draft_preview(merchant, trial_id, raw["draft_ref"])
            data["draft_original"] = original["draft_original"]
            data["draft_source_mode"] = original["source_mode"]
            data["draft_changes"] = [k for k,v in original["design"].items() if k not in ("scope_confirmed", "source_note") and data.get(k) != v]
        data["model_refs"] = deepcopy(trial.get("model_refs", []))
        data.update({"trial_snapshot": frozen_trial, "ledger_snapshot": ledger})
        # Unique trial key serializes competing submissions; transaction rolls back both.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT data FROM workbench_records WHERE merchant=? AND kind='design'", (merchant,)).fetchall()
            if any(json.loads(r[0])["trial_id"] == trial_id for r in rows):
                raise ValidationError("该试验已有冻结设计")
            rid = "wb_"+uuid4().hex
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",
                       (merchant, rid, "design", json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return {"id": rid, "data": data}

    def save_measurement(self, merchant, raw):
        designs = self.records(merchant, "design")
        row = next((r for r in designs if r["id"] == raw.get("design_id")), None)
        if not row:
            raise ValidationError("评价设计不存在")
        d = row["data"]
        prior = [r for r in self.records(merchant, "measurement") if r["data"]["design_id"] == row["id"]]
        previous_id = prior[-1]["id"] if prior else None
        if raw.get("supersedes_id") != previous_id:
            raise ValidationError("观察记录已有更新，请刷新")
        data = {k: raw.get(k) for k in ("design_id", "end", "revenue", "goods_cost", "expenses", "visits", "buyers", "trial_spend", "closing_cash", "source_note", "change_reason", "supersedes_id", "scope_id", "count_basis")}
        nonempty(data["change_reason"], "本次观察或更正原因")
        if prior and day(data["end"]) < day(prior[-1]["data"]["end"]):
            raise ValidationError("观察截止日不可倒退；同日可留痕更正")
        trial = next(t for t in self.experiments(merchant) if t["id"] == d["trial_id"])
        if trial["status"] not in ("active", "paused", "stopped", "completed"):
            raise ValidationError("先将试验登记为开展中，再记录实际观察")
        evaluation = evaluate_design(d, data, d["trial_snapshot"], d["ledger_snapshot"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT id,data FROM workbench_records WHERE merchant=? AND kind='measurement' ORDER BY seq", (merchant,)).fetchall()
            actual = [r["id"] for r in rows if json.loads(r["data"])["design_id"] == row["id"]]
            if (actual[-1] if actual else None) != previous_id:
                raise ValidationError("观察同时被更新，请刷新")
            rid = "wb_"+uuid4().hex
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",
                       (merchant, rid, "measurement", json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return {"id": rid, "evaluation": evaluation}

    def research_evidence(self, merchant, as_of):
        return [{"design_id": r["id"], "trial_id": r["design"]["trial_id"],
                 "hypothesis": r["design"]["hypothesis"], "measurement_id": r["measurement_id"],
                 "period_end": r["measurement"]["end"], "source_note": r["measurement"]["source_note"],
                 "evaluation": r["evaluation"]}
                for r in self.research_context(merchant, as_of) if r["measurement"] is not None]

    def draft_preview(self, merchant, trial_id, draft_id):
        template = self.design_template(merchant, trial_id)
        trial = next(t for t in self.experiments(merchant) if t["id"] == trial_id)
        report = self.result(merchant, trial["run_id"])
        if report["ledger_changed"] or report["context_changed"]:
            raise ValidationError("资料已变化，草案需重新生成后再审阅")
        d = next((d for d in report["result"].get("experiment_drafts", []) if d["id"] == draft_id and d["proposal_id"] == trial["proposal_id"] and d["proposal_version"] == trial["proposal_version"]), None)
        if d is None:
            raise ValidationError("未找到该试验精确方案版本的实验草案")
        merged = {**template, **deepcopy(d["design"]), "trial_id":trial_id, "draft_ref":draft_id,
                  "scope_confirmed":False, "source_note":""}
        return {"design":merged, "draft_original":d, "source_mode":report["mode"],
                "notice":"草案只预填表单，不会冻结设计、激活试验或执行经营。目标、范围、样本与观察期限须由商户审阅，规则/模拟草案不是真实AI输出。"}

    def lineage(self, merchant):
        trials = self.experiments(merchant)
        designs = self.records(merchant, "design")
        links = []
        for run in self.run_history(merchant, limit=50):
            report = self.result(merchant, run["id"])
            for entry in (report.get("result") or {}).get("proposals", []):
                p = entry["proposal"]
                from .linkage import resolve
                try:
                    models = resolve(report["ledger_snapshot"],p) if p.get("model_refs") else []
                except ValidationError:
                    models = []
                attached = [t for t in trials if t["run_id"] == run["id"] and t["proposal_id"] == p["id"] and t["proposal_version"] == p["version"]]
                links.append({"run_id":run["id"], "proposal_id":p["id"], "proposal_version":p["version"],
                              "title":p["title"], "model_refs":p.get("model_refs", []), "model_snapshots":models,
                              "binding_status":"bound" if models else "legacy_unbound",
                              "trials":[{"id":t["id"],"status":t["status"],"draft_ids":[d["id"] for d in report["result"].get("experiment_drafts", []) if d["proposal_id"] == p["id"] and d["proposal_version"] == p["version"]], "design_ids":[r["id"] for r in designs if r["data"]["trial_id"] == t["id"]]} for t in attached]})
        return links

    def workbench(self, merchant):
        ledger = self.ledger(merchant)
        from .cohorts import analyze_cohorts
        from .supply import analyze
        return {"supply": analyze(ledger), "mode_decisions": self.records(merchant,"mode_decision"), "operating_imports": self.records(merchant,"operating_import")[-10:], "lineage": self.lineage(merchant), "cohorts":analyze_cohorts(ledger), "models": assess_models(ledger), "accounts": reconcile(ledger),
                "research": self.research_context(merchant), "portfolios": self.records(merchant, "portfolio")[-10:]}

