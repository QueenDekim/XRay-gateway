'use strict';
const $ = id => document.getElementById(id);
let state = null, csrf = '', page = 'overview', editing = null, editRevision = 0;
const fmt = (n, rate = false) => {n = Number(n || 0); const units = ['Б','КиБ','МиБ','ГиБ','ТиБ']; let i=0; while(n>=1024 && i<4){n/=1024;i++;}return `${n.toFixed(i ? 1 : 0)} ${units[i]}${rate?'/с':''}`;};
const duration = n => {n=Math.max(0,Math.floor(n));return n>=86400?`${Math.floor(n/86400)} д ${Math.floor(n%86400/3600)} ч`:n>=3600?`${Math.floor(n/3600)} ч ${Math.floor(n%3600/60)} м`:`${Math.floor(n/60)} м ${n%60} с`;};
const esc = x => String(x ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(path, data){const response=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(65000)});const body=await response.json();if(!response.ok){if(response.status===401 && path!=='/api/login'){showLogin();}throw new Error(body.error || 'Ошибка запроса');}return body;}
function showLogin(){$('loginView').hidden=false;$('appView').hidden=true;state=null;csrf='';for(const d of document.querySelectorAll('dialog[open]'))d.close();for(const id of ['passwordForm','userForm'])$(id).reset();for(const id of ['routingSettingsForm','probeSettingsForm','routerForm']){delete $(id).dataset.revision;delete $(id).dataset.dirty;}}
async function refresh(){try{const data=await api('/api/state');state=data;csrf=data.csrf;$('loginView').hidden=true;$('appView').hidden=false;render();}catch(e){if(state)notice(e.message);}}
function selectPage(value){page=value;for(const name of ['overview','profiles','iplists','routeros','settings'])$(name+'Page').hidden=name!==value;document.querySelectorAll('nav [data-page], .account-actions [data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===value));$('settingsToggle').setAttribute('aria-pressed',String(value==='settings'));$('pageName').textContent={overview:'Обзор',profiles:'Профили',iplists:'IP-списки',routeros:'RouterOS',settings:'Настройки'}[value];}
function status(p){if(!p.enabled)return ['Выключен','muted-state'];if(!p.health)return ['Проверка','pending'];if(state.checks[p.id]?.healthy)return [state.selected===p.id?'Активен':'Доступен',state.selected===p.id?'is-active':'ready'];return ['Недоступен','bad'];}
function badge(p){const [label,cls]=status(p);return `<span class="badge ${cls}">${label}</span>`;}
// All four renderers use the same samples, scale and time interval.
function trafficSamples(history){return history.map(p=>({at:Number(p.at)||0,uplink_bps:Math.max(0,Number(p.uplink_bps)||0),downlink_bps:Math.max(0,Number(p.downlink_bps)||0)})).filter(p=>Number.isFinite(p.uplink_bps)&&Number.isFinite(p.downlink_bps));}
function trafficPath(points, mode){
 if(!points.length)return '';
 const xy=p=>`${p.x.toFixed(2)},${p.y.toFixed(2)}`;
 let path='M'+xy(points[0]);
 for(let i=1;i<points.length;i++){
  const a=points[i-1],b=points[i];
  if(mode==='console'){path+=`H${b.x.toFixed(2)}V${b.y.toFixed(2)}`;continue;}
  if(mode!=='titan'){path+='L'+xy(b);continue;}
  const slope=(p,q)=>(q.y-p.y)/(q.x-p.x);
  const d=slope(a,b),before=i>1?slope(points[i-2],a):d,after=i+1<points.length?slope(b,points[i+1]):d;
  const tangent=(u,v)=>u*v>0?2*u*v/(u+v):0;
  const low=Math.min(a.y,b.y),high=Math.max(a.y,b.y),clamp=y=>Math.max(low,Math.min(high,y)),dx=(b.x-a.x)/3;
  path+=`C${(a.x+dx).toFixed(2)},${clamp(a.y+tangent(before,d)*dx).toFixed(2)} ${(b.x-dx).toFixed(2)},${clamp(b.y-tangent(d,after)*dx).toFixed(2)} ${xy(b)}`;
 }
 return path;
}
function renderTraffic(){
 const history=trafficSamples(state?.history||[]),design=document.documentElement.dataset.design||'titan';
 const peak=Math.max(1,...history.flatMap(p=>[p.uplink_bps,p.downlink_bps]));
 const points=key=>history.map((p,i)=>({x:history.length===1?500:8+i/(history.length-1)*984,y:278-p[key]/peak*268}));
 const down=points('downlink_bps'),up=points('uplink_bps'),lineMode=design==='contour'?'paper':design;
 $('downLine').setAttribute('d',design==='contour'?'':trafficPath(down,lineMode));
 $('upLine').setAttribute('d',design==='contour'?'':trafficPath(up,lineMode));
 $('downArea').setAttribute('d',design==='titan'&&down.length>1?trafficPath(down,'titan')+`L${down.at(-1).x},278L${down[0].x},278Z`:'');
 const title=(p,key)=>esc(new Date(p.at*1000).toLocaleTimeString('ru')+' · '+(key==='downlink_bps'?'Получено ':'Отправлено ')+fmt(p[key],true));
 $('trafficBars').innerHTML=design==='contour'?history.map((p,i)=>{
  const slot=1000/history.length,width=slot*.36;
  return ['downlink_bps','uplink_bps'].map((key,k)=>{const height=p[key]/peak*268;return `<rect class="traffic-bar ${k?'bar-up':'bar-down'}" x="${(i*slot+slot*.1+k*slot*.42).toFixed(2)}" y="${(278-height).toFixed(2)}" width="${width.toFixed(2)}" height="${height.toFixed(2)}" rx="1"><title>${title(p,key)}</title></rect>`;}).join('');
 }).join(''):'';
 $('trafficMarkers').innerHTML=(design==='paper'||history.length===1)&&design!=='contour'?history.map((p,i)=>['downlink_bps','uplink_bps'].map((key,k)=>{
  const point=(k?up:down)[i];return `<circle class="traffic-marker ${k?'marker-up':'marker-down'}" cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="3"><title>${title(p,key)}</title></circle>`;
 }).join('')).join(''):'';
 $('trafficChart').dataset.renderer=design;
 $('chartPeak').textContent='Шкала до '+fmt(peak,true);
 $('chartEmpty').textContent=history.length<2?'Ожидание измерений Xray…':`${history.length} измерений · ${new Date(history[0].at*1000).toLocaleTimeString('ru')} — ${new Date(history.at(-1).at*1000).toLocaleTimeString('ru')}`;
 $('trafficChartDescription').textContent=history.length?`${history.length} измерений. Входящий и исходящий трафик, байт в секунду. Максимум шкалы ${fmt(peak,true)}. Последнее измерение: получено ${fmt(history.at(-1).downlink_bps,true)}, отправлено ${fmt(history.at(-1).uplink_bps,true)}`:'Ожидание измерений Xray';
}
document.addEventListener('appearancechange',()=>{if(state)renderTraffic();});
function render(){const s=state,t=s.totals;renderIpLists();renderSettings();notice(s.stats_error || s.last_error || '');$('username').textContent=s.username;$('coreStatus').textContent=s.ready?'Xray работает':'Xray недоступен';$('coreStatus').classList.toggle('bad',!s.ready);$('totalDown').textContent=fmt(t.downlink);$('totalUp').textContent=fmt(t.uplink);$('downRate').textContent=fmt(t.downlink_bps,true)+' сейчас';$('upRate').textContent=fmt(t.uplink_bps,true)+' сейчас';$('uptime').textContent=duration(s.uptime);$('profileCount').textContent=`${s.profiles.filter(p=>p.enabled).length} включено / ${s.profiles.length} профилей`;$('selectedName').textContent=s.profiles.find(p=>p.id===s.selected)?.name || 'Direct';$('routeSince').textContent='Выбран '+duration(Date.now()/1000-s.since)+' назад';$('updated').textContent='Обновлено '+new Date().toLocaleTimeString('ru');
 $('overviewProfiles').innerHTML=s.profiles.length?s.profiles.map(p=>`<article class="profile-card ${p.id===s.selected?'selected':''}"><div class="profile-identity"><div class="card-top"><h3>${esc(p.name)}</h3>${badge(p)}</div><p class="endpoint">${esc(p.address)}:${esc(p.port)} · ${esc(p.transport)}</p></div><div class="card-stats"><div><small>Задержка проверки</small><b>${p.health?.ok?p.health.latency_ms+' мс':'—'}</b></div><div><small>Успешных проверок</small><b>${p.stats.checks?((p.stats.successful_checks||0)/p.stats.checks*100).toFixed(1)+'%':'—'}</b></div><div><small>Получено</small><b>${fmt(p.stats.downlink)}</b></div><div><small>Отправлено</small><b>${fmt(p.stats.uplink)}</b></div></div></article>`).join(''):'<p class="muted">Профилей нет</p>';
 $('profileRows').innerHTML=s.profiles.map(p=>`<tr><td><b>${esc(p.name)}</b><small>${esc(p.address)}:${esc(p.port)} · ${esc(p.transport)}</small></td><td>${badge(p)}</td><td class="mono">${p.priority}</td><td class="mono">${p.health?.ok?p.health.latency_ms+' мс':'—'}</td><td class="mono">↓ ${fmt(p.stats.downlink)}<small>↑ ${fmt(p.stats.uplink)}</small></td><td class="mono">${p.stats.successful_checks||0} / ${p.stats.checks||0}</td><td><button data-edit="${p.id}">Изменить</button><button class="danger" data-delete="${p.id}">Удалить</button></td></tr>`).join('');$('directTraffic').textContent=`↓ ${fmt(s.direct.downlink)} / ↑ ${fmt(s.direct.uplink)}`;
 renderTraffic();
}
function editProfile(id){editing=id;editRevision=state.revision;const p=state.profiles.find(p=>p.id===id),f=$('profileForm');f.reset();f.elements.name.value=p?.name||'';f.elements.priority.value=p?.priority||10;f.elements.enabled.checked=p?.enabled??true;f.elements.uri.required=!p;$('dialogTitle').textContent=p?'Редактирование профиля':'Новый профиль';$('profileError').textContent='';$('profileDialog').showModal();}
document.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;if(button.dataset.page)selectPage(button.dataset.page);if(button.dataset.edit)editProfile(button.dataset.edit);if(button.dataset.delete){const p=state.profiles.find(p=>p.id===button.dataset.delete);if(!confirm(`Удалить профиль «${p.name}»? Xray будет перезапущен, текущие соединения прервутся.`))return;button.disabled=true;try{await api('/api/profiles/delete',{id:p.id,revision:state.revision});await refresh();}catch(e){notice(e.message);}finally{button.disabled=false;}}});
$('loginForm').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('loginError').textContent='';try{await api('/api/login',Object.fromEntries(new FormData(e.target)));e.target.elements.password.value='';await refresh();}catch(error){$('loginError').textContent=error.message;}finally{b.disabled=false;}});
$('logout').onclick=async()=>{try{await api('/api/logout',{});showLogin();}catch(e){notice(e.message);}};
$('addProfile').onclick=()=>editProfile(null);$('closeDialog').onclick=()=>$('profileDialog').close();
$('profileForm').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('profileError').textContent='';try{const data=Object.fromEntries(new FormData(e.target));data.enabled=e.target.elements.enabled.checked;data.priority=Number(data.priority);data.revision=editRevision;if(editing)data.id=editing;if(!confirm('Применить профиль и перезапустить Xray?'))return;$('profileError').textContent='Применение…';await api('/api/profiles/'+(editing?'edit':'add'),data);$('profileDialog').close();await refresh();}catch(error){$('profileError').textContent=error.message;}finally{b.disabled=false;}});
$('routerForm').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const data=await api('/api/routeros',Object.fromEntries(new FormData(e.target)));$('routerOutput').value=data.script;$('routerOutput').dataset.warnings=(data.warnings||[]).join(' ');$('copyRouter').disabled=false;$('copyStatus').textContent=['Скрипт сформирован',...(data.warnings||[])].join(' ');}catch(error){notice(error.message);}finally{b.disabled=false;}});
$('copyRouter').onclick=async()=>{try{if(navigator.clipboard && window.isSecureContext){await navigator.clipboard.writeText($('routerOutput').value);}else{$('routerOutput').focus();$('routerOutput').select();if(!document.execCommand('copy'))throw new Error('copy');}$('copyStatus').textContent=['Скрипт скопирован',$('routerOutput').dataset.warnings||''].filter(Boolean).join(' ');}catch(e){$('copyStatus').textContent='Не удалось скопировать скрипт';}};
let editingList = null, editingListVersion = 0, listOptions = '';
function listCount(n){const mod=n%100;return n+' '+(mod>=11&&mod<=14?'записей':n%10===1?'запись':n%10>=2&&n%10<=4?'записи':'записей');}
function renderIpLists(){
 const lists=state.ip_lists||[];
 $('ipListCards').innerHTML=lists.length?lists.map(item=>`<article class="ip-list-card"><div class="card-top"><h2>${esc(item.name)}</h2><span class="list-count mono">${listCount(item.addresses.length)}</span></div><div class="ip-preview mono">${item.addresses.slice(0,5).map(esc).join('<br>')||'Пустой список'}</div><div class="ip-actions"><button class="secondary" data-list-edit="${item.id}">Изменить</button><button class="text-button" data-list-route="${item.id}">В RouterOS</button><button class="text-button danger" data-list-delete="${item.id}">Удалить</button></div></article>`).join(''):'<p class="muted">Списков нет</p>';
 const options='<option value="">Вручную</option>'+lists.map(item=>`<option value="${item.id}">${esc(item.name)} (${item.addresses.length})</option>`).join('');
 if(options!==listOptions){const previous=$('routerList').value,first=!listOptions;$('routerList').innerHTML=options;if(lists.some(item=>item.id===previous))$('routerList').value=previous;else if(first&&lists.length)$('routerList').value=lists[0].id;listOptions=options;}
 $('manualDestinations').hidden=Boolean($('routerList').value);
}
function editIpList(identifier){
 const item=(state.ip_lists||[]).find(item=>item.id===identifier);
 editingList=identifier;editingListVersion=item?.version||0;
 $('ipListForm').reset();$('ipListForm').elements.name.value=item?.name||'';
 $('ipAddresses').value=item?.addresses.join('\n')||'';
 $('ipListTitle').textContent=item?'Редактирование списка':'Новый список';
 $('ipListError').textContent='';$('ipListDialog').showModal();
}
async function copyText(value){
 if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value);return;}
 const buffer=document.createElement('textarea');buffer.className='clipboard-buffer';buffer.value=value;
 const parent=document.querySelector('dialog[open]')||document.body;parent.appendChild(buffer);
 buffer.select();try{if(!document.execCommand('copy'))throw new Error('Не удалось скопировать');}finally{buffer.remove();}
}
$('addIpList').onclick=()=>editIpList(null);
$('closeIpList').onclick=()=>$('ipListDialog').close();
$('routerList').onchange=()=>{$('manualDestinations').hidden=Boolean($('routerList').value);};
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.listEdit)editIpList(button.dataset.listEdit);
 if(button.dataset.listRoute){$('routerList').value=button.dataset.listRoute;$('manualDestinations').hidden=true;selectPage('routeros');}
 if(button.dataset.listDelete){const item=state.ip_lists.find(item=>item.id===button.dataset.listDelete);if(!confirm(`Удалить список «${item.name}»?`))return;button.disabled=true;try{await api('/api/ip-lists/delete',{id:item.id,version:item.version});await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}}
});
$('ipListForm').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.submitter;button.disabled=true;$('ipListError').textContent='';
 try{const data=Object.fromEntries(new FormData(event.target));if(editingList){data.id=editingList;data.version=editingListVersion;}
 await api('/api/ip-lists/'+(editingList?'edit':'add'),data);$('ipListDialog').close();await refresh();}
 catch(error){$('ipListError').textContent=error.message;}finally{button.disabled=false;}
});
$('importIps').onclick=()=>$('ipFile').click();
$('ipFile').onchange=async()=>{const file=$('ipFile').files[0];if(!file)return;if(file.size>200000){$('ipListError').textContent='Размер файла превышает 200 КБ';return;}$('ipAddresses').value=await file.text();$('ipFile').value='';};
$('copyIps').onclick=async()=>{try{await copyText($('ipAddresses').value);$('ipListError').textContent='';}catch(error){$('ipListError').textContent=error.message;}};

