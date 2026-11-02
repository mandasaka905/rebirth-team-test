"""Additional local endpoints; no outgoing requests during inspection or preview."""
from copy import deepcopy
from .business import STRATEGIES, diagnostics
from .domain import ValidationError
from .knowledge import search
from .preflight import inspect_config, redact_context
import json
from pathlib import Path


def get_route(handler, parts, store, jobs, config_path, allow_cloud):
    if parts == ["api", "preflight"]:
        handler.reply(200, inspect_config(config_path, allow_cloud))
    elif parts == ["api", "acceptance-example"]:
        handler.reply(200, json.loads((Path(__file__).resolve().parent.parent/"examples/acceptance.synthetic.json").read_text(encoding="utf-8")))
    elif parts == ["api", "planning-example"]:
        handler.reply(200, json.loads((Path(__file__).resolve().parent.parent/"examples/planning.synthetic.json").read_text(encoding="utf-8")))
    elif parts == ["api", "operating-templates"]:
        from .operating_imports import TEMPLATES
        handler.reply(200, {"templates":TEMPLATES})
    elif parts == ["api", "strategies"]:
        handler.reply(200, {"strategies": STRATEGIES})
    elif len(parts) >= 4 and parts[:2] == ["api", "merchants"]:
        merchant, action = parts[2:4]
        if len(parts) == 4:
            if action == "community":
                value = store.community_home(merchant)
            elif action == "social":
                value = store.social_home(merchant)
            elif action == "agendas":
                value = store.agendas(merchant)
            elif action == "workbench":
                value = store.workbench(merchant)
            elif action == "design-template":
                raise ValidationError("请使用POST并指定试验")
            elif action == "diagnostics":
                value = diagnostics(store.ledger(merchant))
            elif action == "knowledge":
                value = {"documents": store.knowledge(merchant)}
            elif action == "feedback-journal":
                value = {"entries": store.feedback_journal(merchant)}
            elif action == "experiments":
                value = {"experiments": store.experiments(merchant)}
            elif action == "investigations":
                value = {"cards": store.investigations(merchant)}
            elif action == "export":
                value = store.export_bundle(merchant)
            elif action == "outbound-preview":
                value = {"preview": redact_context({"ledger": store.ledger(merchant)}), "notice": "预览为结构化标识和常见个人信息最小化后的底账；经营金额、价格、客户观察仍属敏感资料。自由文字不能保证自动脱敏，请逐项检查。经营模式与采购/收支账簿也在底账内；历史反馈、实验评价、检索片段和工具计算会作为后续上下文发送。"}
            else:
                return False
            handler.reply(200, value)
        elif len(parts) == 5 and action == "jobs":
            handler.reply(200, jobs.get(merchant, parts[4]))
        else:
            return False
    else:
        return False
    return True


def post_route(handler, parts, data, store, jobs):
    if parts == ["api", "jobs"]:
        handler.reply(202, jobs.start(data))
    elif len(parts) >= 4 and parts[:2] == ["api", "merchants"]:
        merchant, action = parts[2:4]
        if len(parts) == 4:
            community_actions={"experience-consent":"experience_consent","support-consent":"support_consent","support-request":"support_request","support-event":"support_event","experience-share":"experience_share","experience-withdraw":"experience_withdraw","experience-adopt":"experience_adopt","experience-result":"experience_result","support-handover":"support_handover","impact-start":"impact_start","impact-observe":"impact_observe","industry-review":"industry_review","mutual-resource":"save_resource","mutual-transfer":"mutual_transfer","mutual-receipt":"mutual_receipt"}
            if action in community_actions:
                if not isinstance(data,dict):raise ValidationError("请提交结构化表单")
                value=getattr(store,community_actions[action])(merchant,data)
            elif action == "agenda-preview":
                value = store.agenda_preview(merchant, data)
            elif action == "agendas":
                value = store.save_agenda(merchant, data)
            elif action == "agenda-progress":
                value = store.agenda_progress(merchant, data)
            elif action in ("operating-preview", "operating-import"):
                value = store.operating_import(merchant, data, commit=action=="operating-import")
            elif action in ("mode-decision", "mode-preview"):
                value = store.mode_decision(merchant, data, commit=action=="mode-decision")
            elif action == "supply-options":
                value = store.save_section(merchant, "supply_options", data.get("offers"), data.get("source_note"))
            elif action == "models":
                value = store.save_section(merchant, "business_models", data.get("models"), data.get("source_note"))
            elif action == "accounts":
                value = store.save_section(merchant, "accounts", data.get("accounts"), data.get("source_note"))
            elif action in ("accounts-preview", "accounts-import"):
                value = store.import_accounts(merchant, data, commit=action == "accounts-import")
            elif action == "portfolio":
                value = store.select_portfolio(merchant, data)
            elif action == "draft-preview":
                value = store.draft_preview(merchant, data.get("trial_id"), data.get("draft_id"))
            elif action == "cohorts":
                value = store.save_section(merchant, "customer_cohorts", data.get("cohorts"), data.get("source_note"))
            elif action == "design-template":
                value = store.design_template(merchant, data.get("trial_id"))
            elif action == "design":
                value = store.save_design(merchant, data)
            elif action == "measurement":
                value = store.save_measurement(merchant, data)
            elif action == "periods":
                value = store.put_period(merchant, data)
            elif action == "knowledge":
                value = store.add_knowledge(merchant, data)
            elif action == "knowledge-search":
                value = search(store.knowledge(merchant), data.get("query"))
            elif action == "feedback-update":
                value = store.advance_feedback(merchant, data)
            elif action == "experiments":
                value = store.save_experiment(merchant, data)
            elif action == "investigations":
                value = store.save_investigation(merchant, data)
            elif action == "import-copy":
                from uuid import uuid4
                ledger = deepcopy(data.get("ledger"))
                if not isinstance(ledger, dict):
                    raise ValidationError("导入需要ledger对象；只恢复店铺资料副本，不覆盖原店铺或历史任务")
                ledger["merchant_id"] = "shop_" + uuid4().hex[:16]
                ledger["name"] += "（导入副本）"
                value = store.put_ledger(ledger)
            else:
                return False
            handler.reply(201, value)
        elif len(parts) == 6 and action == "jobs" and parts[5] == "cancel":
            handler.reply(200, jobs.cancel(merchant, parts[4]))
        else:
            return False
    else:
        return False
    return True
