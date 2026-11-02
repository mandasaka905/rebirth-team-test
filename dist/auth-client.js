"use strict";
(()=>{
 const userId=document.querySelector('meta[name="rebirth-account-id"]')?.content;
 if(!userId)return;
 let banner;
 const demoOnly=document.querySelector('meta[name="rebirth-demo-only"]')?.content==='true';
 if(demoOnly){const notice=document.createElement('aside');notice.className='hosted-test-notice';notice.textContent='队员测试站 · 只填虚构资料 · AgentArts尚未接入';document.body.prepend(notice);document.body.classList.add('hosted-demo')}
 globalThis.RebirthHosted={userId,demoOnly,sessionRestored(){banner?.remove();banner=null},sessionProblem(changed=false){
  if(!banner){banner=document.createElement('section');banner.className='hosted-expired';banner.setAttribute('role','alert');document.body.prepend(banner)}
  banner.replaceChildren();const p=document.createElement('p');p.textContent=changed?'账号已改变，这个旧页面不能继续保存。请先复制手边未保存的文字，再打开工作台，确认账号。':'登录已过期。正在填写的文字还留在页面，请在新标签页登录同一账号，再回到这里重试；刚才的操作没有自动重发。';
  const link=document.createElement('a');link.href=changed?'/account':'/login';link.target='_blank';link.rel='noopener';link.textContent=changed?'在新标签页查看账号':'在新标签页重新登录';banner.append(p,link);
 }};
})();