const routingKeys = ['gateway','host','source','interface','local_networks'];
const probeKeys = ['probe_url','check_interval','fail_threshold','recover_threshold'];
const settingsTabs=['appearance','routing','probes','users','security'];
let settingsTab='appearance';
function allowedSettingsTabs(){return settingsTabs.filter(name=>state?.user?.role==='admin'||['appearance','security'].includes(name));}
function selectSettingsTab(name,focus=false){
 const allowed=allowedSettingsTabs();settingsTab=allowed.includes(name)?name:'appearance';
 for(const key of settingsTabs){const button=$('settingsTab-'+key);button.hidden=!allowed.includes(key);button.setAttribute('aria-selected',String(key===settingsTab));button.tabIndex=key===settingsTab?0:-1;$('settingsPanel-'+key).hidden=!allowed.includes(key)||key!==settingsTab;}
 if(focus)$('settingsTab-'+settingsTab).focus();
}
$('settingsTabs').addEventListener('click',event=>{const button=event.target.closest('button');if(button?.dataset.settingsTab)selectSettingsTab(button.dataset.settingsTab);});
$('settingsTabs').addEventListener('keydown',event=>{
 if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
 const button=event.target.closest('button');if(!button?.dataset.settingsTab)return;
 const allowed=allowedSettingsTabs(),index=allowed.indexOf(button.dataset.settingsTab);
 const next=event.key==='Home'?0:event.key==='End'?allowed.length-1:(index+(event.key==='ArrowRight'?1:-1)+allowed.length)%allowed.length;
 event.preventDefault();selectSettingsTab(allowed[next],true);
});
let editingUser = null, editingUserRevision = 0;
function fillSettingsForm(id, keys, settings){
 const form=$(id);if(!settings||form.dataset.dirty==='1'||form.dataset.revision===String(settings.revision))return;
 for(const key of keys)form.elements.namedItem(key).value=settings[key];form.dataset.revision=String(settings.revision);
}
function renderSettings(){
 const admin=state.user?.role==='admin';
 selectSettingsTab(settingsTab);
 for(const id of ['routingSettingsForm','probeSettingsForm','usersSettings'])$(id).hidden=!admin;
 fillSettingsForm('routingSettingsForm',routingKeys,state.settings);
 fillSettingsForm('probeSettingsForm',probeKeys,state.settings);
 fillSettingsForm('routerForm',['source','interface','local_networks'],state.settings);
 $('userRows').innerHTML=admin?(state.users||[]).map(u=>`<tr><td><b>${esc(u.username)}</b>${u.id===state.user.id?'<small>Вы</small>':''}</td><td>${u.role==='admin'?'Администратор':'Пользователь'}</td><td><button data-user-edit="${u.id}">Изменить</button>${u.id===state.user.id?'':`<button class="danger" data-user-delete="${u.id}">Удалить</button>`}</td></tr>`).join(''):'';
}
function readableSettingsError(text){const labels={check_interval:'Интервал проверки',fail_threshold:'Порог ошибок',recover_threshold:'Порог восстановления'};return String(text).replace(/^(check_interval|fail_threshold|recover_threshold):/,(_,key)=>labels[key]+':');}
function formStatus(id, text, error=false){$(id).textContent=text;$(id).classList.toggle('error',error);}
for(const [id,statusId] of [['routingSettingsForm','routingSettingsStatus'],['probeSettingsForm','probeSettingsStatus']]){
 $(id).addEventListener('input',()=>{$(id).dataset.dirty='1';formStatus(statusId,'');});
 $(id).addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter,form=event.target;button.disabled=true;
  try{const data=Object.fromEntries(new FormData(form));data.revision=Number(form.dataset.revision);await api('/api/settings',data);delete form.dataset.dirty;delete form.dataset.revision;formStatus(statusId,'Настройки сохранены');await refresh();}
  catch(error){formStatus(statusId,readableSettingsError(error.message),true);}finally{button.disabled=false;}
 });
}
$('routerForm').addEventListener('input',()=>{$('routerForm').dataset.dirty='1';});
$('passwordForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter,form=event.target;button.disabled=true;
 try{const data=Object.fromEntries(new FormData(form));if(data.password!==data.repeat_password)throw new Error('Пароли не совпадают');delete data.repeat_password;await api('/api/password',data);form.reset();formStatus('passwordStatus','Пароль изменён');await refresh();}
 catch(error){formStatus('passwordStatus',error.message,true);}finally{button.disabled=false;}
});
function editUser(id){
 const user=(state.users||[]).find(u=>u.id===id),form=$('userForm');editingUser=id;editingUserRevision=user?.revision||0;form.reset();
 form.elements.username.value=user?.username||'';form.elements.role.value=user?.role||'operator';form.elements.password.required=!user;
 $('userDialogTitle').textContent=user?'Редактирование пользователя':'Новый пользователь';$('userPasswordLabel').textContent=user?'Новый пароль (необязательно)':'Пароль';$('userError').textContent='';$('userDialog').showModal();
}
$('addUser').onclick=()=>editUser(null);
$('closeUser').onclick=()=>$('userDialog').close();
$('userDialog').addEventListener('close',()=>{$('userForm').reset();$('userError').textContent='';});
document.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;
 if(button.dataset.userEdit)editUser(button.dataset.userEdit);
 if(button.dataset.userDelete){const user=state.users.find(u=>u.id===button.dataset.userDelete);if(!confirm(`Удалить пользователя «${user.username}»?`))return;button.disabled=true;
  try{await api('/api/users/delete',{id:user.id,revision:user.revision});await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}
 }
});
$('userForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter,form=event.target;button.disabled=true;$('userError').textContent='';
 try{const data=Object.fromEntries(new FormData(form));if(editingUser){data.id=editingUser;data.revision=editingUserRevision;}await api('/api/users/'+(editingUser?'edit':'add'),data);form.reset();$('userDialog').close();await refresh();}
 catch(error){$('userError').textContent=error.message;}finally{button.disabled=false;}
});

refresh();setInterval(()=>{if(state && !document.hidden)refresh();},5000);
