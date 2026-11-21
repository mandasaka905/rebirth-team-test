const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {escapeHtml}=require('../dist/core.js');
function renderer(){const c={URL,h:escapeHtml,document:{addEventListener(){}}};vm.createContext(c);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../dist/features.js'),'utf8'),c);return c;}

test('business model comparison preserves unknowns and escapes structural text',()=>{
 const c=renderer();const fixture=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../testing/model-reconstruction/case-and-results.json'),'utf8'));
 fixture.before.rows[1].model.channel='<script>test</script>';
 const html=c.renderModelComparison(fixture.before);
 assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/待核实/);assert.match(html,/即时配送/);
 assert.match(html,/零订单／半量／申报量/);
});

test('cost editor keeps unknown amount null and records its basis',()=>{
 const c=renderer();Object.assign(c,require('../dist/core.js'));
 const fields={uc_count:'1',uc_id_0:'delivery',uc_label_0:'配送',uc_amount_0:'',uc_basis_0:'尚未取得报价',uc_kind_0:'assumption'};
 const f={has:k=>k==='uc_enabled',get:k=>fields[k]};const m={uc_count:'1'};c.readUnitCosts(f,m);
 assert.equal(m.unit_cost_components[0].amount,null);assert.equal(m.unit_cost_components[0].basis,'尚未取得报价');assert.equal(m.uc_count,undefined);
});
test('expense detail shows source limits, zero cancellation and escapes text',()=>{
 const html=renderer().renderExpenseBreakdown({expense_breakdown:[{label:'<script>广告</script>',quantity:0,unit_cost:'1800.00',amount:'0.00',basis:'构造假设',basis_kind:'assumption'}]});
 assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/待验证假设/);assert.match(html,/0 × ¥1800.00/);assert.match(html,/不另行重复扣款/);
});
test('legacy plans do not acquire invented expense rows',()=>assert.equal(renderer().renderExpenseBreakdown({}),''));

function draftContext(upfront){
 const c=renderer(),fields={title:'修改方案',upfront_cost:upfront,other_cost:'0.00',spend_date:'2026-11-04',weekly_hours:'2',rationale:'待核实费用',stop_conditions:'超预算时停止'};
 Object.assign(c,{moneyText:require('../dist/core.js').moneyText,intText:require('../dist/core.js').intText,
  FormData:class{get(k){return fields[k];}has(k){return k==='costs_confirmed';}},readModelChoices:()=>[],readProcurements:()=>[],$$:()=>[]});
 vm.runInContext("sandboxBase={version:1,upfront_cost:'80.00',other_cost:'0.00',expense_breakdown:[{label:'旧分项'}]};sandboxNew=false;",c);
 return c;
}

test('changing fixed costs clears stale detail and confirmation only in new version',()=>{
 const c=draftContext('100.00'),p=c.readDraft({});
 assert.equal(p.version,2);assert.equal(p.expense_breakdown,undefined);assert.equal(p.costs_confirmed,false);
 assert.ok(p.assumptions.some(s=>s.includes('重新核实')));
 assert.equal(vm.runInContext('sandboxBase.expense_breakdown.length',c),1);
});

test('unchanged fixed totals preserve recorded expense detail',()=>{
 const c=draftContext('80.00'),p=c.readDraft({});
 assert.equal(p.expense_breakdown.length,1);assert.equal(p.expense_breakdown[0].label,'旧分项');
});

test('knowledge card exposes original source, scope and dated limits',()=>{
 const html=renderer().renderKnowledgeCard({id:'ref',title:'参考',source:'摘要',content:'内容',url:'https://example.com/guide',scope:'一般经营参考',checked_on:'2026-11-12'});
 assert.match(html,/href="https:\/\/example.com\/guide"/);assert.match(html,/noopener noreferrer/);
 assert.match(html,/一般经营参考/);assert.match(html,/不表示内容持续有效/);
});

