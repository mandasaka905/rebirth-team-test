const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('formal default has zero additional rounds and every extra round is labelled experimental',()=>{
 const c={document:{addEventListener(){}},state:{executionMode:'agentarts',maxCalls:40,extras:{preflight:{can_request_cloud:true}}},h:s=>s,executionName:s=>s};vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/../dist/features.js','utf8'),c);
 const html=c.analysisControls();assert.match(html,/<option value="0" selected>先出一版，自己审阅/);assert.equal((html.match(/实验功能，非正式演示流程/g)||[]).length,2);
});
