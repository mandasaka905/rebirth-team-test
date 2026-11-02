"""One draft contract for rules, simulation and AgentArts; drafts never activate trials."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from .domain import ValidationError, day, identifier, nonempty, amount
from .research import validate_design, window
from .linkage import resolve


def period_baseline(ledger, period_id, scope_id, count_basis):
    period = next((p for p in ledger.get("operating_periods", []) if p["id"] == period_id), None)
    if period is None:
        raise ValidationError("草案基准须引用本次底账的真实经营期间ID")
    if scope_id != period.get("scope_id", "shop_all") or count_basis != period.get("count_basis", "person_visits"):
        raise ValidationError("实验草案范围或计数口径与实际基准期间不一致")
    return {"start":period["start"], "end":period["end"], "revenue":period.get("revenue"),
            "goods_cost":period.get("goods_cost"), "expenses":period.get("operating_cost"),
            "visits":period.get("visits"), "buyers":period.get("buyers"),
            "source_note":ledger["sources"][period["source_id"]], "scope_id":scope_id, "count_basis":count_basis}


def validate_draft(raw, proposal, ledger):
    if not isinstance(raw, dict):
        raise ValidationError("实验草案必须为对象")
    d = deepcopy(raw)
    identifier(d.get("id"))
    if d.get("proposal_id") != proposal["id"] or type(d.get("proposal_version")) is not int or d["proposal_version"] != proposal["version"] or d.get("owner") != proposal["owner"]:
        raise ValidationError("实验草案须绑定本角色方案的精确版本")
    resolve(ledger, proposal)
    nonempty(d.get("target_basis"), "草案目标依据与假设")
    if not isinstance(d.get("evidence_ids"), list) or not d["evidence_ids"]:
        raise ValidationError("实验草案须引用本次工具证据")
    design = d.get("design")
    if not isinstance(design, dict):
        raise ValidationError("草案缺少结构化设计")
    # Numeric baseline always comes from the immutable ledger, never an LLM invention.
    design["baseline"] = period_baseline(ledger, d.get("baseline_period_id"), design.get("scope_id"), design.get("count_basis"))
    design["scope_confirmed"] = False
    design["source_note"] = "待人工审阅的实验草案；"+d["target_basis"]
    validate_design(design, {"spend_date":proposal["spend_date"],"end_date":(day(ledger["as_of"])+timedelta(days=30)).isoformat()}, ledger, draft=True)
    d["model_refs"] = deepcopy(proposal.get("model_refs", []))
    return d


def rule_draft(ledger, proposal, refs):
    periods = [p for p in ledger.get("operating_periods", []) if day(p["end"]) < day(proposal["spend_date"])]
    if not periods:
        return None
    p = max(periods, key=lambda p:p["end"])
    scope, basis = p.get("scope_id", "shop_all"), p.get("count_basis", "person_visits")
    try:
        baseline = period_baseline(ledger,p["id"],scope,basis)
        value = window(baseline,baseline["start"],baseline["end"])["revenue_per_day"]
        start = day(proposal["spend_date"])
        draft = {"id":"draft_"+proposal["id"]+"_v"+str(proposal["version"]),
                 "proposal_id":proposal["id"],"proposal_version":proposal["version"],"owner":proposal["owner"],
                 "baseline_period_id":p["id"],"evidence_ids":list(refs),
                 "target_basis":"本地规则演练：以已有基准日均销售额的1.05倍作为明示目标假设，5%不是市场预测或统计功效结论，须人工修改确认",
                 "design":{"hypothesis":proposal["title"]+"能否在约束内改善同口径观察",
                     "intervention":proposal["title"],"metric":"revenue_per_day","target_value":amount(value*Decimal("1.05")),
                     "min_days":7,"min_visits":20,"observe_start":start.isoformat(),
                     "observe_end":(start+timedelta(days=6)).isoformat(),
                     "scope_id":scope,"scope_description":"全店同口径经营，不能与单项SKU收款混比","count_basis":basis,
                     "comparison_method":"同范围前后对比，记录实际营业时长差异",
                     "confounders":"季节、天气、客流、同期活动和投入工时",
                     "stop_rule":"预算和现金硬退出线始终生效；其他规则需人工转成结构化条件",
                     "exit_rules":[]}}
        return validate_draft(draft,proposal,ledger)
    except ValidationError:
        return None  # Incomplete baseline is not manufactured into a draft.

