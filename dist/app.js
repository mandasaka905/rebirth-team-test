"use strict";
globalThis.RebirthInitialHash = location.hash;

const $ = (query, root = document) => root.querySelector(query);
const $$ = (query, root = document) => [...root.querySelectorAll(query)];
const state = { booting: true, merchant: null, merchants: [], readiness: null, baseline: null, inventory: null, runs: [], report: null, outcomes: [], view: "overview", busy: false, editing: null, feedbackPlan: null, extras: null, job: null, executionMode: "rules", simulationCase: "normal", maxCalls: 64, feedbackMeta: null };
const titles = { overview: "经营概览", ledger: "店铺资料", analysis: "经营分析", feedback: "行动与复盘" };
const roles = { coordinator: "经营协调", inventory: "商品与库存", customer: "客户与经营方式", cash: "现金流与风险" };
const roleIcons = { coordinator: "team", inventory: "box", customer: "users", cash: "wallet" };
const icons = {
  home: '<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',
  store: '<path d="M4 10v10h16V10M3 10l2-6h14l2 6M3 10c0 3 4 3 4 0 0 3 5 3 5 0 0 3 5 3 5 0 0 3 4 3 4 0M8 20v-6h4v6"/>',
  team: '<circle cx="12" cy="7" r="3"/><path d="M7 21v-3a5 5 0 0 1 10 0v3M3 9a3 3 0 0 1 2 5M21 9a3 3 0 0 0-2 5M2 21v-2a4 4 0 0 1 3-4M22 21v-2a4 4 0 0 0-3-4"/>',
  book: '<path d="M5 3h14v18H5zM8 7h8M8 11h8M8 15h5"/>',
  box: '<path d="m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10M8 5l9 4"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M21 21v-3a5 5 0 0 0-3-4"/>',
  wallet: '<path d="M4 6h16v14H4zM4 6V4h13v2M20 11h-6v5h6M16 13.5h1"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5M12 17h.01"/>',
  arrow: '<path d="M4 12h15m-5-5 5 5-5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  leaf: '<path d="M20 3C9 2 2 7 5 15c3 8 14 4 15-12ZM4 21 16 9"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.book}</svg>`;
const { escapeHtml: h, moneyText, intText } = globalThis.RebirthCore;
const yuan = (value) => value === null || value === undefined ? "待核实" : new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(Number(value));
const badge = (text, tone = "") => `<span class="tag ${tone}">${h(text)}</span>`;
const button = (text, action, kind = "primary", extra = "") => `<button type="button" class="button ${kind}" data-action="${action}" ${extra}>${h(text)}</button>`;
const roleLabel = (role) => role === 'host' ? '系统归档' : roles[role] || role;
const shopArt = `<svg class="store-art" viewBox="0 0 240 190" aria-hidden="true"><ellipse cx="125" cy="174" rx="100" ry="8" fill="#d5dfc7"/><path d="M45 67h142v102H45z" fill="#f6f8ec" stroke="#8d9e7a" stroke-width="2"/><path d="M37 67h158l-15-34H52z" fill="#c4d1af" stroke="#8d9e7a" stroke-width="2"/><path d="M52 34h128v-9H52z" fill="#f5f8eb" stroke="#8d9e7a" stroke-width="2"/><path d="M37 67v10q10 16 22 0 12 16 23 0 12 16 23 0 12 16 23 0 12 16 23 0 12 16 23 0 12 16 21 0V67" fill="#e8edda" stroke="#8d9e7a" stroke-width="2"/><path d="M59 101h65v43H59zM140 100h33v69h-33z" fill="#dfe8d1" stroke="#8d9e7a" stroke-width="2"/><path d="M91 101v43M59 123h65M155 134h3M37 170h159" fill="none" stroke="#8d9e7a" stroke-width="2"/><path d="M202 165v-40M200 142q-22-3-19-21 20-1 20 15M204 132q22-4 18-23-20 2-19 18" fill="#b7c99e" stroke="#8d9e7a" stroke-width="2"/><path d="M190 165h24l-4 10h-16z" fill="#d3dfbd" stroke="#8d9e7a" stroke-width="2"/><path d="M17 105h13M23 99v12M209 48h13M215 42v12" stroke="#a8b88f" stroke-width="2"/></svg>`;

async function api(path, data) {
  const headers=globalThis.RebirthHosted?{'X-Rebirth-Account':globalThis.RebirthHosted.userId}:{};
  const response = await fetch(path, data === undefined ? { cache: "no-store", headers } : { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const body = await response.json();
  if(response.status===401||body.account_changed)globalThis.RebirthHosted?.sessionProblem(!!body.account_changed);
  else if(response.ok)globalThis.RebirthHosted?.sessionRestored();
  if (!response.ok) { const error=new Error(body.error || body.message || "操作未完成，请稍后重试"); error.status=response.status; throw error; }
  return body;
}
let toastTimer;
function toast(message) { const el = $("#toast"); el.textContent = message; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4800); }
function remember(id) { try { localStorage.setItem("rebirth_merchant", id); } catch {} }
function remembered() { try { return localStorage.getItem("rebirth_merchant"); } catch { return null; } }
function setView(view) {
  state.view = Object.prototype.hasOwnProperty.call(titles,view) ? view : "overview";
  $$(".view").forEach(el => { el.hidden = el.id !== `view-${state.view}`; });
  $$(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.view === state.view));
  $("#page-title").textContent = titles[state.view];
  if (location.hash !== `#${state.view}`) history.replaceState(null, "", `#${state.view}`);
}
function busyBox() { return taskProgressBox(); }
function noShop() { return `<div class="empty-state empty-wide">${icon("store")}<h3>先让我们了解你的小店</h3><p>添加店铺资料后，就能检查库存、梳理现金与待付款。也可以先体验一份合成示例。</p><div class="hero-actions inline-flex">${button("添加我的店铺", "new-shop")}${button("体验示例店铺", "example", "secondary")}</div></div>`; }
function metric(label, value, unit, hint, symbol) { return `<div class="metric"><div class="metric-top"><span>${h(label)}</span><span class="metric-symbol">${icon(symbol)}</span></div><div class="metric-value number">${h(value)}<span class="metric-unit">${h(unit)}</span></div><small>${h(hint)}</small></div>`; }
function heading(title, text = "", actions = "") { return `<div class="title-actions"><div class="intro-head"><h1>${h(title)}</h1><p>${h(text)}</p></div><div class="inline-flex">${actions}</div></div>`; }
function agentsPanel() { return `<div class="panel"><div class="panel-title"><div><h3>小店的经营协作团队</h3><p>从不同角度检查同一个决定</p></div>${badge("本地规则")}</div><div class="agent-list">${Object.entries(roles).map(([role, name]) => `<div class="agent-line"><div class="agent-avatar">${icon(roleIcons[role])}</div><div><strong>${name}</strong><p>${{ coordinator: "整理问题，协调分歧与待办", inventory: "核对库存、成本与尺码", customer: "检查需求线索与待验证假设", cash: "检查投入、付款与现金底线" }[role]}</p></div></div>`).join("")}</div><div class="note-box">当前使用可核查的本地规则。接入AgentArts后，才会启用真正的大模型智能体。</div></div>`; }

