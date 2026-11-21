const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {escapeHtml,moneyText,intText}=require('../dist/core.js');

function context(){
  const sandbox={h:escapeHtml,moneyText,intText,document:{addEventListener(){}},state:{merchant:{merchant_id:'demo',business_models:[]}},
    crypto:require('node:crypto'),console};
  vm.createContext(sandbox);
  for(const file of ['features.js','workbench.js','connections.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist',file),'utf8'),sandbox);
  return sandbox;
}

test('model choice escapes text and selects exact version only',()=>{
  const c=context();c.state.merchant.business_models=[{id:'m1',version:2,name:'<script>bad</script>'}];
  const old=c.modelChoices({model_refs:[{id:'m1',version:1}]});
  assert.ok(old.includes('&lt;script&gt;'));assert.ok(!old.includes('<script>'));
  assert.ok(!old.includes('checked'));
  assert.ok(c.modelChoices({model_refs:[{id:'m1',version:2}]}).includes('checked'));
});

test('model selection serializes only checked refs with numeric versions',()=>{
  const c=context();c.$$=()=>[{checked:true,dataset:{model:'m1',version:'2'}},{checked:false,dataset:{model:'m2',version:'1'}}];
  assert.deepEqual(JSON.parse(JSON.stringify(c.readModelChoices({}))),[{id:'m1',version:2}]);
});

test('scope confirmation is required and never automatically checked',()=>{
  const c=context();
  const html=c.designScopeFields({scope_id:'shop_all',scope_description:'全店',count_basis:'person_visits',baseline:{scope_id:'shop_all',count_basis:'person_visits'}});
  assert.match(html,/name=\"scope_confirmed\" type=\"checkbox\" required/);
  assert.ok(!html.includes('checked'));
  assert.ok(html.includes('base_scope_id'));assert.ok(html.includes('base_count_basis'));
});

test('structured exit serialization keeps signed decimal string',()=>{
  const c=context();const fields={exit_metric:'contribution_per_day',exit_op:'lte',exit_value:'-25.00',exit_description:'贡献退出'};
  c.$$=()=>[{dataset:{id:'e1'}}];c.$=selector=>({value:fields[selector.match(/name=(\w+)/)[1]]});
  const rows=c.readExits({});
  assert.equal(rows[0].value,'-25.00');assert.equal(rows[0].metric,'contribution_per_day');
});

test('agent draft preview flows through human-reviewed form to design API',async()=>{
  const c=context(),calls=[];
  const design={trial_id:'t1',draft_ref:'d1',scope_id:'shop_all',scope_description:'全店',scope_confirmed:false,count_basis:'person_visits',
    hypothesis:'合成假设',intervention:'合成改变',metric:'contribution_per_day',target_value:'-25.00',min_days:7,min_visits:20,
    observe_start:'2026-10-25',observe_end:'2026-10-31',comparison_method:'同范围',confounders:'季节',stop_rule:'核对退出',
    source_note:'',exit_rules:[],baseline:{start:'2026-10-01',end:'2026-10-20',revenue:'100.00',goods_cost:'200.00',expenses:'20.00',visits:50,buyers:10,source_note:'合成',scope_id:'shop_all',count_basis:'person_visits'}};
  c.api=async(route,payload)=>{calls.push({route,payload});return route.endsWith('draft-preview')?{design,draft_original:{target_basis:'明示目标'},source_mode:'rules',notice:'仅草案'}:{};};
  c.wbRefresh=async()=>{};c.openFeature=(title,html,submit)=>{c.captured={title,html,submit};};
  await c.openDesign('t1','d1');
  assert.ok(c.captured.html.includes('明示目标'));assert.ok(c.captured.html.includes('value=\"-25.00\"'));
  const form={...design,source_note:'人工确认',scope_confirmed:'on',min_days:'7',min_visits:'20'};
  for(const [k,v]of Object.entries(design.baseline))form['base_'+k]=String(v);
  c.FormData=class{constructor(f){this.f=f;}get(k){return this.f[k]??null;}has(k){return Object.hasOwn(this.f,k);}[Symbol.iterator](){return Object.entries(this.f)[Symbol.iterator]();}};
  c.readExits=()=>[];
  await c.captured.submit(form);
  const saved=calls.find(x=>x.route.endsWith('/design')).payload;
  assert.equal(saved.draft_ref,'d1');assert.equal(saved.scope_confirmed,true);
  assert.equal(saved.target_value,'-25.00');assert.equal(saved.baseline.scope_id,'shop_all');
  assert.equal(saved.baseline.visits,50);
});

test('pending trial exposes only its nested exact-version draft buttons',()=>{
  const c=context(),sections=[];
  c.appendSection=(view,html)=>sections.push({view,html});
  c.state.report=null;
  c.state.extras={experiments:{experiments:[{id:'t1',run_id:'run1',proposal_id:'p1',proposal_version:2,status:'planned',hypothesis:'待审阅'}]}};
  const w={cohorts:{notice:'匿名汇总',windows:[],findings:[]},research:[],lineage:[{
    run_id:'run1',proposal_id:'p1',proposal_version:2,title:'正确方案',model_snapshots:[],trials:[
      {id:'other',status:'planned',draft_ids:['wrong'],design_ids:[]},
      {id:'t1',status:'planned',draft_ids:['draft2'],design_ids:[]}
    ]
  }]};
  c.renderConnections(w);
  const html=sections.filter(s=>s.view==='feedback').map(s=>s.html).join('');
  assert.match(html,/data-wb="agent-design" data-trial="t1" data-draft="draft2"/);
  assert.ok(!html.includes('data-draft="wrong"'));
  sections.length=0;c.state.extras.experiments.experiments[0].proposal_version=1;
  c.renderConnections(w);
  const old=sections.filter(s=>s.view==='feedback').map(s=>s.html).join('');
  assert.ok(!old.includes('data-wb="agent-design"'));
  assert.ok(old.includes('没有当前精确版本的有效草案'));
});

test('role evidence displays fixed-cohort source and unknown counts without injection',()=>{
  const c=context(),source=fs.readFileSync(path.join(__dirname,'../dist/app.js'),'utf8');
  vm.runInContext(source.slice(source.indexOf('function evidenceDetails('),source.indexOf('const checkNames =')),c);
  c.state.report={events:[{id:'retention1',kind:'tool_result',data:{tool:'customer_retention',value:{
    windows:[{label:'八月客群',cohort_id:'aug',start:'2026-10-01',end:'2026-10-25',retained:null,base_size:100,retention:null,not_repeated:null,source_note:'<img src=x onerror=evil()>'}],findings:[],notice:'本窗未复购不代表永久流失'
  }}}]};
  const html=c.evidenceDetails(['retention1']);
  assert.match(html,/复购去重人数待核实 \/ 固定基准100/);
  assert.ok(html.includes('本窗未复购待核实'));
  assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));
  assert.ok(html.includes('不代表永久流失'));
});