test('knowledge cards reject unsafe or credentialed links and escape text',()=>{
 for(const url of ['javascript:alert(1)','data:text/html,hi','https://name:password@example.com/']){
  const html=renderer().renderKnowledgeCard({title:'<script>',id:'x',source:'记录',content:'说明',url});
  assert.ok(!html.includes('<a '));assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);
 }
});

test('action basis escapes the reason and supports legacy saved agendas',()=>{
 const c=renderer();assert.equal(c.renderActionBasis({}), '');
 const html=c.renderActionBasis({basis:{reasons:['<script>'],proposal_id:'p',proposal_version:2,notice:'需核对',evidence_ids:['e2']}});
 assert.match(html,/为什么安排/);assert.match(html,/第2版/);assert.match(html,/&lt;script&gt;/);assert.ok(!html.includes('<script>'));
});

test('claim citation display refuses another roles or phases search record',()=>{
 const c=renderer();c.roleLabel=x=>x;
 const events=[{id:'e1',kind:'tool_result',actor:'cash',data:{phase:'review',tool:'knowledge_search',value:{matches:[{id:'guide',title:'指南',source:'自编',content:'先核对付款日'}]}}},
  {id:'e2',kind:'agent_result',actor:'cash',data:{phase:'review',result:{assessment:{knowledge_citations:[{claim:'<script>付款',document_id:'guide',supporting_text:'核对付款日',evidence_id:'e1',scope_limit:'不预测收入'}]}}}}];
 assert.match(c.renderKnowledgeClaims({events}),/语义|人工核对/);assert.ok(!c.renderKnowledgeClaims({events}).includes('<script>'));
 events[1].actor='customer';assert.equal(c.renderKnowledgeClaims({events}),'');
 events[1].actor='cash';events[1].data.phase='propose';assert.equal(c.renderKnowledgeClaims({events}),'');
});

test('saved-review closure is visibly distinguished from an agent decision',()=>{
 const c=renderer();c.roleLabel=x=>x;
 const report={events:[],result:{collaboration:{role_assessments:[{role:'inventory',phase:'investigate',conclusion:'待核对',assumptions:[],limits:[],missing_data:[],evidence_ids:[]}],
  revisions:[],proposal_reviews:[],coordination_plans:[{source:'host_archive_of_validated_reviews',revision_budget_exhausted:true,tasks:[],requirements:[]}]}}};
 assert.match(c.renderCollaborationEvidence(report),/由系统根据三方已完成的复审整理/);
});


test('collaboration journey follows saved stage outputs rather than starting events',()=>{
 const c=renderer();c.badge=x=>x;
 let html=c.collaborationJourney({events:[{kind:'phase_started',data:{phase:'investigate'}}],result:{}});
 assert.ok(!html.includes('已记录'));
 html=c.collaborationJourney({events:[{kind:'agent_result',data:{phase:'investigate'}}],result:{}});
 assert.equal((html.match(/已记录/g)||[]).length,1);
});
test('merchant audit avoids raw protocol and evaluation commentary',()=>{
 const c=renderer();c.section=(title,html)=>html;c.badge=x=>x;c.renderCollaborationEvidence=()=>'';
 const html=c.renderAudit({events:[{kind:'agent_result',data:{phase:'investigate',result:{secret_marker:'never render'}}}],result:{}});
 assert.ok(!html.includes('secret_marker'));assert.ok(!html.includes('json-block'));assert.ok(html.includes('分别核对店铺资料'));
});


test('historical collaboration evidence stays bound to its own report',()=>{
 const c=renderer();c.roleLabel=x=>x;
 const report={events:[],result:{collaboration:{role_assessments:[{role:'cash',phase:'investigate',conclusion:'需核对',assumptions:[],limits:[],missing_data:[],evidence_ids:['e1']}],revisions:[],proposal_reviews:[],coordination_plans:[]}}};
 c.evidenceDetails=(ids,r)=>{assert.strictEqual(r,report);assert.deepEqual(Array.from(ids),['e1']);return '本次报告的依据';};
 assert.match(c.renderCollaborationEvidence(report),/本次报告的依据/);
});
