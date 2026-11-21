const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(failure){
 const saved=new Map([['rebirth_active_job',JSON.stringify({merchant:'shop',job:'job',mode:'agentarts'})]]);
 const c={document:{addEventListener(){}},state:{busy:true,job:{mode:'agentarts'},merchant:{merchant_id:'shop'}},
 localStorage:{getItem:k=>saved.get(k),removeItem:k=>saved.delete(k)},api:async()=>{throw failure},render(){},toast(m){c.message=m},selectMerchant:async()=>{c.loaded=true}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/../dist/features.js','utf8'),c);return {c,saved};
}
test('temporary network failure preserves active job and prevents duplicate starts',async()=>{
 const {c,saved}=setup(new Error('network'));await c.pollTask('shop','job');
 assert.equal(c.state.busy,true);assert.equal(c.state.job.observation_error,true);assert.equal(saved.has('rebirth_active_job'),true);
});
test('server restart releases stale observer but preserves analysis history',async()=>{
 const {c,saved}=setup(Object.assign(new Error('未找到该店铺任务；服务重启后请查看分析历史'),{status:404}));await c.pollTask('shop','job');
 assert.equal(c.state.busy,false);assert.equal(saved.has('rebirth_active_job'),false);assert.equal(c.loaded,true);assert.match(c.message,/未完成记录不会当作有效结论/);
});
test('another-account denial cannot be mistaken for a restarted job',async()=>{
 const {c,saved}=setup(Object.assign(new Error('账号改变'),{status:409}));await c.pollTask('shop','job');assert.equal(saved.has('rebirth_active_job'),true);assert.equal(c.loaded,undefined);
});
