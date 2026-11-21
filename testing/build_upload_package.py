from pathlib import Path
import shutil,json,csv,hashlib
R=Path(__file__).resolve().parents[1];src=R/'team-delivery/逆势重生-队友录制包-20261117-v4';P=R/'team-delivery/逆势重生-自主上传录制包-20261117-v5'
P.mkdir(exist_ok=True)
for folder in ['runtime','app']:
 shutil.copytree(src/folder,P/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for folder in ['agentarts/prompts','.agentarts-deps']:
 shutil.copytree(R/folder,P/'app'/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for f in (R/'dist').iterdir():
 if f.is_file():shutil.copy2(f,P/'app/dist'/f.name)
cfg=json.loads((R/'config/agentarts.managed.local.json').read_text(encoding='utf-8-sig'))
safe={'allowed_hosts':cfg['allowed_hosts'],'agents':{role:{k:v for k,v in row.items() if k in ['url','transport','auth_header','token_env']} for role,row in cfg['agents'].items()}}
(P/'app/config/team-endpoints.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
D=P/'录制资料';D.mkdir(exist_ok=True)
s=json.loads((R/'testing/upload-demo-candidates.json').read_text(encoding='utf-8'));skus=['22843','20698','22288'];names=['复古绿色饼干罐','粉色玩偶','金属兔子挂饰']
original=[row for sku in skus for row in s['rows'][sku]]
with (D/'公开交易原始摘录_英镑_勿直接导入.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(original[0]));w.writeheader();w.writerows(original)
net=[sum(x['quantity'] for x in s['rows'][sku]) for sku in skus]
source='UCI Online Retail公开交易最近30日净件数；中文名为译名；日期平移为演示。库存、入库日、人民币售价及已填成本为演示假设；未知成本留空。见资料来源与加工清单。'
with (D/'01_上传这份库存表.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['商品编号','商品名称','库存数量','近30天销量','入库日期','采购单价','销售单价','尺码齐全','来源说明'])
 for sku,name,stock,sales,cost,price in zip(skus,names,[60,40,32],net,['12.00','','9.00'],['25.00','18.00','20.00']):
  w.writerow([sku,name,stock,sales,'2026-07-20',cost,price,'是',source])
manifest={'source_url':'https://archive.ics.uci.edu/dataset/352/online+retail','citation':'Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33','license':'CC BY 4.0','checked_on':'2026-11-17','source_archive_sha256':hashlib.sha256((R/'testing/public-retail/raw/online-retail.zip').read_bytes()).hexdigest(),'original_window':['2011-11-10','2011-12-09'],'selected_skus':skus,'selection':'从完整30日窗口净销量2至12且交易记录不超过10行的候选商品中，选用饼干罐、玩偶与挂饰；并非随机抽样或完整店铺经营数据。','original_rows':len(original),'transforms':['不包含CustomerID，不包含姓名或联系方式','保留原始发票号、日期、英镑单价及撤销标记供核对，不作为平台人民币销售导入','导入表30天销量为各SKU本窗口有符号Quantity求和，保留取消/退货的负数影响','仅导入演示底账的销量与商品名；未将英镑直接改写为人民币','将历史观察窗映射为2026-10-19至2026-11-17，仅作演示时序，原始日期保留在摘录','库存60/40/32、入库日2026-07-20、人民币售价25/18/20及成本12/未知/9均为明确演示假设','现金6000、备用金1500、试验预算800、房租3000及工时4小时为演示约束，不是UCI店铺真实资料'],'products':[{'sku':sku,'name_zh':name,'net_units':n,'source_rows':[x['xlsx_row'] for x in s['rows'][sku]]} for sku,name,n in zip(skus,names,net)]}
(D/'资料来源与加工清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(D/'02_店铺情况粘贴文本.txt').write_text('''本案例将公开零售交易与明确的演示假设结合，不代表该英国零售商实际采用了本系统。公开数据能验证三种商品的历史净销售件数，但没有提供库存盘点、采购成本、顾客购买动机或当前现金。
演示店名：拾光社区礼品店（公开数据演示）。截至2026-11-17。现金6000元，备用金1500元，试验预算800元，每周可投入4小时。2026-11-20应付房租3000元。上述金额与日期均为演示假设，人民币价格未由英镑转换。玩偶采购成本未知；顾客购买意愿未知；不把历史销量视为未来订单。不新增借款、不新增雇员，先确认缺口，再考虑处理现货。没有真实顾客或经营成效记录。
''',encoding='utf-8')
(R/'testing/upload-demo-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'package':str(P),'rows':len(original),'net_units':net},ensure_ascii=False))
