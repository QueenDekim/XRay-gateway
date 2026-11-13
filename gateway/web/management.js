'use strict';
(() => {
 let challenge='',accountTab='profile',appliedUser='',applyingPreferences=false,preferenceTimer;
 let sshConnecting=false,sshManual=false,sshEpoch=0;
 let routerLoaded=false,savedRouter=null,jobTimer,jobId='',jobCursor=0,jobLines=[],sshId='',sshCursor=0,sshTimer,terminal,fit,sshSending=Promise.resolve();
 const jobState=value=>t(({queued:'В очереди',running:'Выполняется',done:'Завершено',error:'Ошибка'})[value]||value);
 const owns=['profile','appearance','security'];
 function resetFactor(){challenge='';$('loginCode').value='';message('loginFactorError','');}
 function passwordStep(){resetFactor();if($('loginFactorDialog').open)$('loginFactorDialog').close();for(const name of ['username','password']){const field=$('loginForm').elements.namedItem(name);field.disabled=false;field.required=true;}}
 function selectAccount(name,focus=false){accountTab=owns.includes(name)?name:'profile';for(const key of owns){$('accountPanel-'+key).hidden=key!==accountTab;const b=$('accountTab-'+key);b.setAttribute('aria-selected',String(key===accountTab));b.tabIndex=key===accountTab?0:-1;}if(focus)$('accountTab-'+accountTab).focus();}
 function image(user,prefix){const img=$(prefix==='header'?'headerAvatar':'accountAvatar'),letters=$(prefix==='header'?'headerInitials':'accountInitials');letters.textContent=(user.display_name||user.username||'').split(/\s+/).map(v=>Array.from(v)[0]||'').join('').slice(0,2).toUpperCase();img.hidden=!user.avatar;letters.hidden=!!user.avatar;if(user.avatar&&img.getAttribute('src')!==user.avatar)img.setAttribute('src',user.avatar);img.onerror=()=>{img.hidden=true;letters.hidden=false;};}
 function render(){
  if(!state)return;const user=state.user;image(user,'header');image(user,'account');selectAccount(accountTab);
  if(appliedUser!==user.id){appliedUser=user.id;applyingPreferences=true;try{window.Appearance.set(user.preferences||{});if(user.preferences?.language)window.I18n.setLanguage(user.preferences.language);}finally{applyingPreferences=false;}}
  const profile=$('accountProfileForm');if(profile.dataset.dirty!=='1')profile.elements.display_name.value=user.display_name||user.username;
  const enabled=!!user.two_factor_enabled;message('factorState',enabled?'Включена':'Выключена');$('factorSetupForm').hidden=enabled;$('factorManageForm').hidden=!enabled;
  if(enabled){$('factorEnrollment').hidden=true;message('factorSecret','');$('factorQr').removeAttribute('src');}
  $('terminalConnect').hidden=user.role!=='admin'||!!sshId||sshConnecting;$('terminalDisconnect').hidden=!sshId;
  if(user.role!=='admin')message('terminalStatus','Требуются права администратора.');
  if(user.role==='admin'&&!routerLoaded)loadRouter();
 }
 function clear(){
  passwordStep();sshEpoch++;sshConnecting=false;sshManual=false;appliedUser='';routerLoaded=false;savedRouter=null;clearTimeout(preferenceTimer);clearTimeout(jobTimer);clearTimeout(sshTimer);jobId='';sshId='';
  for(const id of ['accountProfileForm','routerConnectionForm'])delete $(id).dataset.dirty;
  for(const id of ['factorSetupForm','factorEnableForm','factorManageForm','accountProfileForm','routerConnectionForm'])$(id).reset();credentialMasks();
  $('recoveryCodes').value='';$('factorRecovery').hidden=true;$('factorEnrollment').hidden=true;message('factorSecret','');$('factorQr').removeAttribute('src');if(terminal)terminal.reset();
 }
 async function login(event){
  const button=event.submitter;button.disabled=true;message('loginError','');passwordStep();
  try{
   const result=await api('/api/login',Object.fromEntries(new FormData(event.target)));
   if(result.requires_2fa){challenge=result.challenge;$('loginFactorDialog').showModal();$('loginCode').focus();return;}
   event.target.reset();await refresh();
  }catch(error){message('loginError',error.message);}finally{button.disabled=false;}
 }
 $('loginFactorForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;message('loginFactorError','');
  try{
   if(!challenge){passwordStep();message('loginError','Вход истёк. Введите логин и пароль заново.');return;}
   await api('/api/login/2fa',{challenge,code:$('loginCode').value.trim()});
   $('loginForm').reset();passwordStep();await refresh();
  }catch(error){message('loginFactorError',error.message);}finally{button.disabled=false;}
 });
 $('loginBack').onclick=()=>{passwordStep();$('loginForm').elements.password.focus();};
 $('loginFactorDialog').addEventListener('close',()=>{if(!$('loginFactorDialog').open)resetFactor();});
 $('loginForm').addEventListener('input',event=>{if(challenge&&['username','password'].includes(event.target.name)){passwordStep();message('loginError','');}});
 $('accountToggle').onclick=()=>selectPage('account');
 $('accountTabs').addEventListener('click',event=>{const b=event.target.closest('button');if(b?.dataset.accountTab)selectAccount(b.dataset.accountTab);});
 $('accountTabs').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;const b=event.target.closest('button');if(!b?.dataset.accountTab)return;const i=owns.indexOf(b.dataset.accountTab);const n=event.key==='Home'?0:event.key==='End'?2:(i+(event.key==='ArrowRight'?1:-1)+3)%3;event.preventDefault();selectAccount(owns[n],true);});
 $('accountProfileForm').addEventListener('input',()=>{$('accountProfileForm').dataset.dirty='1';});
 $('accountProfileForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{await api('/api/account/profile',Object.fromEntries(new FormData(event.target)));delete event.target.dataset.dirty;formStatus('accountProfileStatus','Настройки сохранены');await refresh();}catch(error){formStatus('accountProfileStatus',error.message,true);}finally{button.disabled=false;}});
 function savePreferences(){if(!state||applyingPreferences)return;clearTimeout(preferenceTimer);preferenceTimer=setTimeout(async()=>{try{await api('/api/account/profile',{preferences:{...window.Appearance.get(),language:window.I18n.language()}});}catch(error){notice(error.message);}},400);}
 document.addEventListener('appearancechange',savePreferences);document.addEventListener('languagechange',()=>{savePreferences();if(state)renderJobs();});
 $('uploadAvatar').onclick=()=>$('avatarFile').click();
 $('avatarFile').onchange=async()=>{const file=$('avatarFile').files[0];if(!file)return;try{if(file.size>2000000)throw new Error(t('Выберите PNG, JPEG или WebP до 2 МБ.'));const data=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<data.length;i+=8192)text+=String.fromCharCode(...data.subarray(i,i+8192));await api('/api/account/avatar',{image:btoa(text)});await refresh();formStatus('accountProfileStatus','Аватар сохранён');}catch(error){formStatus('accountProfileStatus',error.message,true);}finally{$('avatarFile').value='';}};
 $('removeAvatar').onclick=async()=>{try{await api('/api/account/avatar',{image:''});await refresh();}catch(error){formStatus('accountProfileStatus',error.message,true);}};
 function recovery(result){$('recoveryCodes').value=(result.recovery_codes||[]).join('\n');$('factorRecovery').hidden=!result.recovery_codes?.length;}
 for(const [form,path]of [['factorSetupForm','setup'],['factorEnableForm','enable'],['factorManageForm','manage']])$(form).addEventListener('submit',async event=>{event.preventDefault();const b=event.submitter;b.disabled=true;formStatus('factorStatus','');try{const action=path==='manage'?b.value:path;if(action==='disable'&&!await confirmAction('Отключить двухфакторную защиту?'))return;const data=Object.fromEntries(new FormData(event.target));const result=await api('/api/account/2fa/'+action,data);event.target.reset();if(action==='setup'){$('factorSecret').textContent=result.secret;$('factorQr').setAttribute('src','/api/account/2fa/qr?at='+Date.now());$('factorEnrollment').hidden=false;}else{recovery(result);await refresh();formStatus('factorStatus',action==='disable'?'Двухфакторная защита отключена':'Настройки сохранены');}}catch(error){formStatus('factorStatus',error.message,true);}finally{b.disabled=false;}});
 $('downloadRecovery').onclick=()=>{const blob=new Blob([$('recoveryCodes').value+'\n'],{type:'text/plain'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='xray-gateway-recovery-codes.txt';a.click();URL.revokeObjectURL(url);};
 $('closeRecovery').onclick=()=>{$('factorRecovery').hidden=true;$('recoveryCodes').value='';};
 function credentialMasks(){const f=$('routerConnectionForm'),same=savedRouter&&savedRouter.configured&&['host','username','auth'].every(key=>f.elements.namedItem(key).value.trim()===String(savedRouter[key]))&&Number(f.elements.port.value)===savedRouter.port;const fields={private_key:same&&savedRouter.auth==='key',password:same&&savedRouter.auth==='password',passphrase:same&&savedRouter.auth==='key'&&savedRouter.passphrase_set};for(const [name,present]of Object.entries(fields))f.elements.namedItem(name).placeholder=present?'••••••••••••':'';}
 function authFields(){$('routerKeyFields').hidden=$('routerAuth').value!=='key';$('routerPasswordField').hidden=$('routerAuth').value!=='password';credentialMasks();}
 $('routerAuth').onchange=authFields;
 async function loadRouter(){routerLoaded=true;try{const config=await api('/api/routeros/config'),form=$('routerConnectionForm');savedRouter=config;if(form.dataset.dirty==='1'){credentialMasks();return;}for(const key of ['host','port','username','auth','fingerprint'])form.elements.namedItem(key).value=config[key];authFields();message('routerConnectionState',config.configured?'Подключение настроено':'Подключение не настроено');}catch(error){routerLoaded=false;formStatus('routerConnectionStatus',error.message,true);}}
 $('routerConnectionForm').addEventListener('input',()=>{$('routerConnectionForm').dataset.dirty='1';credentialMasks();});
 $('routerScanKey').onclick=async()=>{const b=$('routerScanKey');b.disabled=true;try{const form=$('routerConnectionForm'),result=await api('/api/routeros/host-key',{host:form.elements.host.value,port:Number(form.elements.port.value)});form.elements.fingerprint.value=result.fingerprint;form.dataset.dirty='1';formStatus('routerConnectionStatus','Отпечаток получен');}catch(error){formStatus('routerConnectionStatus',error.message,true);}finally{b.disabled=false;}};
 $('routerConnectionForm').addEventListener('submit',async event=>{event.preventDefault();const b=event.submitter;b.disabled=true;try{const data=Object.fromEntries(new FormData(event.target));data.port=Number(data.port);if(!await confirmAction(()=>t('Сохранить подключение к RouterOS с ключом {0}?',data.fingerprint),'Сохранить'))return;await api('/api/routeros/config',data);for(const name of ['password','private_key','passphrase'])event.target.elements.namedItem(name).value='';delete event.target.dataset.dirty;routerLoaded=false;await loadRouter();formStatus('routerConnectionStatus','Подключение проверено и сохранено');}catch(error){formStatus('routerConnectionStatus',error.message,true);}finally{b.disabled=false;}});
 $('openRouterScript').onclick=()=>$('routerScriptDialog').showModal();$('closeRouterScript').onclick=()=>$('routerScriptDialog').close();
 let recent=[];
 function renderJobs(){$('routerJobs').innerHTML=recent.map(job=>`<div class="operation-row"><div><b>${esc(job.name)}</b><small>${esc(t(job.action==='delete'?'Удаление списка':'Установка списка'))}</small></div><span class="operation-state${job.status==='error'?' is-error':''}">${esc(jobState(job.status))}</span><button class="text-button" data-router-job="${job.id}">${t('Журнал')}</button></div>`).join('')||`<p class="muted">${t('Операций пока нет')}</p>`;}
 async function loadJobs(){try{recent=(await api('/api/routeros/jobs')).jobs;renderJobs();}catch(error){notice(error.message);}}
 async function startJob(action,identifier){const item=state.ip_lists.find(v=>v.id===identifier);if(!item)return;const source=action==='delete'?'Удалить список «{0}» из панели и все его ресурсы в RouterOS?':'Установить или обновить список «{0}» в RouterOS?';if(!await confirmAction(()=>t(source,item.name),action==='delete'?'Удалить':'Применить'))return;try{const job=await api(action==='delete'?'/api/ip-lists/delete':'/api/routeros/apply',{id:item.id,version:item.version});openJob(job.id);}catch(error){notice(error.message);}}
 function openJob(identifier){jobId=identifier;jobCursor=0;jobLines=[];$('routerJobLog').textContent='';if(!$('routerJobDialog').open)$('routerJobDialog').showModal();clearTimeout(jobTimer);pollJob();}
 async function pollJob(){const id=jobId;if(!id)return;try{const job=await api('/api/routeros/jobs/'+id+'?cursor='+jobCursor);if(jobId!==id)return;jobCursor=job.cursor;jobLines.push(...job.logs);jobLines=jobLines.slice(-600);$('routerJobTitle').textContent=job.name;message('routerJobStatus',()=>jobState(job.status));$('routerJobLog').textContent=jobLines.join('\n');$('routerJobLog').scrollTop=$('routerJobLog').scrollHeight;if(['done','error'].includes(job.status)){await refresh();await loadJobs();return;}}catch(error){message('routerJobStatus',error.message);return;}jobTimer=setTimeout(pollJob,500);}
 $('closeRouterJob').onclick=()=>$('routerJobDialog').close();$('routerJobDialog').addEventListener('close',()=>{jobId='';clearTimeout(jobTimer);});
 document.addEventListener('click',event=>{const b=event.target.closest('button');if(b?.dataset.routerJob)openJob(b.dataset.routerJob);});$('refreshRouterJobs').onclick=loadJobs;
 function fitTerminal(){if(!terminal||!sshId)return;fit.fit();api('/api/routeros/terminal/resize',{id:sshId,cols:terminal.cols,rows:terminal.rows}).catch(error=>message('terminalStatus',error.message));}
 function initTerminal(){if(terminal)return;terminal=new window.Terminal({cursorBlink:false,fontFamily:'Consolas, "Liberation Mono", monospace',fontSize:14,scrollback:2000,theme:{background:'#111820',foreground:'#e4eaf2'}});fit=new window.FitAddon.FitAddon();terminal.loadAddon(fit);terminal.open($('sshTerminal'));terminal.onData(data=>{const id=sshId;if(id)sshSending=sshSending.then(()=>id===sshId?api('/api/routeros/terminal/input',{id,data}):null).catch(error=>message('terminalStatus',error.message));});new ResizeObserver(()=>fitTerminal()).observe($('sshTerminal'));}
 async function pollTerminal(){const id=sshId;if(!id)return;try{const result=await api('/api/routeros/terminal/'+id+'?cursor='+sshCursor);if(sshId!==id)return;sshCursor=result.cursor;if(result.data)terminal.write(Uint8Array.from(atob(result.data),v=>v.charCodeAt(0)));if(result.closed){sshId='';message('terminalStatus','Соединение закрыто');render();if(page==='routeros'&&!sshManual)connectTerminal();return;}}catch(error){if(sshId!==id)return;sshId='';message('terminalStatus',error.message);render();return;}sshTimer=setTimeout(pollTerminal,150);}
 async function connectTerminal(){
  if(sshId||sshConnecting||!state||state.user.role!=='admin')return;
  const epoch=sshEpoch;sshConnecting=true;sshManual=false;message('terminalStatus','Подключение…');render();
  try{initTerminal();fit.fit();const result=await api('/api/routeros/terminal/open',{cols:terminal.cols,rows:terminal.rows});if(epoch!==sshEpoch)return;sshId=result.id;sshCursor=0;terminal.reset();message('terminalStatus','Подключено');if(page==='routeros')terminal.focus();pollTerminal();}
  catch(error){if(epoch===sshEpoch)message('terminalStatus',error.message);}
  finally{if(epoch===sshEpoch){sshConnecting=false;render();}}
 }
 $('terminalConnect').onclick=connectTerminal;
 $('terminalDisconnect').onclick=async()=>{sshManual=true;const id=sshId;sshId='';clearTimeout(sshTimer);try{if(id)await api('/api/routeros/terminal/close',{id});message('terminalStatus','Не подключено');}catch(error){message('terminalStatus',error.message);}render();};
 function pageChanged(name){if(name==='routeros'){loadJobs();if(!sshManual)connectTerminal();if(terminal)setTimeout(fitTerminal,0);}if(name!=='account'){$('recoveryCodes').value='';$('factorRecovery').hidden=true;}}
 window.Management={render,clear,login,startJob,page:pageChanged};if(state)render();
})();
