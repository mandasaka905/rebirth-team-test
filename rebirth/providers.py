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


class ResponseFormatError(ProviderError):
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
        if value.startswith("```") and value.endswith("```"):
            first,sep,rest=value.partition('\n')
            if sep and first.lower() in ('```json','```'):value=rest[:-3].strip()
        try:
            return extract_action(json.loads(value))
        except (json.JSONDecodeError, RecursionError):
            pass
        # Some managed models prepend a short explanation. Accept only one
        # complete action object at the end, never multiple or embedded actions.
        start=value.find('{')
        if 0<start<=1000 and not any(c in value[:start] for c in '{}[]`'):
            try:
                candidate,end=json.JSONDecoder().raw_decode(value[start:])
                if not value[start+end:].strip() and isinstance(candidate,dict) and candidate.get('action') in ('tool','final'):
                    return candidate
            except (json.JSONDecodeError,RecursionError):pass
    raise ResponseFormatError("云端未返回约定的JSON动作；请核对角色提示词或响应结构")


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

    def __init__(self, config_path, *, control=None, required_roles=None, instruction_override=None):
        self.instruction_override = instruction_override
        self.control = control or RunControl()
        try:
            self.config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ProviderError("无法读取AgentArts本地配置") from exc
        for role in (required_roles if required_roles is not None else ("coordinator", "inventory", "customer", "cash")):
            cfg = self.config.get("agents", {}).get(role)
            if not cfg:
                raise ProviderError(f"尚未配置{role}的AgentArts调用路径")
            parts = urllib.parse.urlsplit(cfg.get("url", ""))
            transport=cfg.get('transport','workflow_http')
            if transport not in ('workflow_http','managed_ws'):
                raise ProviderError('不支持的AgentArts接入方式')
            scheme='wss' if transport=='managed_ws' else 'https'
            if parts.scheme != scheme or not parts.hostname or parts.username or parts.password or parts.fragment or parts.query:
                raise ProviderError("AgentArts调用路径必须是无账号密码的HTTPS URL")
            if parts.hostname not in self.config.get("allowed_hosts", []):
                raise ProviderError("调用域名尚未加入本机allowed_hosts确认列表")
            if not os.environ.get(cfg.get("token_env", "AGENTARTS_TOKEN")):
                raise ProviderError("缺少AgentArts鉴权环境变量；请在本机设置，不要发送到聊天")
            if cfg.get("auth_header", "X-Auth-Token") not in ("Authorization", "X-Auth-Token"):
                raise ProviderError("仅支持Authorization或X-Auth-Token认证头")
        self.sessions = {}
        self.prefetch_readonly_evidence = self.config.get("prefetch_readonly_evidence", True) is True

    def step(self, context):
        cfg = self.config["agents"][context["role"]]
        prompt = self.instruction_override or (ROOT / "agentarts" / "prompts" / f"{context['role']}.md").read_text(encoding="utf-8")
        contracts=json.loads((ROOT/"config/contracts.json").read_text(encoding="utf-8"))
        envelope = {"instruction": prompt, "context": redact_context(context), "output_contract": contracts,
            "execution_protocol":"这是本地宿主驱动的单步协作协议。context.tools列出的业务工具由本地执行，不是云端内置工具。需要证据时只返回一个action=tool的JSON动作；下一次请求的observations携带真实结果。最终只返回一个action=final及result对象。禁止调用云端文件、命令、浏览器或创建计划。契约示例只说明结构，不得照抄示例商品、日期、证据ID或经营模式版本；实际值取自context。"}
        envelope['stage_requirements']={
            'phase':context.get('phase'),'remaining_steps':context.get('remaining_steps',8),
            'fresh_tool_required':context.get('role') in ('inventory','customer','cash') and not any('value' in o for o in context.get('observations',[])),
            'instructions':'每个阶段必须先取得本角色本阶段实际计算的业务工具结果，才可返回final；本阶段host_prefetch结果满足取证要求，不必为相同参数重复调用。own_memory仅供参考，不能替代本阶段的observations。若fresh_tool_required为true，本次只能输出tool动作，不能输出final。调查阶段按需取证，工具充分后结束，不机械遍历。只输出一个完整JSON对象。',
            'concise_output':'调查阶段优先主工具和business_diagnostics，其他工具仅在缺少关键证据时使用。提案阶段每个角色最多一个小范围方案；客户角色可另外提出一个完整经营模式草案。解释写在notes或rationale，不重复长篇输入；资料完整时可为本角色方案提出一个有依据、待商户确认的实验草案，条件不足时保留为空。最多8步动作，本阶段已有6次工具结果时必须整理final。',
            'primary_tool':{'inventory':'inventory_analyze','customer':'customer_evidence','cash':'cash_baseline'}.get(context.get('role'))}
        candidates = context.get('proposals') or []
        if not candidates and isinstance(context.get('ledger', {}).get('candidate_for_review'), dict):
            candidates = [context['ledger']['candidate_for_review']]
        envelope['stage_requirements']['proposal_scope'] = [
            {'proposal_id': p.get('id'), 'version': p.get('version'),
             'has_new_procurement': bool(p.get('procurements')),
             'supplier_terms_required_for_this_plan': bool(p.get('procurements'))}
            for p in candidates]
        envelope['stage_requirements']['prefetched_evidence'] = 'observations中的host_prefetch结果由宿主对当前冻结底账实际计算，带本角色本阶段evidence_id；已满足的相同参数工具无需重复请求。仍须自行审查并给出结论；追加检索或不同参数可继续使用只读工具。'
        envelope['stage_requirements']['cash_cost_rule'] = '已有现货采购款默认已付，unit_cost进入毛利，不复制到variable_cash_cost；variable_cash_cost仅为本次额外包装、平台等单件现金费用。若确有未付采购款，在obligations核实，不重复填入两处。未知费用不能编零或标记已核实。'
        envelope['stage_requirements']['field_meanings'] = {
            'items[].receipt_date': '销售回款日，不是采购到货日',
            'items[].sale_date': '交付日；未填写时按工具规定的默认值计算',
            'procurements': '新增采购安排；为空时本方案仅使用现货，不据此要求新增采购报价或起订量'}
        envelope['stage_requirements']['instructions'] += (
            ' 审查按当前方案范围展开。没有procurements的现货处理方案，不得仅因缺少供货报价、起订量或供货天数而判失败；'
            'receipt_date只表示销售回款日，不能把它当成到货日或据此要求供应商证明。'
            '已有库存数量、成本、未付采购欠款、顾客需求及回款依据仍须核对；'
            '若建议新增采购，再核对相应供应条件。不要把与本次方案无关的资料变成必填。')
        models=context.get('ledger',{}).get('business_models') or []
        envelope['stage_requirements']['business_model_linkage'] = {
            'existing_versions':[{'id':m['id'],'version':m.get('version',1)} for m in models],
            'model_refs_required':bool(models),
            'when_no_models':'允许model_refs=[]的现货等普通候选；不得编造模式版本，也不得把缺少模式档案作为所有方案的前置门槛。'}
        envelope['stage_requirements']['instructions'] += (
            ' 同一阶段需要多项只读资料时，优先用read_tools一次列出主工具、data_readiness和必要的方案计算；'
            '每个子结果会获得独立真实evidence_id。已有资料充分后返回final，不重复读取。'
            ' 没有business_models时，普通经营候选允许model_refs=[]；'
            '已有模式时才引用其精确版本。新商业模式仍须另走草案审阅流程。'
            '降低upfront_cost只是待验证假设；必须说明取消或缩减了哪些具体动作、费用依据和待确认项，'
            '不能把改小金额本身说成降本已可行或经营收益已实现。')
        envelope['stage_requirements']['expense_breakdown']={
            'optional':True,'scope':'只分解upfront_cost+other_cost，不重复计入单件费用或采购',
            'fields':['id','label','quantity','unit_cost','amount','basis','basis_kind'],
            'basis_kind':['assumption','merchant_record'],
            'rules':'数量乘单价等于小计，各项之和等于固定支出；假设费用的costs_confirmed必须false；记录说明并不证明报价真实。'}
        envelope['stage_requirements']['knowledge_citations']={
            'optional':'仅在实际检索资料并用于专业判断时填写assessment.knowledge_citations；未检索时省略或为空。',
            'fields':['claim','document_id','supporting_text','evidence_id','scope_limit'],
            'rules':'evidence_id必须是本阶段knowledge_search的真实记录；document_id须在matches中，supporting_text须摘自其content；scope_limit说明这份资料不能支持什么。程序只验证出处与摘录，语义支持仍须人工复核。'}
        envelope['stage_requirements']['business_model_design']={
            'comparison':'有明确现行模式时，可用business_model_compare比较1至4个模式草案，说明客群、渠道、履约或收入方式的变化；没有依据时保留补证，不强凑模式。',
            'costs':'model.unit_cost_components可逐项记录商品、平台、包装、配送等每单费用，字段id、label、amount（未知用null）、basis、basis_kind（assumption或merchant_record）。分项与unit_cost一致；存在未知分项时unit_cost为null，假设不得标为已核实。',
            'review':'比较工具不代替各角色对精确草案版本的model_draft_evaluate及model_reviews。不得把文字变化等同于商业创新，订单和收益均非预测。'}
        if context.get('collaboration_protocol') == 2:
            phase, role = context.get('phase'), context.get('role')
            schema = contracts['collaboration_protocol_2']
            final = {'notes': []}
            if role == 'coordinator':
                final.update(coordination_tasks=schema['coordination_tasks'], revise_roles=[])
            else:
                final['assessment'] = schema['assessment']
                if phase == 'review': final.update(proposal_reviews=schema['proposal_reviews'], objections=[])
                elif phase == 'revise': final.update(revision_responses=schema['revision_responses'], proposals=[])
                elif phase == 'propose': final.update(proposals=[])
                elif phase == 'investigate': final.update(findings=[])
                if role=='customer' and phase in ('propose','revise'):final['model_drafts']=[]
                if phase=='review' and context.get('model_drafts'):final['model_reviews']=[contracts['model_review_contract']]
            # Keep the primary final example consistent with the enforced protocol.
            envelope['output_contract']['final_action'] = {'action':'final', 'result':final}
            envelope['stage_requirements']['current_evidence_ids'] = [o['evidence_id'] for o in context.get('observations', []) if 'value' in o]
            observed = {o.get('tool') for o in context.get('observations', []) if 'value' in o}
            if (phase == 'revise' and 'proposal_evaluate' in observed) or (phase == 'investigate' and 'data_readiness' in observed and envelope['stage_requirements']['primary_tool'] in observed):
                envelope['stage_requirements']['next_action_hint'] = '必要取证已具备，优先返回完整final；直接引用current_evidence_ids，不重复调用相同工具。每条说明尽量80字内。'
            envelope['stage_requirements']['required_result_fields'] = (
                ['coordination_tasks', 'revise_roles'] if role == 'coordinator' else
                ['assessment'] + (['proposal_reviews', 'objections'] if phase == 'review' else ['revision_responses'] if phase == 'revise' else []))
            envelope['stage_requirements']['instructions'] += ' 协作协议2字段不可省略。调查必须先调用本角色主工具和data_readiness，按field_id覆盖本角色全部已知缺口；review逐个调用当前版本proposal_evaluate；协调必须逐项回应coordination_requirements。字段结构见collaboration_protocol_2。每条解释尽量控制在80字内。'
        from .provider_contracts import clarify
        clarify(envelope,context)
        token = os.environ[cfg.get("token_env", "AGENTARTS_TOKEN")]
        auth_header = cfg.get("auth_header", "X-Auth-Token")
        session_key = (context["run_id"], context["role"])
        session = self.sessions.setdefault(session_key, uuid4().hex)
        if cfg.get('transport')=='managed_ws':
            if auth_header!='Authorization':
                raise ProviderError('Managed Agents需要Authorization认证')
            from .managed_ws import invoke
            return invoke(cfg['url'],token,uuid4().hex,envelope,self.control,observer=getattr(self,'frame_observer',None))
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
            if c.get('collaboration_protocol') == 2:
                for proposal in c.get('proposals', []):
                    if not any(o.get('tool') == 'proposal_evaluate' and 'value' in o and o.get('arguments', {}).get('proposal', {}).get('id') == proposal['id'] for o in c['observations']):
                        return {'action': 'tool', 'name': 'proposal_evaluate', 'arguments': {'proposal': proposal}}
            reviews=[]
            for d in c.get("model_drafts",[]):
                obs=next((o for o in c["observations"] if o.get("tool")=="model_draft_evaluate" and o.get("arguments",{}).get("draft",{}).get("id")==d["id"] and "value" in o),None)
                if obs is None:return {"action":"tool","name":"model_draft_evaluate","arguments":{"draft":d}}
                v=obs["value"]
                reviews.append({"draft_id":d["id"],"version":d["version"],"status":"blocked" if v["blockers"] else "needs_data" if v["warnings"] else "pass",
                                "reason":"；".join(v["perspectives"][role]),"evidence_ids":[obs["evidence_id"]]})
            result["model_reviews"]=reviews
        if c.get('collaboration_protocol') == 2:
            from .collaboration_protocol import rule_contract
            rule_contract(c, result)
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
                "notes": ["先核对未解决的问题，再决定是否尝试方案。"]}}
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
            return {"action": "final", "result": {"notes": [{"statement": "先核对必要付款和备用金，再看是否有余力尝试。", "evidence_ids": refs}], "proposals": []}}
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
                "statement": "缺少预约需求记录，先了解顾客是否愿意预约。", "evidence_ids": refs}], "proposals": []}}
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
        return {"action": "final", "result": {"notes": [{"statement": "这个办法需要先小范围验证。", "evidence_ids": refs}], "proposals": [proposal], "experiment_drafts": [draft] if draft else []}}


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
