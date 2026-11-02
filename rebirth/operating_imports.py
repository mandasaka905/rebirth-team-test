"""Atomic, previewed inventory snapshots and anonymous sale records from CSV."""
import csv, hashlib, json
from io import StringIO
from copy import deepcopy
from datetime import timedelta
from .domain import ValidationError, day, identifier, integer, money, nonempty, validate_ledger

TEMPLATES={
 "inventory":"sku,name,stock,sales_30d,received_on,unit_cost,unit_price,size_complete,source_note\n",
 "sales":"id,date,sku,quantity,revenue,goods_cost,source_note\n"}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()

def parse(text,kind):
    if kind not in TEMPLATES or not isinstance(text,str) or len(text)>500000:raise ValidationError("请选择库存或销售CSV，最多50万字")
    r=csv.DictReader(StringIO(text.lstrip('\ufeff')))
    expected=TEMPLATES[kind].strip().split(',')
    if not r.fieldnames or len(r.fieldnames)!=len(set(r.fieldnames)) or set(r.fieldnames)!=set(expected):raise ValidationError("CSV列名须为："+','.join(expected))
    rows=[]
    for line,row in enumerate(r,2):
        if None in row or any(v is None for v in row.values()):raise ValidationError("CSV第"+str(line)+"行列数错误")
        row={k:v.strip() for k,v in row.items()}
        try:
            for k in (("stock","sales_30d") if kind=="inventory" else ("quantity",)):
                if not row[k].isdigit():raise ValidationError(k+"须为非负整数")
                row[k]=int(row[k]);integer(row[k],k)
            for k in (("unit_cost","unit_price") if kind=="inventory" else ("revenue","goods_cost")):
                if row[k]=='':row[k]=None
                else:money(row[k])
            if kind=="sales" and row["revenue"] is None:raise ValidationError("销售额不能留空，商品成本未知可以留空")
            if kind=="inventory":
                if row["size_complete"].lower() not in ('true','false',''):raise ValidationError("尺码状态只接受true、false或空白")
                row["size_complete"]={'true':True,'false':False,'':None}[row["size_complete"].lower()]
            nonempty(row["source_note"],"逐行来源");identifier(row["sku"])
        except ValidationError as e:raise ValidationError("CSV第"+str(line)+"行："+str(e)) from None
        rows.append(row)
        if len(rows)>500:raise ValidationError("每批最多500行，整批未保存")
    if not rows:raise ValidationError("CSV没有数据")
    return rows

def validate_sales(records,ledger):
    if not isinstance(records,list) or len(records)>5000:raise ValidationError("本地销售明细最多5000行")
    seen=set();skus={p["sku"] for p in ledger["products"]}
    for r in records:
        identifier(r.get("id"));identifier(r.get("sku"))
        if r["id"] in seen or r["sku"] not in skus:raise ValidationError("销售单号重复或商品未建档")
        seen.add(r["id"])
        if day(r.get("date"))>day(ledger["as_of"]):raise ValidationError("销售日期不可晚于底账")
        integer(r.get("quantity"),"销售件数");money(r.get("revenue"))
        if r.get("goods_cost") is not None:money(r["goods_cost"])
        nonempty(r.get("source_note"),"销售来源")
    return records

def sales_windows(ledger):
    known=deepcopy(ledger.get("sales_windows",{}));legacy=ledger.get("sales_window",{})
    for sku in legacy.get("complete_skus",[]):
        if sku not in known:
            product=next((p for p in ledger["products"] if p["sku"]==sku),None)
            if product:known[sku]={"start":legacy["start"],"end":legacy["end"],"source_id":ledger.get("field_sources",{}).get("products/"+sku+"/sales_30d",product["source_id"])}
    return known


def validate_windows(windows,ledger):
    if not isinstance(windows,dict):raise ValidationError("商品销售统计窗口须为对象")
    skus={p["sku"] for p in ledger["products"]}
    for sku,w in windows.items():
        if sku not in skus or not isinstance(w,dict):raise ValidationError("销售窗口须对应已建档商品")
        if (day(w.get("end"))-day(w.get("start"))).days!=29 or day(w["end"])>day(ledger["as_of"]):raise ValidationError("销售窗口须为不晚于底账的连续30天")
        if w.get("source_id") not in ledger["sources"]:raise ValidationError("销售窗口来源不存在")
    return windows


