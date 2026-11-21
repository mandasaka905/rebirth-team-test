"use strict";

function completionButton(text, action, extra="") { return '<button type="button" class="button secondary small" data-completion="'+action+'" '+extra+'>'+h(text)+'</button>'; }
function renderSupplyPlan(s) {
  if (!s?.lines?.length) return '';
  return '<div class="panel"><h3>补货与交付安排</h3><p>'+h(s.notice)+'</p>'+wbTable(['商品 / 数量','下单 / 到货','全额付款日 / 金额','退换条件'],s.lines.map(l=>'<tr><td>'+h(l.sku)+' / '+l.quantity+'</td><td>'+h(l.order_date)+'<br>'+h(l.arrival_date||'到货未知')+'</td><td>'+h(l.payment_date||'付款日未知')+'<br>¥'+yuan(l.cash_cost)+'</td><td>'+h(l.return_policy)+'<br>'+h(({not_allowed:'不可退换',unknown:'退换条件未知',outside_window:'试验交付已超过所录退换时限',within_window_needs_check:'处于所录时限内，仍须核验条件'})[l.return_review_status]||'条件待核对')+(l.return_deadline?'<br>时限至 '+h(l.return_deadline):'')+'</td></tr>'))+wbTable(['商品','现货','补货','交付日前可用','假设销售','交付后余量'],s.stock_path.map(r=>'<tr>'+[r.sku,r.opening,r.ordered,r.available_on_delivery,r.declared_sold,r.remaining_on_delivery].map(v=>'<td>'+h(v)+'</td>').join('')+'</tr>'))+'</div>';
}
function renderCompletion(w) {
  const offers=state.merchant.supply_options||[];
  appendSection('ledger',section('供应条件与补货约束','<div class="panel"><p>'+h(w.supply.notice)+'</p>'+wbTable(['商品 / 历史覆盖天数','供应方 / 起订 / 可供','到货 / 付款天数','核实 / 来源'],w.supply.products.flatMap(p=>p.offers.map(o=>'<tr><td>'+h(p.sku)+' / '+h(p.coverage_days_at_past_rate??'未知')+'</td><td>'+h(o.supplier)+' / '+h(o.min_qty??'未知')+' / '+h(o.capacity??'未知')+'</td><td>'+h(o.lead_days??'未知')+' / '+h(o.payment_days??'未知')+'</td><td>'+h(o.confirmed?'已核实':'待核实')+'<br>'+h(o.source_note)+completionButton('编辑供应条件','offer','data-id="'+h(o.id)+'"')+'</td></tr>')))+(offers.length?'':'<p>暂无供应条件。先核实起订量、到货和付款安排，未知不能填零。</p>')+'</div>',completionButton('添加供应条件','offer')+completionButton('导入库存 / 销售表格','operating-import')));
  appendSection('ledger',section('经营表格导入记录','<div class="panel"><p>库存按盘点快照替换；销售按确认完整的最近30天净销售件数更新。导入不会扣减盘点库存或自动改现金。</p>'+w.operating_imports.map(r=>'<p>'+h(r.data.kind==='sales'?'销售明细':'库存盘点')+'：'+r.data.rows.length+'行；'+h(r.data.source_note)+'</p>').join('')+'</div>'));
  const report=state.report, drafts=report?.result?.model_drafts||[],decisions=w.mode_decisions||[];
  if(report?.result?.model_comparison)appendSection('analysis',section('经营方式怎么改变',renderModelComparison(report.result.model_comparison)));
  appendSection('analysis',section('新商业模式草案与交叉审查','<div class="panel"><p>客户角色提出新模式，商品和现金角色核查依赖。草案不直接改底账；商户可以修改、接纳或否决。接纳后仍需重新核查具体行动。</p>'+drafts.map(d=>{
    const decision=decisions.find(r=>r.data.decision_key===report.run_id+':'+d.id+':'+d.version);
    const stale=report.ledger_changed||report.context_changed;
    return '<article class="knowledge-card"><strong>'+h(d.model.name)+'</strong> '+badge('草案 v'+d.version)+'<p>客户：'+h(d.model.customer_segment)+'；价值：'+h(d.model.value_proposition)+'<br>渠道：'+h(d.model.channel)+'；履约：'+h(d.model.fulfilment)+'</p><p>'+h(d.rationale)+'</p>'+d.assumptions.map(a=>'<p class="muted">待验证：'+h(a)+'</p>').join('')+d.reviews.map(r=>'<p><strong>'+h(roleLabel(r.from))+'</strong>：'+h(r.reason)+'</p>').join('')+(decision?'<p class="note-box">已'+h(decision.data.decision==='accept'?'保存为候选模式':'否决')+'；说明：'+h(decision.data.source_note)+'</p>':completionButton('审阅、修改或否决','mode-draft','data-id="'+h(d.id)+'" '+(stale?'disabled':'')))+(stale&&!decision?'<p>资料已变化，请重新分析。</p>':'')+'</article>';
  }).join('')+(drafts.length?'':'<p>先完成一次分析，再根据顾客线索和店铺条件整理草案，确认后才采用。</p>')+'</div>'));
  for (const p of report?.result?.proposals||[]) if(p.evaluation.procurement?.lines.length)appendSection('analysis',section(p.proposal.title+'：供应与资金依据',renderSupplyPlan(p.evaluation.procurement)));
  const refs=state.extras.knowledge.documents.filter(d=>d.kind==='primary_source_summary');
  appendSection('ledger',section('有来源的经营参考资料','<div class="panel">'+refs.map(d=>'<article class="knowledge-card"><strong>'+h(d.title)+'</strong><p>'+h(d.content)+'</p><p class="muted">适用范围：'+h(d.scope)+'；核对日：'+h(d.checked_on)+'</p><a href="'+h(d.url)+'" target="_blank" rel="noopener noreferrer">查看原始来源</a></article>').join('')+'</div>'));
}

