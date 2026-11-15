'use strict';
(() => {
 const $=id=>document.getElementById(id),t=(key,...args)=>window.I18n.t(key,...args);let challenge='',blockedUntil=0,rateTimer=null;
 const messages=new Map();
 function message(id,text){messages.set(id,text);$(id).textContent=typeof text==='function'?text():t(text);}
 async function post(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','Accept-Language':window.I18n.language()},body:JSON.stringify(data),signal:AbortSignal.timeout(65000)});const body=await response.json();if(!response.ok){const error=new Error(body.error||t('Ошибка запроса'));error.retryAfter=response.status===429?Number(body.retry_after||response.headers?.get('Retry-After')||60):0;throw error;}return body;}
 function countdown(){
  clearTimeout(rateTimer);const remaining=Math.max(0,Math.ceil((blockedUntil-Date.now())/1000));
  $('loginSubmit').disabled=remaining>0;$('loginFactorSubmit').disabled=remaining>0;
  if(remaining){
   const time=()=>{const seconds=Math.max(0,Math.ceil((blockedUntil-Date.now())/1000));return(seconds>=3600?Math.floor(seconds/3600)+':':'')+String(Math.floor(seconds/60)%60).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');};
   message('loginError',()=>t('Повторите вход через {0}',time()));rateTimer=setTimeout(countdown,1000);
  }else if(blockedUntil){blockedUntil=0;message('loginError','');try{window.sessionStorage?.removeItem('xray-auth-until');}catch{}}
 }
 function failed(id,error){
  if(error.retryAfter>0){blockedUntil=Date.now()+error.retryAfter*1000;try{window.sessionStorage?.setItem('xray-auth-until',String(blockedUntil));}catch{}if($('loginFactorDialog').open)$('loginFactorDialog').close();countdown();}
  else message(id,error.message);
 }
 function destination(){const raw=new URLSearchParams(window.location.search).get('next')||'/overview';if(!/^\/(?:overview|profiles|iplists|routeros|settings|account|wiki(?:\/[a-z-]+)?)(?:#[a-z-]+)?$/.test(raw))return '/overview';return raw+(raw.includes('#')?'':window.location.hash);}
 function resetFactor(){challenge='';$('loginCode').value='';message('loginFactorError','');}
 $('loginForm').addEventListener('submit',async event=>{event.preventDefault();if(Date.now()<blockedUntil)return;const button=event.submitter;button.disabled=true;message('loginError','');try{const result=await post('/auth/login',Object.fromEntries(new FormData(event.target)));if(result.requires_2fa){challenge=result.challenge;$('loginFactorDialog').showModal();$('loginCode').focus();}else window.location.replace(destination());}catch(error){failed('loginError',error);}finally{button.disabled=Date.now()<blockedUntil;}});
 $('loginFactorForm').addEventListener('submit',async event=>{event.preventDefault();if(Date.now()<blockedUntil)return;const button=event.submitter;button.disabled=true;message('loginFactorError','');try{if(!challenge)throw new Error(t('Вход истёк. Введите логин и пароль заново.'));await post('/auth/login/2fa',{challenge,code:$('loginCode').value.trim()});window.location.replace(destination());}catch(error){failed('loginFactorError',error);}finally{button.disabled=Date.now()<blockedUntil;}});
 $('loginBack').onclick=()=>$('loginFactorDialog').close();$('loginFactorDialog').addEventListener('close',resetFactor);
 $('loginForm').addEventListener('input',()=>{if(challenge){$('loginFactorDialog').close();resetFactor();}});
 document.addEventListener('languagechange',()=>{for(const [id,text]of messages)$(id).textContent=typeof text==='function'?text():t(text);});
 try{blockedUntil=Math.min(Number(window.sessionStorage?.getItem('xray-auth-until'))||0,Date.now()+86400000);}catch{}countdown();
 fetch('/api/version').then(response=>response.json()).then(info=>{document.querySelectorAll('[data-version-link]').forEach(link=>{link.textContent=info.version;link.href=info.url;link.hidden=false;});}).catch(()=>{});
})();