function renderOverview() {
  const l = state.merchant;
  const questions = state.readiness?.questions || [];
  const total = l ? l.products.reduce((n, p) => n + p.stock, 0) : "—";
  const slow = state.inventory?.products.filter(p => p.slow_moving).length ?? "—";
  const name = l ? l.name.replace("（合成测试，不是真实商户）", "") : "把小店的下一步，看得更清楚";
  $("#view-overview").innerHTML = `<div class="hero"><div><span class="eyebrow">A LITTLE CLARITY. A STEADIER STEP.</span><h1>${h(name)}</h1><p>${l ? "先看清库存、顾客和资金之间的关系，再决定哪些改变值得小步尝试。" : "从日常账目里理清经营问题，让每一份投入，都更有依据。"}</p><div class="hero-actions">${l ? button("开始经营核查", "analyze", "primary", state.busy ? "disabled" : "") + button("完善店铺资料", "edit-shop", "secondary") : button("添加我的店铺", "new-shop") + button("体验示例店铺", "example", "secondary")}</div></div>${shopArt}</div>
    <div class="metric-grid">${metric("当前可用现金", l ? "¥ " + yuan(l.cash_balance) : "—", "", l ? `底账日期 ${l.as_of}` : "填写后查看资金情况", "wallet")}${metric("已登记商品库存", total, l ? "件" : "", "按录入商品合计", "box")}${metric("需要留意的商品", slow, l ? "类" : "", "仅按库存年龄和销量筛查", "search")}${metric("待补充的资料", l ? questions.length : "—", l ? "项" : "", "把不确定的地方先问清楚", "book")}</div>
    <div class="two-column"><div><div class="panel"><div class="panel-title"><div><h3>今天，从哪一步开始？</h3><p>不用懂复杂报表，按顺序来就好</p></div>${badge(l ? "资料已保存" : "等待建档")}</div><div class="steps"><div class="step"><span class="step-num">1</span>了解店铺</div><div class="step"><span class="step-num">2</span>看清问题</div><div class="step"><span class="step-num">3</span>小步复盘</div></div>${l ? `<div class="empty-state">${icon(questions.length ? "book" : "check")}<h3>${questions.length ? `还有 ${questions.length} 项资料需要核对` : "基本资料已经齐全"}</h3><p>${questions.length ? "不确定的成本、客户反馈和待付款会影响判断。我们会逐项说明需要补充什么。" : "可以进行本地核查。资料完整并不代表经营假设已经得到验证。"}</p>${button(questions.length ? "查看待补资料" : "查看经营分析", questions.length ? "go-ledger" : "go-analysis", "secondary")}</div>` : `<div class="empty-state">${icon("store")}<h3>每一家小店，都有自己的经营节奏</h3><p>先记录现金、商品和近期付款。没有完整账本，也可以从已知的部分开始。</p>${button("用示例了解操作", "example", "secondary")}</div>`}</div><div class="callout">${icon("leaf")}<div><strong>先弄清楚，再做决定</strong>这里的方案是待验证的经营假设，不是收益承诺。资金紧张时，允许先停下来核对。</div></div></div>${agentsPanel()}</div>`;
}

function renderLedger() {
  const l = state.merchant;
  if (!l) { $("#view-ledger").innerHTML = heading("店铺资料", "清楚的经营记录，是可靠分析的起点。") + noShop(); return; }
  const rows = l.products.map(p => `<tr><td><strong>${h(p.name)}</strong><br><small class="muted">${h(p.sku)}</small></td><td>${p.stock} 件</td><td>${p.sales_30d} 件</td><td>${p.unit_cost === null ? badge("待核实", "amber") : "¥ " + yuan(p.unit_cost)}</td><td>${p.unit_price === null ? badge("待核实", "amber") : "¥ " + yuan(p.unit_price)}</td><td>${p.size_complete === null ? badge("待核实", "amber") : badge(p.size_complete ? "满足需求" : "存在缺码", p.size_complete ? "" : "amber")}</td></tr>`).join("");
  $("#view-ledger").innerHTML = heading("店铺资料", "先记录已知的事实，未知的地方可以继续补充。", button("编辑店铺资料", "edit-shop", "secondary")) + `<div class="panel"><div class="panel-title"><div><h3>${h(l.name)}</h3><p>记录日期 ${h(l.as_of)} · ${l.synthetic ? "合成示例，不能作为真实经营证据" : "商户在本机填写的经营资料"}</p></div>${badge(l.synthetic ? "合成示例" : "店铺资料", l.synthetic ? "amber" : "")}</div><div class="summary-list"><div>可用现金<strong>¥ ${yuan(l.cash_balance)}</strong></div><div>希望保留的现金<strong>¥ ${yuan(l.reserve_floor)}</strong></div><div>试验投入上限<strong>¥ ${yuan(l.max_trial_budget)}</strong></div></div><p>当前想解决：${h(l.goal)}</p><div class="check-list">${Object.entries({ inventory_complete: "库存记录", obligations_complete: "待付款记录", receivables_complete: "待收款记录" }).map(([key, label]) => `<span>${l.completeness[key] ? "✓" : "○"} ${label}${l.completeness[key] ? "已核对完整" : "仍待核对"}</span>`).join("")}</div></div>
    <div class="section-head"><h2>商品与库存</h2><span class="muted">${l.products.length} 类商品</span></div><div class="panel table-wrap"><table><thead><tr><th>商品</th><th>库存</th><th>近30天销售</th><th>采购单价</th><th>当前标价</th><th>尺码情况</th></tr></thead><tbody>${rows || '<tr><td colspan="6">尚未登记商品，点击上方编辑补充。</td></tr>'}</tbody></table></div>
    <div class="section-head"><h2>需要补充与核对</h2><span class="tag">${state.readiness.questions.length} 项待办</span></div>${state.readiness.questions.length ? state.readiness.questions.map(questionCard).join("") : '<div class="panel">基本资料已核对。后续经营中的变化，请及时回到“编辑店铺资料”更新。</div>'}
    <div class="section-head"><h2>近期收支与客户观察</h2></div><div class="two-column"><div class="panel"><h3>待付款与待收款</h3><div class="table-wrap mini-table"><table><thead><tr><th>类型</th><th>记录</th><th>日期</th><th>金额</th></tr></thead><tbody>${[...l.obligations.map(x => ({ ...x, label: "待付款" })), ...l.receivables.map(x => ({ ...x, label: "待收款" }))].map(x => `<tr><td>${x.label}</td><td>${h(x.label_text || x.id)}</td><td>${h(x.date)}</td><td>¥ ${yuan(x.amount)}</td></tr>`).join("") || '<tr><td colspan="4">尚无录入记录；请核对是否确实没有。</td></tr>'}</tbody></table></div></div><div class="panel"><h3>顾客实际说过什么</h3>${l.customer_signals.map(x => `<p>${h(x.observation)}</p>`).join("") || '<p>还没有记录客户反馈，不会替顾客猜测需求。</p>'}</div></div>`;
}
function questionCard(q) {
  const field = q.value_type === "boolean" ? '<select name="value" class="field" required><option value="">请选择核对结果</option><option value="true">是，已核对确认</option><option value="false">否，暂不能确认</option></select>' : `<input name="value" class="field" ${q.value_type === "money" ? 'type="number" min="0" step="0.01"' : q.value_type === "integer" ? 'type="number" min="0" step="1"' : 'type="text" maxlength="1000"'} required placeholder="${q.value_type === "money" ? "填写金额，单位元" : q.value_type === "integer" ? "填写核对后的净销售件数" : "填写一条实际观察"}">`;
  return `<form class="question-card answer-form" data-question-id="${h(q.id)}" data-value-type="${h(q.value_type)}">${badge(roleLabel(q.owner))}<h3>${h(q.question)}</h3><p>${h(q.reason)}</p><div class="answer-fields"><label class="form-label">核对结果${field}</label><label class="form-label">依据什么核对<input name="source_note" class="field" required maxlength="1000" placeholder="例如：采购单、收银记录、与店主核对"></label><button class="button secondary" type="submit">保存回答</button></div><p class="form-error" hidden></p></form>`;
}

