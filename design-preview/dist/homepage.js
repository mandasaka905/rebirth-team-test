"use strict";
const hero=document.querySelector('.hero'),canvas=document.querySelector('#breeze'),ctx=canvas.getContext('2d');
const motionButton=document.querySelector('#motion'),motionLabel=document.querySelector('#motion-label'),reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
let motion=true,visible=true,last=0,elapsed=0,raf=0,w=0,h=0;
try{motion=localStorage.getItem('rebirth_home_motion')!=='off'}catch{}
if(reduce.matches)motion=false;
const leaves=Array.from({length:8},(_,i)=>({x:.53+i*.115,y:.24+i*.14,size:4+i%3,phase:i*1.7,speed:.013+i*.0018}));
const scene=document.querySelector('.scene'),portrait=window.matchMedia('(max-width: 600px)');
// Architecture is a static painting. Wind acts only on independent particles and hinged objects.
// One airflow drives smoke, leaves and hanging objects; gravity restores each pendulum.
const pointerWind={x:-500,y:-500,tx:-500,ty:-500,gust:0,active:false};
hero.addEventListener('pointermove',e=>{
 if(!motion||reduce.matches||e.pointerType==='touch')return;
 const r=scene.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
 if(y<0||y>r.height)return;
 if(pointerWind.active)pointerWind.gust=Math.max(-1.8,Math.min(1.8,pointerWind.gust+(x-pointerWind.tx)*.007));
 pointerWind.tx=x;pointerWind.ty=y;
 if(!pointerWind.active){pointerWind.x=x;pointerWind.y=y}pointerWind.active=true;
 canvas.dataset.pointer='following';
});
hero.addEventListener('pointerleave',()=>{pointerWind.active=false;canvas.dataset.pointer='resting'});
const windAt=t=>.28+.5*Math.sin(t*.65)+.22*Math.sin(t*1.6+.8)+pointerWind.gust;
const windTravel=t=>.28*t+(.5/.65)*(1-Math.cos(t*.65))+(.22/1.6)*(Math.cos(.8)-Math.cos(t*1.6+.8));
const pendulums={bell:{angle:0,speed:0,length:.28,damping:2.6,response:.17},tag:{angle:0,speed:0,length:.15,damping:5,response:.23},tail:{angle:0,speed:0,length:.11,damping:6.5,response:.30}};
function advancePendulums(dt,t){
 const steps=Math.ceil(dt/.012),step=dt/steps;
 for(let i=0;i<steps;i++)for(const p of Object.values(pendulums)){
  const gravity=9.81/p.length,force=gravity*p.response*windAt(t-dt+i*step);
  p.speed+=(-gravity*Math.sin(p.angle)-p.damping*p.speed+force)*step;p.angle+=p.speed*step;
 }
}
const steamPuff=document.createElement('canvas');steamPuff.width=steamPuff.height=96;
const puff=steamPuff.getContext('2d'),mist=puff.createRadialGradient(48,48,2,48,48,46);
mist.addColorStop(0,'rgba(255,250,230,.48)');mist.addColorStop(.36,'rgba(255,249,230,.30)');mist.addColorStop(.7,'rgba(255,249,230,.10)');mist.addColorStop(1,'rgba(255,249,230,0)');
puff.fillStyle=mist;puff.fillRect(0,0,96,96);
function resize(){
 const dpr=Math.min(devicePixelRatio||1,1.5);w=scene.clientWidth;h=scene.clientHeight;
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
 canvas.dataset.composition=portrait.matches?'portrait':'panorama';paintScene(elapsed/1000);
}
// The stage follows the exact aspect ratio of its painting: no cover crop or guessed offsets.
function scenePoint(nx,ny){return {x:nx*w,y:ny*h,scale:w/(portrait.matches?863:1672)}}
function drawSteam(t){
 const p=portrait.matches?scenePoint(.897,.785):scenePoint(.928,.672),k=p.scale;
 ctx.save();
 for(let i=0;i<20;i++){
  const age=(t/6.8+i/20)%1,gust=windAt(t);
  const x=p.x+(Math.sin(age*7+i*.48)*age*5+gust*age*age*38)*k,y=p.y-(age*95+age*age*50)*k;
  const rx=(7+age*24)*k,ry=(11+age*28)*k;
  ctx.globalAlpha=Math.sin(age*Math.PI)*.68;
  ctx.drawImage(steamPuff,x-rx,y-ry,rx*2,ry*2);
 }
 ctx.lineCap='round';ctx.strokeStyle='#fff9e6';ctx.lineWidth=2*k;ctx.shadowColor='#fff7df';ctx.shadowBlur=4*k;
 for(let i=0;i<3;i++){
  const age=(t/6.9+i*.31)%1,y=p.y-age*116*k,x=p.x+Math.sin(t*.45+age*4+i)*age*19*k;
  ctx.globalAlpha=Math.sin(age*Math.PI)*.23;ctx.beginPath();ctx.moveTo(x,y);
  ctx.bezierCurveTo(x-7*k,y-9*k,x+11*k,y-21*k,x+2*k,y-33*k);ctx.stroke();
 }
 ctx.restore();
}
function drawShopPaper(t){
 const p=portrait.matches?scenePoint(.54,.765):scenePoint(.749,.642),k=p.scale;
 const gust=windAt(t);
 ctx.save();ctx.translate(p.x,p.y);ctx.rotate(-pendulums.tag.angle);ctx.strokeStyle='#736447';ctx.lineWidth=.6*k;
 ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(0,4*k);ctx.stroke();
 ctx.fillStyle='#e2ce9c';ctx.beginPath();ctx.moveTo(-3*k,4*k);ctx.lineTo(4*k,4*k);ctx.quadraticCurveTo((4+gust*2)*k,12*k,3*k,20*k);ctx.lineTo(-3*k,19*k);ctx.closePath();ctx.fill();
 ctx.globalAlpha=.5;ctx.beginPath();ctx.moveTo(-1*k,8*k);ctx.lineTo(2*k,8*k);ctx.moveTo(-1*k,11*k);ctx.lineTo(2*k,11*k);ctx.stroke();ctx.restore();
}
function drawChime(t){
 const p=portrait.matches?scenePoint(.81,.658):scenePoint(.875,.536),k=p.scale*1.15;
 const angle=pendulums.bell.angle;
 ctx.save();ctx.translate(p.x,p.y);ctx.rotate(-angle);ctx.globalAlpha=.72;ctx.strokeStyle='#5e6650';ctx.fillStyle='#c2ad79';ctx.lineWidth=.8*k;
 ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(0,22*k);ctx.stroke();
 ctx.beginPath();ctx.moveTo(-5*k,30*k);ctx.quadraticCurveTo(-5*k,21*k,0,21*k);ctx.quadraticCurveTo(5*k,21*k,5*k,30*k);ctx.closePath();ctx.fill();ctx.stroke();
 ctx.beginPath();ctx.moveTo(-6*k,30*k);ctx.quadraticCurveTo(0,33*k,6*k,30*k);ctx.stroke();
 ctx.translate(0,31*k);ctx.rotate(angle-pendulums.tail.angle);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(0,10*k);ctx.stroke();
 ctx.fillStyle='#f2ebce';ctx.beginPath();ctx.moveTo(-2*k,10*k);ctx.lineTo(2.5*k,10*k);ctx.lineTo(2*k,27*k);ctx.lineTo(-2.5*k,26*k);ctx.closePath();ctx.fill();
 ctx.globalAlpha=.3;ctx.beginPath();ctx.moveTo(0,14*k);ctx.lineTo(0,23*k);ctx.stroke();ctx.restore();
}
function drawLake(t){
 const p=portrait.matches?scenePoint(.11,.578):scenePoint(.09,.708),k=p.scale;
 ctx.save();ctx.lineWidth=.8*k;ctx.strokeStyle='#fffce6';
 for(let i=0;i<6;i++){
  const glow=(Math.sin(t*1.2+i*1.9)+1)*.5,x=p.x+(i*13+Math.sin(t*.6+i)*3)*k,y=p.y+(i%3)*3*k;
  ctx.globalAlpha=.07+glow*.23;ctx.beginPath();ctx.moveTo(x,y);
  ctx.quadraticCurveTo(x+14*k,y-Math.sin(t+i)*1.2*k,x+(25+glow*17)*k,y);ctx.stroke();
 }
 ctx.restore();
}
function drawLeaves(t){
 for(const leaf of leaves){
  const travel=windTravel(t)*(15+leaf.phase*1.2);
  const x=((leaf.x*w+travel+Math.sin(t*.6+leaf.phase)*8)%(w*1.2)+w*1.2)%(w*1.2)-w*.1;
  const y=(leaf.y*h+t*16+Math.sin(t*.75+leaf.phase)*18)%(h*.8)+h*.15;
  let pushX=0,pushY=0;
  if(pointerWind.active){const dx=x-pointerWind.x,dy=y-pointerWind.y,d=Math.hypot(dx,dy),reach=Math.min(180,w*.18);if(d<reach){const force=(1-d/reach)*42;pushX=(dx/(d||1))*force;pushY=(dy/(d||1))*force-8}}
  ctx.save();ctx.translate(x+pushX,y+pushY);ctx.rotate(t*.35+leaf.phase+pointerWind.gust*.15);ctx.scale(Math.cos(t*.9+leaf.phase)*.7+.8,1);ctx.globalAlpha=.57;ctx.fillStyle=leaf.phase%2<1?'#73865b':'#b49a59';ctx.beginPath();ctx.moveTo(-leaf.size,0);ctx.quadraticCurveTo(-leaf.size*.6,-leaf.size*1.6,leaf.size,0);ctx.quadraticCurveTo(leaf.size*.4,leaf.size*.9,-leaf.size,0);ctx.fill();ctx.restore();
 }
}
function paintScene(t){
 if(!w||!h)return;
 ctx.clearRect(0,0,w,h);
 drawLake(t);drawShopPaper(t);drawChime(t);drawSteam(t);drawLeaves(t);
 canvas.dataset.physics='static-architecture';canvas.dataset.phase=String(Math.floor(t));canvas.dataset.ambient='leaves steam chime lake shop-paper';
}
function frame(now){
 raf=0;if(!motion||!visible||document.hidden)return;
 if(!last)last=now;
 const dt=now-last;
 if(dt<1000/30){raf=requestAnimationFrame(frame);return}
 last=now;const step=Math.min(dt,80);elapsed+=step;
 pointerWind.x+=(pointerWind.tx-pointerWind.x)*.13;pointerWind.y+=(pointerWind.ty-pointerWind.y)*.13;pointerWind.gust*=.95;
 canvas.dataset.gust=pointerWind.gust.toFixed(3);advancePendulums(step/1000,elapsed/1000);paintScene(elapsed/1000);raf=requestAnimationFrame(frame);
}
function start(){if(!raf&&motion&&visible&&!document.hidden){last=0;raf=requestAnimationFrame(frame)}}
function syncMotion(){
 document.documentElement.style.scrollBehavior=motion&&!reduce.matches?'smooth':'auto';document.body.dataset.motion=motion?'on':'off';
 motionButton.setAttribute('aria-pressed',String(motion));motionButton.setAttribute('aria-label',motion?'暂停场景动效':'开启场景动效');motionLabel.textContent=motion?'风在吹':'画面静止';
 if(!motion){cancelAnimationFrame(raf);raf=0;paintScene(elapsed/1000)}else start();
}
motionButton.addEventListener('click',()=>{motion=!motion;try{localStorage.setItem('rebirth_home_motion',motion?'on':'off')}catch{}syncMotion()});
reduce.addEventListener('change',e=>{if(e.matches){motion=false;syncMotion()}});
window.addEventListener('resize',resize);new ResizeObserver(resize).observe(scene);
document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0}else start()});
new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;document.body.classList.toggle('scene-sleep',!visible);if(!visible){cancelAnimationFrame(raf);raf=0}else start()}).observe(hero);
const menu=document.querySelector('#menu'),opener=document.querySelector('#open-menu');
let closeTimer=0;
opener.addEventListener('click',()=>{clearTimeout(closeTimer);menu.classList.remove('is-closing');menu.showModal();document.body.style.overflow='hidden'});
function closeMenu(after){
 if(!menu.open)return;
 const finish=()=>{menu.close();menu.classList.remove('is-closing');if(typeof after==='function')after()};
 clearTimeout(closeTimer);
 if(!motion||reduce.matches){finish();return}
 menu.classList.add('is-closing');closeTimer=setTimeout(finish,340);
}
document.querySelector('#close-menu').addEventListener('click',()=>closeMenu());
menu.addEventListener('cancel',e=>{e.preventDefault();closeMenu()});
menu.addEventListener('close',()=>{clearTimeout(closeTimer);document.body.style.overflow='';opener.focus({preventScroll:true})});
menu.addEventListener('click',e=>{if(e.target===menu){const r=menu.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right)closeMenu()}});
menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',e=>{
 if(a.getAttribute('href').startsWith('#')){
  e.preventDefault();const target=document.querySelector(a.getAttribute('href'));
  closeMenu(()=>{history.pushState(null,'',a.getAttribute('href'));target?.scrollIntoView({behavior:motion&&!reduce.matches?'smooth':'instant',block:'start'})});
 }else closeMenu();
}));

