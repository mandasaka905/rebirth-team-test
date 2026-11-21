"use strict";

const executionNames = {rules:"内置规则核查",simulation:"离线协议演练（非AI）",manual:"人工方案与本地复核",agentarts:"华为 AgentArts 多智能体分析"};
const phaseNames = {investigate:"独立调查",propose:"提交候选",review:"交叉审查",coordinate:"协调异议",revise:"修订复核"};
const toolNames = {business_model_compare:"经营方式对照",supply_analyze:"供货条件核查",model_draft_evaluate:"新模式三方约束核对",customer_retention:"固定客群复购核对",business_model_assess:"经营模式测算",accounts_reconcile:"账簿核对",inventory_analyze:"库存核查",cash_baseline:"现金基线",customer_evidence:"客户记录",proposal_evaluate:"方案计算",data_readiness:"资料追问",feedback_history:"历史反馈",business_diagnostics:"经营期间比较",knowledge_search:"经营资料检索",investigation_history:"原因调查卡"};
function executionName(mode) { return executionNames[mode] || mode; }
function unitCostFields(m,prefix='') {
  const rows=m.unit_cost_components||['商品','包装','平台费用','配送','其他'].map((label,i)=>({id:'cost_'+i,label,amount:null,basis:'',basis_kind:'assumption'}));
  return `<details><summary>逐项填写每单成本（可选）</summary><p>启用后，每项填写金额和依据。不知道的金额留空，总成本也须留空；确认没有这项费用时填0并说明依据。</p><label><input type="checkbox" name="${prefix}uc_enabled" ${m.unit_cost_components?'checked':''}>使用下面的成本明细</label><input type="hidden" name="${prefix}uc_count" value="${rows.length}">${rows.map((r,i)=>`<div class="form-grid two"><input type="hidden" name="${prefix}uc_id_${i}" value="${h(r.id)}">${featureInput('费用名称',prefix+'uc_label_'+i,r.label)}${featureInput('每单金额（元，未知留空）',prefix+'uc_amount_'+i,r.amount??'','type="number" min="0" step="0.01"')}${featureText('金额依据或待核实原因',prefix+'uc_basis_'+i,r.basis)}<label>依据类型<select name="${prefix}uc_kind_${i}" class="field"><option value="assumption" ${r.basis_kind==='assumption'?'selected':''}>待核实假设</option><option value="merchant_record" ${r.basis_kind==='merchant_record'?'selected':''}>商户记录，仍须核对</option></select></label></div>`).join('')}</details>`;
}
function readUnitCosts(f,m,prefix='') {
  for(const k of Object.keys(m))if(k.startsWith(prefix+'uc_'))delete m[k];
  if(!f.has(prefix+'uc_enabled')){delete m.unit_cost_components;return;}
  const count=intText(f.get(prefix+'uc_count'));if(count<1||count>12)throw new Error('每单成本分项数量不正确');
  m.unit_cost_components=Array.from({length:count},(_,i)=>({id:String(f.get(prefix+'uc_id_'+i)),label:String(f.get(prefix+'uc_label_'+i)),amount:moneyText(f.get(prefix+'uc_amount_'+i),true),basis:String(f.get(prefix+'uc_basis_'+i)),basis_kind:String(f.get(prefix+'uc_kind_'+i))}));
}
function renderModelComparison(value) {
  if(!value?.rows?.length)return `<div class="panel"><p>${h(value?.notice||'尚无可比较的经营模式')}</p></div>`;
  const names={customer_segment:'客群',customer_problem:'客户问题',value_proposition:'服务价值',channel:'获客渠道',fulfilment:'交付方式',revenue_method:'收入方式',key_resources:'所需资源',required_skills:'所需能力'};
  const money=x=>x===null||x===undefined?'待核实':'¥'+h(x);
  return `<div class="panel"><p>${h(value.scope)}</p><p>${h(value.notice)}</p>${!value.same_period?'<p class="note-box amber">测算期间不同，不能直接按总贡献排名。</p>':''}<div class="table-wrap"><table><thead><tr><th>经营方式</th><th>渠道与交付</th><th>每单收入／成本／贡献</th><th>期间与保本订单</th><th>零订单／半量／申报量贡献</th></tr></thead><tbody>${value.rows.map(r=>`<tr><td>${h(r.model.name)}<br>${r.kind==='baseline'?'现行模式':'候选 v'+h(r.draft_version)}</td><td>${h(r.model.channel)}<br>${h(r.model.fulfilment)}<br>${h(r.model.revenue_method)}</td><td>${money(r.model.unit_revenue)} ／ ${money(r.model.unit_cost)} ／ ${money(r.assessment.unit_contribution)}</td><td>${h(r.model.period_days)}天<br>${r.assessment.break_even_orders===null?'待核实或单位贡献不足':h(r.assessment.break_even_orders)+'单'}</td><td>${r.scenarios.map(s=>money(s.period_contribution)).join(' ／ ')}</td></tr>`).join('')}</tbody></table></div>${value.rows.filter(r=>r.kind==='candidate').map(r=>`<details class="knowledge-card"><summary>${h(r.model.name)}：改变了什么，仍缺什么</summary>${r.structural_field_changes.map(c=>`<p>${h(names[c.field]||c.field)}：${h(c.before)} → ${h(c.after)}</p>`).join('')||'<p>结构字段没有变化。</p>'}<p>${h(r.structural_change_notice)}</p>${(r.model.unit_cost_components||[]).map(c=>`<p>每单${h(c.label)}：${money(c.amount)}；依据：${h(c.basis)}（${c.basis_kind==='assumption'?'假设':'商户记录，仍需核对'}）</p>`).join('')}${[...(r.blockers||[]),...(r.warnings||[])].map(t=>`<p class="note-box amber">${h(t)}</p>`).join('')}<p>先验证：${h(r.validation_plan)}</p></details>`).join('')}</div>`;
}
function renderKnowledgeClaims(report) {
  const events=report.events||[],cards=[];
  for(const event of events.filter(e=>e.kind==='agent_result'))for(const c of event.data.result.assessment?.knowledge_citations||[]){
    const source=events.find(e=>e.id===c.evidence_id&&e.kind==='tool_result'&&e.actor===event.actor&&e.data.phase===event.data.phase&&e.data.tool==='knowledge_search');
    const doc=source?.data.value.matches.find(d=>d.id===c.document_id);
    if(!doc||!doc.content.includes(c.supporting_text))continue;
    cards.push(`<article><strong>${h(c.claim)}</strong><blockquote>${h(c.supporting_text)}</blockquote><p>使用边界：${h(c.scope_limit)}</p><small>${h(roleLabel(event.actor))} · ${h(c.evidence_id)}</small><details><summary>核对引用资料</summary>${renderKnowledgeCard(doc)}</details></article>`);
  }
  return cards.length?`<details class="collab-proof"><summary>哪些判断引用了经营资料 · ${cards.length}项</summary><p>请人工核对参考原文与适用条件，再决定是否适合本店。</p>${cards.join('')}</details>`:'';
}
function merchantText(value) { return globalThis.RebirthCore?.merchantText(value)??String(value??''); }
function renderActionBasis(t) {
  const b=t.basis;if(!b)return '';
  return `<details class="task-stop"><summary>为什么安排这件事</summary>${b.reasons.map(r=>`<p>${h(merchantText(r))}</p>`).join('')}${b.proposal_id?`<p>对应方案：${h(b.proposal_id)} · 第${h(b.proposal_version)}版</p>`:''}<p>${h(b.notice)}</p>${b.evidence_ids.length?`<small>工具记录：${h(b.evidence_ids.join('、'))}</small>`:''}${b.coordination_ref?`<p>来自本次协调中交给店主核实的事项；完成条件见下方。</p>`:''}</details>`;
}
function renderKnowledgeCard(doc) {
  let original='';
  try { const url=new URL(doc.url);if(url.protocol==='https:'&&!url.username&&!url.password)original=`<a href="${h(url.href)}" target="_blank" rel="noopener noreferrer">查看参考原文 ↗</a>`; } catch (_) {}
  return `<article class="knowledge-card"><strong>${h(doc.title)}</strong><small>引用 ${h(doc.id)} · ${h(doc.source)}</small><p>${h(doc.content)}</p>${doc.scope?`<p>适用范围：${h(doc.scope)}</p>`:''}${doc.checked_on?`<small>资料核对日：${h(doc.checked_on)}（不表示内容持续有效）</small>`:''}${original?`<p>${original}</p>`:''}</article>`;
}
function renderExpenseBreakdown(p) {
  if(!p.expense_breakdown?.length)return '';
  return `<div class="panel"><h4>这笔固定费用花在哪里</h4><p>仅分解前期及其他固定支出，不另行重复扣款。填写依据不等于报价已经核实。</p><div class="table-wrap"><table><thead><tr><th>具体动作</th><th>数量 × 单价</th><th>小计</th><th>依据</th></tr></thead><tbody>${p.expense_breakdown.map(x=>`<tr><td>${h(x.label)}</td><td>${h(x.quantity)} × ¥${h(x.unit_cost)}</td><td>¥${h(x.amount)}</td><td>${h(x.basis)}<br>${x.basis_kind==='assumption'?'待验证假设':'商户填写的记录，仍须核对'}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function featureButton(text, action, extra="") { return `<button type="button" class="button secondary small" data-feature="${action}" ${extra}>${h(text)}</button>`; }
function featureInput(text,name,value="",attrs="") { return `<label class="form-label">${h(text)}<input class="field" name="${name}" value="${h(value)}" ${attrs}></label>`; }
function featureText(text,name,value="",attrs="") { return `<label class="form-label">${h(text)}<textarea class="field" name="${name}" ${attrs}>${h(value)}</textarea></label>`; }
function merchantRoot() { return '/api/merchants/'+encodeURIComponent(state.merchant.merchant_id); }
function appendSection(view,html) { $("#view-"+view).insertAdjacentHTML("beforeend",html); }
function section(title,body,actions="") { return `<div class="section-head"><h2>${h(title)}</h2><div class="inline-flex">${actions}</div></div>${body}`; }

async function loadExtras(id) {
  const root='/api/merchants/'+encodeURIComponent(id);
  const [diagnostics,knowledge,journal,experiments,preflight,strategies,investigations,workbench] = await Promise.all([api(root+'/diagnostics'),api(root+'/knowledge'),api(root+'/feedback-journal'),api(root+'/experiments'),api('/api/preflight'),api('/api/strategies'),api(root+'/investigations'),api(root+'/workbench')]);
  state.extras={diagnostics,knowledge,journal,experiments,preflight,strategies,investigations,workbench};
}

function renderExtras() {
  appendSection('overview',section('资料备份与恢复',`<div class="panel"><p>可以导出店铺记录，或导入一份资料副本。</p><div class="feature-actions">${featureButton('新建示例店铺','acceptance')}${wbButton('体验示例店铺','example')}${featureButton('粘贴资料导入副本','import-copy')}${state.merchant?featureButton('导出本店完整记录','export'):''}${featureButton('恢复任务观察','recover-job')}</div></div>`));
  if (!state.merchant || !state.extras) return;
  const x=state.extras,d=x.diagnostics;
  appendSection('ledger',section('可能原因与补证调查',`<div class="panel"><p>把账面异常转成待查假设，分别记录支持、反例和下一项核对。状态“有支持”不代表已证明因果，不能代替实地调查。</p>${x.investigations.cards.map(c=>`<article class="knowledge-card">${badge(roleLabel(c.owner))} <strong>${h(c.hypothesis)}</strong><p>状态：${h({unverified:'待验证',supported:'有支持证据，未证明因果',conflicted:'发现反例',undetermined:'证据不足'}[c.status])} · 核对日 ${h(c.checked_on)}</p><p>支持：${h(c.supporting||'暂无')}<br>反例：${h(c.counter||'暂无')}<br>下一步：${h(c.next_check)}<br>来源：${h(c.source_note)}</p>${featureButton('更新调查记录','investigation',`data-id="${h(c.id)}"`)}</article>`).join('')||'<p>尚未建立原因假设。下方经营期间比较只指出变化，不自动替你断言原因。</p>'}</div>`,featureButton('建立待查假设','investigation')));
  const periodRows=d.periods.map(p=>`<tr><td>${h(p.start)}<br>${h(p.end)}</td><td>${p.days}天</td><td>${h(p.scope_id||"shop_all")}<br>${h(p.count_basis==="unique_people"?"去重人数":"人次")}</td><td>${p.revenue===null||p.revenue===undefined?'待核实':'¥ '+yuan(p.revenue)}</td><td>${p.contribution===null?'待核实':'¥ '+yuan(p.contribution)}</td><td>${p.visits??'待核实'}</td><td>${p.buyers??'待核实'}</td><td>${p.returning_buyers??'待核实'}</td><td>${featureButton('更正本期','period',`data-id="${h(p.id)}"`)}</td></tr>`).join('');
  appendSection('ledger',section('分期经营记录与调查线索',`<div class="panel"><p>${h(d.note)}</p>${d.needs_two_periods?'<div class="note-box amber">至少录入两个不重叠期间，才能进行前后比较。缺失字段保留待核实，不补零。</div>':''}<div class="table-wrap"><table><thead><tr><th>期间</th><th>天数</th><th>范围/计数口径</th><th>营业额</th><th>经营贡献</th><th>到店计数</th><th>成交计数</th><th>老客成交计数</th><th>操作</th></tr></thead><tbody>${periodRows||'<tr><td colspan="9">尚未录入经营期间</td></tr>'}</tbody></table></div>${d.findings.map(f=>`<div class="diagnostic-line">${badge(roleLabel(f.owner),'amber')} <strong>${h(f.title)}</strong><p>${h(f.before)} → ${h(f.after)}；待查：${h(f.question)}</p></div>`).join('')}<p class="muted">更正期间会使旧分析过期；旧任务快照和来源记录保留。</p></div>`,featureButton('添加经营期间','period')));
  appendSection('ledger',section('经营知识与证据资料',`<div class="panel"><p>查看经营核查指南，或添加本店已获授权的文字资料。每份资料保留来源与适用范围；指南供核对参考，不是官方政策。</p><form id="knowledge-search-form" class="search-row"><input class="field" name="query" required maxlength="200" aria-label="检索本地资料" placeholder="例如：现金 预算、预约 需求、退货"><button class="button secondary" type="submit">检索资料</button></form><div id="knowledge-results"></div><details><summary>已收录 ${x.knowledge.documents.length} 份资料</summary>${x.knowledge.documents.map(renderKnowledgeCard).join('')}</details></div>`,featureButton('添加文字资料','knowledge')));
  if(state.report && !state.busy) {
    const r=state.report,mode=executionName(r.mode);
    const history=$('#report-select');if(history)[...history.options].forEach(option=>{const run=state.runs.find(x=>x.id===option.value);if(run)option.textContent=new Date(run.created_at).toLocaleString('zh-CN')+' · '+executionName(run.mode)+(['failed','cancelled'].includes(run.status)?'（未完成）':'');});
    $$('.agent-card header small',$('#view-analysis')).forEach(el=>el.textContent=mode);
    const banner=$('.result-banner>span',$('#view-analysis')); if(banner)banner.textContent=mode+' · 底账日期 '+r.ledger_as_of;
    const coord=$('.agent-card:last-child .note-box',$('#view-analysis')); if(coord)coord.textContent=r.mode==='agentarts'?'本次分析已完成；请核实资料与方案，不会自动执行。':mode+'，请按已填资料核对，再决定是否行动。';
    $$('.plan',$('#view-analysis')).forEach((el,i)=>{
      const p=r.result.proposals[i];
      el.insertAdjacentHTML('beforeend',`<div class="feature-actions">${featureButton('编辑并重算','plan',`data-index="${i}" ${r.ledger_changed||r.context_changed?'disabled':''}`)}${featureButton('登记试验计划','trial',`data-index="${i}" ${r.ledger_changed||r.context_changed?'disabled':''}`)}</div>${p.objections?.length?`<div class="note-box amber"><strong>尚未解决的异议</strong>${p.objections.map(o=>`<p>${h(roleLabel(o.from))}：${h(o.reason)}；要求：${h(o.request)}</p>`).join('')}</div>`:''}`);
    });
    if(r.result?.comparison) appendSection('analysis',renderComparison(r.result.comparison));
    appendSection('analysis',section('候选经营路径与人工建模',`<div class="panel"><p>这些是可供核查的路径，不是系统推荐或收益预测。可选择一条路径，填写自己的商品、预算与明确的销量假设后重算。</p><div class="strategy-grid">${x.strategies.strategies.map(s=>`<article><strong>${h(s.title)}</strong><p>前提：${h(s.requirements)}</p><p class="muted">风险：${h(s.risk)}</p>${featureButton('填写此路径的假设','new-plan',`data-strategy="${h(s.id)}" ${r.ledger_changed||r.context_changed||['failed','cancelled','running','interrupted'].includes(r.result?.status)?'disabled':''}`)}</article>`).join('')}</div></div>`));
    appendSection('analysis',renderAudit(r));
  }
  appendSection('feedback',section('试验登记与退出条件',`<div class="panel"><p>这里只记录你的计划和人工状态，不会下单、联系顾客、采购或转账。同一店铺只允许一项开展中的试验，避免叠加预算。</p>${x.experiments.experiments.map(e=>`<article class="trial-card"><strong>${h(e.hypothesis)}</strong> ${badge(({planned:'计划中',active:'开展中',paused:'暂停',stopped:'停止',completed:'已复盘'})[e.status])}<p>指标与目标：${h(e.success_metric)}；截止 ${h(e.end_date)}；停止预算 ¥${yuan(e.stop_budget)}</p><p>资料来源：${h(e.source_note)}</p>${e.review_alerts.map(a=>`<div class="note-box amber">${h(a)}</div>`).join('')}${featureButton('记录状态或复盘','edit-trial',`data-id="${h(e.id)}"`)}</article>`).join('')||'<p>还没有登记试验，可在具体方案下点击“登记试验计划”。</p>'}</div>`));
  appendSection('feedback',renderFeedbackJournal());
  renderWorkbench();
  const searchForm=$('#knowledge-search-form');
  if(searchForm)searchForm.addEventListener('submit',async e=>{e.preventDefault();const btn=$('button',searchForm);btn.disabled=true;try{const result=await api(merchantRoot()+'/knowledge-search',{query:new FormData(searchForm).get('query')});$('#knowledge-results').innerHTML=`<p>${h(result.method)}</p>${result.matches.length?result.matches.map(renderKnowledgeCard).join(''):'<p>没有匹配资料，不补造答案。</p>'}`;}catch(err){toast(err.message);}finally{btn.disabled=false;}});
}

function renderComparison(c) {
  return section('明示假设下的候选比较',`<div class="panel"><p>${h(c.note)}</p><div class="table-wrap"><table><thead><tr><th>方案/版本</th><th>额外支出</th><th>每周工时</th><th>零销量最低现金</th><th>申报贡献</th><th>当前判断</th></tr></thead><tbody>${c.rows.map(r=>`<tr><td>${h(r.title)} v${r.version}</td><td>¥${yuan(r.spend)}</td><td>${r.hours}小时</td><td>¥${yuan(r.cash_floor)}</td><td>${r.contribution===null?'待核实':'¥'+yuan(r.contribution)}</td><td>${!r.hard_pass?'有硬约束或异议':r.dominated_by.length?'有候选在这些假设下更优':'候选内非支配'}<br>另有${r.unknowns}项待核实</td></tr>`).join('')}</tbody></table></div></div>`);
}

function renderCollaborationEvidence(r) {
  const c=r.result?.collaboration;
  if(!c?.role_assessments?.length)return '<p>这份分析暂无分工明细，可查看已有结论和待核对资料。</p>';
  const evidence=new Map(r.events.filter(e=>e.kind==='tool_result').map(e=>[e.id,e]));
  const proof=ids=>ids.length?evidenceDetails(ids,r):'';
  const roles=['inventory','customer','cash'].map(role=>c.role_assessments.find(a=>a.role===role&&a.phase==='investigate')).filter(Boolean);
  const last=c.coordination_plans?.at(-1), requirements=new Map((last?.requirements||[]).map(q=>[q.id,q]));
  const verdict={pass:'本专业复核通过',needs_data:'仍需补证',blocked:'仍有风险'};
  const choices={revise:'修改方案',ask_merchant:'向店主补证',retain_unresolved:'保留未解决问题'};
  const rawVersions=r.events.flatMap(e=>e.kind==='merchant_candidate'?[{p:e.data.proposal,phase:'merchant'}]:e.kind==='proposal_revision'&&e.actor==='merchant'?[{p:e.data.after,phase:'merchant'}]:e.kind==='agent_result'&&['propose','revise'].includes(e.data.phase)?(e.data.result.proposals||[]).map(p=>({p,phase:e.data.phase})):[]);
  const versionKeys=new Set(),versions=rawVersions.filter(({p})=>{const key=JSON.stringify([p.id,p.version]);if(versionKeys.has(key))return false;versionKeys.add(key);return true;});
  let html=`<div class="collab-evidence">${renderKnowledgeClaims(r)}<h3>这次分别查了什么</h3><div class="collab-roles">${roles.map(a=>`<article><h4>${h(roleLabel(a.role))}</h4><p>${h(merchantText(a.conclusion))}</p><details><summary>判断依据、假设与资料缺口</summary><p>假设：${a.assumptions.map(x=>h(merchantText(x))).join('；')}</p><p>边界：${a.limits.map(x=>h(merchantText(x))).join('；')}</p>${a.missing_data.map(q=>`<p><strong>${h(merchantText(q.question))}</strong><br>为什么要补：${h(merchantText(q.why_needed))}<br>完成条件：${h(merchantText(q.completion_condition))}</p>`).join('')}${proof(a.evidence_ids)}</details></article>`).join('')}</div>
  <h3>接下来由谁处理</h3>${last?.source==='host_archive_of_validated_reviews'?'<p>以下待办由系统根据三方已完成的复审整理，仍需核对的条件继续保留。</p>':''}${last?.revision_budget_exhausted?'<p>已到本次修订上限，以下未完成事项继续保留，不能视为已解决。</p>':''}${last?.tasks?.length?last.tasks.map(t=>{const q=requirements.get(t.requirement_id);return `<article class="collab-task"><strong>${h(roleLabel(t.assignee))} · ${h(choices[t.disposition]||t.disposition)}</strong><p>${h(merchantText(t.action))}</p><p>完成条件：${h(merchantText(t.acceptance))}</p><small>关联方案：${q?.proposal_id?h(versions.find(v=>v.p.id===q.proposal_id)?.p.title||'待审方案')+' · 第'+h(q.version)+'版':'店铺资料补证'}</small></article>`;}).join(''):'<p>本轮没有新的分派任务；仍需由商户审阅候选。</p>'}
  <h3>方案怎样一步步变化</h3>${versions.map(({p,phase})=>{const review=c.proposal_reviews.filter(v=>v.proposal_id===p.id&&v.version===p.version);const effect=c.revisions.find(v=>v.proposal_id===p.id&&v.after_version===p.version);return `<details class="collab-version"><summary>${h(p.title)} · 第 ${p.version} 版 · ${phase==='merchant'?'商户待审候选':phase==='propose'?'初始方案':'修订方案'}</summary><p>前置投入 ¥${h(p.upfront_cost)}；每周 ${h(p.weekly_hours)} 小时；停止条件：${p.stop_conditions.map(h).join('；')}</p>${effect?`<p>${effect.material_change?'实际安排已改变':'实际安排未改变'}；已消除 ${effect.resolved_checks.length} 项约束问题，新增 ${effect.introduced_checks.length} 项。</p>`:''}${review.map(v=>`<article><strong>${h(roleLabel(v.role))}：${h(verdict[v.status]||v.status)}</strong><p>${h(merchantText(v.reason))}</p>${(v.responses||[]).map(x=>`<p>对上轮质询 ${h(x.objection_id)} 的回应：${h({resolved:'本轮认为已解除',retained:'继续保留',needs_data:'仍待补证'}[x.outcome])}。${h(merchantText(x.reason))}</p>`).join('')}${proof(v.evidence_ids)}</article>`).join('')}${proof(p.evidence_ids)}</details>`;}).join('')||'<p>资料尚不足以提出方案，先处理补证问题。</p>'}</div>`;
  for(const {p} of versions)html=html.replaceAll(h(p.id),h(merchantText(p.title)));
  return html;
}

function collaborationJourney(r) {
  const events=r.events||[],c=r.result?.collaboration||{};
  const actual=phase=>events.some(e=>e.kind==='agent_result'&&e.data.phase===phase);
  const stages=[['分别核对店铺资料',actual('investigate'),'从商品、顾客与现金三个角度找出问题。'],['提出可选办法',actual('propose'),'候选需要核对条件，不会自动执行。'],['交叉检查与修改',actual('review'),'检查同一版本的预算、用时、资料和不同意见。'],['整理下一步',actual('coordinate')||(c.coordination_plans||[]).length>0,'把修改和补证事项交给对应角色或店主。']];
  return `<ol class="collab-journey">${stages.map(([title,done,note])=>`<li><strong>${h(title)}</strong> ${badge(done?'已记录':'暂无记录',done?'':'amber')}<p>${h(note)}</p></li>`).join('')}</ol>`;
}
function renderAudit(r) {
  return section('本次核对与处理经过',`<div class="panel">${collaborationJourney(r)}${renderCollaborationEvidence(r)}</div>`);
}

function renderFeedbackJournal() {
  const entries=state.extras.journal.entries;
  return section('分期反馈与更正留痕',`<div class="panel"><p>每一期都填从行动开始日累计值，不把多个累计检查点相加。更正只作用于最新一期，旧记录及已完成分析快照保持不变。</p>${entries.length?`<div class="table-wrap"><table><thead><tr><th>截止日</th><th>版本</th><th>记录类型</th><th>净现金/贡献</th><th>记录依据与原因</th><th>操作</th></tr></thead><tbody>${entries.slice().reverse().map(e=>{const d=e.data;const newer=entries.some(n=>n.data.supersedes_id===d.id);return `<tr><td>${h(d.period_end)}</td><td>${h(d.proposal_id)} v${d.proposal_version}</td><td>${d.operation==='correction'?'留痕更正':d.operation==='checkpoint'?'累计检查点':'首次累计反馈'}${newer?'（已有后续）':''}</td><td>¥${yuan(e.summary.trial_net_cash)} / ${e.summary.trial_margin_contribution===null?'待核实':'¥'+yuan(e.summary.trial_margin_contribution)}</td><td class="wrap-value">${h(d.source_note)}<br>${h(d.change_reason||'首次记录')}</td><td>${!newer?featureButton('下一期','feedback-next',`data-id="${h(d.id)}"`)+featureButton('更正本期','feedback-correct',`data-id="${h(d.id)}"`):'原始记录保留'}</td></tr>`;}).join('')}</tbody></table></div>`:'<p>尚无反馈。</p>'}</div>`);
}

function openFeature(title,body,onSubmit,submitLabel='保存') {
  $('#feature-title').textContent=title;
  $('#feature-form').innerHTML=`<div class="form-body">${body}<p class="form-error" role="alert" hidden></p></div><div class="dialog-footer"><small>仅保存本机记录，不自动执行经营动作。</small><div class="inline-flex"><button type="button" class="button secondary" data-close="feature-dialog">取消</button>${onSubmit?`<button class="button primary" type="submit">${h(submitLabel)}</button>`:''}</div></div>`;
  $('#feature-form').onsubmit=onSubmit?async event=>{event.preventDefault();const form=event.target,submit=$('[type=submit]',form),error=$('.form-error',form);submit.disabled=true;error.hidden=true;try{await onSubmit(form);$('#feature-dialog').close();}catch(err){error.textContent=err.message;error.hidden=false;error.scrollIntoView({block:'nearest'});}finally{submit.disabled=false;}}:event=>event.preventDefault();
  $('#feature-dialog').showModal();
}

function openPeriod(id) {
  const p=state.merchant.operating_periods?.find(p=>p.id===id)||{};
  openFeature(id?'更正经营期间':'添加经营期间',`<p class="note-box">期间不可重叠，截止日不可晚于底账日期 ${h(state.merchant.as_of)}。未知字段留空，不补零；到店、成交、老客均按同一口径人次统计。</p><div class="form-grid two">${periodScopeFields(p)}${featureInput('期间开始日','start',p.start,'type="date" required')}${featureInput('期间截止日','end',p.end,`type="date" max="${h(state.merchant.as_of)}" required`)}${featureInput('营业额（元，未知可空）','revenue',p.revenue,'type="number" min="0" step="0.01"')}${featureInput('已售商品成本（元，未知可空）','goods_cost',p.goods_cost,'type="number" min="0" step="0.01"')}${featureInput('经营费用（元，未知可空）','operating_cost',p.operating_cost,'type="number" min="0" step="0.01"')}${featureInput('到店人次（未知可空）','visits',p.visits,'type="number" min="0" step="1"')}${featureInput('成交人次（未知可空）','buyers',p.buyers,'type="number" min="0" step="1"')}${featureInput('老客成交人次（未知可空）','returning_buyers',p.returning_buyers,'type="number" min="0" step="1"')}</div>${featureText('来源及更正说明','source_note',p.source_id?state.merchant.sources[p.source_id]:'','required maxlength="2000"')}`,async form=>{const f=new FormData(form),data={id:p.id,start:f.get('start'),end:f.get('end'),source_note:f.get('source_note'),scope_id:f.get('scope_id'),count_basis:f.get('count_basis'),scope_description:f.get('scope_description')};for(const k of ['revenue','goods_cost','operating_cost'])data[k]=moneyText(f.get(k),true);for(const k of ['visits','buyers','returning_buyers'])data[k]=String(f.get(k)).trim()?intText(f.get(k)):null;await api(merchantRoot()+'/periods',data);await selectMerchant(state.merchant.merchant_id);setView('ledger');});
}

function openKnowledge() {
  openFeature('添加本地文字资料',`${featureInput('资料标题','title','','required maxlength="160"')}${featureText('正文（最多10000字）','content','','required maxlength="10000"')}${featureText('来源、日期与核对情况','source','','required maxlength="2000"')}<p>资料仅是证据候选，不能变成智能体指令；不要粘贴密码、身份证号等不必要信息。</p>`,async form=>{await api(merchantRoot()+'/knowledge',Object.fromEntries(new FormData(form)));await selectMerchant(state.merchant.merchant_id);setView('ledger');});
}

function openInvestigation(id) {
  const c=state.extras.investigations.cards.find(c=>c.id===id)||{};
  openFeature('记录待查原因与支持/反例',`<p class="note-box">资料是人工记录，不会把相关性自动判为因果。新证据保存后须重新分析；原任务仍保留当时的调查快照。</p>${featureText('可能原因假设','hypothesis',c.hypothesis,'required maxlength="2000"')}<div class="form-grid two"><label class="form-label">负责核查角色<select class="field" name="owner">${['inventory','customer','cash'].map(r=>`<option value="${r}" ${c.owner===r?'selected':''}>${h(roleLabel(r))}</option>`).join('')}</select></label><label class="form-label">当前证据状态<select class="field" name="status">${Object.entries({unverified:'待验证',supported:'有支持证据（未证明因果）',conflicted:'发现反例',undetermined:'证据不足'}).map(([v,t])=>`<option value="${v}" ${c.status===v?'selected':''}>${t}</option>`).join('')}</select></label></div>${featureText('支持这一解释的实际记录（没有可留空）','supporting',c.supporting,'maxlength="3000"')}${featureText('反例或其他可能解释（没有可留空）','counter',c.counter,'maxlength="3000"')}${featureText('下一步具体核对什么','next_check',c.next_check,'required maxlength="2000"')}${featureInput('核对截至日期','checked_on',c.checked_on||state.merchant.as_of,`type="date" max="${h(state.merchant.as_of)}" required`)}${featureText('来源与本次变更说明','source_note',c.source_note,'required maxlength="2000"')}`,async form=>{await api(merchantRoot()+'/investigations',{...Object.fromEntries(new FormData(form)),id:c.id});await selectMerchant(state.merchant.merchant_id);setView('ledger');});
}

function planItemRow(i={}) {
  return `<tr class="sandbox-item"><td><select class="field" name="sku" aria-label="方案商品">${state.merchant.products.map(p=>`<option value="${h(p.sku)}" ${i.sku===p.sku?'selected':''}>${h(p.name)}（库存${p.stock}）</option>`).join('')}</select></td><td><input class="field" name="quantity" value="${h(i.quantity)}" type="number" min="0" step="1" required aria-label="假设销售件数"></td><td><input class="field" name="price" value="${h(i.price)}" type="number" min="0" step="0.01" required aria-label="假设成交单价"></td><td><input class="field" name="variable_cash_cost" value="${h(i.variable_cash_cost)}" type="number" min="0" step="0.01" required aria-label="每件额外费用"></td><td><input class="field" name="receipt_date" value="${h(i.receipt_date)}" type="date" required aria-label="假设回款日"><label class="form-label">交付日<input class="field" name="sale_date" value="${h(i.sale_date||i.receipt_date)}" type="date" required aria-label="交付日"></label></td><td>${featureButton('移除','remove-plan-item')}</td></tr>`;
}

let sandboxBase=null,sandboxNew=false;
function openPlan(index,strategyId) {
  if(!state.report||state.report.ledger_changed||state.report.context_changed||['failed','cancelled','running','interrupted'].includes(state.report.result?.status))throw new Error('先重新分析当前资料再创建或编辑方案');
  if(!state.merchant.products.length)throw new Error('先登记至少一种商品');
  const s=state.extras.strategies.strategies.find(s=>s.id===strategyId);
  const p=index===undefined?{id:'manual_'+crypto.randomUUID().replaceAll('-','').slice(0,16),version:0,owner:s?.owner||'customer',title:s?.title||'人工经营假设',spend_date:state.merchant.as_of,upfront_cost:'',other_cost:'',weekly_hours:'',items:[{sku:state.merchant.products[0].sku,price:state.merchant.products[0].unit_price,receipt_date:state.merchant.as_of}],rationale:s?.requirements||'',stop_conditions:['达到登记预算或影响必要付款时停止新增投入']} : state.report.result.proposals[index].proposal;
  sandboxBase=p;sandboxNew=index===undefined;
  openFeature(sandboxNew?'创建候选经营假设':'编辑方案并保留新版本',`<div class="note-box">基于当前任务，${sandboxNew?'创建一个新候选':'保留旧版并生成第 '+(p.version+1)+' 版'}。填写的是明示假设，不是预测；费用是否核实请如实选择。若改动固定费用总额，旧版分项不沿用，本版先标为待核实，旧版本保留。可先只重算，不会保存或触发经营动作。</div><div class="form-grid two">${featureInput('方案名称','title',p.title,'required maxlength="160"')}${featureInput('开始支出日','spend_date',p.spend_date,'type="date" required')}${featureInput('前期固定支出（元）','upfront_cost',p.upfront_cost,'type="number" min="0" step="0.01" required')}${featureInput('其他固定支出（元）','other_cost',p.other_cost,'type="number" min="0" step="0.01" required')}${featureInput('每周投入工时','weekly_hours',p.weekly_hours,'type="number" min="0" max="168" step="1" required')}</div><div class="table-wrap"><table class="editable-table"><thead><tr><th>商品</th><th>假设件数</th><th>成交单价</th><th>每件额外费用</th><th>回款日</th><th></th></tr></thead><tbody id="sandbox-items">${p.items.map(planItemRow).join('')}</tbody></table></div>${featureButton('再添加商品','add-plan-item')}${procurementFields(p)}<label class="checkbox-line"><input type="checkbox" name="costs_confirmed" ${p.costs_confirmed?'checked':''}>这些固定与变动费用已经人工核实（未知不能当作0）</label>${modelChoices(p)}${featureText('依据与仍待调查的条件','rationale',p.rationale,'required maxlength="3000"')}${featureText('停止条件（每行一条）','stop_conditions',p.stop_conditions.join('\n'),'required maxlength="2000"')}<div class="feature-actions">${featureButton('只重算，不保存','preview-plan')}</div><div id="sandbox-preview"></div>`,async form=>{const draft=readDraft(form);await startTask({mode:'manual',draft,parent_run:state.report.run_id});},'保存新版本并交叉复核');
}

function readDraft(form) {
  const f=new FormData(form),p={...sandboxBase,title:String(f.get('title')),version:sandboxBase.version+1,upfront_cost:moneyText(f.get('upfront_cost')),other_cost:moneyText(f.get('other_cost')),spend_date:String(f.get('spend_date')),weekly_hours:intText(f.get('weekly_hours')),costs_confirmed:f.has('costs_confirmed'),sales_assumption:'merchant_estimate',rationale:String(f.get('rationale')),assumptions:['用户填写的明示销量与回款假设，未由模型预测'],stop_conditions:String(f.get('stop_conditions')).split('\n').map(x=>x.trim()).filter(Boolean),model_refs:readModelChoices(form),new_candidate:sandboxNew,evidence_ids:['preview_only_not_evidence']};
  if(p.expense_breakdown && (p.upfront_cost!==sandboxBase.upfront_cost || p.other_cost!==sandboxBase.other_cost)) {
    delete p.expense_breakdown;p.costs_confirmed=false;
    p.assumptions.push('固定费用已修改，旧版分项依据只保留在旧版本；本版费用须重新核实。');
  }
  p.procurements=readProcurements(form);
  p.items=$$('.sandbox-item',form).map(row=>{const val=n=>$('[name="'+n+'"]',row).value;return {sku:val('sku'),quantity:intText(val('quantity')),price:moneyText(val('price')),variable_cash_cost:moneyText(val('variable_cash_cost')),receipt_date:val('receipt_date'),sale_date:val('sale_date')};});return p;
}

function previewHtmlBase(e) { return `<div class="panel"><strong>本次重算结果（尚未保存）</strong><p>额外支出 ¥${yuan(e.trial_cash_commitment)}；申报贡献 ${e.gross_profit_after_declared_trial_costs===null?'待核实':'¥'+yuan(e.gross_profit_after_declared_trial_costs)}</p>${e.checks.map(c=>`<p class="form-error">${h(checkNames[c.code]||c.code)}</p>`).join('')||'<p>所录条件未触及硬约束，不等于推荐执行。</p>'}<ul>${e.unknowns.map(x=>`<li>${h(x)}</li>`).join('')}</ul><div class="table-wrap"><table><thead><tr><th>情景</th><th>最低现金</th><th>期末现金</th></tr></thead><tbody>${e.scenarios.map(s=>`<tr><td>${h({zero_sales:'零销量',half_sales:'半销量',declared_sales:'申报销量'}[s.scenario])}</td><td>¥${yuan(s.minimum_cash_before_receipts)}</td><td>¥${yuan(s.ending_cash)}</td></tr>`).join('')}</tbody></table></div></div>`; }

function previewHtml(e) {return previewHtmlBase(e)+renderSupplyPlan(e.procurement);}

function analysisControls() {
  return `<div class="mode-controls"><label class="mode-label">运行方式<select class="field" id="execution-mode" ${state.busy?'disabled':''}>${['rules','agentarts'].map(m=>`<option value="${m}" ${state.executionMode===m?'selected':''}>${h(executionName(m))}${m==='agentarts'&&!state.extras?.preflight.can_request_cloud?'（尚未就绪）':''}</option>`).join('')}</select></label>${state.executionMode==='simulation'?`<label class="mode-label">演练场景<select class="field" id="simulation-case" ${state.busy?'disabled':''}>${Object.entries({normal:'正常协议',conflict:'故障注入：超预算后修订',malformed:'故障注入：格式错误',timeout:'故障注入：超时',slow:'慢响应：检验取消'}).map(([v,t])=>`<option value="${v}" ${state.simulationCase===v?'selected':''}>${t}</option>`).join('')}</select></label>`:''}${state.executionMode==='agentarts'?`<label class="mode-label">审查后再补充讨论<select class="field" id="revision-rounds" ${state.busy?'disabled':''}>${[0,1,2].map(n=>`<option value="${n}" ${(state.maxRounds||0)===n?'selected':''}>${n===0?'先出一版，自己审阅（推荐）':n+'次（实验功能，非正式演示流程）'}</option>`).join('')}</select></label>`:''}<label class="mode-label">调用上限<input class="field" id="call-limit" type="number" min="1" max="96" step="1" value="${state.maxCalls}" ${state.busy?'disabled':''}></label></div>`;
}

function taskProgressBox() {
  const j=state.job;
  const progress=globalThis.RebirthCore?.jobProgressText(j);
  return `<div class="panel busy-box"><span class="spinner" aria-hidden="true"></span><div>${h(executionName(j?.mode||state.executionMode))}${j?.observation_error?' · 进度待恢复':'执行中'}</div>${progress?`<p><strong>${h(progress.stage)}</strong></p><p>${h(progress.elapsed)}</p><p class="muted">${h(progress.notice)}</p>`:""}<p class="job-count">已记录 ${j?.event_count||0} 条事件 · 已调用 ${j?.usage?.calls||0} 次</p><p>${j?.last_event?h(roleLabel(j.last_event.actor)+' · '+({task_opened:'开始分析',history_snapshot:'读取以往记录',knowledge_snapshot:'读取经营资料',investigation_snapshot:'读取已知线索',tool_result:'核对数字和证据',tool_error:'有资料需要补充',agent_result:'形成阶段结论',run_failed:'本次分析未完成',agent_output_rejected:'正在核对并纠正分析格式'}[j.last_event.kind]||'正在核对资料')):'正在建立任务与快照'}</p><p>${j?.mode==='agentarts'?'本次任务可能产生模型费用；取消只停止后续调用。':'仅在本机执行，不调用任何付费模型。'}</p>${featureButton('恢复进度查看','recover-job')}${featureButton('取消本次任务','cancel-job')}<p></p></div>`;
}

async function requestAnalysis() {
  if(!state.merchant||state.busy)return;
  if(state.executionMode==='agentarts') {
    await openCloudConsent();return;
  }
  await startTask({mode:state.executionMode,simulation_case:state.simulationCase,max_calls:state.maxCalls});
}

async function startTask(options) {
  if(state.busy)throw new Error('已有任务正在运行');
  const merchant=state.merchant.merchant_id;
  const started=await api('/api/jobs',{merchant_id:merchant,max_calls:state.maxCalls,...(options.mode==='agentarts'?{max_rounds:state.maxRounds||0}:{}),...options});
  state.job={...started,mode:options.mode,event_count:0};state.busy=true;state.view='analysis';render();
  try{localStorage.setItem('rebirth_active_job',JSON.stringify({merchant,job:started.job_id,mode:options.mode}));}catch{}
  setTimeout(()=>pollTask(merchant,started.job_id),100);
}

async function pollTask(merchant,job) {
  try {
    const value=await api('/api/merchants/'+encodeURIComponent(merchant)+'/jobs/'+encodeURIComponent(job));
    state.job={...value,job_id:job};
    if(value.state==='running') {render();setTimeout(()=>pollTask(merchant,job),400);return;}
    state.busy=false;
    try{localStorage.removeItem('rebirth_active_job');}catch{}
    await selectMerchant(merchant,value.run_id||undefined);if(globalThis.RebirthApp)globalThis.RebirthApp.taskFinished();else setView('analysis');
    toast(value.state==='completed'?executionName(value.mode)+'已完成':value.error||'任务未完成，已有记录保留');
  } catch(err) {
    if([400,404].includes(err.status) && err.message.includes('未找到该店铺任务')) {
      state.busy=false;state.job=null;
      try{localStorage.removeItem('rebirth_active_job');}catch{}
      await selectMerchant(merchant);
      toast('服务已重新启动，本次任务观察已结束。已完成步骤保留在分析记录中；未完成记录不会当作有效结论。');
      return;
    }
    state.busy=true;state.job={...state.job,observation_error:true};render();toast('暂时无法读取进度，后台任务可能仍在运行。请恢复进度查看，不要重复开始。'+err.message);
  }
}

async function recoverTask(silent=false) {
  let active;try{active=JSON.parse(localStorage.getItem('rebirth_active_job'));}catch{}
  if(!active) {if(!silent)toast('没有待恢复的任务。已完成记录可在分析历史中查看。');return;}
  if(state.merchant?.merchant_id!==active.merchant)await selectMerchant(active.merchant);
  state.job={job_id:active.job,mode:active.mode||'agentarts',observation_error:true};state.busy=true;state.view='analysis';render();await pollTask(active.merchant,active.job);
}

async function openPreflight() {
  const p=await api('/api/preflight');if(state.extras)state.extras.preflight=p;
  openFeature('分析服务状态',`<p class="note-box">本次检查没有发出任何外部请求，也不会测试扣费接口。${h(p.notice)}</p><div class="preflight-grid">${p.roles.map(r=>`<div class="preflight-line"><strong>${h(roleLabel(r.role))}</strong><p>目的域名：${h(r.host||'未配置有效HTTPS端点')}</p><div class="status-list">${Object.entries({https_endpoint:'调用路径',host_confirmed:'域名人工确认',credential_present:'服务凭证已配置',auth_header_supported:'认证头'}).map(([k,t])=>`<span class="${r[k]?'pass':'fail'}">${r[k]?'✓':'○'} ${t}</span>`).join('')}</div></div>`).join('')}</div><p>服务启动云调用开关：${p.server_allows_cloud?'已显式开启':'关闭（当前不会意外收费）'}</p><p>${h(p.remaining)}</p><p>如有项目尚未就绪，请联系服务管理员检查配置。不要在店铺资料中填写服务密钥。</p><p class="evidence-privacy">调用次数与文本体积上限不是人民币账单上限。还需在华为云侧设置额度；真实模型质量与接口差异只能在接入后验证。</p>`,null);
}

async function openCloudConsent(extra={}) {
  const ready=await api('/api/preflight');
  if(!ready.can_request_cloud) {await openPreflight();return;}
  const outbound=await api(merchantRoot()+'/outbound-preview');
  openFeature('仅为本次云任务确认数据与费用',`<p class="evidence-privacy">目的地：${h([...new Set(ready.roles.map(r=>r.host))].join('、'))}。会发送库存、成本、价格、现金、付款、经营期间、客户观察、匿名客群汇总、经营模式、采购与收支账簿，以及后续工具结果、检索片段、历史反馈和实验评价。属于经营敏感资料，可能产生资源费用。</p><p>${h(outbound.notice)}</p><details><summary>逐项检查出站底账预览</summary><pre class="json-block">${h(JSON.stringify(outbound.preview,null,2))}</pre></details><p>本次最多${state.maxCalls}次角色调用，累计输入2MB、输出300KB、总时长最多10分钟、单次HTTP超时20秒，Managed Agents单次响应最长3分钟。网络失败不自动重试；输出格式不合格时，每阶段最多请求纠正2次，计入调用上限。取消不能追回已发生费用。</p><label class="checkbox-line"><input type="checkbox" name="consent" required>我已检查资料及目的域名，同意仅这次任务向配置的AgentArts服务发送上述经营数据，并知悉可能计费</label>`,async form=>{if(!new FormData(form).has('consent'))throw new Error('尚未确认');await startTask({mode:'agentarts',cloud_data_consent:true,...extra});},'确认并仅运行这一次');
}

function hydrateFeedback() {
  const form=$('#feedback-form'),meta=state.feedbackMeta;
  $('.dialog-footer small',form).textContent='每次填写从开始日累计的数据。新检查点与更正不会删除旧记录，也不会自动修改库存或现金。';
  if(state.report.ledger_changed)$('.form-body',form).insertAdjacentHTML('afterbegin','<div class="note-box amber">当前店铺资料已更新。本反馈仍使用原任务的商品成本和精确方案版本，不会改写旧分析。</div>');
  if(typeof procurementFeedbackFields==='function')procurementFeedbackFields(form);
  if(!meta)return;
  const entry=state.extras.journal.entries.find(e=>e.data.id===meta.prior.feedback_id);
  if(!entry)throw new Error('未找到原始累计反馈，请刷新');
  const d=entry.data;
  for(const k of ['fixed_spend','hours_spent','source_note'])$('[name="'+k+'"]',form).value=d[k];
  $('[name="observations"]',form).value=d.observations.join('\n');
  $('[name="costs_confirmed"]',form).checked=d.costs_confirmed;
  $$('.feedback-item',form).forEach(row=>{const item=d.items.find(i=>i.sku===row.dataset.sku);for(const k of ['units_sold','units_returned','units_returned_resellable','cash_received','refund_paid','variable_spend'])$('[name="'+k+'"]',row).value=item[k]??0;});
  const end=$('[name="period_end"]',form);
  if(meta.operation==='correction'){end.value=d.period_end;end.readOnly=true;}
  else{const next=new Date(d.period_end+'T00:00:00Z');next.setUTCDate(next.getUTCDate()+1);end.min=next.toISOString().slice(0,10);end.value='';}
  $('.form-body',form).insertAdjacentHTML('afterbegin',`<div class="note-box">${meta.operation==='correction'?'更正最新一期，截止日不变':'记录下一期，数字须从开始日累计，不是这一期增量'}。上一检查点截止 ${h(d.period_end)}，旧记录保留。</div>`);
  $('.form-body',form).insertAdjacentHTML('beforeend',featureText('本次记录或更正原因','change_reason','','required maxlength="2000"'));
}

async function openExistingFeedback(id,operation) {
  const e=state.extras.journal.entries.find(e=>e.data.id===id);if(!e)throw new Error('记录不存在');
  await selectMerchant(state.merchant.merchant_id,e.data.run_id);
  const index=state.report.result.proposals.findIndex(p=>p.proposal.id===e.data.proposal_id&&p.proposal.version===e.data.proposal_version);
  if(index<0)throw new Error('原方案版本未找到');
  openFeedback(index,operation);
}

function openTrial(index,existing) {
  const p=existing?null:state.report.result.proposals[index].proposal;
  const raw=existing||{run_id:state.report.run_id,proposal_id:p.id,proposal_version:p.version,hypothesis:p.title,success_metric:'',end_date:p.spend_date,stop_budget:state.report.result.proposals[index].evaluation.trial_cash_commitment,status:'planned',source_note:''};
  openFeature('登记或更新试验计划',`<p class="note-box">只登记人工计划，不代表系统批准经营方案，不会自动执行交易。先确认费用和必要付款，登记指标、预算及截止日；同一店铺一次只开展一项。</p><div class="form-grid two">${featureText('待验证假设','hypothesis',raw.hypothesis,'required maxlength="2000"')}${featureText('观察指标、目标与判断方法','success_metric',raw.success_metric,'required maxlength="2000"')}${featureInput('截止日','end_date',raw.end_date,'type="date" required')}${featureInput('停止新增投入的预算（元）','stop_budget',raw.stop_budget,'type="number" min="0" step="0.01" required')}<label class="form-label">人工记录状态<select class="field" name="status">${Object.entries({planned:'计划中',active:'开展中',paused:'暂停',stopped:'停止',completed:'已复盘'}).map(([v,t])=>`<option value="${v}" ${raw.status===v?'selected':''}>${t}</option>`).join('')}</select></label></div>${featureText('记录来源与状态变更原因','source_note',raw.source_note,'required maxlength="2000"')}<label class="checkbox-line"><input type="checkbox" name="acknowledged" required>我知道这只是记录计划与人工状态，不会自动联系顾客或执行经营动作</label>`,async form=>{const f=new FormData(form);await api(merchantRoot()+'/experiments',{...raw,...Object.fromEntries(f),stop_budget:moneyText(f.get('stop_budget')),acknowledged:f.has('acknowledged')});await selectMerchant(state.merchant.merchant_id);setView('feedback');});
}

async function exportLocal() {
  const data=await api(merchantRoot()+'/export');
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='rebirth-'+state.merchant.merchant_id+'-local-records.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('导出包含经营敏感资料，请只保存在本机，不公开分享');
}

function importCopy() {
  openFeature('粘贴资料并导入新店铺副本',`${featureText('粘贴本地导出的JSON，或包含ledger的资料对象','bundle','','required maxlength="950000"')}<p>仅将店铺底账导入为新ID，不覆盖旧店铺。原始任务和试验历史保留在导出文件中用于查阅，不伪装成新店铺已完成的任务。完整数据库恢复请使用SQLite备份。</p>`,async form=>{const data=JSON.parse(new FormData(form).get('bundle'));const value=await api('/api/merchants/local/import-copy',data);await reloadMerchants(value.merchant_id);setView('ledger');},'导入新副本');
}

document.addEventListener('change',event=>{
  if(event.target.id==='execution-mode'){state.executionMode=event.target.value;render();}
  if(event.target.id==='simulation-case')state.simulationCase=event.target.value;
  if(event.target.id==='revision-rounds'){state.maxRounds=Number(event.target.value);}
  if(event.target.id==='call-limit'){const value=Number(event.target.value);state.maxCalls=Number.isInteger(value)&&value>=1&&value<=96?value:64;event.target.value=state.maxCalls;}
});

document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-feature]');if(!b||b.disabled)return;
  const a=b.dataset.feature;
  if(state.busy&&!['cancel-job','recover-job'].includes(a)){toast('任务执行中，请先等待或取消');return;}
  b.disabled=true;
  try{
    if(a==='preflight')await openPreflight();
    else if(a==='acceptance'){const ledger=await api('/api/acceptance-example');ledger.merchant_id='accept_'+crypto.randomUUID().replaceAll('-','').slice(0,16);await api('/api/ledgers',ledger);await reloadMerchants(ledger.merchant_id);setView('ledger');toast('已新建示例店铺，原店铺未改动');}
    else if(a==='period')openPeriod(b.dataset.id);
    else if(a==='knowledge')openKnowledge();
    else if(a==='investigation')openInvestigation(b.dataset.id);
    else if(a==='plan')openPlan(Number(b.dataset.index));
    else if(a==='new-plan')openPlan(undefined,b.dataset.strategy);
    else if(a==='add-plan-item')$('#sandbox-items').insertAdjacentHTML('beforeend',planItemRow());
    else if(a==='remove-plan-item')b.closest('tr').remove();
    else if(a==='preview-plan'){const form=$('#feature-form');if(form.reportValidity())$('#sandbox-preview').innerHTML=previewHtml(await api('/api/tools/'+encodeURIComponent(state.merchant.merchant_id)+'/proposal_evaluate',{proposal:readDraft(form)}));}
    else if(a==='trial')openTrial(Number(b.dataset.index));
    else if(a==='edit-trial')openTrial(undefined,state.extras.experiments.experiments.find(e=>e.id===b.dataset.id));
    else if(a==='feedback-next')await openExistingFeedback(b.dataset.id,'checkpoint');
    else if(a==='feedback-correct')await openExistingFeedback(b.dataset.id,'correction');
    else if(a==='cancel-job'){if(!state.job?.job_id)throw new Error('任务尚未建立');await api(merchantRoot()+'/jobs/'+encodeURIComponent(state.job.job_id)+'/cancel',{});toast('已请求取消；已发出的请求等待返回，不再启动后续调用');}
    else if(a==='recover-job')await recoverTask();
    else if(a==='export')await exportLocal();
    else if(a==='import-copy')importCopy();
  }catch(err){toast(err.message);}finally{b.disabled=false;}
});

function renderFactChanges(before,after) {
  const rows=globalThis.RebirthCore?.analysisChanges(before,after)||[];
  if(!rows.length)return '';
  const value=v=>v==null?'待核实':String(v);
  return `<details class="panel"><summary>这份分析后，哪些资料发生了变化（${rows.length}项）</summary><p>以下与当前店铺资料比较；旧结论仍依据旧快照。补证不会自动重写分析，请确认后重新核查。</p><div class="table-wrap"><table><thead><tr><th>资料</th><th>这份分析使用的值</th><th>当前已保存的值</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${h(r.label)}</td><td>${h(value(r.before))}</td><td>${h(value(r.after))}</td></tr>`).join('')}</tbody></table></div><p>这里只列出主要金额、工时和商品字段；其他来源、付款和观察变化仍以完整资料为准。</p></details>`;
}