function renderAnalysis() {
  if (!state.merchant) { $("#view-analysis").innerHTML = heading("经营分析", "从账面事实开始，保留尚未得到验证的假设。") + noShop(); return; }
  const actions = analysisControls() + button("重新核查", "analyze", "primary", state.busy ? "disabled" : "");
  const head = heading("经营分析", "围绕商品、客户与现金，检查一次经营行动是否站得住。", actions);
  if (state.busy) { $("#view-analysis").innerHTML = head + busyBox(); return; }
  const r = state.report;
  if (!r) { $("#view-analysis").innerHTML = head + `<div class="panel empty-state">${icon("search")}<h3>资料已保存，开始一次本地核查</h3><p>不会调用云服务。系统会检查库存与现金条件，列出尚需补充的资料。</p>${button("开始经营核查", "analyze")}</div>` + agentsPanel(); return; }
  const result = r.result || {};
  const findings = result.investigations || {};
  const choose = `<select class="field report-select" id="report-select" aria-label="查看历史分析">${state.runs.map(run => `<option value="${h(run.id)}" ${run.id === r.run_id ? "selected" : ""}>${h(new Date(run.created_at).toLocaleString("zh-CN"))} · ${run.mode === "rules" ? "本地核查" : "云端任务"}${run.status === "failed" ? "（失败）" : ""}</option>`).join("")}</select>`;
  const changed = (r.ledger_changed || r.context_changed ? '<p class="note-box amber">底账、知识、调查或时间有效的历史反馈已变化（或旧任务缺少上下文快照）。这份分析不会被重写，请重新核查后再参考。</p>' : "") + renderFactChanges(r.ledger_snapshot,state.merchant);
  if (["running","failed","cancelled","interrupted"].includes(r.status)) { $("#view-analysis").innerHTML = head + choose + changed + `<div class="connection-error">任务${r.status === "cancelled" ? "已取消" : "未完成"}，没有生成可用结论。${h(result.error_message || "请核对资料与连接状态后重试")}</div>`; return; }
  const cards = ["inventory", "customer", "cash"].map(role => {
    const rows=findings[role]?.findings||[],evidence=[...new Set(rows.flatMap(f=>f.evidence_ids||[]))];
    return `<article class="agent-card"><header><div class="agent-avatar">${icon(roleIcons[role])}</div><div><h3>${roleLabel(role)}</h3><small>根据你填写的资料检查</small></div></header>${rows.map(f=>`<div class="finding">${badge(f.kind==='hypothesis'?'可能的原因，还要核实':'从已填资料看到的情况',f.kind==='hypothesis'?'amber':'')}<p>${h(merchantFinding(f.statement))}</p></div>`).join('')||'<p class="muted">目前没有更多提醒。资料不全时，仍需先核对。</p>'}${evidenceDetails(evidence)}${(findings[role]?.historical_followups||[]).map(q=>`<p class="note-box">还要弄清楚：${h(q.question)}</p>`).join('')}</article>`;
  }).join('');
  const coordinator = `<article class="agent-card"><header><div class="agent-avatar">${icon("team")}</div><div><h3>经营协调</h3><small>管理资料、版本与未解决问题</small></div></header><div class="finding"><p>本次记录了 ${r.events.length} 条调查、工具及协作事件，进行了 ${result.revision_rounds || 0} 轮修订。</p>${result.collaboration ? `<p>其中 ${Number(result.collaboration.material_revisions)||0} 次修改了方案内容，${Number(result.collaboration.unchanged_revisions)||0} 次未改变方案内容；重算后消除了 ${Number(result.collaboration.resolved_check_count)||0} 项约束问题。请按最新版本查看方案，未解决的条件仍需核对。</p>` : ""}</div><div class="finding"><p>${result.readiness?.questions?.length || 0} 项资料仍待核对。${result.plans_are_alternatives ? "下方方案为备选项，不能直接叠加执行。" : ""}</p></div><div class="note-box">${r.mode === "agentarts" ? "本次由华为AgentArts智能体协同分析，工具计算与证据校验由系统执行。" : "本次使用内置规则核查，未调用大模型。"}</div></article>`;
  $("#view-analysis").innerHTML = head + `<div class="result-banner"><span>${r.mode === "agentarts" ? "华为 AgentArts 多智能体分析" : "内置规则核查"} · 底账日期 ${h(r.ledger_as_of || state.merchant.as_of)}</span>${choose}</div>` + changed + `<div class="agent-grid">${cards}${coordinator}</div><div class="section-head"><div><h2>可供讨论的经营假设</h2><p>先看成立条件，再考虑是否开展小范围验证。</p></div>${badge(`${result.proposals?.length || 0} 个备选`)}</div>${result.proposals?.length ? `<div class="plans-grid">${result.proposals.map(planCard).join("")}</div>` : '<div class="panel"><h3>目前没有形成符合条件的提案</h3><p>可能缺少客户线索、可售商品或可确认的额外投入空间。请先核对店铺资料中的待办。</p>' + button("补充店铺资料", "go-ledger", "secondary") + '</div>'}<div class="note-box">所有销量都是明示假设，情景推演不代表未来预测。已有库存成本计入毛利，但不会重复扣减已支付的现金。</div>`;
}
function merchantFinding(text){
  const phrases=[
    ['同一固定客群、相同时长观察窗的复购比例下降，需调查未复购原因','对比同一批老顾客在两段同样长的时间里，再次购买的比例下降。需要问问他们为什么没再来'],
    ['固定客群：','老顾客再次购买的情况：'],
    ['日均经营贡献','每天营业额减去商品成本和已填费用后的余额'],
    ['日均营业额','平均每天的营业额'],['日均到店人次','平均每天到店的人次'],
    ['到店成交比例','到店顾客中实际买东西的比例'],['统计口径','记账范围'],
    ['老客成交占比较前期下降；占比不是流失率；需要客户分组与自愿回访证据。','成交顾客中，老顾客所占比例比前一段时间少了。也可能是新客变多，不能就认定老客流失；要再看老顾客记录或询问本人。'],
    ['在当前明示订单假设下无法覆盖本期成本','如果只卖出填写的这些订单，收入还不够支付这段时间的成本'],
    ['能力尚待补齐：预约协调','还没确认能否安排好预约，需要先核实人手和时间'],
    ['不是盈利判断','这不代表已经赚到钱']
  ];
  let result=globalThis.RebirthCore.merchantText(text);for(const [before,after] of phrases)result=result.replaceAll(before,after);return result;
}
function evidenceDetails(ids, report=state.report) {
  const events = report?.events || [];
  const lines = [];
  for (const id of ids) {
    const event = events.find(e => e.id === id && e.kind === "tool_result");
    if (!event) { lines.push("这条依据暂未找到，不能补造。请重新核查。"); continue; }
    const { tool, value } = event.data;
    if (tool === "inventory_analyze") {
      for (const row of value.products) {
        const product=(report?.ledger_snapshot?.products||state.merchant?.products||[]).find(p=>p.sku===row.sku);
        lines.push(`${product?.name||'未命名商品'}（商品编号：${row.sku}）：现在还剩${row.stock}件，最近30天卖了${row.sales_30d}件，从进货到这份账的日期已过${row.age_days}天。${row.size_complete === null ? '还没确认顾客要的尺码是否齐全。' : row.size_complete ? '已记录：顾客需要的尺码齐全。' : '有些尺码缺货，需要先确认顾客想买哪一款、哪个尺码。'}`);
        if(row.slow_moving)lines.push(`为什么提醒查看这件货：它已经进货至少90天，剩下的数量也超过最近30天卖出数量的两倍。请先核对实物和进货单，再决定是否处理；这不能说明卖得慢的原因，也不等于应该马上降价。`);
      }
      lines.push('这里比较的是你填写的库存和销量。没有被提醒的商品，也不代表一定好卖；资料过期或没填全时，请先更新。');
    } else if (tool === "cash_baseline") {
      lines.push(`可用现金 ¥${yuan(value.cash_balance)} − 保留额 ¥${yuan(value.reserve_floor)} − 30天内必要付款 ¥${yuan(value.obligations_30d_including_overdue)}，再受试验预算约束。`);
      lines.push(`保守额外支出上限：¥${yuan(value.conservative_budget_ceiling)}。${value.note}`);
    } else if (tool === "customer_evidence") {
      lines.push(...value.observations.map(x => x.observation));
      if (!value.observations.length) lines.push("尚无客户观察记录。");
    } else if (tool === "feedback_history") lines.push(`使用${value.outcomes.length}份同店、时间有效的既往反馈。`);
    else if (tool === "business_diagnostics") { for (const p of value.periods) lines.push(`${p.start}至${p.end}，共${p.days}天：平均每天营业额${p.revenue_per_day==null?'还没算清':p.revenue_per_day+'元'}；减去商品成本和已填费用后，每天剩${p.contribution_per_day==null?'还没算清':p.contribution_per_day+'元'}（负数表示这些支出比收入多）。记录来自：${report?.ledger_snapshot?.sources?.[p.source_id] || p.source_id}`); lines.push('只比较最近两段时间，先除以天数再比较。这里没包含所有可能的税费，不是最终净利润。季节、营业时间或记账范围不同都会影响数字，不能仅凭下降就确定原因。'); }
    else if (tool === "customer_retention") { for (const r of value.windows) lines.push(`${r.label}（${r.cohort_id}），${r.start}至${r.end}：复购去重人数${r.retained ?? "待核实"} / 固定基准${r.base_size}；复购比例${r.retention ?? "待核实"}；本窗未复购${r.not_repeated ?? "待核实"}；来源：${r.source_note}`); for (const f of value.findings) lines.push(f.statement); lines.push(value.notice); }
    else if (tool === "business_model_compare") { for(const r of value.rows)lines.push(`${r.model.name}：渠道${r.model.channel}；交付${r.model.fulfilment}；每单贡献${r.assessment.unit_contribution??"待核实"}；${r.model.period_days}天保本订单${r.assessment.break_even_orders??"待核实"}；工时与成本问题见草案复核。`);lines.push(value.notice); }
    else if (tool === "business_model_assess") { for (const r of value.models) lines.push(`${r.model.name}：单位贡献${r.unit_contribution ?? "待核实"}；保本订单${r.break_even_orders ?? "待核实"}；来源：${r.model.source_note}`); lines.push(value.notice); }
    else if (tool === "accounts_reconcile") { lines.push(`流水收入${value.incoming}；流水支出${value.outgoing}；推算期末${value.closing ?? "待核实"}；与底账差额${value.balance_difference ?? "待核实"}。`); lines.push(...value.warnings, value.notice); }
    else if (tool === "knowledge_search") { for (const d of value.matches) lines.push(`${d.title}（${d.id}）：${d.content}；来源：${d.source}`); lines.push(value.method); }
    else if (tool === "proposal_evaluate") { lines.push(`方案${value.proposal_id}的申报支出${value.trial_cash_commitment}元；硬约束${value.checks.length}项，未知${value.unknowns.length}项；不等于批准执行。`); }
    else if (tool === "investigation_history") { for(const card of value.cards) lines.push(`待查假设：${card.hypothesis}；支持：${card.supporting || "暂无"}；反例：${card.counter || "暂无"}；来源：${card.source_note}；下一步：${card.next_check}`); lines.push(value.note); }
    else if (tool === "data_readiness") lines.push(`仍有${value.questions.length}项资料需要补充或核对。`);
  }
  return lines.length ? `<details class="evidence-details"><summary>为什么这样提醒？看具体数字</summary><ul class="detail-list">${lines.map(text => `<li>${h(text)}</li>`).join("")}</ul></details>` : "";
}
const checkNames = { SALES_WINDOW_STALE:"近30天销量统计已过期，请按底账日期重新核对", SUPPLY_MINIMUM:"未达到供应起订量", SUPPLY_CAPACITY:"补货超过核实可供数量", SUPPLY_OUTSIDE_HORIZON:"到货或付款超出本次30天范围", SUPPLY_DATA_REQUIRED:"供应条件或费用尚未核实", MODEL_BINDING_REQUIRED: "方案需关联当前有效的经营模式版本", UNRECONCILED_ACCOUNTS: "采购或收支账簿尚未核对一致，请先核账", BUDGET_EXCEEDED: "超过试验预算", CASH_RESERVE_BREACH_ZERO_SALES: "零销量情景下现金低于保留额", STOCK_EXCEEDED: "商品数量超出库存", SIZE_EVIDENCE_REQUIRED: "尺码需进一步核实", UNKNOWN_SKU: "商品未登记", WORKLOAD_EXCEEDED: "超出可用时间" };
function planCard(entry, index) {
  const p = entry.proposal, e = entry.evaluation;
  const decision = RebirthCore.proposalDecision(e);
  return `<article class="plan">${badge(roleLabel(p.owner))} ${badge(`第 ${p.version} 版`)}<h3>${h(merchantFinding(p.title))}</h3><div class="note-box ${decision.kind==='review'?'':'amber'}"><strong>${h(decision.title)}</strong><p>${h(decision.detail)}</p></div><p>${h(merchantFinding(p.rationale))}</p>${renderExpenseBreakdown(p)}${e.cash_cost_breakdown?`<details><summary>这次要花的钱与商品成本怎样区分</summary><p>前置额外费用 ¥${yuan(e.cash_cost_breakdown.upfront_extra)}；单件额外费用合计 ¥${yuan(e.cash_cost_breakdown.variable_extra)}；新增采购承诺 ¥${yuan(e.cash_cost_breakdown.new_procurement)}。</p><p>已知已售商品成本 ¥${yuan(e.cash_cost_breakdown.sold_goods_cost)}，用于毛利核算。${h(e.cash_cost_breakdown.notice)}</p></details>`:""}<div class="plan-metrics"><div><span>申报试验支出</span><strong>¥ ${yuan(e.trial_cash_commitment)}</strong></div><div><span>每周所需时间</span><strong>${p.weekly_hours} <small>小时</small></strong></div><div><span>假设销售额</span><strong>¥ ${yuan(e.declared_revenue)}</strong></div></div>${e.checks.length ? e.checks.map(x => `<div class="note-box amber">${h(checkNames[x.code] || x.code)}</div>`).join("") : badge("所录条件未触及硬约束")}<details><summary>查看仍待核实的条件（${e.unknowns.length}项）</summary><ul class="detail-list">${e.unknowns.map(x => `<li>${h(merchantFinding(x))}</li>`).join("")}</ul></details><details><summary>比较现金情景</summary><div class="table-wrap"><table class="mini-table"><thead><tr><th>销量假设</th><th>最低现金</th><th>期末现金</th></tr></thead><tbody>${e.scenarios.map(x => `<tr><td>${{ zero_sales: "零销量", half_sales: "一半件数", declared_sales: "申报件数" }[x.scenario] || h(x.scenario)}</td><td>¥ ${yuan(x.minimum_cash_before_receipts)}</td><td>¥ ${yuan(x.ending_cash)}</td></tr>`).join("")}</tbody></table></div></details><details><summary>商品范围与停止条件</summary><ul class="detail-list">${p.items.map(i => `<li>${h(state.merchant.products.find(x => x.sku === i.sku)?.name || i.sku)}：${i.quantity} 件，假设成交单价 ¥ ${yuan(i.price)}</li>`).join("")}${p.stop_conditions.map(x => `<li>${h(merchantFinding(x))}</li>`).join("")}</ul></details><p>开展行动需自行核实；此按钮只记录已经发生的结果。</p>${button("记录实际反馈", "open-feedback", "secondary", `data-plan-index="${index}" `)}</article>`;
}

