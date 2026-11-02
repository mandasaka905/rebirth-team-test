"""Final pre-model workflows use optimistic concurrency and an append-only audit journal."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json
from .domain import ValidationError, nonempty, validate_ledger
from .operating_imports import preview
from .model_drafts import assess_draft

class CompletionWorkflows:
    def commit_change(self,merchant,before,after,kind,data,unique=None):
        after=validate_ledger(after)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT data FROM ledgers WHERE merchant=?",(merchant,)).fetchone()
            if not row or json.loads(row[0])!=before:raise ValidationError("资料同时被修改，请重新预览")
            if unique:
                previous=db.execute("SELECT data FROM workbench_records WHERE merchant=? AND kind=?",(merchant,kind)).fetchall()
                if any(json.loads(r[0]).get(unique[0])==unique[1] for r in previous):raise ValidationError("该导入或草案已处理，不能重复保存")
            db.execute("UPDATE ledgers SET data=? WHERE merchant=?",(json.dumps(after,ensure_ascii=False,allow_nan=False),merchant))
            rid="wb_"+uuid4().hex
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,kind,json.dumps(data,ensure_ascii=False,allow_nan=False),datetime.now(timezone.utc).isoformat()))
        return {"record_id":rid,"ledger":after}

    def operating_import(self,merchant,raw,commit=False):
        before=self.ledger(merchant);p=preview(before,raw)
        if commit:
            if raw.get("confirmed") is not True or raw.get("preview_digest")!=p["preview_digest"]:raise ValidationError("请先预览并确认未变化的完整CSV；旧预览已失效")
            saved=self.commit_change(merchant,before,p["ledger"],"operating_import",{**{k:v for k,v in p.items() if k!='ledger'},"kind":raw["kind"],"source_note":raw["source_note"]},("batch_digest",p["batch_digest"]))
            p["record_id"]=saved["record_id"]
        return {k:v for k,v in {**p,"committed":commit}.items() if k!='ledger'}

    def mode_decision(self,merchant,raw,commit=True):
        if not isinstance(raw,dict):raise ValidationError("模式决定须为对象")
        report=self.result(merchant,raw.get("run_id"));before=self.ledger(merchant)
        if report["ledger_changed"] or report["context_changed"] or report["status"] in ("running","failed","cancelled","interrupted"):raise ValidationError("分析未完成或资料已变化，请重新分析再处理草案")
        d=next((d for d in (report["result"] or {}).get("model_drafts",[]) if d["id"]==raw.get("draft_id") and d["version"]==raw.get("version")),None)
        if not d:raise ValidationError("模式草案精确版本不存在")
        if {r["from"] for r in d.get("reviews",[])}!={"inventory","customer","cash"}:raise ValidationError("模式草案缺少三个专业角色交叉审查")
        decision=raw.get("decision","accept")
        if decision not in ("accept","reject"):raise ValidationError("请选择接纳或否决草案")
        nonempty(raw.get("source_note"),"审阅与修改说明")
        if commit and raw.get("confirmed") is not True:raise ValidationError("须由商户明确确认草案处理")
        changed=deepcopy(d)
        if decision=="accept":
            if raw.get("model") is not None:changed["model"]=deepcopy(raw["model"])
            if raw.get("supply_requirements") is not None:changed["supply_requirements"]=deepcopy(raw["supply_requirements"])
            changed["model"]["status"]="candidate"
            assessment=assess_draft(before,changed)
            if assessment["blockers"]:raise ValidationError("候选模式仍有硬约束："+"；".join(assessment["blockers"]))
        else:assessment=None
        if not commit:return {"edited_draft":changed,"assessment":assessment,"original":d,"notice":"只是重新核对，尚未保存"}
        after=deepcopy(before);key=report["run_id"]+":"+d["id"]+":"+str(d["version"])
        if decision=="accept":
            changed["model"].update(id="model_"+uuid4().hex[:16],version=1)
            changed["model"]["source_note"]+="；商户审阅："+raw["source_note"]
            changed["model"].update(supply_requirements=deepcopy(changed["supply_requirements"]), assumptions=deepcopy(changed["assumptions"]), validation_plan=changed["validation_plan"], origin={"run_id":report["run_id"],"draft_id":d["id"],"draft_version":d["version"]})
            after.setdefault("business_models",[]).append(changed["model"])
        data={"decision_key":key,"decision":decision,"run_id":report["run_id"],"original":d,"edited":changed,"assessment":assessment,"source_note":raw["source_note"],
              "notice":"只保存候选模式，不执行经营；人工修改后本地重新核约束，原角色审查意见保留，具体行动仍须新一轮交叉复核"}
        return {**self.commit_change(merchant,before,after,"mode_decision",data,("decision_key",key)),"decision":data}
