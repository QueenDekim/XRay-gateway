'use strict';
(() => {
 const $=id=>document.getElementById(id),t=(key,...args)=>window.I18n.t(key,...args);let challenge='';
 const messages=new Map();
 function message(id,text){messages.set(id,text);$(id).textContent=t(text);}
 async function post(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','Accept-Language':window.I18n.language()},body:JSON.stringify(data),signal:AbortSignal.timeout(65000)});const body=await response.json();if(!response.ok)throw new Error(body.error||t('Ошибка запроса'));return body;}
 function destination(){const raw=new URLSearchParams(window.location.search).get('next')||'/overview';if(!/^\/(?:overview|profiles|iplists|routeros|settings|account|wiki(?:\/[a-z-]+)?)(?:#[a-z-]+)?$/.test(raw))return '/overview';return raw+(raw.includes('#')?'':window.location.hash);}
 function resetFactor(){challenge='';$('loginCode').value='';message('loginFactorError','');}
 $('loginForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;message('loginError','');try{const result=await post('/api/login',Object.fromEntries(new FormData(event.target)));if(result.requires_2fa){challenge=result.challenge;$('loginFactorDialog').showModal();$('loginCode').focus();}else window.location.replace(destination());}catch(error){message('loginError',error.message);}finally{button.disabled=false;}});
 $('loginFactorForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;message('loginFactorError','');try{if(!challenge)throw new Error(t('Вход истёк. Введите логин и пароль заново.'));await post('/api/login/2fa',{challenge,code:$('loginCode').value.trim()});window.location.replace(destination());}catch(error){message('loginFactorError',error.message);}finally{button.disabled=false;}});
 $('loginBack').onclick=()=>$('loginFactorDialog').close();$('loginFactorDialog').addEventListener('close',resetFactor);
 $('loginForm').addEventListener('input',()=>{if(challenge){$('loginFactorDialog').close();resetFactor();}});
 document.addEventListener('languagechange',()=>{for(const [id,text]of messages)$(id).textContent=t(text);});
 fetch('/api/version').then(response=>response.json()).then(info=>{document.querySelectorAll('[data-version-link]').forEach(link=>{link.textContent=info.version;link.href=info.url;link.hidden=false;});}).catch(()=>{});
})();
