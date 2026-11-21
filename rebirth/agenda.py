"""Evidence-linked, deterministic daily agenda. It never executes merchant actions."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4
from .domain import ValidationError, day, integer, money, amount, nonempty


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def selected_entry(report, request):
    pid=request.get("proposal_id")
    if not pid:return None
    row=next((r for r in report["result"].get("proposals",[]) if r["proposal"]["id"]==pid and r["proposal"]["version"]==request.get("proposal_version")),None)
    if row is None:raise ValidationError("请选择此任务中存在的精确方案版本")
    return row


def clearance(store, merchant, report, entry, start, end):
    l=store.ledger(merchant);issues=[]
    if report["ledger_changed"] or report["context_changed"]:issues.append("底账或依据已更新，需要重新核查")
    if not l.get("merchant_confirmed") or not all(l["completeness"].values()):issues.append("先由店主核对底账完整性与经营约束")
    pending=store.questions(merchant)["questions"]
    if pending:issues.append(f"还有{len(pending)}项资料待核对，先完成补证")
    if not entry:return issues+["尚未选择一个互斥候选；本次只整理补证与准备任务"]
    p=entry["proposal"];ev=entry["evaluation"]
    if not ev.get("constraint_pass") or entry.get("objections"):issues.append("方案仍有硬约束或未解决异议，先修改并重新复核")
    if not p.get("costs_confirmed") or ev.get("trial_cash_commitment") is None:issues.append("方案费用尚未核实")
    if ev.get("trial_cash_commitment") is not None and money(ev["trial_cash_commitment"])>money(l["max_trial_budget"]):issues.append("方案承诺支出超过店铺试验预算")
    dates=[p["spend_date"]]+[x["order_date"] for x in p.get("procurements",[])]+[x.get("sale_date",x["receipt_date"]) for x in p["items"]]
    if any(day(d)<start for d in dates):issues.append("方案的投入、采购或销售日期已早于日程开始日，请在原方案中改日期并重算")
    if any(day(d)>end for d in dates):issues.append("方案投入或销售超出本次日程范围，请延长日程或调整原方案")
    trial=next((t for t in store.experiments(merchant) if t["run_id"]==report["run_id"] and t["proposal_id"]==p["id"] and t["proposal_version"]==p["version"]),None)
    if trial and trial["status"] in ("paused","stopped","completed"):issues.append("该方案试验已暂停、停止或复盘，请先审阅状态，不能直接再投入")
    if any(t["status"]=="active" and (not trial or t["id"]!=trial["id"]) for t in store.experiments(merchant)):issues.append("另有一项试验开展中，先处理已有试验，避免叠加预算")
    return issues


class AgendaWorkflows:
    def agenda_preview(self, merchant, raw):
        if not isinstance(raw,dict):raise ValidationError("日程请求必须为对象")
        report=self.result(merchant,raw.get("run_id"))
        if report["status"] not in ("rehearsal_only","needs_data","awaiting_merchant_choice","unresolved") or not report.get("result"):raise ValidationError("先完成一次经营核查，再整理总结")
        if report["ledger_changed"] or report["context_changed"]:raise ValidationError("分析依据已更新，请重新核查，不能拿旧结论生成新日程")
        l=self.ledger(merchant);start=day(raw.get("start_date"));horizon=raw.get("days",7);daily=raw.get("daily_minutes",30)
        if type(horizon) is not int or horizon not in (7,14):raise ValidationError("行动日程支持7或14天")
        integer(daily,"每日额外投入分钟",180)
        if daily<10:raise ValidationError("每日至少留出10分钟用于核对与复盘")
        if start<day(l["as_of"]):raise ValidationError("日程不能早于所用底账日期")
        if not l["synthetic"] and start<date.today():raise ValidationError("真实店铺的行动日程不可倒填过去日期")
        weekly=l["weekly_available_hours"]*60
        if weekly<10:raise ValidationError("目前没有可用于额外行动的工时，请先核对可投入时间")
        end=start+timedelta(days=horizon-1)
        if end>day(l["as_of"])+timedelta(days=30):raise ValidationError("日程超出原底账30天核查范围，请先更新底账并重新分析")
        entry=selected_entry(report,raw);gates=clearance(self,merchant,report,entry,start,end)
        request={"run_id":report["run_id"],"start_date":start.isoformat(),"days":horizon,"daily_minutes":daily,"proposal_id":entry["proposal"]["id"] if entry else None,"proposal_version":entry["proposal"]["version"] if entry else None}
        issues=self.questions(merchant)["questions"]
        facts=[]
        for role in ("cash","inventory","customer"):
            for f in report["result"].get("investigations",{}).get(role,{}).get("findings",[]):
                facts.append({"role":role,"statement":f["statement"],"kind":f.get("kind","observation"),"evidence_ids":f.get("evidence_ids",[])})
        summary={"title":"先守住现金底线，再验证一个改变" if gates else "把一个已核查候选，变成小范围行动",
            "goal":l["goal"],"cash":l["cash_balance"],"reserve_floor":l["reserve_floor"],"trial_budget":l["max_trial_budget"],"as_of":l["as_of"],
            "findings":facts[:6],"questions":[q["question"] for q in issues[:6]],"gates":gates,
            "chosen_plan":entry["proposal"]["title"] if entry else "先核实，不新增投入",
            "source":"依据：规则核查结果，已核对预算与用时。" if report["mode"]!="agentarts" else "依据：华为 AgentArts 分析结果，已核对预算与用时。",
            "not_inferred":"销量与收益需以实际经营记录核实。"}
        tasks=[];backlog=[];day_use=[0]*horizon;week_use=[0]*((horizon+6)//7);placed={}
        from .action_basis import basis, merchant_followups
        def task(tid,title,steps,output,role="coordinator",minutes=15,depends=(),fixed=None,kind="preparation",cap="0.00",link="ledger",not_before=0):
            t={"id":tid,"title":title,"steps":steps,"deliverable":output,"review_role":role,"owner":"店主","minutes":min(minutes,daily),"depends_on":list(depends),"kind":kind,"spend_cap":cap,"view":link,
               "stop_when":"发现来源不符、金额不清或前置任务未完成，先暂停并补证。","status":"pending","note":""}
            t['basis']=basis(report,entry,role)
            earliest=max([placed.get(d,-1) for d in depends]+[not_before]);slots=[(day(fixed)-start).days] if fixed else range(earliest,horizon)
            for slot in slots:
                if any(d not in placed for d in depends) or not 0<=slot<horizon or slot<earliest:continue
                if day_use[slot]+t["minutes"]>daily or week_use[slot//7]+t["minutes"]>weekly:continue
                t["date"]=(start+timedelta(days=slot)).isoformat();day_use[slot]+=t["minutes"];week_use[slot//7]+=t["minutes"];placed[tid]=slot;tasks.append(t);return
            backlog.append({**t,"reason":"前置任务或当日/本周工时不足；保留待安排，未擅自移动方案投入日期。"})
        for i,o in enumerate(l.get("obligations",[])):
            due=day(o["date"])
            if due<=end:task("due_"+str(i),"核对到期必要付款",[f"核对 {o.get('label_text',o['id'])}：¥{o['amount']}，原到期日 {due.isoformat()}。","确认是否已支付及依据，避免与可投入资金混用；确有困难先整理沟通资料。"],"付款状态与凭证，或未付原因。",role="cash",minutes=10,fixed=max(start,due).isoformat())
        task("check_cash","先守住这周不能动的钱",["对照现金记录与账户余额，核对实际可用现金。",f"圈出至少要保留的 ¥{l['reserve_floor']}，单列到期房租、货款和待收款。","把不确定的金额留下，不能把未到账销售当现金。"],"一张有日期与来源的现金、必要付款核对单。",role="cash")
        names="、".join(p["name"] for p in l["products"][:3]) or "本店已登记商品"
        task("check_stock","从货架上找回占住的钱",["先盘点："+names+"。","逐项核对实物数量、采购成本与近30天销售记录，记录差异与来源。","只写观察；不要看到积压就立刻降价或补货。"],"一份能回到采购单和盘点记录的差异清单。",role="inventory",depends=("check_cash",),not_before=1)
        task("check_demand","听懂顾客上一次没买的原因",["整理已获得授权的客户反馈，记录原话、时间与场景。","区分问询、预约与实际付款；没有证据时明确写待核实。","只保留经营所需匿名观察，不收集无关个人信息。"],"至少一条可核查的客户观察，或明确记录暂无线索。",role="customer",depends=("check_stock",),not_before=2)
        preparation=['check_demand']
        if entry and entry['proposal'].get('expense_breakdown'):
            rows=entry['proposal']['expense_breakdown']
            details=[f"{r['label']}：{r['quantity']} × ¥{r['unit_cost']} = ¥{r['amount']}；依据：{r['basis']}。" for r in rows]
            task('check_costs','逐项核对这次准备花的钱',details+['把假设与已有记录分开，取得实际报价或费用记录后回原方案更正；本任务不授权采购或付款。'],
                 '每项费用对应的报价、记录日期和来源；缺失项明确留待核实。',role='cash',depends=('check_demand',),not_before=3)
            preparation.append('check_costs')
        if gates:
            for i,followup in enumerate(merchant_followups(report,entry)):
                tid='followup_'+str(i)
                task(tid,'补充一项方案判断所需资料',[followup['action']],followup['acceptance'],role=followup['assignee'],depends=('check_demand',),not_before=3)
                target=next((t for t in tasks+backlog if t['id']==tid),None)
                target['basis']['coordination_ref']={k:followup[k] for k in ('event_id','requirement_id','proposal_id','proposal_version')}
                preparation.append(tid)
            task("resolve_gates","把卡住的条件一项项补齐",gates+["在原资料与方案中更正，再重新核查、生成新版日程。"],"已补证项与仍未解决项分别列出。",depends=tuple(preparation),link="analysis",not_before=3)
            task("review","回到桌前，决定下一步",["对照本周补到的证据，区分事实、假设和未核实项。","在经营分析中重新核查。条件未成立时，继续准备或暂不投入。"],"一个有依据的继续、调整或暂停决定。",depends=("resolve_gates",),link="analysis",not_before=horizon-1)
        else:
            p=entry["proposal"];cap=entry["evaluation"]["trial_cash_commitment"]
            task("register_trial","只选一个候选，先写清退出线",["确认候选："+p["title"]+f"（v{p['version']}），其他方案不叠加执行。",f"本方案总承诺支出上限 ¥{cap}；同时不得突破保留现金 ¥{l['reserve_floor']}。","在方案下登记一项试验，预先冻结评价基准、目标与退出条件；人工确认后才开展。"],"同一任务、同一方案版本的试验登记和冻结评价设计。",depends=tuple(preparation),link="analysis",not_before=3)
            dates=sorted(set([p["spend_date"]]+[x["order_date"] for x in p.get("procurements",[])]))
            for i,d in enumerate(dates):
                task("execute_"+str(i),"按已核查日期，小范围开展",[f"核对原方案日期 {d}；不同日期的采购与支出仍受同一预算总额约束。","只开展已登记试验内的动作，核对实际费用与可用库存。","供应、需求、现金或工时不符就暂停；本系统不替你下单或联系他人。"],"实际发生的动作、凭证及未开展原因。",minutes=20,depends=("register_trial",),fixed=d,kind="execution",cap=cap,link="analysis")
            task("review","留一页，记下实际发生的事",["记录实际销售、退款、费用、工时与客户反馈。","收到的钱与扣除商品成本后的贡献分别看，累计反馈不能相加。","对照退出条件，决定继续、调整或停止；在行动与复盘登记实际结果。"],"一份有来源、可回查的实际反馈。",depends=tuple("execute_"+str(i) for i in range(len(dates))),link="feedback",not_before=horizon-1)
        days=[{"date":(start+timedelta(days=i)).isoformat(),"minutes":day_use[i],"tasks":[t for t in tasks if t["date"]==(start+timedelta(days=i)).isoformat()]} for i in range(horizon)]
        stop=[f"可用现金低于 ¥{l['reserve_floor']} 时停止新增投入。",f"所有已登记试验合计额外投入不得突破本店预算 ¥{l['max_trial_budget']}。","前置条件、供应条件或资料来源发生变化时，先暂停并重新核查。"]+(entry["proposal"].get("stop_conditions",[]) if entry else [])
        out={"request":request,"merchant_id":merchant,"merchant_name":l["name"],"synthetic":l["synthetic"],"source_run":report["run_id"],"source_mode":report["mode"],"summary":summary,"days":days,"backlog":backlog,"stop_conditions":stop,
             "weekly_minutes_cap":weekly,"daily_minutes_cap":daily,"total_minutes":sum(day_use),"plan_spend_cap":entry["evaluation"]["trial_cash_commitment"] if entry and not gates else "0.00",
             "scope":"补证准备日程" if gates else "单一候选的条件行动日程","notice":"完成任务后，请另行记录实际收支。"}
        out["fingerprint"]=digest(out)
        return out

    def agendas(self, merchant):
        rows=self.records(merchant,"action_agenda");events=self.records(merchant,"agenda_progress")
        result=[]
        for row in reversed(rows):
            data=deepcopy(row["data"]);report=self.result(merchant,data["source_run"])
            data["stale"]=report["ledger_changed"] or report["context_changed"]
            data["id"]=row["id"];data["created_at"]=row["created_at"];data["revision"]=0
            by_id={t["id"]:t for d in data["days"] for t in d["tasks"]}
            for event in events:
                e=event["data"]
                if e["agenda_id"]==row["id"]:
                    by_id[e["task_id"]].update(status=e["status"],note=e["note"]);data["revision"]+=1
            data["current"]=row is rows[-1]
            data["completed_count"]=sum(t["status"]=="done" for t in by_id.values());data["paused_count"]=sum(t["status"]=="skipped" for t in by_id.values());data["pending_count"]=sum(t["status"]=="pending" for t in by_id.values());data["task_count"]=len(by_id)
            result.append(data)
        return {"agendas":result,"current_id":rows[-1]["id"] if rows else None}

    def save_agenda(self, merchant, raw):
        if not isinstance(raw,dict):raise ValidationError("日程请求必须为对象")
        if raw.get("confirmed") is not True:raise ValidationError("请预览并确认日程后保存")
        draft=self.agenda_preview(merchant,raw)
        if draft["fingerprint"]!=raw.get("fingerprint"):raise ValidationError("日程或依据已变化，请重新预览")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current=db.execute("SELECT id FROM workbench_records WHERE merchant=? AND kind='action_agenda' ORDER BY seq DESC LIMIT 1",(merchant,)).fetchone()
            if (current[0] if current else None)!=raw.get("expected_current_id"):raise ValidationError("已有新的日程，请刷新后再保存，旧版本保留")
            # Recheck the source while holding the write lock; prevents stale save races.
            if self.agenda_preview(merchant,raw)["fingerprint"]!=draft["fingerprint"]:raise ValidationError("依据已变化，请重新预览")
            rid="agenda_"+uuid4().hex[:20]
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,"action_agenda",json.dumps(draft,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return {"id":rid,**self.agendas(merchant)}

    def agenda_progress(self, merchant, raw):
        if not isinstance(raw,dict):raise ValidationError("进度请求必须为对象")
        listing=self.agendas(merchant);agenda=next((a for a in listing["agendas"] if a["id"]==raw.get("agenda_id")),None)
        if not agenda or not agenda["current"]:raise ValidationError("仅可更新当前日程，历史日程只读")
        if agenda["stale"]:raise ValidationError("底账或依据已变化，先生成新日程；旧进度保留")
        tasks={t["id"]:t for d in agenda["days"] for t in d["tasks"]};task=tasks.get(raw.get("task_id"));status=raw.get("status")
        if not task or status not in ("pending","done","skipped"):raise ValidationError("任务或进度状态无效")
        note=nonempty(raw.get("note"),"实际记录、依据或暂停原因")
        if status=="done" and not agenda["synthetic"] and day(task["date"])>date.today():raise ValidationError("不能提前把未来的实际行动记为完成")
        if status=="done" and any(tasks[x]["status"]!="done" for x in task["depends_on"]):raise ValidationError("请先完成前置任务；跳过前置项不能解锁后续动作")
        if status!="done" and any(task["id"] in t["depends_on"] and t["status"]=="done" for t in tasks.values()):raise ValidationError("已有完成的后续任务，先撤回后续记录再更正前置任务")
        if status=="done" and task["kind"]=="execution":
            report=self.result(merchant,agenda["source_run"]);entry=selected_entry(report,agenda["request"])
            if clearance(self,merchant,report,entry,day(agenda["request"]["start_date"]),day(agenda["days"][-1]["date"])):raise ValidationError("执行条件有变化，请重新核查")
            p=entry["proposal"];trial=next((t for t in self.experiments(merchant) if t["run_id"]==report["run_id"] and t["proposal_id"]==p["id"] and t["proposal_version"]==p["version"] and t["status"]=="active"),None)
            if not trial or not any(r["data"]["trial_id"]==trial["id"] for r in self.records(merchant,"design")):raise ValidationError("先登记并开展该精确版本的试验，冻结评价设计，再记录执行完成")
        event={"agenda_id":agenda["id"],"task_id":task["id"],"status":status,"note":note}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest=db.execute("SELECT id FROM workbench_records WHERE merchant=? AND kind='action_agenda' ORDER BY seq DESC LIMIT 1",(merchant,)).fetchone()
            count=db.execute("SELECT count(*) FROM workbench_records WHERE merchant=? AND kind='agenda_progress' AND json_extract(data,'$.agenda_id')=?",(merchant,agenda["id"])).fetchone()[0]
            if not latest or latest[0]!=agenda["id"] or count!=raw.get("expected_revision"):raise ValidationError("日程或进度已更新，请刷新后操作")
            fresh=self.result(merchant,agenda["source_run"])
            if fresh["ledger_changed"] or fresh["context_changed"]:raise ValidationError("依据刚被更新，请重新核查并生成日程")
            if status=="done" and task["kind"]=="execution":
                current_entry=selected_entry(fresh,agenda["request"])
                if clearance(self,merchant,fresh,current_entry,day(agenda["request"]["start_date"]),day(agenda["days"][-1]["date"])):raise ValidationError("执行条件刚被更新，请重新核查")
                current_trial=next((t for t in self.experiments(merchant) if t["id"]==trial["id"] and t["status"]=="active"),None)
                if not current_trial:raise ValidationError("试验状态刚被更新，不能记录继续执行")
            db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,"progress_"+uuid4().hex[:20],"agenda_progress",json.dumps(event,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return self.agendas(merchant)
