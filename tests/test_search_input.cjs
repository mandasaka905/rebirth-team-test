const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../dist/app-ui.js'),'utf8');
const functions=source.slice(source.indexOf(' function renderSearchResults('),source.indexOf(' function renderServices('));

function setup(){
 const results={innerHTML:''},count={textContent:''},clear={hidden:true};
 const input={id:'app-function-search',value:'',selectionStart:0,selectionEnd:0};
 const nodes={'#app-search-results':results,'.app-search-count':count,'[data-app-action="clear-search"]':clear};
 const services={querySelector:s=>nodes[s]};
 Object.defineProperty(services,'innerHTML',{set(){throw Error('The search form must not be rebuilt while typing')}});
 const context={services,catalogueItems:()=>({items:['one'],socials:[]}),catalogueResultHtml:()=>'<p>result</p>'};
 vm.createContext(context);
 vm.runInContext('let search="";'+functions+';this.update=updateFunctionSearch;this.query=()=>search;',context);
 return {context,input,results,count,clear};
}

test('Chinese composition commits without replacing the focused input or its selection',()=>{
 const {context,input,results,clear}=setup();
 input.value='da';input.selectionStart=input.selectionEnd=2;
 context.update({target:input,isComposing:true});
 assert.equal(context.query(),'');assert.equal(results.innerHTML,'');
 input.value='打印';context.update({target:input});
 assert.equal(context.query(),'打印');assert.equal(input.value,'打印');assert.equal(input.selectionStart,2);
 assert.equal(results.innerHTML,'<p>result</p>');assert.equal(clear.hidden,false);
});
test('clearing a committed query updates results without resetting the input element',()=>{
 const {context,input,clear,count}=setup();
 input.value='求助';context.update({target:input,isComposing:false});
 input.value='';context.update({target:input,isComposing:false});
 assert.equal(context.query(),'');assert.equal(clear.hidden,true);assert.match(count.textContent,/1项功能/);
});
test('typing in another form does not change the function search',()=>{
 const {context,results}=setup();
 context.update({target:{id:'goal',value:'草稿'}});
 assert.equal(context.query(),'');assert.equal(results.innerHTML,'');
});
