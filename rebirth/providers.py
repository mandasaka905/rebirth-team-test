"""Rule rehearsal and opt-in AgentArts execution. Never silently fall back."""

from datetime import timedelta
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from .domain import ValidationError, amount, day, money
from .control import RunControl
from .preflight import redact_context


ROOT = Path(__file__).resolve().parent.parent


class ProviderError(RuntimeError):
    pass


def extract_action(payload):
    """Only accept a structured action or a JSON end-node response, not prose."""
    if isinstance(payload, dict) and payload.get("action") in ("tool", "final"):
        return payload
    if isinstance(payload, dict) and payload.get("event") in ("error", "failed"):
        raise ProviderError("AgentArts返回执行错误；未回退到本地规则")
    if isinstance(payload, dict):
        for key in ("response", "output", "content", "text", "data", "result"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                return extract_action(value)
            except ProviderError:
                continue
    if isinstance(payload, str):
        value = payload.strip()
        if value.startswith("```json") and value.endswith("```"):
            value = value[7:-3].strip()
        try:
            return extract_action(json.loads(value))
        except (json.JSONDecodeError, RecursionError):
            pass
    raise ProviderError("未找到符合协议的JSON动作；请检查工作流结束节点输出映射")


def decode_response(raw, content_type):
    if len(raw) > 4 * 1024 * 1024:
        raise ProviderError("AgentArts响应超过4MB")
    if "text/event-stream" not in content_type:
        try:
            return extract_action(json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("AgentArts响应不是有效JSON") from exc
    # SSE may carry fragments or a complete action on the End node. Ignore thought text.
    fragments, end_texts = [], []
    for block in raw.decode("utf-8-sig").replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProviderError("SSE事件JSON损坏") from exc
        if event.get("event") in ("error", "failed"):
            raise ProviderError("AgentArts流式执行失败")
        nested = event.get("data", {})
        if isinstance(nested, dict) and str(nested.get("node_type", "")).lower() == "end":
            end_texts.append(nested.get("text"))
        elif isinstance(event.get("content"), str) and event.get("event") == "message":
            fragments.append(event["content"])
        elif isinstance(nested, dict) and isinstance(nested.get("text"), str) and event.get("event") == "message":
            fragments.append(nested["text"])
    if end_texts:
        # Prefer only the declared End node. Never accept an earlier draft on End failure.
        for candidate in reversed(end_texts):
            try:
                return extract_action(candidate)
            except ProviderError:
                pass
        return extract_action("".join(t for t in end_texts if isinstance(t, str)))
    return extract_action("".join(fragments))


class AgentArtsProvider:
    mode = "agentarts"
    handles_budget = True

    def __init__(self, config_path, *, control=None):
        self.control = control or RunControl()
        try:
            self.config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ProviderError("无法读取AgentArts本地配置") from exc
        for role in ("coordinator", "inventory", "customer", "cash"):
            cfg = self.config.get("agents", {}).get(role)
            if not cfg:
                raise ProviderError(f"尚未配置{role}的AgentArts调用路径")
            parts = urllib.parse.urlsplit(cfg.get("url", ""))
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment or parts.query:
                raise ProviderError("AgentArts调用路径必须是无账号密码的HTTPS URL")
            if parts.hostname not in self.config.get("allowed_hosts", []):
                raise ProviderError("调用域名尚未加入本机allowed_hosts确认列表")
            if not os.environ.get(cfg.get("token_env", "AGENTARTS_TOKEN")):
                raise ProviderError("缺少AgentArts鉴权环境变量；请在本机设置，不要发送到聊天")
            if cfg.get("auth_header", "X-Auth-Token") not in ("Authorization", "X-Auth-Token"):
                raise ProviderError("仅支持Authorization或X-Auth-Token认证头")
        self.sessions = {}

    def step(self, context):
        cfg = self.config["agents"][context["role"]]
        prompt = (ROOT / "agentarts" / "prompts" / f"{context['role']}.md").read_text(encoding="utf-8")
        contracts=json.loads((ROOT/"config/contracts.json").read_text(encoding="utf-8"))
        envelope = {"instruction": prompt, "context": redact_context(context), "output_contract": {k:contracts[k] for k in ("model_draft_contract","model_review_contract","procurement_contract")}}
        token = os.environ[cfg.get("token_env", "AGENTARTS_TOKEN")]
        auth_header = cfg.get("auth_header", "X-Auth-Token")
        session_key = (context["run_id"], context["role"])
        session = self.sessions.setdefault(session_key, uuid4().hex)
        request = urllib.request.Request(
            cfg["url"],
            data=json.dumps({"inputs": {"request": json.dumps(envelope, ensure_ascii=False)}}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "X-Invoke-Mode": "published",
                     auth_header: ("Bearer " if auth_header == "Authorization" else "") + token,
                     "x-hw-agentarts-session-id": session, "X-Request-Id": uuid4().hex},
            method="POST")
        # Do not forward credentials to a redirect target.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        self.control.reserve(len(request.data))
        try:
            with opener.open(request, timeout=20) as response:
                raw = response.read(min(4 * 1024 * 1024 + 1, self.control.max_output_bytes + 1))
                self.control.receive(len(raw))
                return decode_response(raw, response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"AgentArts HTTP {exc.code}，请检查路径、权限、额度；响应正文未写入日志") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError("AgentArts连接失败或超时；未回退到本地规则") from None


class RuleProvider:
    """Transparent offline policies. Fault injection belongs in tests, never here."""

    mode = "rules"

    def step(self, c):
        action=self._base_step(c)
        if action.get("action")!="final": return action
        result=action["result"];role=c["role"];phase=c["phase"]
        if role=="inventory" and phase in ("propose","revise"):
            from .supply import rule_restock
            from .linkage import default_refs
            refs=[o["evidence_id"] for o in c["observations"] if "value" in o]
            previous=next((p for p in c.get("proposals",[]) if p["id"]=="inventory_restock"),None)
            p=rule_restock(c["ledger"],refs,previous)
            if p:
                p["model_refs"]=default_refs(c["ledger"],"inventory")
                checked=any(o.get("tool")=="proposal_evaluate" and o.get("arguments",{}).get("proposal",{}).get("id")==p["id"] and "value" in o for o in c["observations"])
                if not checked:return {"action":"tool","name":"proposal_evaluate","arguments":{"proposal":p}}
                result.setdefault("proposals",[]).append(p)
        if role=="customer" and phase in ("propose","revise"):
            from .model_drafts import rule_draft
            prior=next((d for d in c.get("model_drafts",[]) if d["id"]=="customer_mode"),None)
            refs=[o["evidence_id"] for o in c["observations"] if "value" in o]
            d=rule_draft(c["ledger"],refs,prior)
            result["model_drafts"]=[d] if d else []
        if role in ("inventory","customer","cash") and phase=="review":
            reviews=[]
            for d in c.get("model_drafts",[]):
                obs=next((o for o in c["observations"] if o.get("tool")=="model_draft_evaluate" and o.get("arguments",{}).get("draft",{}).get("id")==d["id"] and "value" in o),None)
                if obs is None:return {"action":"tool","name":"model_draft_evaluate","arguments":{"draft":d}}
                v=obs["value"]
                reviews.append({"draft_id":d["id"],"version":d["version"],"status":"blocked" if v["blockers"] else "needs_data" if v["warnings"] else "pass",
                                "reason":"；".join(v["perspectives"][role]),"evidence_ids":[obs["evidence_id"]]})
            result["model_reviews"]=reviews
        return action

    def _base_step(self, c):
        role, phase = c["role"], c["phase"]
        observed = {r["tool"] for r in c["observations"] if "value" in r}
        primary = {"inventory": "inventory_analyze", "customer": "customer_evidence", "cash": "cash_baseline"}
        if role in primary and primary[role] not in observed:
            return {"action": "tool", "name": primary[role], "arguments": {}}
        refs = [r["evidence_id"] for r in c["observations"] if "evidence_id" in r]
        values = {r["tool"]: r["value"] for r in c["observations"] if "value" in r}
        if role == "coordinator":
            roles = sorted({o["owner"] for o in c.get("proposals", [])
                            if any(r["proposal_id"] == o["id"] and r["objections"] for r in c.get("reviews", []))})
            return {"action": "final", "result": {"revise_roles": roles,
                "notes": ["本地规则仅用于协作协议与计算测试，不构成AI诊断或经营建议。"]}}
        if phase == "review":
            needed = [p for p in c["proposals"] if p["owner"] != role]
            already = {r["arguments"]["proposal"]["id"] for r in c["observations"] if r["tool"] == "proposal_evaluate" and "value" in r}
            for p in needed:
                if p["id"] not in already:
                    return {"action": "tool", "name": "proposal_evaluate", "arguments": {"proposal": p}}
            objections = []
            for obs in c["observations"]:
                if obs["tool"] != "proposal_evaluate" or "value" not in obs:
                    continue
                evaluation = obs["value"]
                codes = [x for x in evaluation["checks"] if (
                    role == "inventory" and x["code"] in ("SIZE_EVIDENCE_REQUIRED", "STOCK_EXCEEDED", "UNKNOWN_SKU", "SUPPLY_MINIMUM", "SUPPLY_CAPACITY", "SUPPLY_OUTSIDE_HORIZON", "SUPPLY_DATA_REQUIRED")) or (
                    role == "cash" and x["code"] not in ("SIZE_EVIDENCE_REQUIRED", "STOCK_EXCEEDED", "UNKNOWN_SKU", "SUPPLY_MINIMUM", "SUPPLY_CAPACITY", "SUPPLY_OUTSIDE_HORIZON", "SUPPLY_DATA_REQUIRED"))]
                if codes:
                    proposal = next(p for p in c["proposals"] if p["id"] == evaluation["proposal_id"])
                    objections.append({"proposal_id": proposal["id"], "version": proposal["version"],
                        "reason": json.dumps(codes, ensure_ascii=False), "request": "按上述工具约束修改后重新计算",
                        "evidence_ids": [obs["evidence_id"]]})
            return {"action": "final", "result": {"notes": ["规则审查完成；需求仍需真实商户验证"], "objections": objections}}
        if phase == "investigate":
            for tool in ("data_readiness", "feedback_history", "business_diagnostics", "knowledge_search", "investigation_history"):
                if tool not in observed:
                    return {"action": "tool", "name": tool, "arguments": {"query": {"inventory": "库存 尺码 成本", "customer": "需求 预约 成交", "cash": "现金 付款 预算"}[role]} if tool == "knowledge_search" else {}}
            own_questions = [q for q in values["data_readiness"]["questions"] if q["owner"] == role]
            followups = [q for f in values["feedback_history"]["outcomes"]
                         for q in f["follow_up_questions"] if q["owner"] == role]
            primary_ref = next(r["evidence_id"] for r in c["observations"] if r["tool"] == primary[role] and "value" in r)
            findings = []
            for card in values["investigation_history"]["cards"]:
                if card["owner"] == role:
                    ev = next(r["evidence_id"] for r in c["observations"] if r["tool"] == "investigation_history" and "value" in r)
                    findings.append({"kind": "hypothesis", "statement": "人工待查假设："+card["hypothesis"]+"；状态："+card["status"]+"；下一步："+card["next_check"], "evidence_ids": [ev]})
            for f in values["business_diagnostics"]["findings"]:
                if f["owner"] == role:
                    ev = next(r["evidence_id"] for r in c["observations"] if r["tool"] == "business_diagnostics" and "value" in r)
                    findings.append({"kind": "observation", "statement": f["title"]+"；"+f["question"], "evidence_ids": [ev]})
            if role == "cash":
                ev = next(r["evidence_id"] for r in c["observations"] if r["tool"] == "business_diagnostics" and "value" in r)
                for warning in values["business_diagnostics"]["accounts"]["warnings"]:
                    findings.append({"kind": "observation", "statement": "账簿核对："+warning, "evidence_ids": [ev]})
                for model in values["business_diagnostics"]["models"]["models"]:
                    for issue in model["issues"]:
                        findings.append({"kind": "hypothesis", "statement": model["model"]["name"]+"："+issue, "evidence_ids": [ev]})
            for review in values["feedback_history"].get("experiment_reviews", []):
                if role == "customer":
                    ev = next(r["evidence_id"] for r in c["observations"] if r["tool"] == "feedback_history" and "value" in r)
                    findings.append({"kind": "observation", "statement": "试验评价："+review["evaluation"]["label"]+"；下一步："+review["evaluation"]["next_action"], "evidence_ids": [ev]})
            if role == "customer":
                ev = next(r["evidence_id"] for r in c["observations"] if r["tool"] == "business_diagnostics" and "value" in r)
                for f in values["business_diagnostics"]["cohorts"]["findings"]:
                    findings.append({"kind": "observation", "statement": "固定客群："+f["statement"], "evidence_ids": [ev]})
            if role == "inventory":
                for p in values["inventory_analyze"]["products"]:
                    if p["slow_moving"]:
                        name = next((x['name'] for x in c['ledger']['products'] if x['sku'] == p['sku']), p['sku'])
                        findings.append({"kind": "observation", "statement": f"{name}还剩{p['stock']}件，最近30天只卖了{p['sales_30d']}件，进货已过{p['age_days']}天。建议先核对这件货，看看有没有压货。", "evidence_ids": [primary_ref]})
                        findings.append({"kind": "hypothesis", "statement": f"{name}为什么卖得慢还不清楚。可以先问顾客想要什么款式和尺码，再检查陈列；不能仅凭库存就认定原因或直接降价。", "evidence_ids": [primary_ref]})
            elif role == "cash":
                baseline = values["cash_baseline"]
                findings.append({"kind": "observation", "statement": f"按已录入现金、保留额及30天必要付款计算，保守额外支出上限为{baseline['conservative_budget_ceiling']}元；不是盈利判断。", "evidence_ids": [primary_ref]})
                if baseline["overdue_ids"]:
                    findings.append({"kind": "observation", "statement": "存在逾期应付款："+", ".join(baseline["overdue_ids"]), "evidence_ids": [primary_ref]})
            else:
                count = len(values["customer_evidence"]["observations"])
                findings.append({"kind": "observation", "statement": f"当前录入{count}条客户观察；观察条数不等于客户人数或可成交订单数。", "evidence_ids": [primary_ref]})
            return {"action": "final", "result": {
                "notes": [{"statement": "已完成账面筛查；观察与假设分开，不能据此推定经营原因。", "evidence_ids": refs}],
                "findings": findings, "questions": own_questions, "historical_followups": followups, "proposals": []}}
        if role == "cash":
            return {"action": "final", "result": {"notes": [{"statement": "现金约束单独维护，不为了凑角色强行生成商品方案。", "evidence_ids": refs}], "proposals": []}}
        for tool in ("inventory_analyze", "cash_baseline", "feedback_history"):
            if tool not in observed:
                return {"action": "tool", "name": tool, "arguments": {}}
        ledger = c["ledger"]
        bad_previous = [f for f in values["feedback_history"]["outcomes"] if f["owner"] == role and (
            money(f["trial_net_cash"], negative=True) < 0 or (f["trial_margin_contribution"] is not None and money(f["trial_margin_contribution"], negative=True) < 0))]
        if bad_previous:
            return {"action": "final", "result": {"notes": [{
                "statement": "同类历史试验出现负贡献，先核实反馈中的原因，不自动重复投入或外推失败原因。",
                "evidence_ids": refs}], "proposals": []}}
        candidates = [p for p in values["inventory_analyze"]["products"] if p["stock"]
                      and p["unit_price"] is not None and p["unit_cost"] is not None
                      and p["size_complete"] is True]
        if role == "inventory":
            candidates = [p for p in candidates if p["slow_moving"]]
        if role == "customer" and not any("预约" in signal["observation"] for signal in ledger["customer_signals"]):
            return {"action": "final", "result": {"notes": [{
                "statement": "本地规则只支持有预约反馈线索的试验模板；当前缺少相应证据，先调查真实需求。", "evidence_ids": refs}], "proposals": []}}
        if not candidates:
            return {"action": "final", "result": {"notes": ["缺少可售且成本完整的商品，先补充资料"], "proposals": []}}
        budget = min(money(values["cash_baseline"]["conservative_budget_ceiling"]), money("500"))
        if not budget or not values["cash_baseline"]["complete"]:
            return {"action": "final", "result": {"notes": [{
                "statement": "当前没有可确认的额外投入空间或收支记录不完整；先补账并核对必要付款。", "evidence_ids": refs}], "proposals": []}}
        chosen = candidates[:2]
        proposal_id = role + "_trial"
        prior = next((p for p in c.get("proposals", []) if p["id"] == proposal_id), None)
        version = prior["version"] + 1 if prior else 1
        from .linkage import default_refs
        proposal = {"model_refs": default_refs(ledger, role), "id": proposal_id, "version": version, "owner": role,
            "title": "小范围预约试衣假设" if role == "customer" else "库存商品组合清理假设",
            "upfront_cost": amount(budget), "other_cost": "0.00", "spend_date": ledger["as_of"],
            "weekly_hours": min(ledger["weekly_available_hours"], 4), "sales_assumption": "unverified", "costs_confirmed": False,
            "items": [{"sku": p["sku"], "quantity": min(5, p["stock"]), "price": p["unit_price"],
                       "variable_cash_cost": "0.00", "receipt_date": (day(ledger["as_of"])+timedelta(days=7)).isoformat()}
                      for p in chosen],
            "rationale": "本地规则：仅选成本和尺码已知的商品，费用上限取保守现金上限与500元较小值；数量与预算仍需商户确认，不代表最优方案。",
            "evidence_ids": refs, "assumptions": ["试验销量仅为假设，非预测", "变动费用尚需核实"],
            "stop_conditions": ["新增支出接近批准预算即停止", "必要付款或最低现金要求无法满足时停止"]}
        if "proposal_evaluate" not in observed:
            return {"action": "tool", "name": "proposal_evaluate", "arguments": {"proposal": proposal}}
        if ledger.get("operating_periods") and "business_diagnostics" not in observed:
            return {"action": "tool", "name": "business_diagnostics", "arguments": {}}
        from .experiment_drafts import rule_draft
        draft = rule_draft(ledger, proposal, refs)
        return {"action": "final", "result": {"notes": [{"statement": "待验证的规则测试提案", "evidence_ids": refs}], "proposals": [proposal], "experiment_drafts": [draft] if draft else []}}


class SimulationProvider(RuleProvider):
    """Explicit transport/protocol rehearsal, never a claim of model reasoning."""
    mode = "simulation"

    def __init__(self, case="normal", control=None):
        if case not in ("normal", "conflict", "malformed", "timeout", "slow"):
            raise ValidationError("未知离线模拟场景")
        self.case, self.control = case, control or RunControl()

    def step(self, context):
        if self.case == "slow":
            if self.control.cancel.wait(0.2):
                self.control.check()
        if self.case == "timeout":
            raise ProviderError("离线模拟：响应超时；未联系任何云端服务")
        if self.case == "malformed":
            return decode_response(b'{"content":"invalid action"}', "application/json")
        action = super().step(context)
        if self.case == "conflict" and context["role"] == "customer" and context["phase"] == "propose":
            proposals = action.get("result", {}).get("proposals", [])
            if action.get("name") == "proposal_evaluate":
                proposals = [action["arguments"]["proposal"]]
            for p in proposals:
                p["upfront_cost"] = amount(money(context["ledger"]["max_trial_budget"]) + 1)
        wire = ("data:" + json.dumps({"event": "message", "data": {"node_type": "End", "text": json.dumps(action, ensure_ascii=False)}}, ensure_ascii=False) + "\n\n").encode()
        return decode_response(wire, "text/event-stream")