function renderFeedback() {
  const head = heading("行动与复盘", "记录真实发生的销售与费用，给下一次判断留下依据。", state.report?.result?.proposals?.length ? button("查看可记录的方案", "go-analysis", "secondary") : "");
  if (!state.merchant) { $("#view-feedback").innerHTML = head + noShop(); return; }
  const history = state.outcomes.map(f => `<article class="feedback-card"><div class="panel-title"><div><h3>${h(roleLabel(f.owner))} · 行动反馈</h3><p>截至 ${h(f.period_end)} · 第 ${f.proposal_version} 版方案</p></div>${badge(f.synthetic ? "合成反馈" : "商户记录", f.synthetic ? "amber" : "")}</div><div class="summary-list"><div>扣除退款后的收款<strong>¥ ${yuan(f.net_cash_received)}</strong></div><div>实际试验支出<strong>¥ ${yuan(f.actual_trial_spend)}</strong></div><div>试验净现金<strong class="${Number(f.trial_net_cash) < 0 ? "negative" : ""}">¥ ${yuan(f.trial_net_cash)}</strong></div><div>试验毛利贡献<strong class="${Number(f.trial_margin_contribution) < 0 ? "negative" : ""}">${f.trial_margin_contribution === null ? "待核实" : "¥ " + yuan(f.trial_margin_contribution)}</strong></div></div>${f.follow_up_questions.map(q => `<p><span class="tag">${h(roleLabel(q.owner))}</span> ${h(q.question)}</p>`).join("")}${f.observations.map(x => `<p>实际观察：${h(x)}</p>`).join("")}<div class="note-box">${h(f.interpretation)}</div></article>`).join("");
  $("#view-feedback").innerHTML = head + (history || `<div class="panel empty-state">${icon("book")}<h3>还没有行动反馈</h3><p>先完成一次经营分析。若你实际开展了其中一个行动，再记录销售、支出和退货；未发生的数据不要猜测填写。</p>${button("前往经营分析", "go-analysis", "secondary")}</div>`) + '<div class="callout">' + icon("leaf") + '<div><strong>把“收到钱”和“赚到钱”分开看</strong>试验有回款，也可能在计入库存成本和费用后出现负贡献。反馈不会自动改动你的库存或现金底账。</div></div>';
}

