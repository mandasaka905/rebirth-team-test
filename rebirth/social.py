"""Local support and experience loops. Outcomes are records, never causal claims."""
from datetime import date, datetime, timezone
from uuid import uuid4
import json
import re

from .domain import ValidationError, day, integer, money, amount, nonempty

CATEGORIES = {"records": "看懂并整理账目", "digital": "学会使用数字工具", "inventory": "盘清库存与损耗", "operations": "安排经营与工时", "cash": "核对付款与资金底线"}
INDUSTRIES = {"retail": "零售", "food": "餐饮", "repair": "修理", "other": "其他小店"}
OUTCOMES = {"solved": "这次困难已解决", "partial": "解决了一部分", "unresolved": "尚未解决", "stopped": "决定停止这次尝试"}
SOCIAL_KINDS = ("support_request", "support_event", "support_privacy", "experience_share", "experience_visibility", "experience_adoption", "experience_result", "experience_privacy")


def text(raw, key, label, limit=1600):
    value = nonempty(raw.get(key), label)
    if len(value) > limit:
        raise ValidationError(label + "过长，请保留重点")
    return value


def checked(raw, key="confirmed"):
    if raw.get(key) is not True:
        raise ValidationError("请先核对并勾选本次确认")


def occurred(raw, key, synthetic):
    value = day(raw.get(key))
    if not synthetic and value > date.today():
        raise ValidationError("实际发生日期不能填未来")
    return value.isoformat()


def next_date(raw, since):
    value = day(raw.get("next_on"))
    if value < day(since):
        raise ValidationError("下次跟进不能早于本次记录日期")
    return value.isoformat()


def public_text(raw, key, label, limit=1200):
    value = text(raw, key, label, limit)
    if re.search(r"\d{7,}|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}|https?://|www\.", value):
        raise ValidationError(label + "请去掉电话、账号、邮箱或网址，只留下可复用的方法")
    return value


def write(db, merchant, kind, data):
    rid = kind + "_" + uuid4().hex[:16]
    db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)", (merchant, rid, kind, json.dumps(data, ensure_ascii=False, allow_nan=False), datetime.now(timezone.utc).isoformat()))
    return {"id": rid, "kind": kind, "data": data}


