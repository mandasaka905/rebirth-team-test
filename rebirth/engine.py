"""Bounded, evidence-linked collaboration with isolated agent working memory."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

from .domain import ValidationError, validate_proposal
from .providers import ProviderError
from .tools import TOOL_ARGS, dispatch
from .control import RunControl, RunCancelled
from .business import compare_candidates


SPECIALISTS = ("inventory", "customer", "cash")


class Engine:
    def __init__(self, store, provider, *, max_steps=8, max_rounds=2, control=None):
        self.store, self.provider = store, provider
        self.control = control or getattr(provider, "control", None) or RunControl(max_calls=96)
        if hasattr(provider, "control"):
            provider.control = self.control
        if not 1 <= max_steps <= 12 or not 0 <= max_rounds <= 2:
            raise ValidationError("工具循环最多12步，修订最多2轮")
        self.max_steps, self.max_rounds = max_steps, max_rounds

    def call(self, merchant, run, ledger, role, phase, *, proposals=None, reviews=None, model_drafts=None):
        observations = []
        memory = [e for e in self.store.events(merchant, run) if e["actor"] == role and e["kind"] == "agent_result"]
        # Feedback selection is frozen at task creation rather than reread mid-run.
        history_event = next((e for e in self.store.events(merchant, run) if e["kind"] == "history_snapshot"), None)
        history = history_event["data"]["outcomes"] if history_event else []
        docs = next((e["data"]["documents"] for e in self.store.events(merchant, run) if e["kind"] == "knowledge_snapshot"), [])
        cards = next((e["data"]["cards"] for e in self.store.events(merchant, run) if e["kind"] == "investigation_snapshot"), [])
        for step in range(self.max_steps):
            self.control.check()
            context = {"run_id": run, "role": role, "phase": phase,
                "ledger": deepcopy(ledger), "tools": TOOL_ARGS,
                "own_memory": memory, "observations": observations,
                "proposals": deepcopy(proposals or []), "reviews": deepcopy(reviews or []), "model_drafts": deepcopy(model_drafts or [])}
            if not getattr(self.provider, "handles_budget", False):
                self.control.reserve(len(json.dumps(context, ensure_ascii=False).encode()))
            action = self.provider.step(context)
            if not getattr(self.provider, "handles_budget", False):
                self.control.receive(len(json.dumps(action, ensure_ascii=False).encode()))
            self.control.check()
            if not isinstance(action, dict):
                raise ProviderError("智能体动作必须是JSON对象")
            if action.get("action") == "tool":
                name, args = action.get("name"), action.get("arguments", {})
                try:
                    value = dispatch(ledger, name, args, history=history, knowledge=docs, investigations=cards, research=history_event["data"].get("experiment_reviews", []) if history_event else [])
                    data = {"phase": phase, "tool": name, "arguments": args, "value": value}
                    evidence_id = self.store.event(merchant, run, role, "tool_result", data)
                    observations.append({**data, "evidence_id": evidence_id})
                except (ValidationError, KeyError) as exc:
                    self.store.event(merchant, run, role, "tool_error", {"phase": phase, "tool": name, "error": str(exc)})
                    observations.append({"tool": name, "arguments": args, "error": str(exc)})
                continue
            if action.get("action") != "final" or not isinstance(action.get("result"), dict):
                raise ProviderError("智能体必须返回tool动作或final/result对象")
            result = action["result"]
            if role in SPECIALISTS and not any("value" in o for o in observations):
                raise ValidationError("专业智能体必须先调查工具证据，不能直接输出角色台词")
            self.validate_result(merchant, run, role, phase, result, proposals or [], model_drafts or [])
            self.store.event(merchant, run, role, "agent_result", {"phase": phase, "result": result})
            return result
        raise ProviderError(f"{role}/{phase}超过工具循环上限；该轮未生成有效结果")

    def validate_result(self, merchant, run, role, phase, result, proposals, model_drafts=()):
        evidence = {e["id"] for e in self.store.events(merchant, run) if e["kind"] == "tool_result"}
        def check_refs(refs):
            if not isinstance(refs, list) or not refs or not all(isinstance(x, str) for x in refs) or not set(refs) <= evidence:
                raise ValidationError("智能体引用不存在或不属于本次任务的工具证据")
        for field in ("notes", "proposals", "objections", "findings", "experiment_drafts", "model_drafts", "model_reviews"):
            if not isinstance(result.get(field, []), list):
                raise ValidationError(f"{field}必须为列表")
        from .model_drafts import validate_draft as validate_model_draft
        if len(result.get("model_drafts",[]))>3: raise ValidationError("每轮模式草案最多3份")
        seen_models=set()
        for d in result.get("model_drafts",[]):
            validate_model_draft(d)
            if role!="customer" or phase not in ("propose","revise"): raise ValidationError("模式草案仅由客户角色在提案或修订阶段提交")
            if d["id"] in seen_models: raise ValidationError("模式草案ID重复")
            seen_models.add(d["id"]);check_refs(d["evidence_ids"])
            prior=next((x for x in model_drafts if x["id"]==d["id"]),None)
            if d["version"]!=(prior["version"]+1 if prior else 1):raise ValidationError("模式草案版本须连续递增")
        for review in result.get("model_reviews",[]):
            matched=next((d for d in model_drafts if d["id"]==review.get("draft_id") and d["version"]==review.get("version")),None)
            if phase!="review" or role not in SPECIALISTS or not matched: raise ValidationError("模式审查须对应精确版本和专业角色")
            if review.get("status") not in ("pass","needs_data","blocked"):raise ValidationError("模式审查状态无效")
            check_refs(review.get("evidence_ids"));nonempty=review.get("reason")
            if not isinstance(nonempty,str) or not nonempty.strip():raise ValidationError("模式审查须给出理由")
        seen = set()
        for p in result.get("proposals", []):
            validate_proposal(p)
            from .linkage import resolve
            resolve(json.loads(self.store.check(merchant, run)["snapshot"]), p)
            if p.get("sales_assumption") == "observed":
                raise ValidationError("新方案的未来销量不能由模型标记为已观测成交")
            if phase not in ("propose", "revise"):
                raise ValidationError("仅提案或修订阶段可以提交方案")
            if p["id"] in seen:
                raise ValidationError("智能体重复提交方案ID")
            seen.add(p["id"])
            if p["owner"] != role:
                raise ValidationError("智能体不可冒用其他角色提交方案")
            check_refs(p["evidence_ids"])
            prior = next((x for x in proposals if x["id"] == p["id"]), None)
            expected = prior["version"] + 1 if prior else 1
            if type(p.get("version")) is not int or p["version"] != expected:
                raise ValidationError("方案版本必须连续递增")
        from .experiment_drafts import validate_draft
        draft_ids = set()
        if len(result.get("experiment_drafts", [])) > 4: raise ValidationError("单角色实验草案最多4份")
        for d in result.get("experiment_drafts", []):
            if not isinstance(d, dict): raise ValidationError("实验草案须为对象")
            if phase not in ("propose", "revise"):
                raise ValidationError("仅提案或修订阶段可以输出实验草案")
            owner_plan = next((p for p in result.get("proposals", []) if p["id"] == d.get("proposal_id")), None)
            if not owner_plan or d.get("owner") != role:
                raise ValidationError("实验草案只能绑定本次提交的本角色方案")
            normalized = validate_draft(d, owner_plan, json.loads(self.store.check(merchant, run)["snapshot"]))
            check_refs(normalized["evidence_ids"])
            if normalized["id"] in draft_ids: raise ValidationError("实验草案ID重复")
            draft_ids.add(normalized["id"]); d.clear(); d.update(normalized)
        for note in result.get("notes", []):
            if isinstance(note, dict) and "evidence_ids" in note:
                check_refs(note["evidence_ids"])
        for finding in result.get("findings", []):
            if not isinstance(finding, dict) or finding.get("kind") not in ("observation", "hypothesis") or not finding.get("statement"):
                raise ValidationError("调查发现必须区分observation或hypothesis，并提供说明")
            check_refs(finding.get("evidence_ids"))
        for objection in result.get("objections", []):
            if phase != "review":
                raise ValidationError("仅审查阶段可以提交质询")
            matched = next((x for x in proposals if x["id"] == objection.get("proposal_id")), None)
            if not matched or objection.get("version") != matched["version"]:
                raise ValidationError("质询必须指向当前方案的精确版本")
            check_refs(objection.get("evidence_ids"))
            if not objection.get("reason") or not objection.get("request"):
                raise ValidationError("质询必须包含理由与修改请求")
        if role == "coordinator":
            revise_roles = result.get("revise_roles", [])
            if not isinstance(revise_roles, list) or not all(isinstance(x, str) for x in revise_roles) or not set(revise_roles) <= set(SPECIALISTS):
                raise ValidationError("协调智能体返回未知角色")

    def parallel(self, merchant, run, ledger, phase, roles=SPECIALISTS, **kwargs):
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {r: pool.submit(self.call, merchant, run, ledger, r, phase, **kwargs) for r in roles}
            # The phase is an isolation barrier: proposals are only shared after all finish.
            return {r: f.result() for r, f in futures.items()}

    def execute(self, merchant, *, draft=None, parent_run=None):
        run, ledger = self.store.new_run(merchant, self.provider.mode)
        self.run_id = run
        try:
            self.store.event(merchant, run, "coordinator", "task_opened", {
                "mode": self.provider.mode, "synthetic": ledger["synthetic"],
                "notice": "真实AgentArts请求" if self.provider.mode == "agentarts" else "本地规则/协议模拟；不调用模型"})
            self.store.event(merchant, run, "coordinator", "history_snapshot", {"outcomes": self.store.feedback_history(
                merchant, as_of=ledger["as_of"], synthetic=ledger["synthetic"]), "experiment_reviews": self.store.research_evidence(merchant, ledger["as_of"])})
            self.store.event(merchant, run, "coordinator", "knowledge_snapshot", {"documents": self.store.knowledge(merchant)})
            self.store.event(merchant, run, "coordinator", "investigation_snapshot", {"cards": self.store.investigations(merchant, as_of=ledger["as_of"])})
            investigated = self.parallel(merchant, run, ledger, "investigate")
            initial = self.parallel(merchant, run, ledger, "propose") if draft is None else {}
            proposals = []
            if draft is not None:
                parent = self.store.result(merchant, parent_run)
                if (parent.get("result") or {}).get("status") in (None, "failed", "cancelled", "running", "interrupted"):
                    raise ValidationError("原任务尚未完成，不能作为方案编辑依据")
                if parent["ledger_changed"] or parent.get("context_changed"):
                    raise ValidationError("资料已变化，先重新分析再编辑方案")
                before = next((x["proposal"] for x in (parent["result"] or {}).get("proposals", []) if x["proposal"]["id"] == draft.get("id")), None)
                new_candidate = draft.get("new_candidate") is True and before is None and draft.get("version") == 1
                if not new_candidate and (not before or draft.get("owner") != before["owner"] or draft.get("version") != before["version"] + 1):
                    raise ValidationError("编辑必须基于原方案并连续增加版本")
                p = validate_proposal(deepcopy(draft))
                p["sales_assumption"] = "merchant_estimate"
                from .linkage import resolve
                resolve(ledger, p)
                refs = []
                for tool in ("inventory_analyze", "cash_baseline", "customer_evidence", "business_diagnostics"):
                    refs.append(self.store.event(merchant, run, p["owner"], "tool_result", {"phase": "revise", "tool": tool, "arguments": {}, "value": dispatch(ledger, tool, {})}))
                p["evidence_ids"] = refs
                self.store.event(merchant, run, "merchant", "proposal_revision", {"before": before, "after": p, "parent_run": parent_run, "review_refs": []})
                proposals.append(p)
            for role, result in initial.items():
                for p in result.get("proposals", []):
                    if any(p["id"] == x["id"] for x in proposals):
                        raise ValidationError("不同角色的方案ID冲突")
                    proposals.append(p)
            model_drafts = [d for value in initial.values() for d in value.get("model_drafts", [])]
            if len({d["id"] for d in model_drafts}) != len(model_drafts): raise ValidationError("模式草案ID冲突")
            final_model_reviews = []
            final_reviews = []
            completed_rounds = 0
            for round_index in range(self.max_rounds + 1):
                reviews_by_role = self.parallel(merchant, run, ledger, "review", proposals=proposals, model_drafts=model_drafts)
                reviews = []
                for p in proposals:
                    reviews.append({"proposal_id": p["id"], "version": p["version"],
                        "objections": [{"from": role, **o} for role, r in reviews_by_role.items()
                            for o in r.get("objections", []) if o["proposal_id"] == p["id"]]})
                final_model_reviews = [{"from":r, **v} for r, result in reviews_by_role.items() for v in result.get("model_reviews", [])]
                for d in model_drafts:
                    d["reviews"]=[r for r in final_model_reviews if r["draft_id"]==d["id"] and r["version"]==d["version"]]
                final_reviews = reviews
                decision = self.call(merchant, run, ledger, "coordinator", "coordinate", proposals=proposals, reviews=reviews, model_drafts=model_drafts)
                roles = set(decision.get("revise_roles", []))
                # The coordinator cannot suppress failed deterministic checks.
                for p in proposals:
                    value = dispatch(ledger, "proposal_evaluate", {"proposal": p})
                    self.store.event(merchant, run, "coordinator", "constraint_check", {"version": p["version"], "value": value})
                    if value["checks"] or any(r["proposal_id"] == p["id"] and r["objections"] for r in reviews):
                        roles.add(p["owner"])
                from .model_drafts import assess_draft
                if any(assess_draft(ledger,d)["blockers"] for d in model_drafts) or any(r["status"]=="blocked" for r in final_model_reviews): roles.add("customer")
                if not roles or round_index == self.max_rounds:
                    break
                revised = self.parallel(merchant, run, ledger, "revise", roles=tuple(sorted(roles)), proposals=proposals, reviews=reviews, model_drafts=model_drafts)
                for role, result in revised.items():
                    for d in result.get("model_drafts", []):
                        self.store.event(merchant, run, role, "model_revision", {"before": next((x for x in model_drafts if x["id"]==d["id"]),None), "after": d})
                        model_drafts=[x for x in model_drafts if x["id"]!=d["id"]]+[d]
                    replacements = result.get("proposals", [])
                    for new in replacements:
                        previous = next((p for p in proposals if p["id"] == new["id"]), None)
                        if previous is not None and previous["owner"] != role:
                            raise ValidationError("不能覆盖其他智能体的方案")
                        self.store.event(merchant, run, role, "proposal_revision", {
                            "before": previous, "after": new,
                            "review_refs": [r for r in reviews if r["proposal_id"] == new["id"]]})
                        proposals = [p for p in proposals if p["id"] != new["id"]] + [new]
                completed_rounds += 1
            evaluated = [{"proposal": p, "evaluation": dispatch(ledger, "proposal_evaluate", {"proposal": p}),
                          "objections": next((r["objections"] for r in final_reviews if r["proposal_id"] == p["id"]), [])}
                         for p in proposals]
            has_unknown = any(x["evaluation"]["unknowns"] for x in evaluated)
            feasible = [x for x in evaluated if x["evaluation"]["constraint_pass"] and not x["objections"]]
            status = "needs_data" if not evaluated or has_unknown else ("awaiting_merchant_choice" if feasible else "unresolved")
            if self.provider.mode in ("rules", "simulation", "manual"):
                status = "rehearsal_only"
            from .experiment_drafts import rule_draft
            experiment_drafts = []
            for event in self.store.events(merchant, run):
                if event["kind"] == "agent_result":
                    for d in event["data"]["result"].get("experiment_drafts", []):
                        if any(p["id"] == d["proposal_id"] and p["version"] == d["proposal_version"] for p in proposals):
                            experiment_drafts.append(d)
            if draft is not None:
                for p in proposals:
                    generated = rule_draft(ledger, p, p["evidence_ids"])
                    if generated: experiment_drafts.append(generated)
            result = {"model_drafts": [{**d, "reviews":[r for r in final_model_reviews if r["draft_id"]==d["id"] and r["version"]==d["version"]], "evaluation":assess_draft(ledger,d)} for d in model_drafts], "experiment_drafts": experiment_drafts, "status": status, "mode": self.provider.mode, "revision_rounds": completed_rounds,
                      "plans_are_alternatives": True, "proposals": evaluated,
                      "readiness": dispatch(ledger, "data_readiness", {}),
                      "investigations": investigated,
                      "comparison": compare_candidates(([x for x in parent["result"].get("proposals", []) if before is None or x["proposal"]["id"] == before["id"]] if draft is not None else []) + evaluated), "parent_run": parent_run,
                      "usage": self.control.status(),
                      "next_action": "补充并确认真实经营资料；仅供商户审阅，不自动执行任何经营动作。",
                      "limitations": ["可模拟现货及已核实供应条件的补货；不自动采购、发送营销或转账。",
                                      "所有销量为显式情景假设；不估计成功概率或承诺收益。",
                                      "历史反馈以已录入且时间有效的观察供角色调查，不自动更新模型或证明经营因果。"]}
            self.store.finish(merchant, run, result)
        except Exception as exc:
            self.store.event(merchant, run, "coordinator", "run_failed", {"type": type(exc).__name__})
            self.store.finish(merchant, run, {"status": "cancelled" if isinstance(exc, RunCancelled) else "failed", "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "usage": self.control.status(), "next_action": "保留已有记录，不回退规则模式。"})
            raise
        return self.store.result(merchant, run)