function render() {
  const select = $("#merchant-select");
  select.innerHTML = state.merchants.length ? state.merchants.map(m => `<option value="${h(m.merchant_id)}">${h(m.name)}${state.merchants.filter(x => x.name === m.name).length > 1 ? " · " + h(m.merchant_id.slice(-6)) : ""}</option>`).join("") : '<option value="">尚未添加店铺</option>';
  select.value = state.merchant?.merchant_id || "";
  select.disabled = state.busy;
  $("#new-shop-button").disabled = state.busy;
  $("#data-tag").innerHTML = state.merchant ? badge(state.merchant.synthetic ? "合成示例" : "本机资料", state.merchant.synthetic ? "amber" : "") : "";
  renderOverview(); renderLedger(); renderAnalysis(); renderFeedback(); renderExtras(); setView(state.view);
}

async function selectMerchant(id, reportId) {
  const root = `/api/merchants/${encodeURIComponent(id)}`;
  const [l, q, runs, outcomes, baseline, inventory] = await Promise.all([api(root), api(root + "/questions"), api(root + "/runs"), api(root + "/feedback"), api(`/api/tools/${encodeURIComponent(id)}/cash_baseline`, {}), api(`/api/tools/${encodeURIComponent(id)}/inventory_analyze`, {})]);
  const selectedRun = reportId || runs.runs[0]?.id;
  const report = selectedRun ? await api(root + "/runs/" + encodeURIComponent(selectedRun)) : null;
  Object.assign(state, { merchant: l, readiness: q, runs: runs.runs, outcomes: outcomes.outcomes, baseline, inventory, report });
  await loadExtras(id);
  remember(id); render();
}
function merchantChoices(rows, explicitId=null) { return rows.filter(m=>!m.synthetic || globalThis.RebirthHosted?.demoOnly || m.merchant_id===explicitId); }
async function reloadMerchants(id, reportId) { state.merchants = merchantChoices((await api("/api/merchants")).merchants,id); if (id) await selectMerchant(id, reportId); else render(); }
async function example() {
  const l = await api("/api/example");
  const existing = state.merchants.find(m => m.merchant_id === l.merchant_id);
  if (!existing) await api("/api/ledgers", l);
  await reloadMerchants(l.merchant_id); toast("已打开合成示例，不代表真实商户数据");
}
async function analyze() {
  await requestAnalysis();
}

