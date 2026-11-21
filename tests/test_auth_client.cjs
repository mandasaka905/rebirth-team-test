const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../dist/app.js'),'utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('let toastTimer;'));
test('account identity accompanies reads and writes; successful retry clears expired banner',async()=>{
 const calls=[],events=[];
 const c={fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({saved:true})}},RebirthHosted:{userId:'account-a',sessionRestored:()=>events.push('restored')}};
 vm.createContext(c);vm.runInContext(api,c);
 await c.api('/api/merchants');await c.api('/api/ledgers',{merchant_id:'shop'});
 assert.equal(calls[0].options.headers['X-Rebirth-Account'],'account-a');assert.equal(calls[1].options.headers['X-Rebirth-Account'],'account-a');assert.equal(calls[1].options.method,'POST');assert.equal(events.length,2);
});
test('expired or switched sessions show a message and never automatically replay a write',async()=>{
 for(const [status,body,changed] of [[401,{error:'登录过期'},false],[409,{error:'账号改变',account_changed:true},true]]){
  let calls=0;const events=[];const c={fetch:async()=>{calls++;return {ok:false,status,json:async()=>body}},RebirthHosted:{userId:'account-a',sessionProblem:x=>events.push(x)}};
  vm.createContext(c);vm.runInContext(api,c);await assert.rejects(c.api('/api/ledgers',{merchant_id:'shop'}));assert.equal(calls,1);assert.deepEqual(events,[changed]);
 }
});
test('desktop-only mode still works without hosted session code',async()=>{
 const c={fetch:async(url,options)=>({ok:true,status:200,json:async()=>({headers:options.headers})})};vm.createContext(c);vm.runInContext(api,c);const r=await c.api('/api/merchants');assert.equal(Object.keys(r.headers).length,0);
});
