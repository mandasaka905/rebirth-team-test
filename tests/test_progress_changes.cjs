const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../dist/core.js');
test('progress shows actual elapsed and recorded phase without a fake percentage',()=>{
 const text=core.jobProgressText({elapsed_seconds:305,progress:{role:'cash',phase:'review',output_recorded:false}});
 assert.equal(text.elapsed,'已等待 5分5秒');assert.match(text.stage,/现金流与风险.*交叉复核.*等待阶段结论/);assert.ok(!text.stage.includes('%'));
 assert.match(core.jobProgressText({observation_error:true}).notice,/勿重复发起/);
 assert.match(core.jobProgressText({elapsed_seconds:-1}).elapsed,/暂不可用/);
});
test('fact changes retain unknown, include budgets, and never mutate old snapshot',()=>{
 const a={max_trial_budget:'80.00',weekly_available_hours:0,products:[{sku:'A',name:'玩偶',unit_cost:null,stock:2}]};
 const b={max_trial_budget:'90.00',weekly_available_hours:4,products:[{sku:'A',name:'玩偶',unit_cost:'30.00',stock:2}]};
 const rows=core.analysisChanges(a,b);assert.equal(rows.length,3);assert.equal(rows[2].before,null);assert.equal(rows[2].after,'30.00');assert.equal(a.products[0].unit_cost,null);
 assert.equal(core.analysisChanges(null,b).length,0);
});
test('fact comparison escapes imported product and never invents a completed rerun',()=>{
 const c={RebirthCore:core,h:core.escapeHtml,document:{addEventListener(){}}};vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/../dist/features.js','utf8'),c);
 const html=c.renderFactChanges({products:[{sku:'A',unit_cost:null}]},{products:[{sku:'A',name:'<script>',unit_cost:'2'}]});
 assert.match(html,/待核实/);assert.match(html,/&lt;script&gt;/);assert.match(html,/重新核查/);assert.ok(!html.includes('<script>'));
});
