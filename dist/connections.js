"use strict";

function modelChoices(p){
  const models=state.merchant.business_models||[];
  return '<div class="note-box"><strong>本方案关联的经营模式版本</strong>'+(models.length?models.map(m=>'<label class="checkbox-line"><input type="checkbox" name="model_ref" data-model="'+h(m.id)+'" data-version="'+(m.version||1)+'" '+(p.model_refs?.some(r=>r.id===m.id&&r.version===(m.version||1))?'checked':'')+'>'+h(m.name)+' v'+(m.version||1)+'</label>').join(''):'<p>尚未建立经营模式；可以先到店铺资料建模。旧记录不会被自动补上虚构关联。</p>')+'</div>';
}
function readModelChoices(form){return $$('[name=model_ref]',form).filter(e=>e.checked).map(e=>({id:e.dataset.model,version:Number(e.dataset.version)}));}
const countOptions=[['person_visits','到店/成交人次'],['unique_people','到店/成交去重人数']];
function periodScopeFields(p){return featureInput('经营期间范围代号','scope_id',p.scope_id||'shop_all','required maxlength="64"')+featureInput('经营期间范围说明','scope_description',p.scope_description||'全店同口径经营记录','required')+wbSelect('期间计数口径','count_basis',countOptions,p.count_basis||'person_visits');}

function designScopeFields(d){
  return '<div class="form-grid two">'+featureInput('本次经营范围代号','scope_id',d.scope_id,'required maxlength="64"')+featureText('范围具体包括什么','scope_description',d.scope_description,'required')+wbSelect('本次计数口径','count_basis',countOptions,d.count_basis)+featureInput('基准经营范围代号','base_scope_id',d.baseline.scope_id,'required maxlength="64"')+wbSelect('基准计数口径','base_count_basis',countOptions,d.baseline.count_basis)+'</div><label class="checkbox-line"><input name="scope_confirmed" type="checkbox" required>已核实基准和观察范围、计数口径相同；修改标签不能代替重新核对原始记录</label>';
}
const exitMetrics=[['trial_spend','试验累计投入（元）'],['closing_cash','实际可用现金（元）'],['revenue_per_day','日均销售额'],['contribution_per_day','日均贡献'],['conversion','成交比例（0到1）']];
function exitRow(r={}){
  return '<div class="knowledge-card exit-row" data-id="'+h(r.id||'exit_'+crypto.randomUUID().slice(0,8))+'"><div class="form-grid two">'+wbSelect('退出指标','exit_metric',exitMetrics,r.metric||'trial_spend')+wbSelect('触发方式','exit_op',[['gte','大于或等于'],['lte','小于或等于']],r.op||'gte')+featureInput('退出阈值（贡献允许负数）','exit_value',r.value,'type="number" step="0.01" required')+featureInput('退出条件说明','exit_description',r.description,'required maxlength="1000"')+'</div>'+wbButton('移除退出条件','remove-exit')+'</div>';
}
function exitFields(d){return '<h3>程序检查的退出条件</h3><p>预算和现金底线始终检查，不能由自定义规则放宽。经营指标条件达到最低样本后才检查；文字说明不被当作代码执行。</p><div id="exit-rows">'+(d.exit_rules||[]).map(exitRow).join('')+'</div>'+wbButton('添加结构化退出条件','add-exit');}
function readExits(form){return $$('.exit-row',form).map(r=>({id:r.dataset.id,metric:$('[name=exit_metric]',r).value,op:$('[name=exit_op]',r).value,value:$('[name=exit_value]',r).value.trim(),description:$('[name=exit_description]',r).value}));}
function measurementScopeFields(r,m){return '<div class="form-grid two">'+featureInput('观察经营范围代号','scope_id',m.scope_id||r.design.scope_id||'','required maxlength="64"')+wbSelect('观察计数口径','count_basis',countOptions,m.count_basis||r.design.count_basis||'person_visits')+'</div><p>范围或计数口径不匹配时程序拒绝比较。旧设计未声明口径时只保留观察，不自动认定改善。</p>';}

