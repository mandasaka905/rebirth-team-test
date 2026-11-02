"""Local companion records, measured outcomes, industry checks and consented mutual aid."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4
import json
from .domain import ValidationError, day, nonempty, integer, money, amount, identifier

METRICS={"stock_value":("指定范围库存占用","元"),"overdue":("指定范围逾期待付款","元"),"checking_time":("一次同口径资料核对用时","分钟")}
FIELDS={
 "retail":[("stock","库存数量","件"),("sold","最近30天实际销量","件"),("unit_cost","单位采购成本","元"),("price","当前单价","元"),("restock","拟补货数量","件"),("cash","当前可用现金","元"),("reserve","要保留的现金","元"),("due","近期必要付款","元")],
 "food":[("batch","本次盘点原料总量（含损耗）","公斤"),("waste","上述原料中待剔除的损耗","公斤"),("daily_use","最近实际日均用量","公斤"),("unit_cost","原料单位成本","元/公斤"),("shelf_days","经核对剩余保质天数","天"),("orders","已记录当日订单","单"),("margin","每单收入减已录变动成本","元/单"),("fixed","同日已录固定费用","元")],
 "repair":[("queue","待办订单","单"),("minutes_job","每单实际所需工时","分钟"),("minutes_day","每天可用于订单的工时","分钟"),("price","每单收费","元"),("material","每单材料成本","元"),("sample","同一观察期已完工订单","单"),("rework","上述订单中返工订单","单")]
}

def industry_check(raw):
    kind=raw.get("industry")
    if kind not in FIELDS:raise ValidationError("请选择社区零售、餐饮或便民修理")
    observed=day(raw.get("observed_on"));source=nonempty(raw.get("source_note"),"数据来源")
    values=raw.get("values")
    if not isinstance(values,dict):raise ValidationError("请填写行业核查字段")
    v={}
    for k,_,_ in FIELDS[kind]:
        x=values.get(k)
        v[k]=None if x is None or x=="" else money(x,negative=k=="margin")
        count_keys={"retail":{"stock","sold","restock"},"food":{"shelf_days","orders"},"repair":{"queue","minutes_job","minutes_day","sample","rework"}}
        if k in count_keys[kind] and v[k] is not None and (v[k]!=v[k].to_integral_value() or v[k]>1000000):raise ValidationError("数量、订单与工时分钟请填合理整数")
    metrics=[];warnings=[];missing=[label for k,label,_ in FIELDS[kind] if v[k] is None]
    def metric(label,value,unit="元"):metrics.append({"label":label,"value":None if value is None else amount(value.quantize(Decimal(".01"))),"unit":unit})
    def ready(*keys):return all(v[k] is not None for k in keys)
    if kind=="retail":
        metric("账面库存资金占用",v["stock"]*v["unit_cost"] if ready("stock","unit_cost") else None)
        metric("按近30天历史速度的覆盖天数",v["stock"]*30/v["sold"] if ready("stock","sold") and v["sold"]>0 else None,"天")
        metric("拟补货商品成本（未含运费）",v["restock"]*v["unit_cost"] if ready("restock","unit_cost") else None)
        if ready("cash","reserve","due","restock","unit_cost") and v["restock"]*v["unit_cost"]>max(Decimal(0),v["cash"]-v["reserve"]-v["due"]):warnings.append("拟补货商品成本已超过扣除保留额和必要付款后的现金空间；先暂停新增采购核对")
        if v["sold"]==0:warnings.append("最近30天无已记录销量，覆盖天数不作除法，也不能推断将来一定卖不掉")
        if ready("price","unit_cost") and v["price"]<=v["unit_cost"]:warnings.append("当前单价不高于采购成本；还未计入其他费用，不宜以增加销量掩盖问题")
        actions=[("核对货架与原单","盘点指定商品，保留采购单和净销售口径","一张数量与成本差异表"),("核实供货边界","逐项问清运费、起订量、到货和付款时间；未知不填零","有来源的供货条件"),("先比较现货与补货","将未计费用补齐，核对现金后再考虑单一小范围试验","不叠加投入的候选清单")]
    elif kind=="food":
        if ready("batch","waste") and v["waste"]>v["batch"]:raise ValidationError("待剔除损耗不能超过本次盘点原料总量")
        remaining=v["batch"]-v["waste"] if ready("batch","waste") else None
        metric("已记录损耗成本",v["waste"]*v["unit_cost"] if ready("waste","unit_cost") else None)
        metric("按近期实际用量的剩余消耗天数",remaining/v["daily_use"] if remaining is not None and v["daily_use"] and v["daily_use"]>0 else None,"天")
        metric("当日已录口径的贡献余额",v["orders"]*v["margin"]-v["fixed"] if ready("orders","margin","fixed") else None)
        if v["shelf_days"]==0:warnings.append("剩余期限记录为0天，先人工核查可用状态；不将其当成正常可售库存")
        if remaining is not None and ready("daily_use","shelf_days") and remaining>v["daily_use"]*v["shelf_days"]:warnings.append("按近期实际用量，现有原料可能超过剩余期限内的消耗量；先核对批次和采购量")
        if v["daily_use"]==0:warnings.append("近期实际用量为0，不能估计消耗天数")
        actions=[("逐批核对日期与状态","查看实物、批次和期限记录；无法确认的原料单列人工处理","带批次和日期的盘点单"),("记录实际损耗","按同一单位记录采购、用量与损耗，不用营业额代替毛利","损耗数量、原因和来源"),("调整下一次备货假设","先核实实际订单、原料用量与费用；只提出小批量待验证假设","有条件和退出线的备货草案")]
    else:
        if ready("sample","rework") and v["rework"]>v["sample"]:raise ValidationError("返工订单必须属于同一观察期已完工样本")
        capacity=(v["minutes_day"]/v["minutes_job"]).to_integral_value(rounding="ROUND_FLOOR") if ready("minutes_day","minutes_job") and v["minutes_job"]>0 else None
        metric("按已录工时可容纳的日订单",capacity,"单")
        metric("现有排队订单至少占用天数",(v["queue"]/capacity).to_integral_value(rounding=ROUND_CEILING) if capacity and v["queue"] is not None else None,"天")
        metric("收费减材料成本（未扣人工等）",v["price"]-v["material"] if ready("price","material") else None)
        metric("同口径样本返工比例",v["rework"]*100/v["sample"] if ready("rework","sample") and v["sample"]>0 else None,"%")
        if capacity==0 or v["minutes_job"]==0:warnings.append("现有工时记录无法支持日订单安排，先核对单笔工时和每天可用时间")
        if ready("price","material") and v["price"]<=v["material"]:warnings.append("收费不高于材料成本，且还未计入人工与房租，应先核对报价成本")
        actions=[("盘点待办订单","核对每单工作量、承诺时间与待料状态，不承诺超出能力的时限","一份逐单工时与期限表"),("把材料和人工分开核算","记录材料、工时及返工，不把收费减材料误认为净利润","有来源的报价核对单"),("保留一次售后回看","整理返工原因和客户反馈，区分沟通、工艺与材料假设","一条可继续调查的原因记录")]
    if missing:warnings.insert(0,"尚缺："+"、".join(missing)+"；相关计算保持未知")
    start=max(date.today(),observed)
    tasks=[{"date":(start+timedelta(days=i)).isoformat(),"title":a,"steps":b,"deliverable":c,"minutes":15,"spend_cap":"0.00"} for i,(a,b,c) in enumerate(actions)]
    return {"industry":kind,"observed_on":observed.isoformat(),"source_note":source,"values":{k:None if x is None else amount(x) for k,x in v.items()},"metrics":metrics,"warnings":warnings,"tasks":tasks,"notice":"专项本地规则核查与准备行动，不改写原底账、不预测需求或收益，也不代表跨行业真实智能体已验证。"}

class CommunityWorkflows:
    def community_impact_cases(self,merchant):
        records=self.records(merchant)
        starts=[r for r in records if r["kind"]=="impact_start"];observations=[r for r in records if r["kind"]=="impact_observation"]
        cases=[]
        for r in starts:
            obs=[o for o in observations if o["data"]["case_id"]==r["id"]];latest=obs[-1] if obs else None
            delta=money(latest["data"]["value"])-money(r["data"]["baseline_value"]) if latest else None
            cases.append({**r,"latest":latest,"history":obs,"review_on":(day(r["data"]["baseline_date"])+timedelta(days=30)).isoformat(),"difference":None if delta is None else amount(delta),"elapsed_days":(day(latest["data"]["observed_on"])-day(r["data"]["baseline_date"])).days if latest else 0})
        return cases

    def community_home(self,merchant):
        ledger=self.ledger(merchant);records=self.records(merchant)
        return {"synthetic":ledger["synthetic"],"agendas":self.agendas(merchant),"handovers":[r for r in records if r["kind"]=="support_handover"],"cases":self.community_impact_cases(merchant),"industry_checks":[r for r in records if r["kind"]=="industry_check"],"resources":self.resource_directory(merchant),"transfers":self.mutual_transfers(merchant),"metric_definitions":METRICS,"industry_fields":FIELDS,"social":self.social_home(merchant)}

    def support_handover(self,merchant,raw):
        if raw.get("merchant_reviewed") is not True:raise ValidationError("请先与店主逐项核对本次交接内容")
        agenda=next((a for a in self.agendas(merchant)["agendas"] if a["id"]==raw.get("agenda_id")),None)
        if not agenda or not agenda["current"] or agenda["stale"]:raise ValidationError("先生成一份依据有效的当前行动日程")
        role=raw.get("operator_role")
        if role not in ("merchant","companion"):raise ValidationError("请选择店主本人或协助记录者")
        data={"agenda_id":agenda["id"],"agenda_snapshot":agenda,"operator_role":role,"helper_alias":nonempty(raw.get("helper_alias"),"记录者称呼"),"notes":nonempty(raw.get("notes"),"本次交接内容"),"next_check_on":day(raw.get("next_check_on")).isoformat(),"help_minutes":integer(raw.get("help_minutes"),"本次协助分钟",1440),"merchant_reviewed":True,"synthetic":self.ledger(merchant)["synthetic"],"notice":"本机交接登记，不代表原账已核实，也不证明实际受益；未向任何机构发送资料。"}
        return self.append_record(merchant,"support_handover",data)

    def impact_start(self,merchant,raw):
        if raw.get("confirmed") is not True:raise ValidationError("请确认基准口径，保存后不能事后改写")
        metric=raw.get("metric")
        if metric not in METRICS:raise ValidationError("请选择已有指标与单位")
        ledger=self.ledger(merchant);baseline=day(raw.get("baseline_date"))
        if not ledger["synthetic"] and baseline>date.today():raise ValidationError("不能把未来基准记作已发生事实")
        data={"metric":metric,"metric_label":METRICS[metric][0],"unit":METRICS[metric][1],"scope":nonempty(raw.get("scope"),"固定统计范围与口径"),"goal":nonempty(raw.get("goal"),"本次陪跑想改善什么"),"baseline_date":baseline.isoformat(),"baseline_value":amount(money(raw.get("baseline_value"))),"source_note":nonempty(raw.get("source_note"),"基准来源"),"synthetic":ledger["synthetic"],"ledger_snapshot":ledger,"period_days":30}
        return self.append_record(merchant,"impact_start",data)

    def impact_observe(self,merchant,raw):
        case=next((r for r in self.records(merchant,"impact_start") if r["id"]==raw.get("case_id")),None)
        if not case:raise ValidationError("本店成效档案不存在")
        if raw.get("same_scope_confirmed") is not True:raise ValidationError("先确认本次与基准使用同一统计范围和单位")
        observed=day(raw.get("observed_on"));base=case["data"]
        if observed<day(base["baseline_date"]):raise ValidationError("观察日期不能早于基准日期")
        if not base["synthetic"] and observed>date.today():raise ValidationError("不能记录未来的实际观察")
        status=raw.get("status")
        if status not in ("observed","paused","stopped"):raise ValidationError("请选择观察、暂停或停止")
        data={"case_id":case["id"],"observed_on":observed.isoformat(),"value":amount(money(raw.get("value"))),"source_note":nonempty(raw.get("source_note"),"本次观察来源"),"actions":nonempty(raw.get("actions"),"实际做了什么或未做原因"),"external_factors":nonempty(raw.get("external_factors"),"同期外部影响与不确定性"),"extra_spend":amount(money(raw.get("extra_spend"))),"extra_minutes":integer(raw.get("extra_minutes"),"累计额外用时",1000000),"status":status,"previous_id":raw.get("previous_id"),"same_scope_confirmed":True}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE");rows=db.execute("SELECT id,data FROM workbench_records WHERE merchant=? AND kind='impact_observation' ORDER BY seq",(merchant,)).fetchall();prior=[r for r in rows if json.loads(r[1])["case_id"]==case["id"]]
            if (prior[-1][0] if prior else None)!=raw.get("previous_id"):raise ValidationError("已有新的观察，请刷新；旧记录保留")
            if prior and observed<day(json.loads(prior[-1][1])["observed_on"]):raise ValidationError("观察日不能倒退，同日更正会另留记录")
            rid="impact_"+uuid4().hex[:20];db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,"impact_observation",json.dumps(data,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return {"id":rid,"data":data}

    def industry_review(self,merchant,raw):
        result=industry_check(raw);ledger=self.ledger(merchant)
        if not ledger["synthetic"] and day(result["observed_on"])>date.today():raise ValidationError("实际行业记录日期不能填未来")
        result["synthetic"]=ledger["synthetic"];return self.append_record(merchant,"industry_check",result)

    def _mutual_rows(self):
        with self.connect() as db:rows=db.execute("SELECT merchant,id,kind,data,created_at FROM workbench_records WHERE kind IN ('mutual_resource','mutual_transfer','mutual_receipt') ORDER BY seq").fetchall()
        return [{**dict(r),"data":json.loads(r["data"])} for r in rows]

    def _resource_state(self,rows):
        latest={};transfers={};receipts={}
        for r in rows:
            if r["kind"]=="mutual_resource":latest[r["data"]["listing_id"]]=r
            elif r["kind"]=="mutual_transfer":transfers[r["id"]]=r
            else:receipts[r["data"]["transfer_id"]]=r
        return latest,transfers,receipts

    def resource_directory(self,merchant):
        ledger=self.ledger(merchant);latest,transfers,receipts=self._resource_state(self._mutual_rows());out=[]
        for r in latest.values():
            d=r["data"]
            if d["synthetic"]!=ledger["synthetic"]:continue
            used=sum(t["data"]["quantity"] for tid,t in transfers.items() if t["data"]["listing_id"]==d["listing_id"] and receipts.get(tid,{}).get("data",{}).get("decision")=="confirmed")
            pending=any(t["data"]["listing_id"]==d["listing_id"] and tid not in receipts for tid,t in transfers.items())
            if d["status"]=="withdrawn" and r["merchant"]!=merchant:continue
            out.append({"record_id":r["id"],"owned":r["merchant"]==merchant,"owner_merchant":r["merchant"],"remaining":d["quantity"]-used,"pending":pending,"data":d})
        return out

    def save_resource(self,merchant,raw):
        ledger=self.ledger(merchant)
        if raw.get("directory_consent") is not True:raise ValidationError("请确认仅在本机互助目录显示这份登记内容")
        status=raw.get("status","available")
        if status not in ("available","withdrawn"):raise ValidationError("资源状态无效")
        start=day(raw.get("available_from"));end=day(raw.get("available_until"))
        if end<start:raise ValidationError("可用截止日不能早于开始日")
        quantity=integer(raw.get("quantity"),"资源登记数量",1000000)
        if quantity<1:raise ValidationError("登记数量至少为1")
        data={k:nonempty(raw.get(k),k) for k in ("title","unit","condition","area","owner_alias","source_note")}
        data.update(quantity=quantity,available_from=start.isoformat(),available_until=end.isoformat(),status=status,synthetic=ledger["synthetic"],directory_consent=True,listing_id=raw.get("listing_id") or "resource_"+uuid4().hex[:20])
        identifier(data["listing_id"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE");latest,transfers,receipts=self._resource_state(self._mutual_rows());old=latest.get(data["listing_id"])
            if old and old["merchant"]!=merchant:raise ValidationError("只能修改当前店铺自己的互助单")
            if (old["id"] if old else None)!=raw.get("expected_record_id"):raise ValidationError("资源单已有新版本，请刷新")
            associated=[(tid,t) for tid,t in transfers.items() if t["data"]["listing_id"]==data["listing_id"]]
            if any(tid not in receipts for tid,t in associated):raise ValidationError("尚有待确认交接，先确认或取消，再修改资源单")
            used=sum(t["data"]["quantity"] for tid,t in associated if receipts[tid]["data"]["decision"]=="confirmed")
            if quantity<used:raise ValidationError("登记总量不能少于双方已确认交接数量")
            if associated and old["data"]["unit"]!=data["unit"]:raise ValidationError("已有交接历史，不能改写计量单位")
            rid="resourcev_"+uuid4().hex[:20];db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,"mutual_resource",json.dumps(data,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return {"id":rid,"data":data}

    def mutual_transfers(self,merchant):
        self.ledger(merchant);latest,transfers,receipts=self._resource_state(self._mutual_rows());out=[]
        for tid,r in transfers.items():
            if merchant not in (r["merchant"],r["data"]["recipient"]):continue
            out.append({"id":tid,"data":r["data"],"role":"owner" if r["merchant"]==merchant else "recipient","receipt":receipts.get(tid),"status":receipts.get(tid,{}).get("data",{}).get("decision","pending")})
        return out

    def mutual_transfer(self,merchant,raw):
        if raw.get("owner_confirmed") is not True:raise ValidationError("请由资源提供店核对本次交接登记")
        recipient=raw.get("recipient");target=self.ledger(recipient);owner=self.ledger(merchant)
        if recipient==merchant or target["synthetic"]!=owner["synthetic"]:raise ValidationError("交接需选择另一家同为真实或同为合成的本机店铺")
        quantity=integer(raw.get("quantity"),"交接数量",1000000)
        if quantity<1:raise ValidationError("交接数量至少1")
        occurred=day(raw.get("occurred_on"))
        if not owner["synthetic"] and occurred>date.today():raise ValidationError("不能提前登记未来交接已发生")
        source=nonempty(raw.get("source_note"),"提供方交接依据")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE");latest,transfers,receipts=self._resource_state(self._mutual_rows());r=latest.get(raw.get("listing_id"))
            if not r or r["merchant"]!=merchant or r["data"]["status"]!="available":raise ValidationError("请选择本店仍开放的资源单")
            d=r["data"]
            if not day(d["available_from"])<=occurred<=day(d["available_until"]):raise ValidationError("交接日期不在登记可用范围内")
            associated=[(tid,t) for tid,t in transfers.items() if t["data"]["listing_id"]==d["listing_id"]]
            if any(tid not in receipts for tid,t in associated):raise ValidationError("该资源还有一笔待确认交接，请先处理，避免重复安排")
            used=sum(t["data"]["quantity"] for tid,t in associated if receipts[tid]["data"]["decision"]=="confirmed")
            if quantity>d["quantity"]-used:raise ValidationError("交接数量超过未交接余量")
            data={"listing_id":d["listing_id"],"resource_version":r["id"],"title":d["title"],"unit":d["unit"],"owner":merchant,"owner_alias":d["owner_alias"],"recipient":recipient,"quantity":quantity,"occurred_on":occurred.isoformat(),"source_note":source,"synthetic":owner["synthetic"]}
            rid="transfer_"+uuid4().hex[:20];db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,"mutual_transfer",json.dumps(data,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return {"id":rid,"data":data}

    def mutual_receipt(self,merchant,raw):
        self.ledger(merchant);note=nonempty(raw.get("source_note"),"确认或取消依据");decision=raw.get("decision")
        if raw.get("confirmed") is not True:raise ValidationError("请核对这次交接结果")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE");latest,transfers,receipts=self._resource_state(self._mutual_rows());tid=raw.get("transfer_id");r=transfers.get(tid)
            if not r or tid in receipts:raise ValidationError("交接不存在或已处理，不能重复确认")
            d=r["data"]
            if decision=="cancelled" and merchant!=d["owner"]:raise ValidationError("仅提供方可取消待确认交接")
            if decision in ("confirmed","declined") and merchant!=d["recipient"]:raise ValidationError("需切换到接收店铺，独立确认或拒绝")
            if decision not in ("confirmed","declined","cancelled"):raise ValidationError("交接结果无效")
            data={"transfer_id":tid,"decision":decision,"source_note":note,"synthetic":d["synthetic"],"notice":"本机双方店铺分别登记，不等同于线上身份认证或独立实地核验。"}
            rid="receipt_"+uuid4().hex[:20];db.execute("INSERT INTO workbench_records(merchant,id,kind,data,created_at) VALUES (?,?,?,?,?)",(merchant,rid,"mutual_receipt",json.dumps(data,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        return {"id":rid,"data":data}
