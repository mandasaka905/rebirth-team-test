const test=require('node:test'),assert=require('node:assert/strict');
const {merchantText,proposalDecision}=require('../dist/core.js');
test('merchant wording translates missing values without mutating source',()=>{
 const raw={note:'ready_for_analysis=false；unit_cost=null；variable_cash_cost=3；trial_cash_commitment=30'};
 const display=merchantText(raw.note);
 assert.ok(display.includes('尚未确认'));assert.ok(display.includes('待核实'));assert.ok(display.includes('每件额外现金费用=3'));
 assert.ok(!/ready_for_analysis|unit_cost|\bnull\b|\bfalse\b/.test(display));assert.ok(raw.note.includes('unit_cost=null'));
});
test('blocking constraints take precedence over ready review',()=>{
 assert.equal(proposalDecision({checks:[{code:'BUDGET_EXCEEDED'}],unknowns:[],eligible_for_merchant_review:true}).kind,'blocked');
});
test('unknown conditions and old reports never imply approval',()=>{
 assert.equal(proposalDecision({checks:[],unknowns:['成本未知'],eligible_for_merchant_review:false}).kind,'pending');
 assert.equal(proposalDecision({checks:[],unknowns:[]}).kind,'pending');
 const ready=proposalDecision({checks:[],unknowns:[],eligible_for_merchant_review:true});assert.equal(ready.kind,'review');assert.ok(ready.detail.includes('不会自动采购'));
});
const fs=require('node:fs'),vm=require('node:vm');
test('candidate card renders decision and readable cost explanation with escaped model text',()=>{
 const core=require('../dist/core.js');const source=fs.readFileSync(require('node:path').join(__dirname,'../dist/app.js'),'utf8');
 const c={RebirthCore:core,h:core.escapeHtml,merchantFinding:core.merchantText,badge:s=>s,roleLabel:s=>s,yuan:v=>v==null?'待核实':v,renderExpenseBreakdown:()=>'',button:()=>'',state:{merchant:{products:[]}},checkNames:{}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function planCard('),source.indexOf('function renderFeedback(')),c);
 const html=c.planCard({proposal:{owner:'inventory',version:1,title:'<script>标题</script>',rationale:'unit_cost=null',weekly_hours:2,items:[],stop_conditions:['ready_for_analysis=false']},evaluation:{checks:[],unknowns:['variable_cash_cost=null'],scenarios:[],cash_cost_breakdown:{upfront_extra:'10.00',variable_extra:'2.00',new_procurement:'0.00',sold_goods_cost:'8.00',notice:'核实'}}},0);
 assert.ok(html.includes('先补齐依据'));assert.ok(html.includes('已知已售商品成本'));assert.ok(html.includes('每件额外现金费用=待核实'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('unit_cost'));
});