function openSupplyOffer(id) {
  const rows=state.merchant.supply_options||[],o=rows.find(o=>o.id===id)||{id:'offer_'+crypto.randomUUID().slice(0,8),checked_on:state.merchant.as_of};
  if(!state.merchant.products.length)throw new Error('先登记商品，再添加供应条件');
  const nums={lead_days:'下单到到货天数',payment_days:'下单到全额付款天数',min_qty:'起订件数',capacity:'本次最多可供件数',unit_cost:'采购单价（元）',shipping_cost:'每笔下单运费（元）',return_days:'可退换天数'};
  openFeature('核实供应条件','<p>未知留空，不默认零。不同款式、颜色和尺码可分别建立SKU。这里只记录条件，不下单。</p>'+wbSelect('商品SKU','sku',state.merchant.products.map(p=>[p.sku,p.name+' / '+p.sku]),o.sku)+featureInput('供应方代号','supplier',o.supplier,'required')+'<div class="form-grid two">'+Object.entries(nums).map(([k,t])=>featureInput(t,k,o[k],'type="number" min="0" step="'+(['unit_cost','shipping_cost'].includes(k)?'0.01':'1')+'"')).join('')+'</div>'+wbSelect('供应商是否接受退换','returnable',[['','未知'],['true','已核实可退换'],['false','不可退换']],o.returnable==null?'':String(o.returnable))+featureText('退换条件、运费或扣费（不承诺退款）','return_policy',o.return_policy,'required')+featureInput('条件核对日','checked_on',o.checked_on,'type="date" required')+featureText('报价、合同或商户核实来源','source_note',o.source_note,'required')+'<label class="checkbox-line"><input type="checkbox" name="confirmed" '+(o.confirmed?'checked':'')+'>以上供货与费用条件已实际核实</label>',async form=>{
    const f=new FormData(form),value={...o,...Object.fromEntries(f),confirmed:f.has('confirmed'),returnable:f.get('returnable')===''?null:f.get('returnable')==='true'};
    for(const k of Object.keys(nums))value[k]=String(f.get(k)).trim()?(['unit_cost','shipping_cost'].includes(k)?moneyText(f.get(k)):intText(f.get(k))):null;
    await api(merchantRoot()+'/supply-options',{offers:[...rows.filter(r=>r.id!==o.id),value],source_note:value.source_note});await wbRefresh('ledger');
  });
}