class SocialWorkflows:
    def _social_rows(self, db=None):
        if db is None:
            with self.connect() as conn:
                return self._social_rows(conn)
        marks = ",".join("?" for _ in SOCIAL_KINDS)
        rows = db.execute(f"SELECT merchant,id,kind,data,created_at FROM workbench_records WHERE kind IN ({marks}) ORDER BY seq", SOCIAL_KINDS).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def _support_cases(self, merchant, rows):
        cases = []
        for r in rows:
            if r["merchant"] != merchant or r["kind"] != "support_request":
                continue
            history = [e for e in rows if e["merchant"] == merchant and e["kind"] == "support_event" and e["data"]["request_id"] == r["id"]]
            last = history[-1] if history else r
            plan = next((e for e in reversed(history) if e["data"]["action"] == "plan"), None)
            visits = [e for e in history if e["data"]["action"] == "visit"]
            review = next((e for e in reversed(history) if e["data"]["action"] == "review"), None)
            privacy = [e for e in rows if e["merchant"] == merchant and e["kind"] == "support_privacy" and e["data"]["request_id"] == r["id"]]
            cases.append({**r, "history": history, "last_id": last["id"], "status": last["data"].get("status", "waiting"), "next_on": last["data"].get("next_on"), "plan": plan, "visits": visits, "review": review, "aggregate_consent": privacy[-1]["data"]["aggregate_consent"] if privacy else r["data"]["aggregate_consent"], "privacy_id": privacy[-1]["id"] if privacy else None})
        return cases

    def support_request(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw, "local_consent")
        category = raw.get("category")
        if category not in CATEGORIES:
            raise ValidationError("请选择本次最需要的帮助")
        created = occurred(raw, "requested_on", ledger["synthetic"])
        data = {"category": category, "problem": text(raw, "problem", "遇到的困难"), "goal": text(raw, "goal", "这次想先做到什么"), "availability": text(raw, "availability", "方便协助的时段", 160), "requested_on": created, "next_on": next_date(raw, created), "status": "waiting", "synthetic": ledger["synthetic"], "local_consent": True, "aggregate_consent": raw.get("aggregate_consent") is True}
        return self.append_record(merchant, "support_request", data)

    def support_consent(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw)
        if type(raw.get("aggregate_consent")) is not bool:
            raise ValidationError("请明确是否允许匿名汇总")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            case = next((c for c in self._support_cases(merchant, self._social_rows(db)) if c["id"] == raw.get("request_id")), None)
            if not case:
                raise ValidationError("本店的求助记录不存在")
            if case["privacy_id"] != (raw.get("expected_id") or None):
                raise ValidationError("匿名统计设置已更新，请返回重新读取")
            return write(db, merchant, "support_privacy", {"request_id": case["id"], "aggregate_consent": raw["aggregate_consent"], "synthetic": ledger["synthetic"]})

    def support_event(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            case = next((c for c in self._support_cases(merchant, self._social_rows(db)) if c["id"] == raw.get("request_id")), None)
            if not case:
                raise ValidationError("本店的求助记录不存在")
            if raw.get("expected_id") != case["last_id"]:
                raise ValidationError("跟进记录已更新，请返回重新读取；未覆盖旧记录")
            action, status = raw.get("action"), case["status"]
            allowed = {"plan": {"waiting", "arranged", "following"}, "visit": {"arranged", "following"}, "review": {"following"}, "pause": {"waiting", "arranged", "following"}, "resume": {"paused", "closed"}, "withdraw": {"waiting", "arranged", "following", "paused"}}
            if action not in allowed or status not in allowed[action]:
                raise ValidationError("当前阶段不能执行这项操作，请按页面下一步继续")
            on = occurred(raw, "occurred_on", ledger["synthetic"])
            previous_on = case["history"][-1]["data"]["occurred_on"] if case["history"] else case["data"]["requested_on"]
            if on < previous_on:
                raise ValidationError("跟进日期不能早于上一条记录")
            data = {"request_id": case["id"], "previous_id": case["last_id"], "action": action, "occurred_on": on, "notes": text(raw, "notes", "本次实际内容与依据"), "synthetic": ledger["synthetic"], "confirmed": True}
            if action == "plan":
                data.update(status="arranged", helper_alias=text(raw, "helper_alias", "协助者称呼", 80), step=text(raw, "step", "这次只做的一件事"), next_on=next_date(raw, on), planned_minutes=integer(raw.get("planned_minutes"), "约定协助分钟", 240))
                if data["planned_minutes"] < 1:
                    raise ValidationError("约定用时至少1分钟")
                impact_id = raw.get("impact_case_id") or None
                if impact_id and not any(r["id"] == impact_id for r in self.records(merchant, "impact_start")):
                    raise ValidationError("只能关联本店已保存的成效基准")
                data["impact_case_id"] = impact_id
            elif action == "visit":
                data.update(status="following", next_on=next_date(raw, on), actual_minutes=integer(raw.get("actual_minutes"), "实际协助分钟", 1440), extra_spend=amount(money(raw.get("extra_spend"))), blockers=text(raw, "blockers", "还卡在哪里（没有也请说明）"))
            elif action == "review":
                if not case["visits"]:
                    raise ValidationError("先留下实际协助记录，再做店主回访")
                outcome = raw.get("outcome")
                if outcome not in OUTCOMES:
                    raise ValidationError("请选择真实回访结果")
                data.update(status="closed", outcome=outcome, merchant_voice=text(raw, "merchant_voice", "店主对这次帮助的看法"), next_choice=text(raw, "next_choice", "接下来怎么办"), next_on=None)
            elif action == "pause":
                data.update(status="paused", resume_status=status, next_on=next_date(raw, on))
            elif action == "resume":
                data.update(status="following" if case["visits"] else "arranged" if case["plan"] else "waiting", next_on=next_date(raw, on))
            else:
                data.update(status="withdrawn", next_on=None)
            return write(db, merchant, "support_event", data)

    def _experience_cards(self, merchant, rows, *, own=False):
        synthetic = self.ledger(merchant)["synthetic"]
        visibility = {r["data"]["share_id"]: r for r in rows if r["kind"] == "experience_visibility"}
        out = []
        for r in rows:
            if r["kind"] != "experience_share" or r["data"]["synthetic"] != synthetic:
                continue
            is_owner = r["merchant"] == merchant
            withdrawn = visibility.get(r["id"], {}).get("data", {}).get("withdrawn", False)
            source = next((c for c in self._support_cases(r["merchant"], rows) if c["id"] == r["data"]["request_id"]), None)
            stale = not source or source["status"] != "closed" or source["last_id"] != r["data"]["review_id"]
            if (withdrawn or stale) and not is_owner:
                continue
            if own and not is_owner:
                continue
            # Explicit allow-list. No ledger, store identifier, names, original notes or money.
            public = {k: r["data"][k] for k in ("title", "industry", "problem", "steps", "fits", "stop_when", "lesson", "outcome", "synthetic")}
            out.append({"id": r["id"], "owned": is_owner, "withdrawn": withdrawn, "source_changed": stale, "data": public})
        return out

    def experience_share(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw, "share_consent")
        checked(raw, "anonymous_checked")
        industry = raw.get("industry")
        if industry not in INDUSTRIES:
            raise ValidationError("请选择适用的小店类型")
        data = {k: public_text(raw, k, label, limit) for k, label, limit in [("title", "经验标题", 80), ("problem", "适用的问题", 800), ("fits", "适用条件", 800), ("stop_when", "什么时候不要照做", 800), ("lesson", "回看与教训", 1200)]}
        steps = raw.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
            raise ValidationError("请整理1至3个可操作步骤")
        data["steps"] = [public_text({"step": s}, "step", "操作步骤", 600) for s in steps]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._social_rows(db)
            case = next((c for c in self._support_cases(merchant, rows) if c["id"] == raw.get("request_id")), None)
            if not case or case["status"] != "closed" or not case["review"]:
                raise ValidationError("先完成一次店主回访，再整理经验；未解决的经历也可以分享")
            if any(r["merchant"] == merchant and r["kind"] == "experience_share" and r["data"]["review_id"] == case["last_id"] for r in rows):
                raise ValidationError("这次回访已经整理过经验，请查看原卡；再次跟进并回访后可整理新版")
            data.update(industry=industry, request_id=case["id"], review_id=case["last_id"], outcome=case["review"]["data"]["outcome"], synthetic=ledger["synthetic"], share_consent=True, anonymous_checked=True)
            return write(db, merchant, "experience_share", data)

    def experience_withdraw(self, merchant, raw):
        self.ledger(merchant)
        checked(raw)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._social_rows(db)
            card = next((r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_share" and r["id"] == raw.get("share_id")), None)
            if not card:
                raise ValidationError("只能撤回本店整理的经验")
            if any(r["kind"] == "experience_visibility" and r["data"]["share_id"] == card["id"] for r in rows):
                raise ValidationError("这张经验卡已经撤回")
            return write(db, merchant, "experience_visibility", {"share_id": card["id"], "withdrawn": True, "reason": text(raw, "reason", "撤回原因"), "synthetic": card["data"]["synthetic"]})

    def experience_adopt(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._social_rows(db)
            card = next((c for c in self._experience_cards(merchant, rows) if c["id"] == raw.get("share_id") and not c["owned"]), None)
            if not card:
                raise ValidationError("经验卡已撤回、依据已改变或不属于可借鉴的邻店记录，请重新选择")
            adoptions = [r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_adoption" and r["data"]["share_id"] == card["id"]]
            finished = {r["data"]["adoption_id"] for r in rows if r["merchant"] == merchant and r["kind"] == "experience_result"}
            if any(r["id"] not in finished for r in adoptions):
                raise ValidationError("已安排过这张经验卡，先记录原尝试的实际结果")
            index = integer(raw.get("step_index"), "选择步骤", 2)
            if index >= len(card["data"]["steps"]):
                raise ValidationError("选择的经验步骤不存在")
            start = occurred(raw, "planned_on", ledger["synthetic"])
            minutes = integer(raw.get("minutes_cap"), "本次最多用时", 240)
            if minutes < 1:
                raise ValidationError("请为这次小范围尝试安排至少1分钟")
            data = {"share_id": card["id"], "card_snapshot": card["data"], "step_index": index, "planned_on": start, "next_on": next_date(raw, start), "minutes_cap": minutes, "spend_cap": amount(money(raw.get("spend_cap"))), "fit_note": text(raw, "fit_note", "为什么适合本店"), "adapted_step": text(raw, "adapted_step", "本店这次实际打算怎么做"), "stop_when": text(raw, "stop_when", "本店的暂停条件"), "synthetic": ledger["synthetic"], "confirmed": True, "aggregate_consent": raw.get("aggregate_consent") is True}
            return write(db, merchant, "experience_adoption", data)

    def experience_consent(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw)
        if type(raw.get("aggregate_consent")) is not bool:
            raise ValidationError("请明确是否允许匿名汇总")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._social_rows(db)
            original = next((r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_adoption" and r["id"] == raw.get("adoption_id")), None)
            if not original:
                raise ValidationError("本店的借鉴安排不存在")
            prior = [r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_privacy" and r["data"]["adoption_id"] == original["id"]]
            if (prior[-1]["id"] if prior else None) != (raw.get("expected_id") or None):
                raise ValidationError("统计设置已更新，请重新读取")
            return write(db, merchant, "experience_privacy", {"adoption_id": original["id"], "aggregate_consent": raw["aggregate_consent"], "synthetic": ledger["synthetic"]})

    def experience_result(self, merchant, raw):
        ledger = self.ledger(merchant)
        checked(raw)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._social_rows(db)
            original = next((r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_adoption" and r["id"] == raw.get("adoption_id")), None)
            if not original:
                raise ValidationError("本店的借鉴安排不存在")
            prior = [r for r in rows if r["merchant"] == merchant and r["kind"] == "experience_result" and r["data"]["adoption_id"] == original["id"]]
            if (prior[-1]["id"] if prior else None) != (raw.get("expected_id") or None):
                raise ValidationError("尝试结果已更新，请重新读取；原记录保留")
            on = occurred(raw, "observed_on", ledger["synthetic"])
            if on < (prior[-1]["data"]["observed_on"] if prior else original["data"]["planned_on"]):
                raise ValidationError("结果日期不能早于安排或上次观察")
            result = raw.get("result")
            if result not in {"helped", "unchanged", "unsuitable", "stopped"}:
                raise ValidationError("请选择这次尝试的实际情况")
            data = {"adoption_id": original["id"], "previous_id": prior[-1]["id"] if prior else None, "observed_on": on, "result": result, "actual_minutes": integer(raw.get("actual_minutes"), "实际额外用时", 1000000), "extra_spend": amount(money(raw.get("extra_spend"))), "actual": text(raw, "actual", "做了什么与实际结果"), "source_note": text(raw, "source_note", "依据与同期其他影响"), "next_step": text(raw, "next_step", "接下来继续、调整还是停止"), "synthetic": ledger["synthetic"], "confirmed": True}
            return write(db, merchant, "experience_result", data)

    def social_summary(self, merchant, rows):
        synthetic = self.ledger(merchant)["synthetic"]
        candidate_shops = {r["merchant"] for r in rows if r["kind"] == "support_request" and r["data"]["synthetic"] == synthetic}
        cases = [c for shop in candidate_shops for c in self._support_cases(shop, rows) if c["aggregate_consent"]]
        shops = {c["merchant"] for c in cases}
        reviewed = [c for c in cases if c["review"]]
        # Count stores once; several requests or corrections never multiply beneficiaries.
        measures = {}; observed_shops = set()
        for shop in shops:
            linked = {c["plan"]["data"].get("impact_case_id") for c in cases if c["merchant"] == shop and c["plan"]}
            for c in self.community_impact_cases(shop):
                if c["id"] not in linked or not c["latest"] or c["elapsed_days"] < 30 or c["latest"]["data"]["status"] != "observed":
                    continue
                observed_shops.add(shop)
                metric = c["data"]["metric"]
                bucket = measures.setdefault(metric, {"label": c["data"]["metric_label"], "unit": c["data"]["unit"], "cases": 0, "lower": 0, "same": 0, "higher": 0})
                bucket["cases"] += 1
                difference = money(c["difference"], negative=True)
                bucket["lower" if difference < 0 else "higher" if difference > 0 else "same"] += 1
        privacy = {r["data"]["adoption_id"]: r["data"]["aggregate_consent"] for r in rows if r["kind"] == "experience_privacy"}
        adoptions = [r for r in rows if r["kind"] == "experience_adoption" and r["data"]["synthetic"] == synthetic and privacy.get(r["id"], r["data"].get("aggregate_consent", False))]
        latest_results = {r["data"]["adoption_id"]: r for r in rows if r["kind"] == "experience_result"}
        shops.update(r["merchant"] for r in adoptions)
        return {"synthetic": synthetic, "participating_shops": len(shops), "requested_cases": len(cases), "reviewed_cases": len(reviewed), "reviewed_shops": len({c["merchant"] for c in reviewed}), "closed_cases": sum(c["status"] == "closed" for c in cases), "unresolved_cases": sum(c["review"] is not None and c["review"]["data"]["outcome"] in {"partial", "unresolved", "stopped"} for c in cases), "observed_30day_shops": len(observed_shops), "metrics": list(measures.values()), "learning_shops": len({r["merchant"] for r in adoptions}), "learning_reviewed_shops": len({r["merchant"] for r in adoptions if r["id"] in latest_results}), "definition": "仅统计同一真实/合成分组中，对单条求助或借鉴记录自愿允许匿名汇总的本机店铺。店铺去重，回访不等于问题已解决；30天指前后记录的日期跨度，不等于持续接受30天服务，也不证明因果。不同指标、单位与金额不相加，没有推算就业、营业增长或受益人数。"}

    def social_home(self, merchant):
        ledger = self.ledger(merchant)
        rows = self._social_rows()
        cases = self._support_cases(merchant, rows)
        cards = self._experience_cards(merchant, rows)
        for case in cases:
            case["shared"] = any(r["merchant"] == merchant and r["kind"] == "experience_share" and r["data"]["review_id"] == case["last_id"] for r in rows)
        adoptions = []
        for r in rows:
            if r["merchant"] != merchant or r["kind"] != "experience_adoption":
                continue
            history = [e for e in rows if e["merchant"] == merchant and e["kind"] == "experience_result" and e["data"]["adoption_id"] == r["id"]]
            live = next((c for c in cards if c["id"] == r["data"]["share_id"]), None)
            privacy = [e for e in rows if e["merchant"] == merchant and e["kind"] == "experience_privacy" and e["data"]["adoption_id"] == r["id"]]
            adoptions.append({**r, "latest": history[-1] if history else None, "history": history, "source_unavailable": live is None or live["withdrawn"] or live["source_changed"], "aggregate_consent": privacy[-1]["data"]["aggregate_consent"] if privacy else r["data"].get("aggregate_consent", False), "privacy_id": privacy[-1]["id"] if privacy else None})
        reminders = [{"kind": "support", "title": c["data"]["goal"], "date": c["next_on"], "id": c["id"], "status": c["status"]} for c in cases if c["next_on"] and c["status"] not in {"closed", "withdrawn"}]
        reminders += [{"kind": "learning", "title": r["data"]["adapted_step"], "date": r["data"]["next_on"], "id": r["id"], "status": "pending"} for r in adoptions if not r["latest"]]
        return {"synthetic": ledger["synthetic"], "cases": cases, "cards": cards, "adoptions": adoptions, "reminders": sorted(reminders, key=lambda r: r["date"]), "summary": self.social_summary(merchant, rows), "categories": CATEGORIES, "industries": INDUSTRIES, "outcomes": OUTCOMES}