const labelInput = (label, name, value, attrs = "", hint = "") => `<label class="form-label">${h(label)}<input class="field" name="${name}" value="${h(value)}" ${attrs}>${hint ? `<small>${h(hint)}</small>` : ""}</label>`;
function productRow(p = {}) {
  const mobileLabels=["商品名称", "剩余件数", "近30天卖出件数", "进货日期", "采购单价（元）", "标价（元）", "尺码是否齐全", "移除这件商品"];let cell=0;
  return `<tr class="product-row" data-sku="${h(p.sku || "SKU_" + crypto.randomUUID().replaceAll("-", "").slice(0, 10))}"><td><input class="field product-name" name="product_name" required maxlength="100" value="${h(p.name)}" placeholder="例如：基础外套" aria-label="商品名称"></td><td><input class="field" name="stock" type="number" min="0" step="1" required value="${h(p.stock)}" aria-label="库存件数"></td><td><input class="field" name="sales_30d" type="number" min="0" step="1" required value="${h(p.sales_30d)}" aria-label="近30天销售件数"></td><td><input class="field" name="received_on" type="date" required value="${h(p.received_on)}" aria-label="入库日期"></td><td><input class="field" name="unit_cost" type="number" min="0" step="0.01" value="${h(p.unit_cost)}" placeholder="待核实" aria-label="采购单价"></td><td><input class="field" name="unit_price" type="number" min="0" step="0.01" value="${h(p.unit_price)}" placeholder="待核实" aria-label="标价"></td><td><select class="field" name="size_complete" aria-label="尺码情况"><option value="" ${p.size_complete == null ? "selected" : ""}>待核实</option><option value="true" ${p.size_complete === true ? "selected" : ""}>满足需求</option><option value="false" ${p.size_complete === false ? "selected" : ""}>有缺码</option></select></td><td><button class="remove-row" data-action="remove-row" type="button" aria-label="移除此商品">×</button></td></tr>`.replace(/<td>/g,()=>`<td data-label="${h(mobileLabels[cell++])}">`);
}
function paymentRow(p = {}) {
  const mobileLabels=["待付还是待收", "款项说明", "收付日期", "金额（元）", "移除这笔记录"];let cell=0;
  return `<tr class="payment-row" data-id="${h(p.id || "pay_" + crypto.randomUUID().replaceAll("-", "").slice(0, 10))}"><td><select class="field" name="payment_type" aria-label="收支类型"><option value="obligations" ${p.type !== "receivables" ? "selected" : ""}>待付款</option><option value="receivables" ${p.type === "receivables" ? "selected" : ""}>待收款</option></select></td><td><input class="field product-name" name="label_text" value="${h(p.label_text || p.id || "")}" required placeholder="例如：房租" aria-label="款项说明"></td><td><input class="field" name="payment_date" type="date" required value="${h(p.date)}" aria-label="收付日期"></td><td><input class="field" name="payment_amount" type="number" min="0" step="0.01" required value="${h(p.amount)}" aria-label="款项金额"></td><td><button type="button" class="remove-row" data-action="remove-row" aria-label="移除此记录">×</button></td></tr>`.replace(/<td>/g,()=>`<td data-label="${h(mobileLabels[cell++])}">`);
}
function openEditor(editing = false) {
  if (state.busy) { toast("正在进行本地核查，请稍后再修改资料"); return; }
  const l = editing ? state.merchant : null;
  state.editing = l;
  $("#editor-title").textContent = l ? "编辑店铺资料" : "添加店铺资料";
  const today = new Date().toLocaleDateString("sv-SE");
  $("#ledger-form").innerHTML = `<div class="form-body"><div class="form-section"><h3><span class="section-index">01</span> 先说说你的店</h3><div class="form-grid">${labelInput("店铺名称", "name", l?.name || "", 'required maxlength="100" placeholder="例如：街角小店"')}${labelInput("这份记录截至哪天", "as_of", l?.as_of || today, 'type="date" required')}${l ? `<label class="form-label">资料来源<input class="field" readonly value="${l.synthetic ? '演示数据，不能当作实际店铺资料' : '我的店铺资料'}"></label>` : `<label class="form-label">资料性质<select class="field" name="synthetic">${globalThis.RebirthHosted?.demoOnly?'':'<option value="false">我的实际经营资料</option>'}<option value="true">模拟案例（不计入真实成效）</option></select></label>`}<label class="form-label span-all">现在最想解决什么问题<textarea name="goal" class="field" required maxlength="1000" placeholder="例如：换季商品积压，希望在不影响房租的情况下尝试改善。">${h(l?.goal)}</textarea></label></div></div>
    <div class="form-section"><h3><span class="section-index">02</span> 可用资金与时间</h3><div class="form-grid">${labelInput("当前可用现金（元）", "cash_balance", l?.cash_balance, 'type="number" min="0" step="0.01" required')}${labelInput("希望至少保留现金（元）", "reserve_floor", l?.reserve_floor, 'type="number" min="0" step="0.01" required')}${labelInput("本次试验最多投入（元）", "max_trial_budget", l?.max_trial_budget, 'type="number" min="0" step="0.01" required')}${labelInput("每周还能投入多少小时", "weekly_available_hours", l?.weekly_available_hours, 'type="number" min="0" max="168" step="1" required')}</div></div>
    <div class="form-section"><h3><span class="section-index">03</span> 商品与库存</h3><p class="form-hint">可以保存店铺后直接上传库存表格，也可以点击下方手动添加商品。未填写的库存不会当作没有库存；不知道的金额不要填0。</p><div class="table-wrap"><table class="editable-table"><thead><tr><th>商品名称</th><th>库存</th><th>近30天销量</th><th>入库日</th><th>采购单价</th><th>标价</th><th>尺码</th><th></th></tr></thead><tbody id="product-rows">${(l?.products || []).map(productRow).join("")}</tbody></table></div><button class="text-button add-row" data-action="add-product" type="button">＋ 再添加一种商品</button><label class="checkbox-line"><input type="checkbox" name="inventory_complete" ${l?.completeness.inventory_complete ? "checked" : ""}>这些库存记录已经核对完整</label></div>
    <div class="form-section"><h3><span class="section-index">04</span> 近期必须付的钱与待收款</h3><div class="table-wrap"><table class="editable-table"><thead><tr><th>类型</th><th>款项说明</th><th>日期</th><th>金额（元）</th><th></th></tr></thead><tbody id="payment-rows">${[...(l?.obligations || []).map(p => ({ ...p, type: "obligations" })), ...(l?.receivables || []).map(p => ({ ...p, type: "receivables" }))].map(paymentRow).join("")}</tbody></table></div><button class="text-button add-row" data-action="add-payment" type="button">＋ 添加收付记录</button><label class="checkbox-line"><input type="checkbox" name="obligations_complete" ${l?.completeness.obligations_complete ? "checked" : ""}>未付货款、房租等必要付款已全部录入（确实没有也可确认）</label><label class="checkbox-line"><input type="checkbox" name="receivables_complete" ${l?.completeness.receivables_complete ? "checked" : ""}>待收款已全部录入（确实没有也可确认）</label></div>
    <div class="form-section"><h3><span class="section-index">05</span> 顾客反馈与记录来源</h3><div class="form-grid two"><label class="form-label">顾客实际说过什么（每行一条，可暂不填）<textarea class="field" name="customer_notes" maxlength="5000" placeholder="例如：有顾客询问能否在下班后预约试衣。">${h(l?.customer_signals.map(x => x.observation).join("\n"))}</textarea></label><label class="form-label">这些资料依据什么填写<textarea class="field" name="source_note" required maxlength="1000" placeholder="例如：10月收银记录、采购单与店主核对。">${l?.synthetic ? "模拟案例资料，不计入真实商户成效" : ""}</textarea></label></div><label class="checkbox-line"><input type="checkbox" name="merchant_confirmed" ${l?.merchant_confirmed ? "checked" : ""}>我已核对上述记录和经营限制；不确定的部分仍保留为待核实</label></div><p id="ledger-error" class="form-error" role="alert" hidden></p></div><div class="dialog-footer"><small>资料仅保存在本机。保存后可继续补充；原有分析快照会保留。</small><div class="inline-flex"><button class="button secondary" type="button" data-close="editor-dialog">取消</button><button class="button primary" type="submit">保存店铺资料</button></div></div>`;
  $("#editor-dialog").showModal();
}
async function saveLedger(form) {
  const f = new FormData(form), previous = state.editing;
  const sourceId = "entry_" + Date.now(), sources = { ...(previous?.sources || {}), [sourceId]: String(f.get("source_note")) };
  const source = { source_id: sourceId };
  const products = $$(".product-row", form).map(row => { const v = name => $(`[name="${name}"]`, row).value; return { sku: row.dataset.sku, name: v("product_name"), stock: intText(v("stock")), sales_30d: intText(v("sales_30d")), received_on: v("received_on"), unit_cost: moneyText(v("unit_cost"), true), unit_price: moneyText(v("unit_price"), true), size_complete: v("size_complete") === "" ? null : v("size_complete") === "true", ...source }; });
  const ledger = { merchant_id: previous?.merchant_id || "shop_" + crypto.randomUUID().replaceAll("-", "").slice(0, 16), name: String(f.get("name")), as_of: String(f.get("as_of")), currency: "CNY", synthetic: previous ? previous.synthetic : f.get("synthetic") === "true", merchant_confirmed: f.has("merchant_confirmed"), goal: String(f.get("goal")), cash_balance: moneyText(f.get("cash_balance")), reserve_floor: moneyText(f.get("reserve_floor")), max_trial_budget: moneyText(f.get("max_trial_budget")), weekly_available_hours: intText(f.get("weekly_available_hours")), sources, products, obligations: [], receivables: [], customer_signals: String(f.get("customer_notes") || "").split("\n").map(x => x.trim()).filter(Boolean).map(observation => ({ observation, ...source })), completeness: Object.fromEntries(["inventory_complete", "obligations_complete", "receivables_complete"].map(k => [k, f.has(k)])) };
  $$(".payment-row", form).forEach(row => { const v = name => $(`[name="${name}"]`, row).value; ledger[v("payment_type")].push({ id: row.dataset.id, label_text: v("label_text"), date: v("payment_date"), amount: moneyText(v("payment_amount")), ...source }); });
  const saved=globalThis.RebirthCore.mergeLedgerForEdit(previous,ledger,sourceId);
  if(previous)saved._expected_digest=await globalThis.RebirthCore.ledgerDigest(previous);
  await api("/api/ledgers", saved); await reloadMerchants(ledger.merchant_id); $("#editor-dialog").close(); if(globalThis.RebirthApp){globalThis.RebirthApp.recordSaved();if(!previous)globalThis.RebirthApp.navigate("ledger",{replace:true,unguarded:true});}else setView("ledger"); toast(previous?"资料已保存，可继续补充或分析":"店铺已建立，接下来上传自己的经营表格");
}