function procurementRow(o={}) {
  return '<tr class="procurement-row"><td><select class="field" name="offer_id" aria-label="供应条件">'+(state.merchant.supply_options||[]).map(x=>'<option value="'+h(x.id)+'" '+(o.offer_id===x.id?'selected':'')+'>'+h(x.sku+' / '+x.supplier)+'</option>').join('')+'</select></td><td><input class="field" name="quantity" type="number" min="1" step="1" required value="'+h(o.quantity??'')+'" aria-label="补货数量"></td><td><input class="field" name="order_date" type="date" required value="'+h(o.order_date||state.merchant.as_of)+'" aria-label="下单日"></td><td><input class="field" name="shipping_batches" type="number" min="1" step="1" value="'+h(o.shipping_batches??1)+'" required aria-label="运费计费批次"></td><td>'+completionButton('移除','remove-order')+'</td></tr>';
}
function procurementFields(p) {
  return '<div class="panel"><h3>本方案拟补货（可不补货）</h3><p>到货和全额付款日由已录供应条件推导；采购款另计，不要重复填进固定支出。合并方案保留原运费计费批次，不擅自假设合单优惠。交付日须有足够可售商品。</p><div class="table-wrap"><table><thead><tr><th>供应条件</th><th>件数</th><th>下单日</th><th>运费批次</th><th></th></tr></thead><tbody id="procurement-rows">'+(p.procurements||[]).map(procurementRow).join('')+'</tbody></table></div>'+completionButton('添加拟补货','add-order',(state.merchant.supply_options||[]).length?'':'disabled')+'</div>';
}
function readProcurements(form) {return $$('.procurement-row',form).map(row=>({offer_id:$('[name=offer_id]',row).value,quantity:intText($('[name=quantity]',row).value),order_date:$('[name=order_date]',row).value,shipping_batches:intText($('[name=shipping_batches]',row).value)}));}

async function openOperatingImport() {
  const format=await api('/api/operating-templates');const templates=format.chinese_templates||format.templates;
  openFeature('预览并导入库存或销售表格','<p>先下载中文模板填写，或按相同列名整理自家表格。Excel请另存为CSV UTF-8。未知金额留空；尺码齐全填“是”“否”或留空。每行来源相同时，可只填写下方整批来源。</p>'+wbSelect('导入类型','kind',[['inventory','库存盘点快照'],['sales','匿名销售明细']],'inventory')+'<label class="form-label">选择本地CSV<input class="field" id="operating-file" type="file" accept=".csv,text/csv"></label>'+completionButton('下载中文空模板','download-operating-template')+completionButton('在页面填写模板','import-template')+'<details><summary>查看或粘贴表格内容</summary>'+featureText('表格内容','csv',templates.inventory,'required maxlength="500000" rows="8"')+'</details>'+featureText('本批来源与核对说明','source_note','','required')+'<label class="checkbox-line"><input type="checkbox" name="replace_existing">库存：明确同意替换表中已有SKU的盘点快照（不累加库存）</label><label class="checkbox-line"><input type="checkbox" name="confirm_sales_window">销售：本表及既有明细覆盖所列SKU最近30天完整净销售，已处理退货与重复原单号</label>'+completionButton('预览整批变更','preview-operating')+'<div id="operating-preview"></div><label class="checkbox-line"><input type="checkbox" name="confirmed" required>已核对预览中的逐项变化，确认保存</label>',async form=>{
    if(!form.dataset.digest)throw new Error('请先上传表格并点击预览，再确认保存');const raw=operatingRequest(form);raw.preview_digest=form.dataset.digest;raw.confirmed=new FormData(form).has('confirmed');await api(merchantRoot()+'/operating-import',raw);await wbRefresh('ledger');
  },'保存已预览批次');
  $('#feature-form').dataset.templates=JSON.stringify(templates);delete $('#feature-form').dataset.digest;
}
function renderOperatingChanges(r) {
  return '<p>'+h(r.notice)+'<br>校验通过 '+r.rows.length+' 行；尚未保存。</p>'+wbTable(['商品','库存变化','近30天销量变化','采购单价 / 售价'],r.changes.map(c=>{
    const a=c.after,b=c.before;return '<tr><td>'+h(a?a.name+' / '+c.sku:c.sku)+'</td><td>'+h(a?(b?b.stock:'新增')+' → '+a.stock:'保持盘点库存')+'</td><td>'+h(a?(b?b.sales_30d:'新增')+' → '+a.sales_30d:c.sales_30d_before+' → '+c.sales_30d_after)+'</td><td>'+(a?'¥'+yuan(a.unit_cost)+' / ¥'+yuan(a.unit_price):'不改商品价格或成本')+'</td></tr>';
  }));
}
function operatingRequest(form) {const f=new FormData(form);return {kind:f.get('kind'),csv:f.get('csv'),source_note:f.get('source_note'),replace_existing:f.has('replace_existing'),confirm_sales_window:f.has('confirm_sales_window')};}