function renderConnections(w){
  const c=w.cohorts;
  appendSection('ledger',section('固定客群复购与未复购观察','<div class="panel"><p>'+h(c.notice)+'</p>'+wbTable(['固定客群/基准','观察窗','本窗复购/基准人数','复购比例','本窗未复购','操作'],c.windows.map(r=>'<tr><td>'+h(r.label)+'<br>'+h(r.cohort_id)+'：'+h(r.definition)+'</td><td>'+h(r.start)+' 至 '+h(r.end)+'（'+r.days+'天）</td><td>'+h(r.retained??'待核实')+' / '+r.base_size+'</td><td>'+h(r.retention??'待核实')+'</td><td>'+h(r.not_repeated??'待核实')+'</td><td>'+wbButton('更正客群观察','cohort','data-id="'+h(r.id)+'"')+'</td></tr>'))+c.findings.map(f=>'<p class="note-box amber">'+h(f.cohort_id)+'：'+h(f.statement)+(f.before?'（'+h(f.before)+' → '+h(f.after)+'）':'')+'</p>').join('')+'</div>',wbButton('记录固定客群观察','cohort')));
  const r=state.report;
  if(r?.result?.proposals)$$('.plan',$('#view-analysis')).forEach((el,i)=>{
    const p=r.result.proposals[i].proposal,models=r.ledger_snapshot.business_models||[];
    el.insertAdjacentHTML('beforeend','<p class="note-box">模式关联：'+((p.model_refs||[]).map(ref=>h(models.find(m=>m.id===ref.id)?.name||ref.id)+' v'+ref.version).join('、')||'旧记录未关联 / 尚未建模')+'</p>');
  });
  appendSection('analysis',section('经营模式 → 方案 → 试验 → 评价','<div class="panel"><p>按任务快照追踪明确模式版本。修改模式不会重写旧方案；旧未关联记录如实标记，不自动补造。</p>'+wbTable(['模式版本','方案/版本','试验与评价设计'],w.lineage.slice(0,30).map(l=>'<tr><td>'+(l.model_snapshots.map(m=>h(m.name)+' v'+m.version).join('<br>')||'旧记录未关联')+'</td><td>'+h(l.title)+' v'+l.proposal_version+'</td><td>'+l.trials.map(t=>h(({planned:'计划中',active:'开展中',paused:'暂停',stopped:'停止',completed:'已复盘'})[t.status])+'；冻结设计 '+t.design_ids.length+' 份').join('<br>')+'</td></tr>'))+'</div>'));
  const pending=state.extras.experiments.experiments.filter(t=>t.status==='planned'&&!w.research.some(x=>x.design.trial_id===t.id));
  appendSection('feedback',section('审阅由角色输出的实验草案','<div class="panel"><p>草案对应具体方案版本。先核对观察目标、预算与停止条件，可以修改，确认后才保存。</p>'+pending.map(t=>{const link=w.lineage.find(l=>l.run_id===t.run_id&&l.proposal_id===t.proposal_id&&l.proposal_version===t.proposal_version);return '<article class="knowledge-card"><strong>'+h(t.hypothesis)+'</strong>'+(link?.trials.find(x=>x.id===t.id)?.draft_ids?.map(id=>wbButton('审阅实验草案','agent-design','data-trial="'+h(t.id)+'" data-draft="'+h(id)+'"')).join('')||'<p>没有当前精确版本的有效草案，可使用人工设计。</p>')+'</article>';}).join('')+'</div>'));
  if(r?.result?.experiment_drafts?.length)appendSection('analysis',section('角色提交的实验草案','<div class="panel">'+r.result.experiment_drafts.map(d=>'<article class="knowledge-card"><strong>'+h(d.design.hypothesis)+'</strong><p>方案 '+h(d.proposal_id)+' v'+d.proposal_version+'；目标 '+h(d.design.target_value)+'；至少 '+d.design.min_days+' 天 / '+d.design.min_visits+' 计数。</p><p>'+h(d.target_basis)+'</p><p>先登记该方案的计划中试验，再到行动与复盘审阅草案。</p></article>').join('')+'</div>'));
}

function openCohort(id){
  const rows=state.merchant.customer_cohorts||[],r=rows.find(r=>r.id===id)||{id:'cw_'+crypto.randomUUID().slice(0,8)};
  openFeature('固定客群同口径观察（仅匿名汇总）','<p>固定同一批基准客户，不上传姓名、电话或个人ID。更改客群定义或基准人数须使用新的客群代号；观察窗不重叠。</p><div class="form-grid two">'+featureInput('固定客群代号','cohort_id',r.cohort_id,'required maxlength="64"')+featureInput('客群名称','label',r.label,'required')+featureText('固定客群定义','definition',r.definition,'required')+featureInput('基准去重客户人数','base_size',r.base_size,'type="number" min="1" step="1" required')+featureInput('基准开始日','baseline_start',r.baseline_start,'type="date" required')+featureInput('基准截止日','baseline_end',r.baseline_end,'type="date" required')+featureInput('本观察窗开始日','start',r.start,'type="date" required')+featureInput('本观察窗截止日','end',r.end,'type="date" required')+featureInput('该固定客群本窗复购去重人数（未知留空）','retained',r.retained,'type="number" min="0" step="1"')+featureText('计数来源与本次更正说明','source_note',r.source_note,'required')+'</div><label class="checkbox-line"><input type="checkbox" name="membership_confirmed" '+(r.membership_confirmed?'checked':'')+'>已核对是同一固定基准客群、相同分母，复购人数已去重</label><label class="checkbox-line"><input type="checkbox" name="observation_complete" '+(r.observation_complete?'checked':'')+'>本观察窗记录完整；未确认时保留未知，不认作零复购</label>',async form=>{const f=new FormData(form),data={...r,...Object.fromEntries(f),base_size:intText(f.get('base_size')),retained:String(f.get('retained')).trim()?intText(f.get('retained')):null,membership_confirmed:f.has('membership_confirmed'),observation_complete:f.has('observation_complete')};await api(merchantRoot()+'/cohorts',{cohorts:[...rows.filter(x=>x.id!==r.id),data],source_note:data.source_note});await wbRefresh('ledger');});
}

document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-wb]');if(!b||b.disabled||!['cohort','agent-design','add-exit','remove-exit'].includes(b.dataset.wb))return;
  if(state.busy){toast('请等待当前任务完成');return;}
  try{
    if(b.dataset.wb==='cohort')openCohort(b.dataset.id);
    else if(b.dataset.wb==='agent-design')await openDesign(b.dataset.trial,b.dataset.draft);
    else if(b.dataset.wb==='add-exit'){if($$('.exit-row').length>=6)throw new Error('最多6条结构化条件');$('#exit-rows').insertAdjacentHTML('beforeend',exitRow());}
    else b.closest('.exit-row').remove();
  }catch(err){toast(err.message);}
});

