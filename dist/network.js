'use strict';
(()=>{
 const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const avatar=p=>p.avatar?`<img class="social-avatar" src="${h(p.avatar)}" alt="">`:`<span class="social-avatar">${h(p.nickname.slice(0,1))}</span>`;
 let user,profile,avatarData='',view='feed',postId='',peer='',category='',search='';
 const content=document.querySelector('#social-content'),status=document.querySelector('#social-status')||document.querySelector('#auth-error');
 function say(s){if(status){status.hidden=false;status.textContent=s;status.focus()}}
 async function api(query='',body){const r=await fetch('/api/community'+query,{method:body?'POST':'GET',headers:{'X-Rebirth-Account':user.id,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error||'暂时无法完成，请稍后再试');return d}
 const when=t=>new Date(t*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
 const person=p=>`<div class="social-person">${avatar(p)}<span><strong>${h(p.nickname)}</strong><small>${h(p.bio)}</small></span></div>`;
 const action=(op,label,extra='')=>`<button type="button" data-social="${op}" ${extra}>${label}</button>`;
 async function show(next=view,extra=''){
  view=next;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));status.textContent='';content.innerHTML='<p>正在读取…</p>';
  try{
   if(view==='feed'||view==='mine'){
    const d=await api();let rows=d.posts.filter(p=>(view!=='mine'||p.uid===user.id)&&(!category||p.category===category)&&(!search||(p.title+p.body).includes(search)));
    content.innerHTML=`<div class="social-filter"><label>按类别<select id="social-category"><option value="">全部类别</option>${d.categories.map(c=>`<option ${category===c?'selected':''}>${h(c)}</option>`).join('')}</select></label><form id="social-search"><label>搜索求助<input name="search" value="${h(search)}" placeholder="例如：库存、促销、记账"></label><button>搜索</button></form></div><div class="social-feed">${rows.length?rows.map(p=>`<article class="help-card">${person(p.author)}<div class="help-meta"><span>${h(p.category)}</span><span>${p.solved?'已解决':'交流中'}</span><time>${when(p.created)}</time></div><h2><button data-social="post" data-id="${p.id}">${h(p.title)}</button></h2><p class="post-excerpt">${h(p.body)}</p><div class="help-card-bottom"><span>${p.replies} 条回复</span>${action('post','查看与回复 →',`data-id="${p.id}"`)}</div></article>`).join(''):`<div class="social-empty"><h2>${view==='mine'?'你还没有发布求助':'这里还没有符合条件的求助'}</h2><p>说说最近遇到的难处，让其他经营者有机会帮你一起想。</p>${action('compose','发布第一条求助')}</div>`}</div><p class="personal-caption">显示最近100条求助；请勿把交流建议当作效果承诺。</p>`;
   }else if(view==='post'){
    postId=extra||postId;const d=await api('?view=post&id='+encodeURIComponent(postId)),p=d.post;
    content.innerHTML=`${action('feed','← 返回互助广场')}<article class="help-detail">${person(p.author)}<div class="help-meta">${h(p.category)} · ${p.solved?'已解决':'交流中'} · ${when(p.created)}</div><h1>${h(p.title)}</h1><p class="social-body">${h(p.body)}</p><div class="social-actions">${p.uid!==user.id?action('chat','私信交流',`data-peer="${p.uid}"`)+action('report','举报',`data-kind="post" data-id="${p.id}"`):action('solve',p.solved?'重新开放求助':'标记问题已解决',`data-solved="${p.solved?'false':'true'}"`)+action('hide','撤下求助',`data-kind="post" data-id="${p.id}"`)}</div></article><section class="reply-list"><h2>大家的办法 <small>${d.replies.length} 条</small></h2>${d.replies.map(r=>`<article class="reply-card">${person(r.author)}${r.helpful?'<span class="helpful-badge">发起人认为有帮助</span>':''}<p class="social-body">${h(r.body)}</p><small>${when(r.created)}</small><div class="social-actions">${p.uid===user.id?action('helpful',r.helpful?'取消有帮助':'标记有帮助',`data-id="${r.id}"`):''}${r.uid!==user.id?action('chat','私信交流',`data-peer="${r.uid}"`)+action('report','举报',`data-kind="reply" data-id="${r.id}"`):action('hide','撤下回复',`data-kind="reply" data-id="${r.id}"`)}</div></article>`).join('')||'<p>还没有回复，分享一个具体的做法吧。</p>'}</section><form id="reply-form" class="social-form"><label>写下你的建议<textarea name="body" required maxlength="2000" rows="4" placeholder="你遇到过类似情况吗？做了什么、花了多少时间、有哪些要注意的？"></textarea></label><button class="personal-primary">发送回复</button></form>`;
   }else if(view==='inbox'){
    const d=await api('?view=inbox');content.innerHTML=`<h2>我的私信</h2><p>在求助或回复里点击“私信交流”，即可联系对方。此处显示最近500条消息涉及的会话。</p><div class="personal-list">${d.conversations.map(c=>`<button data-social="chat" data-peer="${c.person.id}">${avatar(c.person)}<span><strong>${h(c.person.nickname)} ${c.unread?`<em>${c.unread}条未读</em>`:''}</strong><small>${h(c.last.body.slice(0,70))}</small></span><b>›</b></button>`).join('')||'<p class="social-empty">还没有私信，先去互助广场看看大家的问题。</p>'}</div>${action('inbox','刷新消息')}`;
   }else if(view==='thread'){
    peer=extra||peer;const d=await api('?view=thread&peer='+encodeURIComponent(peer));
    content.innerHTML=`${action('inbox','← 返回私信列表')}<div class="chat-heading">${person(d.person)}${action('block',d.blocked?'解除我对对方的屏蔽':'屏蔽对方',`data-blocked="${d.blocked?'false':'true'}"`)}</div><div class="chat-messages">${d.messages.map(m=>`<article class="chat-bubble ${m.sender===user.id?'mine':''}"><small>${m.sender===user.id?'我':h(d.person.nickname)} · ${when(m.created)}</small><p class="social-body">${h(m.body)}</p>${m.sender!==user.id?action('report','举报',`data-kind="message" data-id="${m.id}"`):''}</article>`).join('')||'<p>还没有消息，先向对方打个招呼吧。</p>'}</div>${d.blocked?'<p>当前无法发送消息。若由对方屏蔽，需对方解除后才能继续交流。</p>':`<form id="message-form" class="social-form"><label>发给 ${h(d.person.nickname)}<textarea name="body" required rows="3" maxlength="2000" placeholder="聊聊你想交流的具体问题"></textarea></label><button class="personal-primary">发送私信</button></form>`}${action('refresh-thread','刷新对话')}<p class="personal-caption">当前显示最近100条消息；点刷新查看新回复。</p>`;
   }else if(view==='blocks'){
    const d=await api('?view=blocks');content.innerHTML=`<h2>屏蔽名单</h2><p>屏蔽后，双方不能继续发送私信，也不能在对方的求助下回复。</p>${d.people.map(p=>`<article class="reply-card">${person(p)}${action('unblock','解除屏蔽',`data-peer="${p.id}"`)}</article>`).join('')||'<p class="social-empty">你没有屏蔽任何人。</p>'}`;
   }else if(view==='reports'){
    const d=await api('?view=reports');content.innerHTML='<h2>举报处理</h2><p>私信正文仅由参与者看到；管理员可按举报信息处理相关账号。</p>'+d.reports.map(r=>`<article class="reply-card"><p>${h(r.kind)} · ${when(r.created)}</p><p>举报原因：${h(r.reason)}</p>${r.content?`<p class="social-body">${h(r.content.body)}</p>${r.content.hidden?'已撤下':action('hide','撤下内容',`data-kind="${h(r.kind)}" data-id="${h(r.target)}"`)}`:`<p>私信举报已记录。发送方：${h(r.participants?.sender||'不可用')}；接收方：${h(r.participants?.recipient||'不可用')}</p><a href="/admin">前往账号管理核查 →</a>`}<small>举报人：${h(r.uid)} · 内容编号：${h(r.target)}</small></article>`).join('');
   }
  }catch(e){content.innerHTML='';say(e.message)}
 }
 function compose(){content.innerHTML=`${action('feed','← 返回广场')}<form id="publish-form" class="social-form help-detail"><h2>说说你遇到的难处</h2><label>问题类别<select name="category">${['库存周转','获客经营','记账工具','资源互助','经验分享'].map(c=>`<option>${c}</option>`).join('')}</select></label><label>一句话说清问题<input name="title" required maxlength="60" placeholder="例如：换季库存压着钱，如何小规模试着清理？"></label><label>具体情况<textarea name="body" required rows="7" maxlength="3000" placeholder="你经营什么店？遇到什么问题？已经试过什么？希望别人怎样帮助你？"></textarea></label><p>发布后，其他已登录经营者可看到你的昵称、头像和这段内容。不要填写客户隐私、联系方式或完整流水。</p><button class="personal-primary">确认公开发布</button></form>`}
 document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-social],[data-view]');if(!b)return;
  try{
   if(b.dataset.view){await show(b.dataset.view);return}const op=b.dataset.social;
   if(['feed','inbox','blocks'].includes(op)){await show(op);return}if(op==='post'){await show('post',b.dataset.id);return}if(op==='chat'){await show('thread',b.dataset.peer);return}if(op==='refresh-thread'){await show('thread');return}if(op==='compose'){compose();return}
   if(op==='report'){content.insertAdjacentHTML('beforeend',`<form id="report-form" class="social-form" data-kind="${h(b.dataset.kind)}" data-id="${h(b.dataset.id)}"><label>举报原因<textarea name="reason" maxlength="300" required placeholder="请说明骚扰、广告或其他问题"></textarea></label><button>提交举报</button></form>`);document.querySelector('#report-form textarea').focus();return}
   if(op==='hide'){if(!confirm('撤下这条内容？其他经营者将无法再看到。'))return;await api('',{op:'hide',kind:b.dataset.kind,target:b.dataset.id});await show(view==='reports'?'reports':'feed');return}
   b.disabled=true;
   if(op==='solve')await api('',{op:'solve',post:postId,solved:b.dataset.solved==='true'});
   if(op==='helpful')await api('',{op:'helpful',post:postId,reply:b.dataset.id});
   if(op==='block'||op==='unblock'){await api('',{op:'block',target:b.dataset.peer||peer,blocked:op==='block'&&b.dataset.blocked==='true'});await show(op==='unblock'?'blocks':'thread');return}
   await show('post');
  }catch(err){say(err.message)}finally{b.disabled=false}
 });
 document.querySelector('#new-post')?.addEventListener('click',compose);
 document.addEventListener('change',e=>{if(e.target.id==='social-category'){category=e.target.value;show(view)}});
 document.addEventListener('submit',async e=>{
  const f=e.target;if(!['publish-form','reply-form','message-form','report-form','social-search','profile-form'].includes(f.id))return;e.preventDefault();const data=Object.fromEntries(new FormData(f)),button=f.querySelector('[type=submit]')||f.querySelector('button');button.disabled=true;
  try{
   if(f.id==='social-search'){search=data.search;await show(view)}
   if(f.id==='publish-form'){const d=await api('',{op:'publish',...data});await show('post',d.id)}
   if(f.id==='reply-form'){await api('',{op:'reply',post:postId,...data});await show('post')}
   if(f.id==='message-form'){await api('',{op:'message',peer,...data});await show('thread')}
   if(f.id==='report-form'){await api('',{op:'report',kind:f.dataset.kind,target:f.dataset.id,...data});f.remove();say('举报已提交给管理员。')}
   if(f.id==='profile-form'){const d=await api('',{op:'profile',...data,avatar:avatarData});profile=d.profile;renderProfile();document.querySelector('#profile-editor').hidden=true;say('个人资料已保存。')}
  }catch(err){say(err.message)}finally{button.disabled=false}
 });
 function renderProfile(){const name=document.querySelector('#account-name'),a=document.querySelector('#account-avatar');if(name)name.textContent=profile.nickname;if(a)a.innerHTML=profile.avatar?`<img src="${h(profile.avatar)}" alt="我的头像">`:h(profile.nickname.slice(0,1));}
 document.querySelector('#edit-profile')?.addEventListener('click',()=>{const form=document.querySelector('#profile-form');form.elements.nickname.value=profile.nickname;form.elements.bio.value=profile.bio;avatarData=profile.avatar;const img=document.querySelector('#avatar-preview');img.hidden=!avatarData;img.src=avatarData;document.querySelector('#profile-editor').hidden=false});
 document.querySelector('#close-profile')?.addEventListener('click',()=>{document.querySelector('#profile-editor').hidden=true});
 document.querySelector('#remove-avatar')?.addEventListener('click',()=>{avatarData='';document.querySelector('#avatar-preview').hidden=true;document.querySelector('#avatar-file').value=''});
 document.querySelector('#avatar-file')?.addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>8000000||!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('请选择8MB以内的PNG、JPEG或WebP图片');const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;const ctx=canvas.getContext('2d'),size=Math.min(bitmap.width,bitmap.height);ctx.fillStyle='#ffffff';ctx.fillRect(0,0,256,256);ctx.drawImage(bitmap,(bitmap.width-size)/2,(bitmap.height-size)/2,size,size,0,0,256,256);bitmap.close();avatarData=canvas.toDataURL('image/jpeg',.85);const preview=document.querySelector('#avatar-preview');preview.src=avatarData;preview.hidden=false}catch(err){e.target.value='';say(err.message)}});
 (async()=>{try{const r=await fetch('/api/session',{cache:'no-store'});if(!r.ok){location.assign('/login');return}user=(await r.json()).user;profile=(await api('?view=profile')).profile;renderProfile();if(content){try{document.body.classList.toggle('comm-large',localStorage.getItem('rebirth_large_type')==='on')}catch{}document.querySelector('#moderation-tab').hidden=user.role!=='admin';await show()}}catch(e){say(e.message)}})();
})();
