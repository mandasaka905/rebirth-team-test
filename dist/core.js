/* Pure input conversion shared by the page and offline unit tests. No network. */
(function (root) {
  "use strict";
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }
  function moneyText(raw, optional = false) {
    const text = String(raw ?? "").trim();
    if (!text && optional) return null;
    if (!/^\d+(\.\d{1,2})?$/.test(text)) throw new Error("金额请填写非负数字，最多保留两位小数");
    const [whole, frac = ""] = text.split(".");
    if (Number(whole) > 1000000000000 || (Number(whole) === 1000000000000 && Number(frac) > 0)) throw new Error("金额超出本地计算支持范围");
    return `${whole.replace(/^0+(?=\d)/, "")}.${frac.padEnd(2, "0")}`;
  }
  function intText(raw) {
    if (!/^\d+$/.test(String(raw))) throw new Error("件数与小时请填写非负整数");
    const value = Number(raw);
    if (!Number.isSafeInteger(value) || value > 1000000) throw new Error("件数超出本地计算支持范围");
    return value;
  }
  function stableJSON(value) {
    if (Array.isArray(value)) return '['+value.map(stableJSON).join(',')+']';
    if (value && typeof value === 'object') return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stableJSON(value[k])).join(',')+'}';
    return JSON.stringify(value);
  }
  async function ledgerDigest(ledger) {
    const bytes = new TextEncoder().encode(stableJSON(ledger));
    const digest = await root.crypto.subtle.digest('SHA-256',bytes);
    return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
  }
  function mergeLedgerForEdit(previous, edited, sourceId) {
    if (!previous) return edited;
    const copy=v=>JSON.parse(JSON.stringify(v)),result=copy(edited);
    for (const k of ['operating_periods','business_models','accounts','customer_cohorts','supply_options','sales_records','sales_window','sales_windows'])
      if (previous[k]!==undefined && result[k]===undefined) result[k]=copy(previous[k]);
    const fields=copy(previous.field_sources||{});
    for (const path of Object.keys(fields)) if(path.startsWith('products/')&&!result.products.some(p=>path.startsWith('products/'+p.sku+'/')))delete fields[path];
    for (const p of result.products) {
      const old=previous.products.find(o=>o.sku===p.sku);if(!old)continue;
      for(const k of Object.keys(old))if(!(k in p))p[k]=copy(old[k]);
      p.source_id=old.source_id;
      for(const k of ['name','stock','sales_30d','received_on','unit_cost','unit_price','size_complete'])
        if(stableJSON(old[k])!==stableJSON(p[k]))fields['products/'+p.sku+'/'+k]=sourceId;
      if(old.sales_30d!==p.sales_30d){
        const start=new Date(result.as_of+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-29);
        (result.sales_windows||={})[p.sku]={start:start.toISOString().slice(0,10),end:result.as_of,source_id:sourceId};
      }
    }
    for(const k of ['obligations','receivables'])for(const row of result[k]){
      const old=previous[k].find(o=>o.id===row.id);
      if(old&&['date','amount','label_text'].every(f=>old[f]===row[f]))row.source_id=old.source_id;
    }
    if(stableJSON(previous.customer_signals.map(o=>o.observation))===stableJSON(result.customer_signals.map(o=>o.observation)))result.customer_signals=copy(previous.customer_signals);
    for(const k of ['merchant_confirmed','inventory_complete','obligations_complete','receivables_complete']){
      const key=k==='merchant_confirmed'?k:'completeness/'+k;
      const old=k==='merchant_confirmed'?previous[k]:previous.completeness[k],now=k==='merchant_confirmed'?result[k]:result.completeness[k];
      if(old!==now&&fields[key])fields[key]=sourceId;
    }
    result.field_sources=fields;return result;
  }
  function merchantText(value) {
    let text=String(value??'');
    const names={'eligible_for_merchant_review':'已具备商户审阅条件','constraint_pass':'所录硬约束检查通过','upfront_cost':'前置费用','sales_assumption':'销量假设依据','variable_cash_cost':'每件额外现金费用','trial_cash_commitment':'本次承诺支出','costs_confirmed':'方案费用已核实','ready_for_analysis':'资料已具备分析条件','data_readiness':'资料完整性检查','customer_evidence':'顾客需求依据核对','business_diagnostics':'经营数据核查','unverified':'待核实','other_cost':'其他前置费用','ledger.obligations':'已登记的必要付款','proposal_evaluate':'方案约束复核','customer_observation':'顾客观察记录','spend_date':'付款日期','upfront':'前期支出','completeness.inventory_complete':'库存记录已核对完整','completeness.obligations_complete':'必要付款已核对完整','completeness.receivables_complete':'待收款已核对完整','merchant_confirmed':'店铺资料与经营限制已核对','customer_signals':'顾客观察记录','inventory_complete':'库存记录已核对完整','unit_cost':'采购单价'};
    for(const [key,label] of Object.entries(names)) {
      text=text.replace(new RegExp('(?<![A-Za-z0-9_])'+key.replaceAll('.', '\\.')+'\\s*(?:=|===|==|:)\\s*(true|false)(?![A-Za-z0-9_])','g'),(_,v)=>label+'（'+(v==='true'?'已确认':'尚未确认')+'）');
      text=text.replaceAll(key,label);
    }
    for(const [key,label] of Object.entries({inventory:'商品与库存',customer:'客户与经营方式',cash:'现金流与风险',SKU:'商品'}))text=text.replace(new RegExp('\\b'+key+'\\b','g'),label);
    text=text.replace(/\bnull\b/g,'待核实').replace(/\bfalse\b/g,'尚未确认').replace(/\btrue\b/g,'已确认');
    return text;
  }
  function jobProgressText(job) {
    const seconds=Number(job?.elapsed_seconds);
    const elapsed=Number.isFinite(seconds)&&seconds>=0?'已等待 '+Math.floor(seconds/60)+'分'+Math.floor(seconds%60)+'秒':'等待时间暂不可用';
    const phases={investigate:'调查资料',propose:'提出方案',review:'交叉复核',coordinate:'统筹处理',revise:'修改方案'};
    const roles={inventory:'商品与库存',customer:'客户与经营方式',cash:'现金流与风险',coordinator:'统筹'};
    const p=job?.progress;
    const stage=p?(roles[p.role]||'分析角色')+' · '+(phases[p.phase]||'核对资料')+(p.output_recorded?'（阶段结论已记录）':'（等待阶段结论）'):'正在准备分析资料';
    const active=p?.active_roles||[];
    const current=active.length>1?'并行核查：'+active.map(x=>(roles[x.role]||'分析角色')+' · '+(phases[x.phase]||'核对资料')).join('；'):stage;
    return {elapsed:job?.observation_error?'上次读取：'+elapsed:elapsed,stage:current,notice:job?.observation_error?'暂时无法读取进度，后台任务可能仍在运行。恢复查看即可，请勿重复发起。':'等待时间不是完成进度；页面不会据此估算百分比。'};
  }
  function analysisChanges(before,after) {
    if(!before||!after)return [];
    const rows=[],add=(label,a,b)=>{if(stableJSON(a)!==stableJSON(b))rows.push({label,before:a??null,after:b??null});};
    for(const [key,label] of Object.entries({cash_balance:'可用现金',reserve_floor:'现金保留额',max_trial_budget:'试验预算',weekly_available_hours:'每周可用工时',as_of:'资料截至日期'}))add(label,before[key],after[key]);
    const old=new Map((before.products||[]).map(p=>[p.sku,p]));
    for(const p of after.products||[]) {
      const b=old.get(p.sku);
      if(!b){rows.push({label:(p.name||p.sku)+' · 商品记录',before:null,after:'新增'});continue;}
      for(const [key,label] of Object.entries({unit_cost:'采购单价',stock:'库存件数',sales_30d:'近30天净销量',unit_price:'销售单价'}))add((p.name||p.sku)+' · '+label,b[key],p[key]);
      old.delete(p.sku);
    }
    for(const p of old.values())rows.push({label:(p.name||p.sku)+' · 商品记录',before:'已登记',after:'移除'});
    return rows;
  }
  function proposalDecision(e) {
    if ((e?.checks || []).length) return {kind:'blocked',title:'先处理限制，再考虑这个办法',detail:'有'+e.checks.length+'项限制需要处理，暂不能据此开展行动。'};
    if ((e?.unknowns || []).length || !e?.eligible_for_merchant_review) return {kind:'pending',title:'先补齐依据，再由你决定',detail:'当前仍有待核实条件；费用和销量假设不代表已经发生。'};
    return {kind:'review',title:'条件已核对，等你选择',detail:'只供经营者比较和决定，系统不会自动采购或发布促销。'};
  }
  function agendaProgress(a) {
    const tasks=(a?.days||[]).flatMap(d=>d.tasks||[]);
    const done=tasks.filter(t=>t.status==='done').length,paused=tasks.filter(t=>t.status==='skipped').length;
    return {done,paused,pending:tasks.length-done-paused,total:tasks.length};
  }
  function agendaProgressText(a) {
    const p=agendaProgress(a);return `共${p.total}项 · 已完成${p.done}项 · 已暂停${p.paused}项 · 待做${p.pending}项`;
  }
  function paymentDueText(t,day) {
    if(!String(t.id||'').startsWith('due_'))return '';
    const due=t.due_date||t.steps?.join(' ').match(/原到期日 (\d{4}-\d{2}-\d{2})/)?.[1];
    if(!due)return '';
    return due<day?`原到期日${due}已过，请核对是否已支付；本提示不代表尚未付款。`:due===day?`原到期日为今天（${due}），请核对付款状态与凭证。`:`原到期日${due}，尚未到期，请提前安排必要付款。`;
  }
  root.RebirthCore = Object.freeze({ escapeHtml, moneyText, intText, stableJSON, ledgerDigest, mergeLedgerForEdit, merchantText, jobProgressText, analysisChanges, proposalDecision, agendaProgress, agendaProgressText, paymentDueText });
  if (typeof module !== "undefined" && module.exports) module.exports = root.RebirthCore;
})(globalThis);