function openFeedback(index, operation = null) {
  const report = state.report;
  if (!report) return;
  const p = report.result.proposals[index]?.proposal;
  if (!p) return;
  const prior = state.extras.journal.entries.filter(e => e.data.run_id === report.run_id && e.data.proposal_id === p.id && e.data.proposal_version === p.version).at(-1)?.summary;
  state.feedbackMeta = prior ? { prior, operation: operation || "checkpoint" } : null;
  state.feedbackPlan = p;
  const max = new Date((report.ledger_as_of || state.merchant.as_of) + "T00:00:00Z"); max.setUTCDate(max.getUTCDate() + 30);
  const iso = max.toISOString().slice(0, 10);
  $("#feedback-form").innerHTML = `<div class="form-body"><div class="note-box">正在记录“${h(p.title)}”第 ${p.version} 版。只填写已实际发生的结果，不会触发任何经营动作。${state.merchant.synthetic ? "当前为合成示例，反馈也会保持合成标记。" : ""}</div><div class="form-section"><div class="form-grid two">${labelInput("从行动开始日累计", "period_start", p.spend_date, 'type="date" readonly required')}${labelInput("记录截止日期", "period_end", "", `type="date" min="${p.spend_date}" max="${iso}" required`)}${labelInput("实际固定支出（元）", "fixed_spend", "", 'type="number" min="0" step="0.01" required placeholder="没有支出请明确填0"')}${labelInput("实际总工时（小时）", "hours_spent", "", 'type="number" min="0" max="744" step="1" required')}</div></div>${p.items.map(i => `<div class="feedback-item" data-sku="${h(i.sku)}"><div class="panel-title"><h4>${h(state.merchant.products.find(x => x.sku === i.sku)?.name || i.sku)} <small class="muted">试验范围 ${i.quantity} 件</small></h4><button class="text-button" data-action="zero-feedback-row" type="button">该商品没有发生交易</button></div><div class="form-grid">${labelInput("实际售出件数", "units_sold", "", `type="number" min="0" max="${i.quantity}" step="1" required`)}${labelInput("退回件数", "units_returned", "", 'type="number" min="0" step="1" required')}${labelInput("退回且可再次销售件数", "units_returned_resellable", "", 'type="number" min="0" step="1" required')}${labelInput("实际收到货款（元）", "cash_received", "", 'type="number" min="0" step="0.01" required')}${labelInput("实际退款（元）", "refund_paid", "", 'type="number" min="0" step="0.01" required')}${labelInput("配送等相关支出（元）", "variable_spend", "", 'type="number" min="0" step="0.01" required')}</div></div>`).join("")}<div class="form-grid two"><label class="form-label">记录来源<textarea class="field" name="source_note" required placeholder="例如：活动收银记录、退款凭证、费用票据"></textarea></label><label class="form-label">实际观察（每行一条，可不填）<textarea class="field" name="observations" placeholder="例如：顾客询问过什么，执行中哪里与原计划不同。"></textarea></label></div><label class="checkbox-line"><input type="checkbox" name="costs_confirmed">我已核对上述费用，没有将未知费用填写为0</label><p id="feedback-error" class="form-error" role="alert" hidden></p></div><div class="dialog-footer"><small>同一方案版本只保存一份累计反馈，提交前请核对。反馈不会自动改动库存与现金底账。</small><div class="inline-flex"><button class="button secondary" type="button" data-close="feedback-dialog">取消</button><button type="submit" class="button primary">保存实际反馈</button></div></div>`;
  hydrateFeedback();
  $("#feedback-dialog").showModal();
}
async function saveFeedback(form) {
  const f = new FormData(form), p = state.feedbackPlan;
  const data = { id: "outcome_" + crypto.randomUUID().replaceAll("-", ""), run_id: state.report.run_id, proposal_id: p.id, proposal_version: p.version, period_start: String(f.get("period_start")), period_end: String(f.get("period_end")), synthetic: state.merchant.synthetic, source_note: String(f.get("source_note")), fixed_spend: moneyText(f.get("fixed_spend")), hours_spent: intText(f.get("hours_spent")), costs_confirmed: f.has("costs_confirmed"), observations: String(f.get("observations") || "").split("\n").map(x => x.trim()).filter(Boolean), items: $$(".feedback-item", form).map(row => { const v = n => $(`[name="${n}"]`, row).value; return { sku: row.dataset.sku, units_sold: intText(v("units_sold")), units_returned: intText(v("units_returned")), units_returned_resellable: intText(v("units_returned_resellable")), cash_received: moneyText(v("cash_received")), refund_paid: moneyText(v("refund_paid")), variable_spend: moneyText(v("variable_spend")) }; }) };
  if(p.procurements?.length){data.procurement_paid=moneyText(f.get("procurement_paid"));data.procurement_expense=moneyText(f.get("procurement_expense"));data.items.forEach(item=>{const row=$$(".feedback-item",form).find(r=>r.dataset.sku===item.sku);item.actual_goods_cost=moneyText($('[name=actual_goods_cost]',row).value,true);});}
  if (state.feedbackMeta) Object.assign(data, { operation: state.feedbackMeta.operation, supersedes_id: state.feedbackMeta.prior.feedback_id, change_reason: String(f.get("change_reason")) });
  await api(`/api/merchants/${encodeURIComponent(state.merchant.merchant_id)}/${state.feedbackMeta ? "feedback-update" : "feedback"}`, data); await selectMerchant(state.merchant.merchant_id, state.report.run_id); $("#feedback-dialog").close(); if(globalThis.RebirthApp)globalThis.RebirthApp.recordSaved();else setView("feedback"); toast("累计反馈已保存，原始记录与更正历史保留");
}