// The lower page is an interactive editorial: no analysis is fabricated here.
function setLines(el,value){el.replaceChildren();value.split('\n').forEach((line,i)=>{if(i)el.append(document.createElement('br'));el.append(document.createTextNode(line))})}
function softChange(el,name='changing'){el.classList.remove(name);if(motion&&!reduce.matches)requestAnimationFrame(()=>el.classList.add(name))}
function bindTabKeys(items,choose){items.forEach((el,i)=>el.addEventListener('keydown',e=>{let next=i;if(['ArrowRight','ArrowDown'].includes(e.key))next=(i+1)%items.length;else if(['ArrowLeft','ArrowUp'].includes(e.key))next=(i+items.length-1)%items.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=items.length-1;else return;e.preventDefault();items[next].focus();choose(items[next])}))}
function activateTabs(items,active){items.forEach(el=>{const selected=el===active;el.setAttribute('aria-selected',String(selected));el.tabIndex=selected?0:-1})}
const shopScenes={
 food:{kind:'餐饮小店 / 经营情境示意',question:'忙了一整天，\n为什么没留下多少？',pain:'备货损耗、客流起伏和固定支出，可能同时挤压利润。',facts:'核对实际销售、食材成本、损耗与近期付款，保留尚不清楚的地方。'},
 grocery:{kind:'社区零售 / 经营情境示意',question:'货架满满当当，\n手头却越来越紧？',pain:'商品周转有快有慢，补货与待付款可能占住原本有限的现金。',facts:'先对照采购单、库存和销售记录，核实钱停在哪些商品、哪些账期里。'},
 service:{kind:'便民服务 / 经营情境示意',question:'一门熟练的手艺，\n怎么让更多人看见？',pain:'获客渠道单一、工时有限，新服务又缺少足够的需求依据。',facts:'整理实际客户反馈、订单、材料成本与可用工时，先核对需求，再讨论新办法。'}
};
const shopTabs=[...document.querySelectorAll('[data-shop]')],shopPanel=document.querySelector('#shop-detail');
function selectShop(tab){activateTabs(shopTabs,tab);const data=shopScenes[tab.dataset.shop];shopPanel.setAttribute('aria-labelledby',tab.id);document.querySelector('#shop-kind').textContent=data.kind;setLines(document.querySelector('#shop-question'),data.question);document.querySelector('#shop-pain').textContent=data.pain;document.querySelector('#shop-facts').textContent=data.facts;softChange(shopPanel)}
shopTabs.forEach(tab=>{tab.addEventListener('click',()=>selectShop(tab));tab.addEventListener('pointermove',e=>{if(!motion||e.pointerType==='touch')return;const r=tab.getBoundingClientRect();tab.style.setProperty('--poster-turn',((e.clientX-r.left)/r.width*.9-.45).toFixed(2)+'deg')});tab.addEventListener('pointerleave',()=>tab.style.setProperty('--poster-turn','0deg'))});bindTabKeys(shopTabs,selectShop);
const stageData=[
 {label:'第一记 / 从已知开始',title:'不必有完整的账，\n先记下知道的事。',description:'整理现金、商品、采购、待付款和客户观察。每一项保留来源；不确定的成本与条件，留作待核实。',purpose:'分清事实与未知，让后面的判断有据可查。',document:'小店经营摘记',subtitle:'把已知和未知，分开写下来。',rows:[['已经知道','现金 · 商品 · 近期付款'],['仍待核实','成本 · 条件 · 记录是否完整'],['记录依据','账单 · 采购单 · 店主核对']],stamp:'据实记录',foot:'空白不是错误，先把未知留下来。'},
 {label:'第二记 / 顺着线索追问',title:'看到异常之后，\n再多问一句为什么。',description:'把商品、顾客和资金的线索放在一起核对。区分账面观察与可能解释，追查依据，遇到缺失信息时提出补证。',purpose:'让每一条判断，都能回到记录和证据。',document:'经营问题核查单',subtitle:'先提出问题，再寻找能核对的依据。',rows:[['账面观察','库存年龄 · 销售变化 · 近期付款'],['可能解释','保留为假设，不替未知补结论'],['继续核对','谁来回答 · 看哪份记录 · 缺什么']],stamp:'循证追问',foot:'找到相关性，不等于已经证明了原因。'},
 {label:'第三记 / 让办法适合小店',title:'新的办法，\n也要适合自己的日子。',description:'结合客户线索、现有资源和履约条件，提出经营模式草案。逐项写清成立前提，交给商品与现金角色继续质询。',purpose:'从自身条件出发，留下值得小步验证的候选。',document:'经营模式草案',subtitle:'每一种改变，都带着需要回答的问题。',rows:[['为谁提供价值','客户需求 · 证据来源'],['怎样获客与交付','渠道 · 商品 · 服务能力'],['成立需要什么','成本 · 工时 · 待验证条件']],stamp:'待验证',foot:'有一个新想法，还需要有人真正需要它。'},
 {label:'第四记 / 先看清投入边界',title:'如果没有销量，\n这一步还走得下去吗？',description:'在明确的销量、回款和成本假设下，比较库存、投入、工时与逐日现金。检查零销量或回款延迟时能否守住底线。',purpose:'投入之前，看见可能代价，也允许先不投入。',document:'投入前的情景检查',subtitle:'推演条件，不把假设当成未来预测。',rows:[['资源约束','商品可用量 · 履约工时'],['资金边界','必要付款 · 保留现金 · 试验预算'],['不利情形','零销量 · 回款延迟 · 退出条件']],stamp:'守住底线',foot:'能否负担得起失败，也是一项重要的判断。'},
 {label:'第五记 / 把实际发生的事留下',title:'试一点，再看清。\n让下一步有迹可循。',description:'把核查结果整理为7或14天行动日程，写清每天做什么、用多久、怎样算完成。保留预算与退出条件，再记录实际收支和反馈，决定继续、调整或停止。',purpose:'把一次建议，变成可以持续核对的小步行动。',document:'小步行动复盘页',subtitle:'记录真实结果，保留变化与不确定。',rows:[['事先说清','目标 · 基准 · 观察期 · 停止条件'],['实际记录','收支 · 反馈 · 记录来源'],['回看差异','继续 · 调整 · 停止 · 再核实']],stamp:'小步验证',foot:'描述观察到的变化，不轻易宣称它证明了因果。'}
];
const stageTabs=[...document.querySelectorAll('[data-stage]')],stagePanel=document.querySelector('#stage-panel');let stageIndex=0;
function renderDocument(data,index){
 const sheet=document.querySelector('#journal-artifact');sheet.replaceChildren();
 const head=document.createElement('div');head.className='document-head';const title=document.createElement('span'),number=document.createElement('small');title.textContent=data.document;number.textContent=String(index+1).padStart(2,'0');head.append(title,number);sheet.append(head);
 const subtitle=document.createElement('p');subtitle.className='document-subtitle';subtitle.textContent=data.subtitle;sheet.append(subtitle);
 for(const [label,value] of data.rows){const row=document.createElement('div');row.className='document-row';const key=document.createElement('span'),text=document.createElement('strong');key.textContent=label;text.textContent=value;row.append(key,text);sheet.append(row)}
 const stamp=document.createElement('div');stamp.className='document-stamp';stamp.textContent=data.stamp;const foot=document.createElement('p');foot.className='document-foot';foot.textContent=data.foot;sheet.append(stamp,foot);
}
function selectStage(tab){stageIndex=Number(tab.dataset.stage);const data=stageData[stageIndex];activateTabs(stageTabs,tab);stagePanel.setAttribute('aria-labelledby',tab.id);document.querySelector('#stage-label').textContent=data.label;setLines(document.querySelector('#stage-title'),data.title);document.querySelector('#stage-description').textContent=data.description;document.querySelector('#stage-purpose').textContent=data.purpose;const page=document.querySelector('#stage-page');page.firstChild.textContent=String(stageIndex+1).padStart(2,'0')+' ';renderDocument(data,stageIndex);document.querySelector('#stage-prev').disabled=stageIndex===0;document.querySelector('#stage-next').disabled=stageIndex===stageData.length-1;softChange(stagePanel,'turning')}
stageTabs.forEach(tab=>tab.addEventListener('click',()=>selectStage(tab)));bindTabKeys(stageTabs,selectStage);document.querySelector('#stage-prev').addEventListener('click',()=>selectStage(stageTabs[Math.max(0,stageIndex-1)]));document.querySelector('#stage-next').addEventListener('click',()=>selectStage(stageTabs[Math.min(stageTabs.length-1,stageIndex+1)]));document.querySelector('#stage-prev').disabled=true;
const roleContent={
 coordinator:['01 / 经营协调','先把问题\n问清楚。','整理商户目标、已知事实和缺失资料，把问题分配给专业角色；收集分歧与待核查事项，形成需要继续核对的清单。','同一个问题：有库存，也有客人，为什么现金仍然越来越紧？','把证据与异议，一起交还商户。'],
 inventory:['02 / 商品与供应链','钱，是否停在了\n库存里？','核对库存结构、采购成本、起订量与到货周期。对新模式提出的供货要求逐项核查，资料不足时提出补证。','追问新方案：少量补货，是否满足起订量、到货与付款条件？','商品侧提出约束，客户与现金侧继续复核。'],
 customer:['03 / 客户与商业模式','新的办法，\n真的有人需要吗？','整理客户观察和需求证据，提出经营模式草案；写清适用前提、渠道、履约和待验证假设，接受其他角色的质询。','追问新模式：预约、预订或新的渠道，是否有实际需求证据？','需求需要证据，履约与成本仍需交叉核对。'],
 cash:['04 / 现金风险','先守住不能\n越过的底线。','核算必要付款、试验投入和现金保留额。在零销量、回款延迟等明确假设下比较风险，保留资金约束带来的异议。','追问一次尝试：如果没有带来销量，近期账款是否仍能支付？','即使其他角色支持，也保留资金侧的异议。']
};
const roleTabs=[...document.querySelectorAll('[data-role]')],rolePanel=document.querySelector('#role-panel');
function selectRole(tab){activateTabs(roleTabs,tab);const data=roleContent[tab.dataset.role];document.querySelector('#role-index').textContent=data[0];setLines(document.querySelector('#role-title'),data[1]);document.querySelector('#role-description').textContent=data[2];document.querySelector('#role-example').textContent=data[3];document.querySelector('#role-trace').textContent=data[4];rolePanel.setAttribute('aria-labelledby',tab.id);document.querySelectorAll('[data-wire]').forEach(line=>line.classList.toggle('active',line.dataset.wire===tab.dataset.role));softChange(rolePanel)}
roleTabs.forEach(tab=>tab.addEventListener('click',()=>selectRole(tab)));bindTabKeys(roleTabs,selectRole);
resize();syncMotion();
// One-time reading entrances, with no scroll locking or forced page changes.
document.body.classList.add('has-editorial-motion');
const revealItems=[...document.querySelectorAll('[data-reveal]')];revealItems.forEach((el,i)=>el.style.setProperty('--reveal-delay',((i%3)*85)+'ms'));
const revealObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('is-seen');revealObserver.unobserve(entry.target)}},{threshold:.08,rootMargin:'0px 0px -20px 0px'});revealItems.forEach(el=>revealObserver.observe(el));
const ambientSections=[...document.querySelectorAll('.council-section,.closing-section,.reading-ribbon')];const sectionObserver=new IntersectionObserver(entries=>entries.forEach(entry=>entry.target.classList.toggle('in-view',entry.isIntersecting)),{threshold:.05});ambientSections.forEach(el=>sectionObserver.observe(el));
const chapterLinks=[...document.querySelectorAll('[data-chapter]')],chapterSections=chapterLinks.map(a=>document.getElementById(a.dataset.chapter)),readingNav=document.querySelector('.reading-nav');let readFrame=0;
function updateReading(){readFrame=0;const y=window.scrollY,total=document.documentElement.scrollHeight-innerHeight;document.documentElement.style.setProperty('--reading-progress',String(total>0?y/total:0));readingNav.classList.toggle('shown',hero.getBoundingClientRect().bottom<90);readingNav.classList.toggle('near-end',document.querySelector('#begin').getBoundingClientRect().top<innerHeight*.65);let current=chapterSections[0];for(const section of chapterSections)if(section.getBoundingClientRect().top<innerHeight*.4)current=section;chapterLinks.forEach(a=>a.classList.toggle('active',a.dataset.chapter===current.id))}
window.addEventListener('scroll',()=>{if(!readFrame)readFrame=requestAnimationFrame(updateReading)},{passive:true});window.addEventListener('resize',updateReading);updateReading();
const doorLink=document.querySelector('.workbench-link');doorLink.addEventListener('pointermove',e=>{if(!motion||e.pointerType==='touch')return;const r=doorLink.getBoundingClientRect();doorLink.style.setProperty('--door-x',((e.clientX-r.left-r.width/2)/r.width*5).toFixed(2)+'px');doorLink.style.setProperty('--door-y',((e.clientY-r.top-r.height/2)/r.height*4).toFixed(2)+'px')});doorLink.addEventListener('pointerleave',()=>{doorLink.style.setProperty('--door-x','0px');doorLink.style.setProperty('--door-y','0px')});
