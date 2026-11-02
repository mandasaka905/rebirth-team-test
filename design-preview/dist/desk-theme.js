"use strict";
(()=>{
 const $=s=>document.querySelector(s);
 const nav=$('.sidebar nav'),sidebar=$('.sidebar'),main=$('.main-area'),content=$('.page-content');
 if(!nav||!sidebar||!content)return;
 document.body.classList.add('story-workspace');
 $('.brand')?.setAttribute('aria-label','逆势重生经营概览');
 const chapters={
  overview:{number:'01',name:'推门入店',label:'经营概览',kicker:'THE DOOR IS OPEN',title:['每一间小店，','都有自己的明天。'],note:'先坐一会儿。把今天的难处说清楚，下一步便有了起点。',object:'一扇窗，照见日常。',folio:'从这里开始'},
  ledger:{number:'02',name:'摊开账本',label:'店铺资料',kicker:'THE STORY IN THE LEDGER',title:['生意的线索，','藏在一笔一账里。'],note:'库存、进出的钱、还没核实的事，摊开来，一件一件理清。',object:'翻开账本，也看清底线。',folio:'把事实写下来'},
  analysis:{number:'03',name:'灯下共议',label:'经营分析',kicker:'A PLACE FOR EVERY PERSPECTIVE',title:['把难题放上桌，','让不同判断相遇。'],note:'商品、顾客与资金，共用事实，也保留分歧。改变，从核对依据开始。',object:'灯亮着，慢慢商量。',folio:'交换证据与判断'},
  feedback:{number:'04',name:'留下新页',label:'行动与复盘',kicker:'ONE SMALL STEP, ONE NEW PAGE',title:['试一小步，','把真实的改变留下。'],note:'先把复杂分析收成一份有日期的行动日程，再记下实际发生的事。下一次决定，会更有根据。',object:'一张新页，记住走过的路。',folio:'记录行动与结果'}
 };
 const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text)el.textContent=text;return el};
 const scene=make('section','chapter-scene');scene.setAttribute('aria-label','经营手记章节');
 scene.innerHTML='<div class="interior-painting" aria-hidden="true"></div><div class="cup-steam" aria-hidden="true"><i></i><i></i><i></i></div><div class="chapter-copy"><p class="chapter-kicker"></p><h2 class="chapter-heading"></h2><p class="chapter-description"></p><span class="chapter-caption"></span></div><div class="chapter-side-note" aria-hidden="true"><span>小店经营手记</span><b></b></div><div class="chapter-foot"><span>慢慢看清 · 稳稳向前</span><span class="chapter-folio"></span></div>';
 const navigation=make('div','chapter-navigation');navigation.setAttribute('aria-label','经营故事章节');navigation.append(nav);
 main.prepend(scene,navigation);
 const masthead=make('div','masthead-note');masthead.innerHTML='<span>一间小店，一份生计。</span><small>A LITTLE SHOP. A LIFE WITHIN.</small>';
 sidebar.querySelector('.brand')?.after(masthead);
 const utility=make('div','story-utilities');
 const home=$('.back-to-street');if(home)utility.append(home);
 const motionButton=make('button','story-motion');motionButton.type='button';
 utility.append(motionButton);const help=$('#help-button');if(help)utility.append(help);
 sidebar.append(utility);
 let enabled=true;try{enabled=localStorage.getItem('rebirth_home_motion')!=='off'}catch{}
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 function syncMotion(){const on=enabled&&!reduced.matches;document.body.dataset.motion=on?'on':'off';motionButton.textContent=on?'风与光 · 开':'风与光 · 停';motionButton.setAttribute('aria-label',on?'暂停页面动效':'开启页面动效');motionButton.setAttribute('aria-pressed',String(on))}
 motionButton.addEventListener('click',()=>{enabled=!enabled;try{localStorage.setItem('rebirth_home_motion',enabled?'on':'off')}catch{}syncMotion()});
 reduced.addEventListener('change',syncMotion);window.addEventListener('storage',e=>{if(e.key==='rebirth_home_motion'){enabled=e.newValue!=='off';syncMotion()}});syncMotion();
 const navigationButtons=[...nav.querySelectorAll('.nav-item')];
 navigationButtons.forEach(button=>{const d=chapters[button.dataset.view];if(!d)return;button.setAttribute('aria-label',d.label);button.replaceChildren();const num=make('span','chapter-num',d.number);num.setAttribute('aria-hidden','true');const text=make('span','chapter-nav-copy');text.append(make('strong','',d.label),make('small','',d.name));const dot=make('span','chapter-node');dot.setAttribute('aria-hidden','true');button.append(num,text,dot);button.addEventListener('click',()=>window.scrollTo({top:0,behavior:document.body.dataset.motion==='on'?'smooth':'auto'}))});
 let current='';
 function syncChapter(){
  const active=navigationButtons.find(b=>b.classList.contains('active'));const key=active?.dataset.view||'overview',d=chapters[key];
  navigationButtons.forEach((b,i)=>{const selected=b===active;b.toggleAttribute('aria-current',selected);if(selected)b.setAttribute('aria-current','page');b.classList.toggle('chapter-past',i<Number(d.number)-1)});
  if(key===current)return;current=key;document.body.dataset.chapter=key;
  scene.querySelector('.chapter-kicker').textContent='经营手记 / 第 '+d.number+' 章　 ·　 '+d.kicker;
  const heading=scene.querySelector('.chapter-heading');heading.replaceChildren();d.title.forEach((line,i)=>{if(i)heading.append(document.createElement('br'));heading.append(make('span','',line))});
  scene.querySelector('.chapter-description').textContent=d.note;
  scene.querySelector('.chapter-caption').textContent=d.object;
  scene.querySelector('.chapter-side-note b').textContent=d.number;
  scene.querySelector('.chapter-folio').textContent=d.number+' / 04 · '+d.folio;
  scene.classList.remove('chapter-arriving');void scene.offsetWidth;scene.classList.add('chapter-arriving');
 }
 new MutationObserver(syncChapter).observe(nav,{attributes:true,subtree:true,attributeFilter:['class']});syncChapter();
 const openVolumes=new Map();
 function organizeVolumes(view){
  if(document.body.classList.contains('app-first'))return;
  if(view.id==='view-overview')return;
  const heads=[...view.children].filter(el=>el.matches('.section-head'));
  if(!heads.length)return;
  const caption=make('div','volume-caption');caption.append(make('span','','继续翻阅'),make('p','','每一页都保留着原始记录。点开页签，继续核对与补充。'));heads[0].before(caption);
  heads.forEach((head,i)=>{
   const title=head.querySelector('h2')?.textContent||'经营记录',key=view.id+':'+title;
   const volume=make('details','story-volume');volume.open=openVolumes.has(key)?openVolumes.get(key):i===0;
   const summary=make('summary','volume-summary'),number=make('span','volume-number',String(i+(view.id==='view-ledger'?3:1)).padStart(2,'0')),body=make('div','volume-body');
   let next=head.nextElementSibling;
   while(next&&!next.matches('.section-head')){const following=next.nextElementSibling;body.append(next);next=following}
   head.before(volume);summary.append(number,head,make('span','volume-sign','＋'));
   const actions=head.querySelector(':scope > .inline-flex');if(actions){actions.classList.add('volume-actions');body.prepend(actions)}
   volume.append(summary,body);volume.addEventListener('toggle',()=>openVolumes.set(key,volume.open));
  });
 }
 const decorated=new WeakSet();
 function addLabel(target,number,title){const label=make('div','sheet-label');label.append(make('span','',number),make('span','',title));target.prepend(label)}
 function enhanceView(view){
  if(document.body.classList.contains('app-first'))return;
  const first=view.firstElementChild;if(!first||decorated.has(first))return;
  if(view.id==='view-ledger'){
   const profile=[...view.children].find(e=>e.matches('.panel:not(.table-wrap):not(.empty-state)'));
   const stock=[...view.children].find(e=>e.matches('.table-wrap'));
   if(profile&&stock){
    const stockHeading=stock.previousElementSibling;
    const spread=make('div','ledger-spread');profile.before(spread);spread.append(profile,stock);
    profile.classList.add('ledger-profile');stock.classList.add('stock-sheet');
    if(stockHeading?.matches('.section-head'))stock.prepend(stockHeading);
    addLabel(profile,'01','店铺底账 · 先守住生活的底线');addLabel(stock,'02','商品明细 · 看见积压的时间');
    const bookmark=make('span','ledger-bookmark','事实');bookmark.setAttribute('aria-hidden','true');profile.append(bookmark);
   }
  }
  if(view.id==='view-overview'){
   const hero=view.querySelector('.hero');if(hero)addLabel(hero,'开篇','今天的小店，记在这一页');
   view.querySelectorAll('.metric').forEach((m,i)=>m.dataset.entry=String(i+1).padStart(2,'0'));
   const team=view.querySelector('.agent-list')?.closest('.panel');if(team){team.classList.add('team-at-table');addLabel(team,'共议席','每一种判断，都有自己的依据')}
  }
  if(view.id==='view-analysis')view.querySelectorAll('.agent-card').forEach((c,i)=>{c.dataset.seat=String(i+1).padStart(2,'0');c.classList.add('council-paper')});
  if(view.id==='view-feedback')view.querySelectorAll('.feedback-card').forEach((c,i)=>{c.classList.add('journal-entry');addLabel(c,String(i+1).padStart(2,'0'),'这一回，真实发生的事')});
  view.querySelectorAll(':scope > .feature-section').forEach((section,i)=>section.dataset.paper=String(i+1).padStart(2,'0'));
  organizeVolumes(view);
  decorated.add(view.firstElementChild);
 }
 let queued=false;const views=[...document.querySelectorAll('.view')];
 const schedule=()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;views.forEach(enhanceView)})};
 views.forEach(v=>new MutationObserver(schedule).observe(v,{childList:true}));schedule();
 const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting)e.target.classList.add('paper-visible')}),{threshold:.05});
 const observePaper=()=>document.querySelectorAll('.feature-section,.ledger-spread,.council-paper,.journal-entry').forEach(el=>{if(!el.dataset.watched){el.dataset.watched='true';observer.observe(el)}});
 new MutationObserver(observePaper).observe(content,{childList:true,subtree:true});observePaper();
 new IntersectionObserver(entries=>{scene.classList.toggle('scene-outside',!entries[0].isIntersecting)},{threshold:0}).observe(scene);
 document.addEventListener('visibilitychange',()=>document.body.classList.toggle('story-hidden',document.hidden));
})();