def stale_sales(ledger):
    return {sku:w for sku,w in sales_windows(ledger).items() if w["end"]!=ledger["as_of"]}


def row_source(updated,batch_source,sku,notes):
    sid="row_"+digest({"batch":batch_source,"sku":sku,"notes":notes})[:20]
    # Full row notes stay in the ledger/journal; this is an explicit bounded summary.
    summary="\n".join(dict.fromkeys(notes))
    if len(summary)>4000:summary=summary[:4000]+"…完整逐行依据见销售明细或导入记录"
    updated["sources"][sid]=updated["sources"][batch_source]+"\n逐行依据："+summary
    return sid


def preview(ledger,raw):
    if not isinstance(raw,dict):raise ValidationError("导入请求须为对象")
    kind=raw.get("kind");rows=parse(raw.get("csv"),kind)
    nonempty(raw.get("source_note"),"本批来源")
    for k in ("replace_existing","confirm_sales_window"):
        if type(raw.get(k,False)) is not bool:raise ValidationError(k+"须为布尔值")
    updated=deepcopy(ledger);changes=[];source="csv_"+digest({"kind":kind,"rows":rows,"source":raw["source_note"]})[:16]
    updated["sources"][source]=raw["source_note"]
    products={p["sku"]:p for p in updated["products"]};seen=set()
    windows=sales_windows(updated);start=day(ledger["as_of"])-timedelta(days=29)
    if kind=="inventory":
        for row in rows:
            if row["sku"] in seen:raise ValidationError("同批SKU重复，不会相加库存")
            seen.add(row["sku"]);old=products.get(row["sku"])
            if old and raw.get("replace_existing") is not True:raise ValidationError("已有SKU，须预览并明确同意替换该商品快照；不会累计入库")
            new={k:v for k,v in row.items() if k!='source_note'};sid=row_source(updated,source,row["sku"],[row["source_note"]]);new["source_id"]=sid
            windows[row["sku"]]={"start":start.isoformat(),"end":ledger["as_of"],"source_id":sid}
            for key in new:
                if key!="source_id":updated.setdefault("field_sources",{})["products/"+row["sku"]+"/"+key]=sid
            changes.append({"sku":row["sku"],"before":deepcopy(old),"after":new})
            products[row["sku"]]=new
        updated["products"]=list(products.values())
    else:
        if raw.get("confirm_sales_window") is not True:raise ValidationError("请确认本表及既有明细覆盖最近30天完整净销售；若不完整，先补齐，不能覆盖现有销量")
        records=deepcopy(updated.get("sales_records",[]));used={r["id"] for r in records};start=day(ledger["as_of"])-timedelta(days=29)
        for row in rows:
            if row["id"] in used:raise ValidationError("销售原单号重复，整批未保存")
            if row["sku"] not in products:raise ValidationError("销售商品未建档，先导入库存")
            if not start<=day(row["date"])<=day(ledger["as_of"]):raise ValidationError("销售CSV须为底账最近30天，较早明细另行归档")
            used.add(row["id"]);records.append(row)
        updated["sales_records"]=records
        for sku in {r["sku"] for r in rows}:
            old=products[sku]["sales_30d"];new=sum(r["quantity"] for r in records if r["sku"]==sku and start<=day(r["date"])<=day(ledger["as_of"]))
            sid=row_source(updated,source,sku,[r["source_note"] for r in rows if r["sku"]==sku])
            products[sku]["sales_30d"]=new
            updated.setdefault("field_sources",{})["products/"+sku+"/sales_30d"]=sid
            windows[sku]={"start":start.isoformat(),"end":ledger["as_of"],"source_id":sid}
            changes.append({"sku":sku,"sales_30d_before":old,"sales_30d_after":new})
        updated["sales_window"]={"start":start.isoformat(),"end":ledger["as_of"],"complete_skus":sorted({r["sku"] for r in rows}),"source_note":raw["source_note"]}
    updated["sales_windows"]=windows
    validate_ledger(updated)
    request={k:raw.get(k,False if k in ("replace_existing","confirm_sales_window") else None) for k in ("kind","csv","source_note","replace_existing","confirm_sales_window")}
    return {"rows":rows,"changes":changes,"ledger":updated,"preview_digest":digest({"ledger":ledger,"request":request}),"batch_digest":digest(request),
            "notice":"库存为当前盘点快照，不累计入库；销售只更新明确确认完整的最近30天件数，不扣减盘点库存、不改现金或经营期间；未知成本保留。"}