const modeTextLabels={name:'候选模式名称',customer_segment:'服务哪类客户',customer_problem:'客户问题',value_proposition:'提供什么价值',channel:'获客渠道',fulfilment:'交付与售后安排',revenue_method:'收入方式',key_resources:'所需资源',required_skills:'所需能力（每行一项）',available_skills:'已有能力（每行一项）',demand_evidence:'实际需求证据与未知项',source_note:'模式来源'};
function modeModelFields(m) {
  return Object.entries(modeTextLabels).map(([k,t])=>featureText(t,'mode_'+k,m[k],'required')).join('')+'<div class="form-grid two">'+Object.entries({period_days:'测算天数',unit_revenue:'每单收入（元）',unit_cost:'每单成本（元）',fixed_cost:'期间固定费用（元）',investment:'初始投入（元）',assumed_orders:'假设订单数',weekly_hours:'每周工时'}).map(([k,t])=>featureInput(t,'mode_'+k,m[k],'type="number" min="0" step="'+(['period_days','assumed_orders','weekly_hours'].includes(k)?'1':'0.01')+'" '+(['period_days','weekly_hours'].includes(k)?'required':''))).join('')+'</div>'+unitCostFields(m,'mode_')+'<label class="checkbox-line"><input name="mode_costs_confirmed" type="checkbox" '+(m.costs_confirmed?'checked':'')+'>模式费用已核实（未知金额留空）</label>';
}
function modeRequirementRow(r={}) { return '<div class="mode-requirement form-grid two">'+wbSelect('所需商品','sku',state.merchant.products.map(p=>[p.sku,p.name]),r.sku)+featureInput('所需件数','quantity',r.quantity,'type="number" min="1" step="1" required')+wbSelect('补货依赖（无则留空）','offer_id',[['','无补货依赖'],...(state.merchant.supply_options||[]).map(o=>[o.id,o.sku+' / '+o.supplier])],r.offer_id||'')+completionButton('移除商品依赖','remove-requirement')+'</div>'; }
function readMode(form,d) {
  const f=new FormData(form);if(f.get("decision")==="reject")return {run_id:state.report.run_id,draft_id:d.id,version:d.version,decision:"reject",source_note:f.get("source_note"),confirmed:f.has("confirmed")};const m={...d.model};for(const k of Object.keys(modeTextLabels))m[k]=String(f.get('mode_'+k));
  for(const k of ['period_days','weekly_hours'])m[k]=intText(f.get('mode_'+k));
  for(const k of ['unit_revenue','unit_cost','fixed_cost','investment'])m[k]=moneyText(f.get('mode_'+k),true);
  m.assumed_orders=String(f.get('mode_assumed_orders')).trim()?intText(f.get('mode_assumed_orders')):null;m.costs_confirmed=f.has('mode_costs_confirmed');readUnitCosts(f,m,'mode_');
  return {run_id:state.report.run_id,draft_id:d.id,version:d.version,decision:f.get('decision'),confirmed:f.has('confirmed'),source_note:f.get('source_note'),model:m,
          supply_requirements:$$('.mode-requirement',form).map(row=>({sku:$('[name=sku]',row).value,quantity:intText($('[name=quantity]',row).value),offer_id:$('[name=offer_id]',row).value}))};
}
function openModeDraft(id) {
  const d=state.report.result.model_drafts.find(d=>d.id===id);if(!d)throw new Error('草案不存在');
  openFeature('审阅并决定新经营模式','<p>可以否决，也可以修改后只保存为候选。接纳不等于已经验证可行；旧草案和审查意见会保留。</p>'+wbSelect('处理决定','decision',[['accept','修改并接纳为候选'],['reject','否决本草案']],'accept')+modeModelFields(d.model)+'<h3>商品与供应依赖</h3><div id="mode-requirements">'+d.supply_requirements.map(modeRequirementRow).join('')+'</div>'+completionButton('添加商品依赖','add-requirement')+featureText('审阅、修改或否决说明','source_note','','required')+completionButton('重新检查修改后的模式','preview-mode')+'<div id="mode-preview"></div><label class="checkbox-line"><input name="confirmed" type="checkbox" required>我已查看三方审查、未知项和修改内容，自主确认本次决定</label>',async form=>{await api(merchantRoot()+'/mode-decision',readMode(form,d));await wbRefresh('analysis');toast('决定已留痕；接纳的候选模式可在店铺资料中查看，重新分析后进入行动方案');},'保存商户决定');
  $('#feature-form').dataset.modeDraft=id;
}