async function guardedSubmit(form, errorSelector, fn) {
  const submit = $('[type="submit"]', form), error = $(errorSelector, form);
  submit.disabled = true; error.hidden = true;
  try { await fn(); } catch (err) { error.textContent = err.message; error.hidden = false; error.scrollIntoView({ block: "nearest" }); } finally { submit.disabled = false; }
}
document.addEventListener("click", async event => {
  const nav = event.target.closest("[data-view]"); if (nav) { setView(nav.dataset.view); return; }
  const closer = event.target.closest("[data-close]"); if (closer) { $("#" + closer.dataset.close).close(); return; }
  const target = event.target.closest("[data-action]"); if (!target || target.disabled) return;
  try {
    switch (target.dataset.action) {
      case "new-shop": openEditor(false); break;
      case "edit-shop": openEditor(true); break;
      case "example": if (state.busy) break; target.disabled = true; await example(); break;
      case "analyze": await analyze(); break;
      case "go-ledger": setView("ledger"); break;
      case "go-analysis": setView("analysis"); break;
      case "add-product": $("#product-rows").insertAdjacentHTML("beforeend", productRow()); break;
      case "add-payment": $("#payment-rows").insertAdjacentHTML("beforeend", paymentRow()); break;
      case "remove-row": target.closest("tr").remove(); break;
      case "open-feedback": openFeedback(Number(target.dataset.planIndex)); break;
      case "zero-feedback-row": $$("input", target.closest(".feedback-item")).forEach(el => { el.value = "0"; }); break;
    }
  } catch (error) { toast(error.message); } finally { target.disabled = false; }
});
$("#new-shop-button").addEventListener("click", () => openEditor(false));
$("#help-button").addEventListener("click", () => { const guide = document.querySelector('#usage-guide [data-comm="guide"]'); if (guide) guide.click(); else $("#help-dialog").showModal(); });
$("#merchant-select").addEventListener("change", async event => { if (!event.target.value) return; try { await selectMerchant(event.target.value); } catch (error) { toast(error.message); } });
document.addEventListener("change", async event => { if (event.target.id === "report-select") { try { await selectMerchant(state.merchant.merchant_id, event.target.value); } catch (error) { toast(error.message); } } });
$("#ledger-form").addEventListener("submit", event => { event.preventDefault(); guardedSubmit(event.target, "#ledger-error", () => saveLedger(event.target)); });
$("#feedback-form").addEventListener("submit", event => { event.preventDefault(); guardedSubmit(event.target, "#feedback-error", () => saveFeedback(event.target)); });
document.addEventListener("submit", async event => {
  const form = event.target.closest(".answer-form"); if (!form) return; event.preventDefault();
  await guardedSubmit(form, ".form-error", async () => { const f = new FormData(form); const value = form.dataset.valueType === "boolean" ? f.get("value") === "true" : form.dataset.valueType === "money" ? moneyText(f.get("value")) : form.dataset.valueType === "integer" ? intText(f.get("value")) : String(f.get("value")); await api(`/api/merchants/${encodeURIComponent(state.merchant.merchant_id)}/answers`, { answers: [{ question_id: form.dataset.questionId, value, source_note: String(f.get("source_note")) }] }); await selectMerchant(state.merchant.merchant_id); if(globalThis.RebirthApp)globalThis.RebirthApp.recordSaved();else setView("ledger"); toast("回答已保存；旧分析不会被静默改写"); });
});
window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
async function boot() {
  $$('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
  state.view = Object.prototype.hasOwnProperty.call(titles,location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  render();
  try { state.merchants = merchantChoices((await api("/api/merchants")).merchants,remembered()); const id = state.merchants.find(m => m.merchant_id === remembered())?.merchant_id || state.merchants[0]?.merchant_id; if (id) { await selectMerchant(id); if(typeof recoverTask==='function')await recoverTask(true); } else render(); }
  catch (error) { state.loadError=error.message; $("#view-" + state.view).insertAdjacentHTML("afterbegin", `<div class="connection-error">暂时无法连接服务，请检查网络后刷新重试。已保存的店铺资料不会因此清空。${h(error.message)}</div>`); }
  finally { state.booting = false; document.dispatchEvent(new Event("rebirth-ready")); }
}
boot();
