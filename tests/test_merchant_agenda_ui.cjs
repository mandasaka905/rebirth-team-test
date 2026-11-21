const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../dist/core.js');
test('paused records are visible and do not count as completed',()=>{
 const a={days:[{tasks:[{status:'done'},{status:'skipped'},{status:'pending'}]}]};
 assert.deepEqual(core.agendaProgress(a),{done:1,paused:1,pending:1,total:3});
 assert.match(core.agendaProgressText(a),/已暂停1项/);
});
test('original due date is preserved and past date does not imply unpaid',()=>{
 const t={id:'due_0',steps:['原到期日 2026-11-15。']};
 assert.match(core.paymentDueText(t,'2026-11-16'),/不代表尚未付款/);
 assert.match(core.paymentDueText(t,'2026-11-15'),/今天/);
 assert.match(core.paymentDueText(t,'2026-11-14'),/尚未到期/);
 assert.equal(t.steps[0],'原到期日 2026-11-15。');
});
test('technical booleans keep their meaning in merchant text',()=>{
 assert.equal(core.merchantText('completeness.inventory_complete=true，merchant_confirmed=false；customer_signals'),
 '库存记录已核对完整（已确认），店铺资料与经营限制已核对（尚未确认）；顾客观察记录');
});
test('actual task renderer displays overdue notice and escapes model text',()=>{
 const source=fs.readFileSync(__dirname+'/../dist/agenda.js','utf8');
 const c={h:core.escapeHtml,merchantText:core.merchantText,RebirthCore:core,today:()=> '2026-11-16',roleLabel:x=>x,renderActionBasis:()=>'',btn:()=>'',Date};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf(' function dayHtml('),source.indexOf(' function contentHtml(')),c);
 const t={id:'due_0',title:'核对',status:'skipped',minutes:10,review_role:'cash',kind:'preparation',steps:['原到期日 2026-11-15。','merchant_confirmed=true <img>'],deliverable:'customer_signals',depends_on:[],stop_when:'暂停',note:'记录'};
 const html=c.dayHtml({days:[{date:'2026-11-16',minutes:10,tasks:[t]}]});
 assert.match(html,/已记暂停/);assert.match(html,/不代表尚未付款/);assert.match(html,/&lt;img&gt;/);assert.ok(!html.includes('customer_signals'));
});
