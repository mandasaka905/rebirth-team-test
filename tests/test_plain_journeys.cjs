const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {escapeHtml}=require('../dist/core.js');

function social(){
 const source=fs.readFileSync(path.join(__dirname,'../dist/social.js'),'utf8');
 const state={categories:{inventory:'盘清库存'},outcomes:{unresolved:'尚未解决',partial:'解决了一部分'},cases:[],adoptions:[],cards:[]};
 const c={h:escapeHtml,state:{merchant:{merchant_id:'demo'}},RebirthCommunity:{data:()=>({social:state,cases:[]}),surface:(html,kind)=>{c.output={html,kind}}}};
 vm.createContext(c);
 vm.runInContext(source.slice(0,source.indexOf(" document.addEventListener('submit'"))+'this.testForms={requestForm,resultForm,adoptForm,caseForm};})();',c);
 return {c,state};
}
test('request hints explain each open question without putting example text in saved fields',()=>{
 const {c}=social();c.testForms.requestForm();
 assert.match(c.output.html,/第1步/);assert.match(c.output.html,/social-help-problem/);
 assert.match(c.output.html,/这次想先做成什么/);
 assert.match(c.output.html,/name="problem"[^>]*><\/textarea>/);
 assert.match(c.output.html,/保存困难，接着约人一起做/);
});
test('trial result distinguishes spending and time, keeps negative outcomes and escapes merchant text',()=>{
 const {c,state}=social();state.adoptions=[{id:'a1',data:{adapted_step:'<script>不执行</script>',minutes_cap:15,spend_cap:'0.00'}}];
 c.testForms.resultForm('a1');const html=c.output.html;
 assert.match(html,/不适合本店/);assert.match(html,/暂时没看出变化/);
 assert.match(html,/social-help-next_step/);assert.match(html,/保存这次结果/);
 assert.match(html,/没花钱填0/);assert.match(html,/做了10分钟就填10/);
 assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));
 assert.match(html,/name="actual"[^>]*><\/textarea>/);
});
test('a new review does not preselect a successful outcome and its evidence example fits a review',()=>{
 const {c,state}=social();state.cases=[{id:'c1',data:{goal:'核对库存'}}];c.testForms.caseForm('review','c1');
 assert.match(c.output.html,/value="unresolved" selected/);
 assert.match(c.output.html,/第4步/);assert.match(c.output.html,/今天当面问过店主/);
 assert.match(c.output.html,/保存最后结果/);
});
test('review search offers three direct daily paths while detailed tools stay reachable',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../dist/app-ui.js'),'utf8');
 const fragment=source.slice(source.indexOf(' let catalogueExpanded='),source.indexOf(' function renderSearchResults('));
 const c={search:'复盘',selectedGroup:'全部',h:escapeHtml,routeButton:(label,path)=>`<button data-path="${path}">${label}</button>`,actionButton:(label,action)=>`<button data-action="${action}">${label}</button>`,featureCard:id=>`<button>${id}</button>`};
 vm.createContext(c);vm.runInContext(fragment+'this.render=catalogueResultHtml;this.expand=()=>catalogueExpanded=true;',c);
 let html=c.render([['research'],['audit']],[]);
 assert.equal((html.match(/data-path=/g)||[]).length,3);assert.match(html,/catalogue-more/);
 assert.ok(!html.includes('<button>research</button>'));
 c.expand();html=c.render([['research'],['audit']],[]);assert.ok(html.includes('<button>research</button>'));
});