function procurementFeedbackFields(form) {
  if(!state.feedbackPlan?.procurements?.length)return;
  const previous=state.feedbackMeta?state.extras.journal.entries.find(e=>e.data.id===state.feedbackMeta.prior.feedback_id)?.data:null;
  $('.form-body',form).insertAdjacentHTML('beforeend','<div class="note-box">补货现金与期间费用分开。下面的实际商品成本是已售/损坏商品成本并考虑可再次销售退货；未知留空，不用计划成本冒充实际。</div>'+featureInput('累计实际采购及进货运费实付（元，不含在固定支出内）','procurement_paid',previous?.procurement_paid,'type="number" min="0" step="0.01" required')+featureInput('上述实付中运费等期间费用（元，不重复填固定支出）','procurement_expense',previous?.procurement_expense,'type="number" min="0" step="0.01" required'));
  $$('.feedback-item',form).forEach(row=>row.insertAdjacentHTML('beforeend',featureInput('实际已售及损坏商品成本（元，扣除可售退回，未知留空）','actual_goods_cost',previous?.items.find(i=>i.sku===row.dataset.sku)?.actual_goods_cost,'type="number" min="0" step="0.01"')));
}

document.addEventListener('change',async event=>{if(event.target.id==='operating-file'&&event.target.files[0]){try{const file=event.target.files[0];if(file.size>600000)throw new Error('文件过大，每批最多500行');$('#feature-form [name=csv]').value=await file.text();delete $('#feature-form').dataset.digest;$('#feature-form [name=confirmed]').checked=false;$('#operating-preview').textContent='文件已更改，请重新预览。';}catch(e){toast(e.message);}}});
document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-completion]');if(!b||b.disabled)return;if(state.busy){toast('请等待当前任务完成');return;}
  const action=b.dataset.completion;
  try{
    if(action==='offer')openSupplyOffer(b.dataset.id);
    else if(action==='operating-import')await openOperatingImport();
    else if(action==='download-operating-template'){const form=$('#feature-form'),kind=$('[name=kind]',form).value,text=JSON.parse(form.dataset.templates)[kind];const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=(kind==='inventory'?'库存表格模板':'销售表格模板')+'.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    else if(action==='import-template'){const form=$('#feature-form');$('[name=csv]',form).value=JSON.parse(form.dataset.templates)[$('[name=kind]',form).value];delete form.dataset.digest;$('#operating-preview').textContent='';}
    else if(action==='preview-operating'){const form=$('#feature-form'),r=await api(merchantRoot()+'/operating-preview',operatingRequest(form));form.dataset.digest=r.preview_digest;$('[name=confirmed]',form).checked=false;$('#operating-preview').innerHTML=renderOperatingChanges(r);}
    else if(action==='add-order')$('#procurement-rows').insertAdjacentHTML('beforeend',procurementRow());
    else if(action==='remove-order')b.closest('.procurement-row').remove();
    else if(action==='mode-draft')openModeDraft(b.dataset.id);
    else if(action==='add-requirement')$('#mode-requirements').insertAdjacentHTML('beforeend',modeRequirementRow());
    else if(action==='remove-requirement')b.closest('.mode-requirement').remove();
    else if(action==='preview-mode'){const form=$('#feature-form'),d=state.report.result.model_drafts.find(d=>d.id===form.dataset.modeDraft),r=await api(merchantRoot()+'/mode-preview',readMode(form,d));$('#mode-preview').innerHTML='<p>尚未保存。'+h(r.assessment?.warnings.join('；')||'本次选择否决')+'</p>';}
  }catch(e){toast(e.message);}
});

function invalidateOperating(event) {
  const form=event.target.closest('#feature-form');
  if(!form||!$('#operating-preview',form)||!['kind','csv','source_note','replace_existing','confirm_sales_window'].includes(event.target.name))return;
  delete form.dataset.digest;$('[name=confirmed]',form).checked=false;$('#operating-preview',form).textContent='内容已变化，请重新预览后确认。';
}
document.addEventListener('input',invalidateOperating);
document.addEventListener('change',event=>{
  invalidateOperating(event);
  if(event.target.name==='decision'&&$('#feature-form').dataset.modeDraft){
    const reject=event.target.value==='reject';for(const e of $$('#feature-form [name^=mode_],#mode-requirements input,#mode-requirements select'))e.disabled=reject;
  }
});
