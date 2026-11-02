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
  root.RebirthCore = Object.freeze({ escapeHtml, moneyText, intText, stableJSON, ledgerDigest, mergeLedgerForEdit });
  if (typeof module !== "undefined" && module.exports) module.exports = root.RebirthCore;
})(globalThis);
