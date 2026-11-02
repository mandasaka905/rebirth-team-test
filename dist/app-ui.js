"use strict";
/* Flat, route-based application shell. Business forms keep their original API handlers. */
(()=>{
 const node=(tag,cls,html='')=>{const e=document.createElement(tag);e.className=cls;e.innerHTML=html;return e};
 const defs=[
 ['profile','店铺基本资料','店铺资料','现金、预算、时间、目标与原账确认','编辑 新增 建档 余额'],
 ['inventory','商品与库存','店铺资料','盘点商品、成本与近30天销量','货架 积压 采购价 尺码'],
 ['readiness','待核对资料','店铺资料','直接填写待补事实及来源','补证 追问 缺失'],
 ['customers','收付款与顾客观察','店铺资料','到期款项、待收款和匿名顾客反馈','房租 债务 客户 付款'],
 ['periods','分期经营记录','店铺资料','同口径记录营业额、费用和客流','同比 环比 期间 天数'],
 ['cohorts','固定客群复购','店铺资料','固定基准客群，查看复购与未复购','老客 留存 顾客'],
 ['accounts','采购与收支账簿','店铺资料','录入采购、现金流水和期初，检查差额','记账 收入 支出 CSV 对账'],
 ['supply','供应与补货条件','店铺资料','起订、到货、付款与退换条件','供应商 采购 货源'],
 ['imports','表格导入记录','店铺资料','库存盘点和销售明细的已保存批次','导入 Excel CSV'],
 ['models','经营模式与单位经济','分析决策','描述客户与价值，核对成本与保本量','商业模式 盈亏 收费'],
 ['investigation','原因调查','分析决策','保存原因假设、支持、反例和下一项核对','为什么 生意 证据'],
 ['analysis-results','各角色核查结论','分析决策','库存、顾客与现金分别检查同一份事实','多智能体 依据 角色'],
 ['plans','经营方案','分析决策','比较候选，编辑测算或登记小范围试验','计划 路径 假设 收益'],
 ['comparison','方案比较','分析决策','比较明示销量、工时和现金情景','选哪个 对比'],
 ['paths','人工经营路径','分析决策','按已有资源建立新的候选路径','新建方案 自定义 转型'],
 ['mode-drafts','新商业模式草案','分析决策','审阅三方意见，修改、接纳或否决','重构 智能体 创新'],
 ['portfolio','组合与预算筛选','分析决策','核对互斥、依赖、库存与累计支出','预算 优化 组合'],
 ['trials','试验登记与状态','行动复盘','计划、开展、暂停、停止和复盘','退出 条件 开始实验'],
 ['sales-feedback','逐商品实际反馈','行动复盘','记录真实销售、退款、成本与费用','回款 收支 结果'],
 ['journal','累计反馈与更正','行动复盘','追加检查点，保留更正前的来源','历史 记录 修正'],
 ['research','试验设计与评价','行动复盘','先固定口径，再测量并评价','基准 目标 冻结 实验'],
 ['drafts','智能体实验草案','行动复盘','审阅与试验精确关联的实验草案','实验设计 自动生成'],
 ['agenda-generator','生成行动日程','行动复盘','把核查结果收成7或14天的安排，先预览再保存','生成日程 日程生成 生成 日历 规划 安排 行程表'],
 ['agenda-summary','本轮经营总结','行动复盘','查看行动依据、现金底线与停止条件','总结 规划 一页'],
 ['agenda-history','日程历史与导出','行动复盘','切换已保存日程，导出日历和行动清单','ICS 下载 行程表 版本'],
 ['knowledge','本地资料检索','资料与设置','检索经营核查指南，保存本店文字资料','知识库 RAG 搜索'],
 ['references','有来源的参考资料','资料与设置','阅读适用范围、核对日期和原始来源','政策 来源 参考'],
 ['links','模式与试验关联','行动复盘','查看经营模式、方案、试验和评价的版本联系','闭环 关联 版本'],
 ['audit','协作与版本记录','资料与设置','回查实际事件、异议和结构化依据','日志 审计 多Agent'],
 ['analysis-settings','分析方式与历史','资料与设置','查看历史任务、运行方式与调用上限','模型 AgentArts AI 设置'],
 ['data','资料导出与本机管理','资料与设置','完整记录导出、导入副本及接入预检','备份 恢复 测试 样例'],
 ['usage','使用指南与数据说明','资料与设置','从建档到行动，了解本机保存与能力范围','帮助 怎么使用 安装 隐私']
 ];
 const lookup={
 '商品与库存':'inventory','需要补充与核对':'readiness','近期收支与客户观察':'customers','可能原因与补证调查':'investigation','分期经营记录与调查线索':'periods','本地知识与证据资料':'knowledge','供应条件与补货约束':'supply','本地经营表格导入记录':'imports','有来源的经营参考资料':'references','经营模式与单位经济':'models','采购、收支与现金核对':'accounts','固定客群复购与未复购调查':'cohorts','固定客群复购与未复购观察':'cohorts','经营模式 → 方案 → 试验 → 评价':'links','角色提交的实验草案':'drafts','固定客群复购核对':'cohorts','可供讨论的经营假设':'plans','明示假设下的候选比较':'comparison','候选经营路径与人工建模':'paths','协作过程、异议与版本':'audit','新商业模式草案与交叉审查':'mode-drafts','经营组合与预算筛选':'portfolio','试验登记与退出条件':'trials','分期反馈与更正留痕':'journal','预先设计、同口径测量与评价':'research','审阅由角色输出的实验草案':'drafts','本地验收与资料管理':'data'
 };
 const serviceDefs={support:['找人一起解决困难','说清困难，约定协助，跟进到店主回访','帮助 求助 社区 志愿者 家人 陪跑 回访'],learning:['看看别家店的办法','匿名整理方法，借鉴一步并记录真实结果','社会价值 影响力 经验 分享 学习 共益 复用'],handover:['打印清单、交接给别人','带走纸单，逐项交接','打印 打印单 纸单 行动单 大字 志愿者 陪跑'],impact:['看看这30天有什么变化','固定基准，记录行动、变化与负担','社会价值 成果 影响力 观察'],industry:['分行业专项核查','零售、餐饮、修理各用自己的单位与工具','行业 餐饮 食材 修理 工时'],mutual:['街坊互助','自愿登记资源，接收店铺另行确认','共享 闲置 资源 回收 街坊']};
 // Merchant-facing words describe an action; original IDs and data handlers stay intact.
 const plainNames={readiness:['还有哪些资料没填清','查看缺什么数字，再补充或核对'],customers:['要付的钱、要收的钱、顾客反馈','查看房租、货款和顾客说过的话'],periods:['每段时间的生意记录','分别记下营业额、费用和来客人数'],cohorts:['老顾客有没有再来','查看同一批顾客有多少人再次购买'],models:['每单赚多少、卖多少才保本','填写售价和成本，查看保本需要的订单数'],investigation:['查一查生意变差的原因','记下可能原因、已知情况和还要问的问题'],'analysis-results':['哪里有问题、为什么这样说','按库存、顾客、现金查看提醒和具体数字'],plans:['有哪些办法可以试','查看每个办法要花多少钱、多久，何时该停'],comparison:['比较几个办法','把花费、用时和不同销量下的剩余现金放在一起看'],paths:['自己添加一个办法','按店里现有条件填写自己的做法'],'mode-drafts':['看看新的经营办法','看建议，再决定修改、采用或不采用'],portfolio:['几个办法一起做会不会超预算','检查总花费、库存是否够用，以及能否一起开展'],trials:['已经试过哪些办法','查看已经登记的尝试，以及开始、暂停和停止记录'],'sales-feedback':['记卖出、退货和花费','按商品记录实际发生的收入和支出'],journal:['补充或改正以前的记录','保留旧记录，补上新的情况'],research:['怎么判断这次尝试有没有用','先定要观察什么，再记实际结果'],drafts:['查看建议的试做步骤','先选一个已经登记的尝试，再查看步骤'],'agenda-generator':['安排接下来每天做什么','生成7天或14天的清单，先看一遍再保存'],'agenda-summary':['这次发现什么、接着做什么','查看问题、要留的钱和需要停下的情况'],'agenda-history':['以前的安排、下载清单','查看以前的安排，或下载日历和清单'],knowledge:['查经营资料','按问题找资料，也可以保存本店的文字说明'],references:['查看资料出处','看原文从哪里来、适合什么情况'],links:['查看办法和行动怎么对应','查看某个经营办法对应的尝试和结果'],audit:['查看分析经过和旧记录','查看各次核对记录和不同意见'],'analysis-settings':['以前的分析、分析设置','查看过去的分析，调整下一次使用的方式'],data:['备份、恢复和本机设置','下载备份，或导入一份资料副本'],usage:['第一次怎么用','按顺序填资料、看问题、安排事情、记结果']};
 for(const d of defs){if(plainNames[d[0]]){d[4]+=' '+d[1];d[1]=plainNames[d[0]][0];d[3]=plainNames[d[0]][1]}}
 const tabLabels={overview:'今日',ledger:'店铺',analysis:'分析',feedback:'行动',services:'全部功能'};
 const tabIcons={overview:'home',ledger:'store',analysis:'team',feedback:'clock',services:'box'};
 const rawSet=setView,rawRender=render,rawSelect=selectMerchant;
 let route=(globalThis.RebirthInitialHash||'#overview').slice(1)||'overview',building=false,routing=false,active=null,requestedService=null,serial=0,lastMerchant=null,dayChoice=null,selectedGroup='全部',search='',pendingLeave=null,initialReady=false,switching=false,printReturn=null,wasBusy=false;
 const positions=new Map();let scrollRestore=null;
 const featureNodes=new Map(),detailNodes=new Map(),parents=new Map(),dirtyForms=new Set();
 const header=node('header','app-top');header.id='app-top';
 const dock=node('nav','app-dock');dock.setAttribute('aria-label','主要功能');
 const outlet=node('section','app-feature-outlet');outlet.id='app-feature-outlet';outlet.hidden=true;
 const services=node('section','app-services');services.id='app-services';services.hidden=true;
 const surface=node('section','app-surface');surface.id='app-surface';surface.hidden=true;
 const switchParking=node('div','app-switch-parking');switchParking.hidden=true;document.body.append(switchParking);
 const store=node('div','app-feature-store');store.id='app-feature-store';store.hidden=true;store.setAttribute('aria-hidden','true');
 const guard=node('section','app-leave-banner');guard.hidden=true;guard.setAttribute('role','alert');
 const connection=node('section','app-connection-banner');connection.hidden=true;connection.setAttribute('role','alert');document.body.prepend(header,connection);document.body.append(dock,store);
 document.querySelector('.page-content').append(outlet,services,surface);surface.prepend(guard);
 const routeButton=(title,path,cls='app-card',note='')=>`<button type="button" class="${cls}" data-app-route="${h(path)}"><span><strong>${h(title)}</strong>${note?`<small>${h(note)}</small>`:''}</span><span aria-hidden="true">↗</span></button>`;
 const actionButton=(title,action,extra='',primary=false)=>`<button type="button" class="button ${primary?'primary':'secondary'}" data-app-action="${action}" ${extra}>${h(title)}</button>`;
 const featureDef=id=>defs.find(d=>d[0]===id);
 const validReport=()=>state.report?.result&&!state.report.ledger_changed&&!state.report.context_changed&&!['running','failed','cancelled','interrupted'].includes(state.report.status);
 const listing=()=>globalThis.RebirthAgenda?.listing()||globalThis.RebirthCommunity?.data()?.agendas;
 const agenda=()=>listing()?.agendas?.find(a=>a.current)||null;
 const today=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
 const mainTab=()=>route.startsWith('service/')?'services':route.startsWith('feature/')?({店铺资料:'ledger',分析决策:'analysis',行动复盘:'feedback'}[featureDef(route.split('/')[1])?.[2]]||'services'):Object.prototype.hasOwnProperty.call(tabLabels,route)?route:'services';
 function titleFor(r=route){if(r.startsWith('feature/'))return featureDef(r.split('/')[1])?.[1]||'经营记录';if(r.startsWith('service/'))return serviceDefs[r.split('/')[1]]?.[0]||'小店陪跑';if(r.startsWith('edit/'))return active?.title||'填写记录';if(r.startsWith('record/'))return detailNodes.get(r)?.title||'查看依据';return {overview:'今天，小店一步一步来。',ledger:'把经营事实，记清楚。',analysis:'看清问题，再作决定。',feedback:'接下来，每一天怎么做。',services:'全部功能'}[r]||'小店经营'}
 function isDirty(){return !!active?.dirty||[...dirtyForms].some(f=>f.isConnected&&f.closest('#app-feature-outlet,.view:not([hidden])'))}
 function guardLeave(fn){if(switching){toast('正在读取店铺资料，请稍候');return false}if(active?.submitting){toast('正在保存，请等待结果');return false}if(!isDirty())return fn();pendingLeave=fn;guard.hidden=false;guard.innerHTML='<strong>这页有尚未保存的内容</strong><p>继续填写后保存，或放弃本次修改再离开；原来的已保存记录会保留。</p>'+actionButton('继续填写','continue-edit')+actionButton('放弃本次修改并离开','discard-edit');if(!guard.isConnected)surface.prepend(guard);if(!active)document.querySelector('#app-feature-outlet').prepend(guard);guard.scrollIntoView({block:'start'});return false}
 function rememberRoute(r,replace=false){const hash='#'+r;if(location.hash!==hash){history[replace?'replaceState':'pushState']({rebirth:true,route:r},'',hash)}}
 function closeRaw(d){if(d.open){d.removeAttribute('open');d.dispatchEvent(new Event('close'))}d.hidden=true}
 function parkFeatures(){for(const el of [...outlet.children])if(el!==guard)store.append(el);outlet.replaceChildren();outlet.hidden=true;services.hidden=true;for(const v of document.querySelectorAll('.view'))v.hidden=true;}
 function baseFor(r){if(Object.prototype.hasOwnProperty.call(titles,r))return r;if(r.startsWith('feature/')){const g=featureDef(r.split('/')[1])?.[2];return g==='店铺资料'?'ledger':g==='分析决策'?'analysis':g==='行动复盘'?'feedback':'overview'}return 'overview'}
 function apply(r,{replace=false,push=true,fromSurface=false}={}){
  routing=true;route=r;if(push)rememberRoute(r,replace);rawSet(baseFor(r));rememberRoute(r,true);parkFeatures();
  if(fromSurface&&active){surface.hidden=false;document.body.classList.add('app-editing');refreshHeader();routing=false;return}
  if(!fromSurface&&active){closeRaw(active.node);active=null;surface.hidden=true;document.body.classList.remove('app-editing')}
  if(r.startsWith('service/')){
   const key=r.split('/')[1];if(!Object.prototype.hasOwnProperty.call(serviceDefs,key)){routing=false;return navigate('services',{replace:true,unguarded:true})}
   requestedService=key;routing=false;refreshHeader();globalThis.RebirthCommunity.open(key);return;
  }
  if(r.startsWith('edit/')){if(active){surface.hidden=false;document.body.classList.add('app-editing')}else{routing=false;toast('请从对应功能页重新打开编辑，已保存记录仍在');return navigate(parents.get(r)||'services',{replace:true,unguarded:true})}}
  else if(r.startsWith('record/')){const detail=detailNodes.get(r);if(detail){outlet.hidden=false;outlet.append(detail.node)}else{routing=false;return navigate('services',{replace:true,unguarded:true})}}
  else if(r==='services'){services.hidden=false;renderServices()}
  else if(r.startsWith('feature/')){outlet.hidden=false;showFeature(r.split('/')[1])}
  else if(Object.prototype.hasOwnProperty.call(titles,r)){document.querySelector('#view-'+r).hidden=false;if(r==='overview')refreshToday();if(r==='feedback')prepareAgenda()}
  else{routing=false;return navigate('overview',{replace:true,unguarded:true})}
  refreshHeader();routing=false;
 }
 function navigate(r,options={}){if(r===route&&!active){apply(r,{...options,replace:true});window.scrollTo({top:0,behavior:'auto'});return}const run=()=>{positions.set(route,window.scrollY);if(!options.replace&&r!==route&&(r.startsWith('feature/')||r.startsWith('service/')))parents.set(r,route);scrollRestore=options.restore?(positions.get(r)||0):null;guard.hidden=true;pendingLeave=null;dirtyForms.clear();if(active)active.dirty=false;apply(r,options);window.scrollTo({top:options.restore?(positions.get(r)||0):0,behavior:'auto'})};return options.unguarded?run():guardLeave(run)}
 function back(){let target=active?.parent||parents.get(route);if(!target){if(route.startsWith('feature/'))target=mainTab();else if(route.startsWith('service/'))target='services';else target='overview'}navigate(target,{replace:true,restore:true})}
 function refreshHeader(){connection.hidden=!state.loadError;if(state.loadError)connection.innerHTML='<strong>本机资料暂未读取成功</strong><p>请保持本项目的后台窗口运行，再重新读取。未保存成功的内容不能当作已记录。</p>'+actionButton('重新读取','retry');
  const feature=route.startsWith('feature/')||route.startsWith('service/')||route.startsWith('record/')||route.startsWith('edit/');
  const title=active?.title&&surface.hidden===false?active.title:titleFor();
  header.innerHTML=`<div class="app-top-inner">${feature?`<button class="app-back" type="button" data-app-action="back" aria-label="返回上一页">← <span>返回</span></button>`:`<a class="app-wordmark" href="/">逆势重生<span>小店的明天</span></a>`}<div class="app-location"><strong>${h(feature?title:'我的经营手记')}</strong><small>${state.booting||switching?'正在读取本机资料':state.merchant?h(state.merchant.name):'尚未添加店铺'}${state.merchant?.synthetic?' · 练习数据':''}</small></div>${globalThis.RebirthHosted?`<a class="app-account-link" href="/account">账号</a>`:''}<button type="button" class="app-header-tool" data-app-action="help" aria-label="使用帮助">?</button></div>`;
  dock.innerHTML=Object.entries(tabLabels).map(([id,label])=>`<button type="button" data-app-route="${id}" ${state.booting||switching?'disabled':''} ${mainTab()===id?'aria-current="page"':''}>${icon(tabIcons[id])}<span>${label}</span></button>`).join('');
  document.body.dataset.appCurrentRoute=route;document.body.dataset.appForm=String(route.startsWith('edit/')||route.includes('/form/'));document.body.dataset.appPrint=String(active?.node.id==='community-print-dialog');document.title=title+' · 逆势重生';if(active){active.node.removeAttribute('aria-labelledby');active.node.setAttribute('aria-label',title)}outlet.setAttribute('aria-label',titleFor());
 }
 function installDialog(d){
  if(d.dataset.appSurface)return;d.dataset.appSurface='true';d.setAttribute('role','region');d.removeAttribute('aria-modal');d.hidden=true;
  d.showModal=()=>{
   const same=active?.node===d;const prior=same?active.parent:route,shared=d.id==='community-dialog',paper=d.id==='community-print-dialog';
   if(active&&active.node!==d)closeRaw(active.node);
   let next=same?route:shared?'service/'+(requestedService||globalThis.RebirthCommunity.tab()):'edit/'+d.id+'/'+(++serial);
   const parent=paper?(printReturn||active?.parent||prior):shared?(parents.get(next)||'services'):prior;if(paper)printReturn=null;
   const title=d.querySelector('h2')?.textContent||'填写记录';
   active={node:d,parent,title,dirty:false,submitting:false};parents.set(next,parent);route=next;rememberRoute(next);parkFeatures();surface.hidden=false;surface.append(d);d.hidden=false;d.setAttribute('open','');document.body.classList.add('app-editing');decorateSurface(d);refreshHeader();window.scrollTo({top:0,behavior:'auto'});
   const focus=header.querySelector('.app-location >strong');if(focus){focus.tabIndex=-1;focus.focus({preventScroll:true})}
  };
  d.close=()=>{const a=active?.node===d?active:null;if(!a){closeRaw(d);return}const done=()=>{const target=a.parent;closeRaw(d);active=null;surface.hidden=true;document.body.classList.remove('app-editing');dirtyForms.clear();navigate(target,{replace:true,unguarded:true})};if(a.submitting||!a.dirty)done();else guardLeave(done)};
 }
 function decorateSurface(d){
  flatten(d);const f=d.querySelector('form');if(!f||f.querySelector('.app-form-outline'))return;
  const sections=[...f.querySelectorAll('.form-section')];const jumps=[];
  for(const section of sections){const heading=section.querySelector('h3');if(heading){section.id='app-form-'+(++serial);jumps.push([heading.textContent.trim(),section.id])}}
  if(!jumps.length&&f.querySelectorAll('input,select,textarea').length>14){
   const names=[['scope_id','核对统计范围'],['metric','设置评价指标'],['observe_start','安排观察日期'],['base_start','核对基准记录'],['comparison_method','说明比较与退出'],['trial_spend','记录实际投入']];
   for(const [name,label] of names){const field=f.querySelector('[name="'+name+'"]');if(!field)continue;const target=field.closest('.form-label');target.id='app-form-'+(++serial);jumps.push([label,target.id])}
  }
  if(jumps.length){const nav=node('nav','app-form-outline','<p>按顺序核对，也可以直接跳到要填写的位置。</p>'+jumps.map(([label,id])=>`<button type="button" data-app-jump="${h(id)}">${h(label)}</button>`).join(''));nav.setAttribute('aria-label','填写位置导航');f.prepend(nav)}
 }
 document.querySelectorAll('dialog').forEach(d=>{installDialog(d);new MutationObserver(()=>{if(d.open&&d.querySelector('details'))flatten(d)}).observe(d,{childList:true,subtree:true});new MutationObserver(()=>{if(active?.node===d&&d.id!=='community-dialog'&&d.id!=='community-print-dialog'){active.title=d.querySelector('h2')?.textContent||active.title;if(!d.querySelector('form [type=submit]:disabled'))active.submitting=false;decorateSurface(d);refreshHeader()}}).observe(d,{childList:true})});
 function communityPage(tab){if(!active||active.node.id!=='community-dialog')return;const target='service/'+tab;active.title=serviceDefs[tab][0];active.parent=parents.get(target)||'services';active.dirty=false;active.submitting=false;route=target;rememberRoute(target,true);refreshHeader();flatten(active.node);if(scrollRestore!==null){const top=scrollRestore;scrollRestore=null;requestAnimationFrame(()=>window.scrollTo({top,behavior:'auto'}))}}
 function communityForm(kind){if(!active||active.node.id!=='community-dialog')return;const parent='service/'+globalThis.RebirthCommunity.tab();active.parent=parent;active.title=active.node.querySelector('#community-content h3')?.textContent||'填写记录';active.dirty=false;active.submitting=false;const r=parent+'/form/'+kind;parents.set(r,parent);route=r;rememberRoute(r);refreshHeader();decorateSurface(active.node);window.scrollTo({top:0,behavior:'auto'})}
 function printPage(){if(!active)return;active.title='大字打印预览';refreshHeader()}
 function flatTitle(head){return head.querySelector('h2')?.textContent.trim()||''}
 function addFeature(id,nodes){if(!nodes.length)return;const pane=featureNodes.get(id)||node('div','app-feature-content');pane.dataset.featureId=id;nodes.forEach(n=>pane.append(n));featureNodes.set(id,pane);store.append(pane);flatten(pane)}
 function flatten(root){
  for(const table of root.querySelectorAll('.table-wrap table')){
   if(table.querySelector('input,select,textarea'))continue;
   const headings=[...table.querySelectorAll('thead th')].map(n=>n.textContent.trim());
   if(headings.length<2)continue;
   table.classList.add('mobile-read-table');
   for(const row of table.querySelectorAll('tbody tr'))for(const [i,cell] of [...row.children].entries()){
    if(cell.colSpan>1){cell.classList.add('mobile-empty-cell');continue}
    cell.dataset.label=headings[i]||'';
   }
  }
  // Optional facts are sections on a functional page, never nested disclosure controls.
  for(const d of [...root.querySelectorAll('details')].reverse()){
   const section=node('section','app-facts');const sum=d.querySelector(':scope > summary');if(sum)section.append(node('h3','app-facts-title',h(sum.textContent.trim().replace(/^展开\s*/, '共'))));for(const c of [...d.childNodes])if(c!==sum)section.append(c);d.replaceWith(section);
  }
  // Raw technical payloads have their own page. Merchant-facing forms keep templates in place.
  for(const pre of root.querySelectorAll('pre.json-block'))if(!pre.closest('form')&&!pre.dataset.appRecord){
   pre.dataset.appRecord='true';const key='record/'+(++serial),body=node('section','app-record-content');const title=pre.closest('li')?.querySelector('strong')?.textContent||'结构化原始依据';body.append(node('h1','app-page-title',h(title)));const button=node('button','button secondary','查看这条结构化记录 ↗');button.type='button';button.dataset.appRoute=key;pre.before(button);body.append(pre);detailNodes.set(key,{title,node:body});parents.set(key,'feature/audit');
  }
 }
 function collect(){
  for(const [view,id] of [['ledger','profile'],['analysis','analysis-results'],['feedback','sales-feedback']]){
   const v=document.querySelector('#view-'+view);const children=[...v.children];let group=[],key=id,unknown=0;
   for(const c of children){
    if(c.id==='agenda-board'){continue}
    if(c.id==='agenda-entry'){addFeature('agenda-generator',[c]);continue}
    if(c.matches('.title-actions')){
     if(view==='analysis'){const controls=c.querySelector('.mode-controls');if(controls)addFeature('analysis-settings',[controls])}
     if(view!=='analysis')group.push(c);continue;
    }
    if(c.matches('.section-head')){addFeature(key,group);group=[];const title=flatTitle(c);key=lookup[title]||('extra-'+view+'-'+(++unknown));if(!featureDef(key))defs.push([key,title,{ledger:'店铺资料',analysis:'分析决策',feedback:'行动复盘'}[view],'查看记录、补充依据与处理下一步',title]);group.push(c)}else group.push(c);
   }
   addFeature(key,group);
  }
  const overview=document.querySelector('#view-overview');
  const head=[...overview.children].find(n=>n.matches('.section-head')&&flatTitle(n)==='本地验收与资料管理');if(head){const rows=[];let n=head;while(n){const next=n.nextElementSibling;rows.push(n);n=next}addFeature('data',rows)}
  // A clear history entry, using the existing exact-version selector and event handler.
  const reportSelect=document.querySelector('#report-select');if(reportSelect)addFeature('analysis-settings',[node('h2','app-subheading','查看历史核查'),reportSelect]);
 }
 function pageHead(title,description,actions=''){return `<div class="app-page-heading"><div><p class="app-eyebrow">小店经营手记 · 本机保存</p><h1>${h(title)}</h1><p>${h(description)}</p></div>${actions?`<div class="app-heading-actions">${actions}</div>`:''}</div>`}
 function everydayGuide(){const ready=validReport(),saved=agenda();return `<section class="app-everyday" aria-label="使用顺序"><h2>从这里开始，不用学专业词。</h2><p>先填资料，再看问题，最后安排事情。做完后回来记结果。</p><ol>${[
  ['店铺资料','ledger',state.merchant?'检查现金、商品和要付的钱':'先添加店铺；不清楚的数字别猜'],
  ['看看有什么问题','analysis',ready?'已分析过，可以看具体数字':'点“开始本地分析”，等结果出来'],
  ['安排每天做什么','feedback',saved?'已有安排，点开后选一天查看':ready?'生成清单，确认后保存':'先完成分析，再生成7天或14天清单'],
  ['做完了记一下','feedback','点任务里的记录按钮；没做也可以如实记']
 ].map(([label,path,note],i)=>`<li>${routeButton((i+1)+'. '+label,path,'app-guide-step',note)}</li>`).join('')}</ol></section>`}
 function builderMain(){
  const ledger=document.querySelector('#view-ledger');ledger.innerHTML=pageHead('把经营事实，记清楚。','先检查现金、商品数量和要付的钱。每张卡片点开就能查看，修改后记得保存。',actionButton(state.merchant?'编辑店铺资料':'添加我的店铺','edit-shop','',true))+`<section class="app-store-card"><div><span class="app-eyebrow">当前店铺</span><h2>${h(state.merchant?.name||'还没有店铺档案')}</h2><p>${state.merchant?'截至 '+h(state.merchant.as_of)+' · '+h(state.merchant.goal):'先建立一个本机档案。也可以用合成店铺练习，不会覆盖已有记录。'}</p></div><div class="app-switcher" id="app-switcher"></div></section><h2 class="app-section-title">要改哪一项？直接点开。</h2><div class="app-link-grid">${['profile','inventory','customers','accounts','readiness','periods','cohorts','supply','imports'].map(id=>featureCard(id)).join('')}</div>`;
  const select=document.querySelector('#merchant-select');if(select)ledger.querySelector('#app-switcher').append(select);const add=document.querySelector('#new-shop-button');if(add)ledger.querySelector('#app-switcher').append(add);
  const a=document.querySelector('#view-analysis');a.innerHTML=pageHead('看清问题，再作决定。','先点“开始本地分析”（分析过会显示“重新核查”）。完成后看“哪里有问题”，再安排每天做什么。只用本机程序，不会扣模型费用。',`<button class="button primary" type="button" data-action="analyze" ${!state.merchant||state.busy?'disabled':''}>${state.busy?'核查进行中…':state.report?'重新核查':'开始本地分析'}</button>`)+(!state.merchant?emptyShop():state.busy?busyBox():`<section class="app-analysis-status"><span class="app-status-dot"></span><div><strong>${!state.report?'先完成一次经营核查':validReport()?'本轮核查已完成':'资料或任务状态需要重新核查'}</strong><p>${!state.report?'点击上方开始；本地模式不会产生模型费用。':validReport()?`${state.report.result.proposals?.length||0}个办法可查看，${state.readiness?.questions?.length||0}项资料还要核对。先看问题，再决定试哪一步。`:'原记录仍可回查，重新核查后再生成当前日程。'}</p></div></section><div class="app-analysis-next">${routeButton('看看有哪些办法可试','feature/plans','app-primary-link','先看花费和条件，不会自动替你执行')}${actionButton('下一步：安排每天做什么','generate','',true)}</div><div class="app-link-grid">${['analysis-results','readiness'].map(id=>featureCard(id)).join('')}</div><h2 class="app-section-title">想再仔细看看？</h2><p>下面是可选的检查工具，不用每一项都填写。</p><div class="app-link-grid">${['comparison','investigation','models','mode-drafts','paths','portfolio','analysis-settings','audit'].map(id=>featureCard(id)).join('')}</div>`);
  const feedback=document.querySelector('#view-feedback');const board=feedback.querySelector('#agenda-board');feedback.replaceChildren();feedback.insertAdjacentHTML('beforeend',pageHead('行动日程','选择日期，按任务行动；完成或暂停，都如实记录。',actionButton('生成行动日程','generate','',true)));feedback.insertAdjacentHTML('beforeend',`<div id="app-social-actions">${globalThis.RebirthSocial?.actionRemindersHtml()||''}</div>`);if(board)feedback.append(board);else feedback.insertAdjacentHTML('beforeend','<section id="agenda-board" class="agenda-board"></section>');feedback.insertAdjacentHTML('beforeend',`<div class="app-follow-through"><h2>做过之后，记实际情况。</h2><div class="app-link-grid">${['trials','sales-feedback','journal','research','agenda-summary','agenda-history'].map(id=>featureCard(id)).join('')}${routeButton('看看这30天有什么变化','service/impact','app-card','留下同一口径的观察，也保留暂停原因')}${routeButton('大字行动单与交接','service/handover','app-card','把任务带回店里，继续做下去')}</div></div>`);
  document.querySelector('#view-overview').innerHTML='<div id="app-today"></div>';
  prepareAgenda();refreshToday();
 }
 function featureCard(id){const d=featureDef(id);return routeButton(d[1],'feature/'+id,'app-card',d[3])}
 function emptyShop(){return `<div class="app-empty"><h2>先让我们认识这间小店。</h2><p>建立本机店铺档案后，资料、核查、行动和复盘就能接在一起。</p>${actionButton('添加我的店铺','new-shop','',true)}${actionButton('先体验练习示例','example')}</div>`}
 function refreshToday(){const target=document.querySelector('#app-today');if(!target)return;
  if(state.booting){target.innerHTML='<div class="app-empty" role="status">正在读取本机店铺与使用进度…</div>';return}
  const l=state.merchant,a=agenda(),date=today(),tasks=a&&!a.stale?a.days.flatMap(d=>d.tasks.filter(t=>t.status==='pending'&&d.date<=date).map(t=>({...t,date:d.date}))):[],nextTasks=tasks.length?tasks:a&&!a.stale?a.days.flatMap(d=>d.tasks.filter(t=>t.status==='pending').map(t=>({...t,date:d.date}))):[];
  const socialReminders=globalThis.RebirthCommunity?.data()?.social?.reminders||[],dueReminder=socialReminders.find(r=>r.date<=date);
  const next=dueReminder?['查看待跟进的事情','social-due','先把记下的小事接着做完']:!l?['添加我的店铺','new-shop','先记下知道的事实']:!validReport()?['先做经营核查','analysis','资料有变化时，先核对再安排']:!a||a.stale?['生成我的行动日程','generate','把核查结果收成每天可以做的事']:['查看我的行动安排','actions','按日期做一小步，把依据留下'];
  target.innerHTML=`<section class="app-welcome"><div><p>${h(new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'}))} · ${l?.synthetic?'练习数据':'本机经营手记'}</p><h1>今天，小店<br>一步一步来。</h1><span>一份生计，值得被认真对待。</span></div></section>${everydayGuide()}<div class="app-today-head"><h2>${l?h(l.name):'从一间小店开始。'}</h2><p>${h(next[2])}</p>${actionButton(next[0],next[1],'',true)}</div>${!l?emptyShop():`<div class="app-snapshot"><div><span>账面可用现金</span><strong>¥${h(yuan(l.cash_balance))}</strong><small>截至 ${h(l.as_of)}</small></div><div><span>待核对资料</span><strong>${state.readiness?.questions?.length||0}<small>项</small></strong><button data-app-route="feature/readiness" type="button">去核对 →</button></div><div><span>当前日程记录</span><strong>${a?a.completed_count+'/'+a.task_count:'尚未生成'}</strong><small>自报进度，不代表经营成效</small></div></div><section class="app-today-list"><div class="app-section-row"><h2>接下来要做的事</h2><button type="button" data-app-route="feedback">查看全部 →</button></div>${todayTasks(a,nextTasks,socialReminders)}</section>`}<section class="app-shortcuts"><h2>常用操作</h2><div class="app-quick-grid">${routeButton('改现金、商品、要付的钱','ledger','app-quick','选要修改的资料，再点保存')}${`<button type="button" class="app-quick" data-app-action="generate"><span><strong>生成行动日程</strong><small>总结、安排与依据</small></span><span aria-hidden="true">↗</span></button>`}${routeButton('分行业核查','service/industry','app-quick','零售 / 餐饮 / 修理')}${routeButton('看看这30天有什么变化','service/impact','app-quick','记录变化与负担')}</div></section>${globalThis.RebirthSocial?.remindersHtml(false)||''}<div class="app-story-line"><span>记录事实</span><i>→</i><span>看清问题</span><i>→</i><span>小步行动</span><i>→</i><span>回看变化</span></div><p class="app-local-note">资料保存在本机。当前复杂分析以服装零售为首个验证场景，其他行业可做专项准备核查；真实AgentArts尚未接入。</p>`;
 }
 function todayTasks(a,tasks,social){const entries=tasks.map(t=>({date:t.date,html:`<button class="app-today-task" type="button" data-app-day="${h(t.date)}"><span class="app-task-check" aria-hidden="true">○</span><span><strong>${h(t.title)}</strong><small>${h(t.date)}${t.date<today()?' · 原安排已到期，请核对':''} · 约${t.minutes}分钟</small></span><b aria-hidden="true">→</b></button>`}));for(const r of social)entries.push({date:r.date,html:`<button class="app-today-task" type="button" data-app-route="service/${r.kind==='support'?'support':'learning'}" data-social-focus="${h(r.id)}"><span class="app-task-check" aria-hidden="true">○</span><span><strong>${h(r.title)}</strong><small>${h(r.date)} · ${r.kind==='support'?'陪跑跟进':'邻店尝试'}${r.date<today()?' · 原安排已到期，请核对':''}</small></span><b aria-hidden="true">→</b></button>`});entries.sort((x,y)=>x.date.localeCompare(y.date));return (a?.stale?'<p class="app-inline-note">经营日程的依据已经变化，先重新核查。已约好的陪跑与借鉴仍可分别核对。</p>':'')+(entries.slice(0,3).map(x=>x.html).join('')||'<p class="app-inline-note">目前没有待安排的任务。可以生成日程，也可以按需要发起求助。</p>')}
 function catalogueItems(){const matches=d=>(selectedGroup==='全部'||d[2]===selectedGroup)&&(!search||d.join(' ').toLowerCase().includes(search.toLowerCase()));return {items:defs.filter(matches),socials:Object.entries(serviceDefs).map(([id,d])=>[id,d[0],'陪跑互助',d[1],d[2]]).filter(matches)}}
 let catalogueExpanded=false;
 function catalogueResultHtml(items,socials){
  const review=/复盘|记结果|记录结果|做完/.test(search);
  const quick=review?`<section class="app-search-recommendation"><h2>你想记哪一种结果？</h2><div class="app-link-grid">${routeButton('记每天的事做了没有','feedback','app-card','打开一条任务，记完成、暂停或没有开展')}${routeButton('记试了邻店办法后的结果','service/learning','app-card','找到已保存的安排，点“记这次试做的结果”')}${routeButton('记别人帮忙后解决了多少','service/support','app-card','打开求助记录，按页面提示继续')}</div></section>`:'';
  const count=items.length+socials.length;
  if(!catalogueExpanded&&selectedGroup==='全部'&&(!search||review))return quick+`<p class="app-inline-note">${review?'上面三项可以直接记录结果。':'日常操作用上面的六个入口就够了。'}需要详细核账、测算或查旧记录时，再打开下面的工具。</p>${actionButton('展开'+count+'项'+(review?'其他相关':'详细')+'工具','catalogue-more')}`;
  return quick+`<div class="app-link-grid">${socials.map(d=>routeButton(d[1],'service/'+d[0],'app-card',d[3])).join('')}${items.map(d=>featureCard(d[0])).join('')}</div>${count?'':`<div class="app-empty"><h2>没有找到匹配的功能</h2><p>试试“库存”“收支”“日程”或“成效”，也可以清空搜索。</p>${actionButton('清空搜索条件','clear-search')}</div>`}`;
 }
 function renderSearchResults(){const {items,socials}=catalogueItems();services.querySelector('#app-search-results').innerHTML=catalogueResultHtml(items,socials);services.querySelector('.app-search-count').textContent=/复盘|记结果|记录结果|做完/.test(search)?'先选下面一种结果；详细工具可按需展开':`${items.length+socials.length}项功能 · 点击直接进入`;services.querySelector('[data-app-action="clear-search"]').hidden=!search;const common=services.querySelector('.app-everyday-services');if(common)common.hidden=!!(search||selectedGroup!=='全部')}
 function updateFunctionSearch(event){if(event.target.id!=='app-function-search'||event.isComposing)return;search=event.target.value;renderSearchResults()}
 function renderServices(){const groups=['全部','店铺资料','分析决策','行动复盘','陪跑互助','资料与设置'],{items,socials}=catalogueItems();
  const everyday=[['修改现金、库存和收付款','ledger','把店里的数字填清楚'],['看问题，再选一个办法','analysis','分析结果和下一步安排在一起'],['查看待办、记录做了没有','feedback','每天的事、暂停和完成都在这里'],['我需要人帮忙','service/support','记困难、约好一起做、记最后结果'],['看看别家店的办法','service/learning','挑一步试试，再记适不适合自己'],['打印或下载待办清单','service/handover','把安排变成一张大字纸单']];
  const matched=search||selectedGroup!=='全部';
  services.innerHTML=pageHead('你现在想做什么？','先选下面一件事。其他工具在下方，不用一次全部学会。')+`<label class="app-search">${icon('search')}<input type="search" id="app-function-search" value="${h(search)}" placeholder="搜索，例如：记结果、打印、库存、求助" aria-label="搜索全部功能"><button type="button" data-app-action="clear-search" aria-label="清空搜索" ${search?'':'hidden'}>×</button></label><section class="app-everyday-services"><h2>最常用的事</h2><div class="app-link-grid">${everyday.map(([label,path,note])=>routeButton(label,path,'app-card',note)).join('')}</div></section><div class="app-section-row app-more-heading"><h2>更多工具</h2><p>按需要使用；不会影响上面的日常流程。</p></div><div class="app-filter" aria-label="功能分类">${groups.map(g=>`<button type="button" data-app-group="${h(g)}" aria-pressed="${g===selectedGroup}">${h(g)}</button>`).join('')}</div><p class="app-search-count" role="status">${items.length+socials.length}项工具 · 点击打开</p><div id="app-search-results">${catalogueResultHtml(items,socials)}</div>`;
  services.querySelector('.app-everyday-services').hidden=!!matched;
 }
 function featureNext(id,pane){if(pane.querySelector('.app-feature-next'))return;const actions=[];
  if(['inventory','customers'].includes(id))actions.push(actionButton('编辑本店相关资料','edit-shop','',true));
  if(id==='imports')actions.push('<button class="button primary" type="button" data-completion="operating-import">导入库存／销售表格</button>');
  if(['trials','sales-feedback','journal'].includes(id))actions.push(routeButton('去经营方案，登记或记录一次行动','feature/plans','app-primary-link'));
  if(id==='drafts'){actions.push('<p class="app-inline-note">实验草案需先关联一项计划中的试验；已有记录可在试验页核对状态与版本。</p>');actions.push(routeButton('查看试验计划与前置条件','feature/trials','app-primary-link'))}if(id==='research'&&!state.extras?.workbench.research.length)actions.push(routeButton('从方案登记计划，再冻结评价设计','feature/plans','app-primary-link'));
  if(id==='readiness')actions.push(routeButton('资料补齐后，继续经营核查','analysis','app-primary-link'));
  if(id==='links')actions.push(routeButton('维护经营模式','feature/models','app-primary-link')+routeButton('查看与登记具体方案','feature/plans','app-inline-link'));if(id==='supply')actions.push(routeButton('到经营方案配置拟补货并测算','feature/plans','app-inline-link'));
  if(id==='references'||id==='investigation')actions.push(routeButton('带着这些依据，继续经营核查','analysis','app-primary-link'));
  if(actions.length)pane.append(node('div','app-feature-next',actions.join('')));
 }
 function showFeature(id){
  if(id==='usage'){outlet.innerHTML=pageHead('怎么使用这份经营手记','四个日常入口，一份能持续使用的记录。',actionButton(document.body.classList.contains('comm-large')?'大字模式：已开启':'大字模式：已关闭','large'))+`<ol class="app-use-list"><li><strong>1. 在“店铺”记录已知事实</strong><p>填写现金、库存、必要付款和经营目标。不确定的值留待核实。</p>${routeButton('去店铺资料','ledger','app-inline-link')}</li><li><strong>2. 在“分析”看清依据与条件</strong><p>开始本地核查，补充资料；选择一个办法可查看，不叠加互斥方案。</p>${routeButton('去经营分析','analysis','app-inline-link')}</li><li><strong>3. 在“行动”按日安排</strong><p>生成日程、查看当天任务、填写实际记录。需要纸单时打开大字行动单。</p>${routeButton('去行动日程','feedback','app-inline-link')}</li><li><strong>4. 记录实际反馈，回看变化</strong><p>在试验、实际反馈和成效档案留下来源、额外投入和暂停原因，再进行下一次核查。</p>${routeButton('去成效档案','service/impact','app-inline-link')}</li><li><strong>有困难时，找人陪跑或借鉴邻店</strong><p>求助记录会提示下一次跟进；借鉴只选一小步，做完后记录是否适合本店。</p>${routeButton("去找人一起解决困难","service/support","app-inline-link")}${routeButton("去看看别家店的办法","service/learning","app-inline-link")}</li></ol><section class="app-data-note"><h2>资料与使用范围</h2><p>当前是本机网页应用，不是已上架的原生App。关闭后台窗口后无法读取或保存；请保持服务运行。完整记录可在“资料导出与本机管理”下载。多店铺档案不是线上账号认证。</p><p>当前本地规则不预测收益，也不证明因果或真实社会受益。未开通付费模型，没有向外部机构发送资料。</p>${routeButton('导出与管理资料','feature/data','app-inline-link')}</section>`;return}
  if(!state.merchant&&id!=='data'){outlet.innerHTML=pageHead(featureDef(id)?.[1]||'经营记录','先建立店铺档案，记录才有清楚的归属。')+emptyShop();return}
  if(id==='agenda-summary'){
   const summary=document.querySelector('#agenda-board .agenda-summary');outlet.innerHTML=pageHead('本轮经营总结','先看事实、约束和未核实的地方，再安排下一步。',actionButton('生成新日程','generate','',true));if(summary){const copy=summary.cloneNode(true);flatten(copy);outlet.append(copy)}else outlet.insertAdjacentHTML('beforeend','<p class="app-inline-note">尚未保存日程。完成核查后点击上方按钮生成，先预览再确认。</p>');outlet.insertAdjacentHTML('beforeend',routeButton('查看每日行动','feedback','app-primary-link'));return;
  }
  if(id==='agenda-history'){
   outlet.innerHTML=pageHead('日程历史与导出','切换历史版本后只作回查；当前日程的进度仍按版本保存。');const history=document.querySelector('#agenda-board .agenda-history');if(history){const proxy=history.cloneNode(true);proxy.querySelector('select').id='app-agenda-history';outlet.append(proxy);}const tools=document.querySelector('#agenda-board .agenda-board-tools');if(tools)outlet.append(tools.cloneNode(true));outlet.insertAdjacentHTML('beforeend',routeButton('回到每日任务','feedback','app-primary-link'));return;
  }
  const pane=featureNodes.get(id);if(pane&&pane.children.length){if(!validReport()&&['plans','comparison','paths','mode-drafts','portfolio','drafts','agenda-generator'].includes(id))outlet.append(node('div','app-inline-note','当前资料需要完成核查后才能开展新的操作；历史仍保留。'+routeButton('去重新核查','analysis','app-inline-link')));outlet.append(pane);featureNext(id,pane);if(id==='analysis-settings')outlet.prepend(node('p','app-inline-note','运行方式只影响你明确开始的下一次核查。真实云调用仍需配置就绪与逐次确认。'));if(id==='plans')outlet.append(node('div','app-flow-footer',actionButton('下一步：生成行动日程','generate','',true)));return}
  outlet.innerHTML=pageHead(featureDef(id)?.[1]||'经营记录','这项记录还没有可展示的内容。')+`<section class="app-empty"><h2>${id==='plans'||['comparison','paths','mode-drafts','analysis-results','audit','portfolio'].includes(id)?'先完成一次当前资料的经营核查':'记录从第一次填写开始。'}</h2><p>原始记录不会被补造。使用下方入口完成必要步骤后，再回到这里查看。</p>${routeButton('去经营分析','analysis','app-primary-link')}${routeButton('查看店铺资料','ledger','app-inline-link')}</section>`;
 }
 let agendaQueued=false;
 function scheduleAgenda(){if(agendaQueued)return;agendaQueued=true;queueMicrotask(()=>{agendaQueued=false;prepareAgenda();if(route==='overview')refreshToday()})}
 function prepareAgenda(){const board=document.querySelector('#agenda-board');if(!board)return;const layout=board.querySelector('.agenda-layout');if(!layout)return;const days=[...board.querySelectorAll('.agenda-days > .agenda-day')];if(!days.length)return;
  const dates=days.map((d,i)=>listing()?.agendas?.find(a=>a.id===document.querySelector('#agenda-history')?.value)?.days[i]?.date||agenda()?.days[i]?.date);
  if(!dayChoice||!dates.includes(dayChoice)){const now=today();dayChoice=dates.includes(now)?now:dates.find(d=>d>=now)||dates[0]}
  let rail=board.querySelector('.app-day-rail');if(!rail){rail=node('div','app-day-rail');rail.setAttribute('aria-label','选择任务日期');layout.before(rail)}
  const currentKey=dates.join('|')+':'+dayChoice;if(rail.dataset.signature!==currentKey){rail.dataset.signature=currentKey;rail.innerHTML=dates.map((date,i)=>`<button type="button" data-app-day="${h(date)}" aria-pressed="${date===dayChoice}"><small>${date===today()?'今天':i===0?'第1天':'第'+(i+1)+'天'}</small><strong>${h(date?.slice(5).replace('-','/'))}</strong><span>${days[i].querySelectorAll('.agenda-task').length}项任务</span></button>`).join('')}
  days.forEach((d,i)=>{d.hidden=dates[i]!==dayChoice;flatten(d)});
  if(!board.querySelector('.app-agenda-links'))layout.before(node('div','app-agenda-links',routeButton('本轮总结与底线','feature/agenda-summary','app-inline-link')+routeButton('历史版本与导出','feature/agenda-history','app-inline-link')));
  const history=board.querySelector('.agenda-history');if(history)history.classList.add('app-inline-history');
 }
 const observedBoards=new WeakSet();
 function watchAgenda(){const board=document.querySelector('#agenda-board');if(board&&!observedBoards.has(board)){observedBoards.add(board);new MutationObserver(m=>{if(m.some(x=>x.target===board))scheduleAgenda()}).observe(board,{childList:true})}}
 selectMerchant=async function(id,run){switching=true;document.body.dataset.appLoading='true';refreshHeader();try{return await rawSelect(id,run)}finally{switching=false;document.body.dataset.appLoading='false';refreshHeader()}};
 render=function(){
  if(building)return;building=true;const oldBusy=state.busy;const retained=detailNodes.get(route);detailNodes.clear();if(retained)detailNodes.set(route,retained);for(const key of parents.keys())if(key.startsWith('record/')&&key!==route)parents.delete(key);for(const id of ['merchant-select','new-shop-button']){const el=document.getElementById(id);if(el)switchParking.append(el)}store.replaceChildren();outlet.replaceChildren();featureNodes.clear();rawRender();collect();builderMain();building=false;
  if(lastMerchant!==state.merchant?.merchant_id){lastMerchant=state.merchant?.merchant_id;positions.clear();dayChoice=null;dirtyForms.clear()}
  if(state.busy&&!wasBusy&&!active)route='analysis';wasBusy=state.busy;apply(route,{push:false,replace:true,fromSurface:!!active});watchAgenda();
 };
 setView=function(view){if(building||routing){rawSet(view);return}if(active?.submitting)return;navigate(view)};
 function changed(e){const f=e.target.closest('form');if(f&&f.id!=='knowledge-search-form'&&!['app-function-search','app-agenda-history'].includes(e.target.id)){dirtyForms.add(f);if(active&&active.node.contains(f))active.dirty=true}}
 document.addEventListener('change',e=>{if(e.target.id==='app-agenda-history'){const original=document.querySelector('#agenda-history');if(original){original.value=e.target.value;original.dispatchEvent(new Event('change',{bubbles:true}));}}});
 document.addEventListener('input',changed);document.addEventListener('change',changed);
 document.addEventListener('submit',e=>{if(active&&active.node.contains(e.target)){active.submitting=true;const f=e.target;const obs=new MutationObserver(()=>{const error=f.querySelector('.form-error:not([hidden]),#ledger-error:not([hidden])');if(error?.textContent||!f.querySelector('[type=submit]:disabled')){if(active?.node.contains(f))active.submitting=false;obs.disconnect()}});obs.observe(f,{subtree:true,attributes:true,childList:true})}},true);
 window.addEventListener('beforeunload',e=>{if(isDirty()){e.preventDefault();e.returnValue=''}});
 window.addEventListener('popstate',()=>{const next=location.hash.slice(1)||'overview';if(isDirty()){rememberRoute(route,true);guardLeave(()=>navigate(next,{replace:true,unguarded:true}))}else{positions.set(route,window.scrollY);apply(next,{push:false});requestAnimationFrame(()=>window.scrollTo({top:positions.get(next)||0,behavior:'auto'}))}});
 window.addEventListener('hashchange',()=>{if(routing)return;const r=location.hash.slice(1)||'overview';if(r!==route)navigate(r,{replace:true})});
 document.addEventListener('click',async e=>{
  const jump=e.target.closest('[data-app-jump]');if(jump){document.getElementById(jump.dataset.appJump)?.scrollIntoView({block:'start',behavior:'smooth'});return}
  const link=e.target.closest('[data-app-route]'),cmd=e.target.closest('[data-app-action]'),day=e.target.closest('[data-app-day]'),group=e.target.closest('[data-app-group]');
  if(link){e.preventDefault();navigate(link.dataset.appRoute);return}
  if(day){dayChoice=day.dataset.appDay;if(route!=='feedback')navigate('feedback');else prepareAgenda();return}
  if(group){selectedGroup=group.dataset.appGroup;catalogueExpanded=false;renderServices();return}
  if(!cmd)return;const action=cmd.dataset.appAction;
  if(action==='catalogue-more'){catalogueExpanded=true;renderSearchResults();return}
  if(action==='continue-edit'){guard.hidden=true;pendingLeave=null;return}
  if(action==='discard-edit'){const fn=pendingLeave;pendingLeave=null;guard.hidden=true;dirtyForms.clear();if(active){active.dirty=false;active.submitting=false}fn?.();return}
  if(action==='social-due'){const r=globalThis.RebirthCommunity?.data()?.social?.reminders?.find(r=>r.date<=today());if(r){globalThis.RebirthSocial.focusNext(r.id);navigate('service/'+(r.kind==='support'?'support':'learning'))}return}if(action==='back'){back();return}if(action==='retry'){guardLeave(()=>location.reload());return}
  if(action==='help'){navigate('feature/usage');return}
  if(action==='large'){document.body.classList.toggle('comm-large');try{localStorage.setItem('rebirth_large_type',document.body.classList.contains('comm-large')?'on':'off')}catch{}outlet.replaceChildren();showFeature('usage');return}
  if(action==='clear-search'){search='';selectedGroup='全部';renderServices();document.querySelector('#app-function-search')?.focus();return}
  if(action==='analysis'){navigate('analysis');return}if(action==='actions'){navigate('feedback');return}
  if(action==='generate'){if(!state.merchant){openEditor(false);return}if(!validReport()){navigate('analysis');toast('先完成当前资料的核查，再生成日程');return}globalThis.RebirthAgenda.begin();return}
  if(action==='edit-shop'){openEditor(!!state.merchant);return}if(action==='new-shop'){openEditor(false);return}
  if(action==='example'){cmd.disabled=true;try{const l=await api('/api/acceptance-example');l.merchant_id='app_'+crypto.randomUUID().slice(0,8);await api('/api/ledgers',l);await reloadMerchants(l.merchant_id);navigate('ledger',{unguarded:true});toast('已新建练习示例，不计作真实商户')}catch(err){toast(err.message)}finally{cmd.disabled=false}}
 });
 document.addEventListener('input',updateFunctionSearch);
 document.addEventListener('compositionend',updateFunctionSearch);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&active){e.preventDefault();back()}});
 document.addEventListener('click',e=>{const commit=e.target.closest('[data-agenda-action="save"]');if(commit&&active){const owner=active.node;active.submitting=true;const watch=new MutationObserver(()=>{if(!commit.disabled){if(active?.node===owner)active.submitting=false;watch.disconnect()}});watch.observe(commit,{attributes:true,attributeFilter:['disabled']})}if(switching&&e.target.closest('button')){e.preventDefault();e.stopImmediatePropagation();toast('正在读取店铺资料，请稍候');return}const tab=e.target.closest('[data-comm="tab"]');if(tab&&active?.dirty){e.preventDefault();e.stopImmediatePropagation();guardLeave(()=>{active.dirty=false;globalThis.RebirthCommunity.open(tab.dataset.tab)});return}const close=e.target.closest('[data-close],[data-agenda-action="close"],[data-comm="close"]');if(close&&active?.dirty&&!active.submitting){e.preventDefault();e.stopImmediatePropagation();guardLeave(()=>{active.dirty=false;active.node.close()})}},true);
 globalThis.RebirthApp={taskFinished:()=>{if(route==='analysis')apply(route,{push:false});else refreshHeader()},preparePrint:()=>{printReturn=route},recordSaved:()=>navigate(route,{replace:true,unguarded:true}),communityPage,communityForm,printPage,contextChanged:()=>{if(!building){refreshToday();const social=document.querySelector('#app-social-actions');if(social)social.innerHTML=globalThis.RebirthSocial?.actionRemindersHtml()||'';if(route==='feature/agenda-summary'){outlet.replaceChildren();showFeature('agenda-summary')}}},navigate,catalog:()=>defs.map(d=>({id:d[0],name:d[1],group:d[2]}))};
 document.addEventListener('rebirth-ready',()=>{initialReady=true;render()});
 render();
})();
