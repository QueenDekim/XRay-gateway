'use strict';
const $ = id => document.getElementById(id);
const t = (source,...values) => window.I18n.t(source,...values);
const locale = () => window.I18n.locale();
const canManage = () => state?.user?.role==='admin';
function successfulChecks(stats){
 if(!stats.checks)return '—';
 const successful=stats.successful_checks||0,value=(successful/stats.checks*100).toFixed(1);
 return successful<stats.checks&&value==='100.0'?'~99.9%':value+'%';
}
const messages = new Map();
function message(id,value){messages.set(id,value);$(id).textContent=typeof value==='function'?value():t(value);}
let confirmationResolve=null,confirmationAccepted=false;
function confirmAction(text,label='Подтвердить'){
 if(confirmationResolve)return Promise.resolve(false);
 message('confirmationText',text);message('confirmationAccept',label);confirmationAccepted=false;
 return new Promise(resolve=>{confirmationResolve=resolve;$('confirmationDialog').showModal();$('confirmationCancel').focus();});
}
$('confirmationAccept').onclick=()=>{confirmationAccepted=true;$('confirmationDialog').close();};
$('confirmationCancel').onclick=()=>$('confirmationDialog').close();
$('confirmationDialog').addEventListener('close',()=>{const resolve=confirmationResolve;confirmationResolve=null;resolve?.(confirmationAccepted);confirmationAccepted=false;message('confirmationText','');});
let state = null, csrf = '', page = 'overview', editing = null, editRevision = 0;
const fmt = (n, rate = false) => {n = Number(n || 0); const units = ['Б','КиБ','МиБ','ГиБ','ТиБ']; let i=0; while(n>=1024 && i<4){n/=1024;i++;}return `${n.toFixed(i ? 1 : 0)} ${t(units[i])}${rate?t('/с'):''}`;};
const duration = n => {n=Math.max(0,Math.floor(n));return n>=86400?`${Math.floor(n/86400)} ${t('д')} ${Math.floor(n%86400/3600)} ${t('ч')}`:n>=3600?`${Math.floor(n/3600)} ${t('ч')} ${Math.floor(n%3600/60)} ${t('м')}`:`${Math.floor(n/60)} ${t('м')} ${n%60} ${t('с')}`;};
const esc = x => String(x ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(text){message('notice',text);$('notice').hidden=!text;}
async function api(path, data){const response=await fetch(path,{method:data?'POST':'GET',headers:{'Accept-Language':window.I18n.language(),...(data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{})},body:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(65000)});const body=await response.json();if(!response.ok){if(response.status===401 && !path.startsWith('/api/login')){showLogin();}throw new Error(t(body.error || 'Ошибка запроса'));}return body;}
function showLogin(){window.Management?.clear();$('loginView').hidden=false;$('appView').hidden=true;state=null;csrf='';for(const d of document.querySelectorAll('dialog[open]'))d.close();for(const id of ['passwordForm','userForm'])$(id).reset();for(const id of ['routingSettingsForm','probeSettingsForm','routerForm']){delete $(id).dataset.revision;delete $(id).dataset.dirty;}}
async function refresh(){try{const data=await api('/api/state');state=data;csrf=data.csrf;$('loginView').hidden=true;$('appView').hidden=false;render();}catch(e){if(state)notice(e.message);}}
function selectPage(value){if(value==='routeros'&&!canManage())value='overview';if(value==='settings'&&state?.user?.role!=='admin')value='account';page=value;for(const name of ['overview','profiles','iplists','routeros','settings','account'])$(name+'Page').hidden=name!==value;document.querySelectorAll('nav [data-page], .account-actions [data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===value));$('settingsToggle').setAttribute('aria-pressed',String(value==='settings'));$('pageName').textContent=t({overview:'Обзор',profiles:'Профили',iplists:'IP-списки',routeros:'RouterOS',settings:'Настройки',account:'Моя учётная запись'}[value]);window.Management?.page(value);}
function status(p){if(!p.enabled)return ['Выключен','muted-state'];if(!p.health)return ['Проверка','pending'];if(state.checks[p.id]?.healthy)return [state.selected===p.id?'Активен':'Доступен',state.selected===p.id?'is-active':'ready'];return ['Недоступен','bad'];}
function badge(p){const [label,cls]=status(p);return `<span class="badge ${cls}">${t(label)}</span>`;}
function profileTransport(p){const name=({tcp:'RAW/TCP',raw:'RAW/TCP',xhttp:'XHTTP',splithttp:'XHTTP',ws:'WebSocket',websocket:'WebSocket',grpc:'gRPC',httpupgrade:'HTTPUpgrade',kcp:'mKCP',mkcp:'mKCP',hysteria:'Hysteria',xdrive:'XDrive'})[p.transport]||p.transport;return name+(p.security?' / '+(p.security==='none'?t('без TLS'):p.security==='tls'?'TLS':p.security==='reality'?'REALITY':p.security):'');}
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
 const title=(p,key)=>esc(new Date(p.at*1000).toLocaleTimeString(locale())+' · '+t(key==='downlink_bps'?'Получено':'Отправлено')+' '+fmt(p[key],true));
 $('trafficBars').innerHTML=design==='contour'?history.map((p,i)=>{
  const slot=1000/history.length,width=slot*.36;
  return ['downlink_bps','uplink_bps'].map((key,k)=>{const height=p[key]/peak*268;return `<rect class="traffic-bar ${k?'bar-up':'bar-down'}" x="${(i*slot+slot*.1+k*slot*.42).toFixed(2)}" y="${(278-height).toFixed(2)}" width="${width.toFixed(2)}" height="${height.toFixed(2)}" rx="1"><title>${title(p,key)}</title></rect>`;}).join('');
 }).join(''):'';
 $('trafficMarkers').innerHTML=(design==='paper'||history.length===1)&&design!=='contour'?history.map((p,i)=>['downlink_bps','uplink_bps'].map((key,k)=>{
  const point=(k?up:down)[i];return `<circle class="traffic-marker ${k?'marker-up':'marker-down'}" cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="3"><title>${title(p,key)}</title></circle>`;
 }).join('')).join(''):'';
 $('trafficChart').dataset.renderer=design;
 $('chartPeak').textContent=t('Шкала до {0}',fmt(peak,true));
 $('chartEmpty').textContent=history.length<2?t('Ожидание измерений Xray…'):t('{0} измерений · {1} — {2}',history.length,new Date(history[0].at*1000).toLocaleTimeString(locale()),new Date(history.at(-1).at*1000).toLocaleTimeString(locale()));
 $('trafficChartDescription').textContent=history.length?t('{0} измерений. Входящий и исходящий трафик, байт в секунду. Максимум шкалы {1}. Последнее измерение: получено {2}, отправлено {3}',history.length,fmt(peak,true),fmt(history.at(-1).downlink_bps,true),fmt(history.at(-1).uplink_bps,true)):t('Ожидание измерений Xray');
}
document.addEventListener('appearancechange',()=>{if(state)renderTraffic();});
function render(){const s=state,totals=s.totals;for(const id of ['addProfile','resetProfileChecks','addIpList','profileActionsHeader','routerNav'])$(id).hidden=!canManage();if(page==='routeros'&&!canManage())selectPage('overview');renderIpLists();renderSettings();notice(s.stats_error || s.last_error || '');$('username').textContent=s.user?.display_name||s.username;$('coreStatus').textContent=t(s.ready?'Xray работает':'Xray недоступен');$('coreStatus').classList.toggle('bad',!s.ready);$('totalDown').textContent=fmt(totals.downlink);$('totalUp').textContent=fmt(totals.uplink);$('downRate').textContent=fmt(totals.downlink_bps,true)+' '+window.I18n.t('сейчас');$('upRate').textContent=fmt(totals.uplink_bps,true)+' '+window.I18n.t('сейчас');$('uptime').textContent=duration(s.uptime);$('profileCount').textContent=window.I18n.t('{0} включено / {1} профилей',s.profiles.filter(p=>p.enabled).length,s.profiles.length);$('selectedName').textContent=s.profiles.find(p=>p.id===s.selected)?.name || 'Direct';$('routeSince').textContent=window.I18n.t('Выбран {0} назад',duration(Date.now()/1000-s.since));$('updated').textContent=window.I18n.t('Обновлено {0}',new Date().toLocaleTimeString(locale()));
 $('overviewProfiles').innerHTML=s.profiles.length?s.profiles.map(p=>`<article class="profile-card ${p.id===s.selected?'selected':''}"><div class="profile-identity"><div class="card-top"><h3>${esc(p.name)}</h3>${badge(p)}</div><p class="endpoint">${esc(p.address)}:${esc(p.port)} · ${esc(profileTransport(p))}</p></div><div class="card-stats"><div><small>${window.I18n.t('Задержка проверки')}</small><b>${p.health?.ok?p.health.latency_ms+' '+window.I18n.t('мс'):'—'}</b></div><div><small>${window.I18n.t('Успешных проверок')}</small><b>${successfulChecks(p.stats)}</b></div><div><small>${window.I18n.t('Получено')}</small><b>${fmt(p.stats.downlink)}</b></div><div><small>${window.I18n.t('Отправлено')}</small><b>${fmt(p.stats.uplink)}</b></div></div></article>`).join(''):`<p class="muted">${window.I18n.t('Профилей нет')}</p>`;
 $('profileRows').innerHTML=s.profiles.map(p=>`<tr><td><b>${esc(p.name)}</b><small>${esc(p.address)}:${esc(p.port)} · ${esc(profileTransport(p))}</small></td><td>${badge(p)}</td><td class="mono">${p.priority}</td><td class="mono">${p.health?.ok?p.health.latency_ms+' '+window.I18n.t('мс'):'—'}</td><td class="mono">↓ ${fmt(p.stats.downlink)}<small>↑ ${fmt(p.stats.uplink)}</small></td><td class="mono">${p.stats.successful_checks||0} / ${p.stats.checks||0}</td>${canManage()?`<td><button data-edit="${p.id}">${window.I18n.t('Изменить')}</button><button class="danger" data-delete="${p.id}">${window.I18n.t('Удалить')}</button></td>`:''}</tr>`).join('');$('directTraffic').textContent=`↓ ${fmt(s.direct.downlink)} / ↑ ${fmt(s.direct.uplink)}`;
 renderTraffic();window.Management?.render();
}
let profileImport=null,profileSourceEpoch=0;
function resetProfileImport(){
 profileSourceEpoch++;profileImport=null;$('subscriptionProfiles').hidden=true;$('subscriptionOptions').innerHTML='';
 $('profileNameField').hidden=false;$('profileForm').elements.name.required=true;
 $('loadSubscription').hidden=!/^https?:\/\//i.test($('profileForm').elements.uri.value.trim());
}
function renderSubscriptionProfiles(updateOptions=true){
 if(!profileImport)return;
 const chosen=profileImport.selected;
 if(updateOptions)$('subscriptionOptions').innerHTML=profileImport.profiles.map(p=>`<label class="subscription-option checkbox"><input type="${editing?'radio':'checkbox'}" name="subscriptionChoice" data-subscription-profile="${esc(p.id)}" ${chosen.has(p.id)?'checked':''}><span><b>${esc(p.name)}</b><small class="mono">${esc(p.address)}:${p.port} · ${esc(profileTransport(p))}</small></span></label>`).join('');
 $('subscriptionProfiles').hidden=false;$('profileNameField').hidden=!editing&&chosen.size!==1;
 const name=$('profileForm').elements.name;name.required=!$('profileNameField').hidden;
 if(!editing&&chosen.size===1&&!name.value)name.value=profileImport.profiles.find(p=>chosen.has(p.id)).name;
}
async function loadProfileSubscription(){
 if(!canManage())return false;
 const source=$('profileForm').elements.uri.value.trim();resetProfileImport();const epoch=profileSourceEpoch,button=$('loadSubscription');button.disabled=true;message('profileError','Загрузка подписки…');
 try{
  const result=await api('/api/profiles/preview',{uri:source});
  if(epoch!==profileSourceEpoch||!canManage()||!$('profileDialog').open||source!==$('profileForm').elements.uri.value.trim())return false;
  const current=state.profiles.find(p=>p.id===editing),profiles=result.profiles;
  const recommended=profiles.find(p=>p.address===current?.address&&p.port===current?.port&&p.transport===current?.transport&&p.security===current?.security)||profiles.find(p=>p.transport===current?.transport&&p.security===current?.security)||profiles[0];
  profileImport={source,token:result.token,profiles,selected:new Set(editing?[recommended.id]:profiles.map(p=>p.id))};
  renderSubscriptionProfiles();message('profileError',result.skipped?()=>t('Пропущено неподдерживаемых профилей: {0}',result.skipped):'');return true;
 }catch(error){if(epoch===profileSourceEpoch)message('profileError',error.message);return false;}finally{if(epoch===profileSourceEpoch)button.disabled=false;}
}
$('loadSubscription').onclick=loadProfileSubscription;
$('profileSource').addEventListener('input',()=>{resetProfileImport();$('loadSubscription').disabled=false;message('profileError','');});
$('subscriptionOptions').addEventListener('change',event=>{
 const id=event.target.dataset.subscriptionProfile;if(!profileImport||!id)return;
 if(editing)profileImport.selected=new Set([id]);else if(event.target.checked)profileImport.selected.add(id);else profileImport.selected.delete(id);
 renderSubscriptionProfiles(false);
});
$('profileDialog').addEventListener('close',()=>{resetProfileImport();$('loadSubscription').disabled=false;});
function editProfile(id){if(!canManage())return;editing=id;editRevision=state.revision;const p=state.profiles.find(p=>p.id===id),f=$('profileForm');f.reset();f.elements.name.value=p?.name||'';f.elements.priority.value=p?.priority||10;f.elements.enabled.checked=p?.enabled??true;f.elements.uri.required=!p;resetProfileImport();$('loadSubscription').disabled=false;$('dialogTitle').textContent=t(p?'Редактирование профиля':'Новый профиль');message('profileError','');$('profileDialog').showModal();}
document.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;if(button.dataset.page)selectPage(button.dataset.page);if(button.dataset.edit)editProfile(button.dataset.edit);if(button.dataset.delete&&canManage()){const p=state.profiles.find(p=>p.id===button.dataset.delete);if(!await confirmAction(()=>t('Удалить профиль «{0}»? Xray будет перезапущен, текущие соединения прервутся.',p.name),'Удалить'))return;button.disabled=true;try{await api('/api/profiles/delete',{id:p.id,revision:state.revision});await refresh();}catch(e){notice(e.message);}finally{button.disabled=false;}}});
$('loginForm').addEventListener('submit',event=>{event.preventDefault();window.Management.login(event);});
$('logout').onclick=async()=>{try{await api('/api/logout',{});showLogin();}catch(e){notice(e.message);}};
$('addProfile').onclick=()=>editProfile(null);$('closeDialog').onclick=()=>$('profileDialog').close();
$('resetProfileChecks').onclick=async()=>{if(!canManage())return;const button=$('resetProfileChecks');button.disabled=true;try{await api('/api/profiles/reset-checks',{});await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}};
$('profileForm').addEventListener('submit',async e=>{
 e.preventDefault();if(!canManage())return;const b=e.submitter;b.disabled=true;message('profileError','');
 try{
  const source=e.target.elements.uri.value.trim();
  if(/^https?:\/\//i.test(source)&&profileImport?.source!==source){await loadProfileSubscription();return;}
  const data=Object.fromEntries(new FormData(e.target));data.enabled=e.target.elements.enabled.checked;data.priority=Number(data.priority);data.revision=editRevision;if(editing)data.id=editing;
  if(profileImport&&profileImport.source===source){
   if(!profileImport.selected.size)throw new Error(t('Выберите хотя бы один профиль подписки.'));
   data.subscription_token=profileImport.token;data.subscription_profiles=[...profileImport.selected];delete data.subscriptionChoice;
  }
  if(!await confirmAction('Применить профили и перезапустить Xray?','Применить'))return;
  message('profileError','Применение…');await api('/api/profiles/'+(editing?'edit':'add'),data);$('profileDialog').close();await refresh();
 }catch(error){message('profileError',error.message);}finally{b.disabled=false;}
});
$('routerForm').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const data=await api('/api/routeros',Object.fromEntries(new FormData(e.target)));$('routerOutput').value=data.script;$('routerOutput').dataset.warnings=(data.warnings||[]).join(' ');$('copyRouter').disabled=false;message('copyStatus',()=>[t('Скрипт сформирован'),...(data.warnings||[]).map(value=>t(value))].join(' '));}catch(error){notice(error.message);}finally{b.disabled=false;}});
$('copyRouter').onclick=async()=>{try{if(navigator.clipboard && window.isSecureContext){await navigator.clipboard.writeText($('routerOutput').value);}else{$('routerOutput').focus();$('routerOutput').select();if(!document.execCommand('copy'))throw new Error('copy');}message('copyStatus',()=>[t('Скрипт скопирован'),t($('routerOutput').dataset.warnings||'')].filter(Boolean).join(' '));}catch(e){message('copyStatus','Не удалось скопировать скрипт');}};
let editingList = null, editingListVersion = 0, listOptions = '';
function listCount(n){if(window.I18n.language()==='en')return n+' '+(n===1?'entry':'entries');const mod=n%100;return n+' '+(mod>=11&&mod<=14?'записей':n%10===1?'запись':n%10>=2&&n%10<=4?'записи':'записей');}
function renderIpLists(){
 const lists=state.ip_lists||[];
 $('ipListCards').innerHTML=lists.length?lists.map(item=>`<article class="ip-list-card"><div class="card-top"><h2>${esc(item.name)}</h2><span class="list-count mono">${listCount(item.addresses.length)}</span></div><div class="ip-preview mono">${item.addresses.slice(0,3).map(esc).join(', ')||t('Пустой список')}</div><div class="ip-actions">${canManage()?`<button class="secondary" data-list-edit="${item.id}">${t('Изменить')}</button><button class="text-button" data-list-route="${item.id}">${t('В RouterOS')}</button><button class="text-button danger" data-list-delete="${item.id}">${t('Удалить')}</button>`:`<button class="secondary" data-list-view="${item.id}">${t('Просмотр списка')}</button>`}</div></article>`).join(''):`<p class="muted">${t('Списков нет')}</p>`;
 const options=`<option value="">${window.I18n.t('Вручную')}</option>`+lists.map(item=>`<option value="${item.id}">${esc(item.name)} (${item.addresses.length})</option>`).join('');
 if(options!==listOptions){const previous=$('routerList').value,first=!listOptions;$('routerList').innerHTML=options;if(lists.some(item=>item.id===previous))$('routerList').value=previous;else if(first&&lists.length)$('routerList').value=lists[0].id;listOptions=options;}
 $('manualDestinations').hidden=Boolean($('routerList').value);
}
function editIpList(identifier){
 const item=(state.ip_lists||[]).find(item=>item.id===identifier);if(!canManage()&&!item)return;
 editingList=identifier;editingListVersion=item?.version||0;
 $('ipListForm').reset();const name=$('ipListForm').elements.namedItem('name');name.value=item?.name||'';name.readOnly=!canManage();$('ipAddresses').readOnly=!canManage();$('saveIpList').hidden=!canManage();$('saveIpList').disabled=!canManage();$('importIps').hidden=!canManage();$('ipFile').disabled=!canManage();
 $('ipAddresses').value=item?.addresses.join('\n')||'';
 $('ipListTitle').textContent=t(!canManage()?'Просмотр списка':item?'Редактирование списка':'Новый список');
 message('ipListError','');$('ipListDialog').showModal();
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
 if(button.dataset.listEdit||button.dataset.listView)editIpList(button.dataset.listEdit||button.dataset.listView);
 if(button.dataset.listRoute&&canManage())await window.Management.startJob('apply',button.dataset.listRoute);
 if(button.dataset.listDelete&&canManage())await window.Management.startJob('delete',button.dataset.listDelete);
});
$('ipListForm').addEventListener('submit',async event=>{
 event.preventDefault();if(!canManage())return;const button=event.submitter;button.disabled=true;message('ipListError','');
 try{const data=Object.fromEntries(new FormData(event.target));if(editingList){data.id=editingList;data.version=editingListVersion;}
 await api('/api/ip-lists/'+(editingList?'edit':'add'),data);$('ipListDialog').close();await refresh();}
 catch(error){message('ipListError',error.message);}finally{button.disabled=false;}
});
$('importIps').onclick=()=>{if(canManage())$('ipFile').click();};
$('ipFile').onchange=async()=>{if(!canManage())return;const file=$('ipFile').files[0];if(!file)return;if(file.size>200000){message('ipListError','Размер файла превышает 200 КБ');return;}$('ipAddresses').value=await file.text();$('ipFile').value='';};
$('copyIps').onclick=async()=>{try{await copyText($('ipAddresses').value);message('ipListError','');}catch(error){message('ipListError',error.message);}};

const routingKeys = ['gateway','host','source','interface','local_networks'];
const probeKeys = ['probe_url','check_interval','fail_threshold','recover_threshold'];
const settingsTabs=['routing','probes','router','users'];
let settingsTab='routing';
function allowedSettingsTabs(){return state?.user?.role==='admin'?settingsTabs:[];}
function selectSettingsTab(name,focus=false){
 const allowed=allowedSettingsTabs();settingsTab=allowed.includes(name)?name:'routing';
 for(const key of settingsTabs){const button=$('settingsTab-'+key);button.hidden=!allowed.includes(key);button.setAttribute('aria-selected',String(key===settingsTab));button.tabIndex=key===settingsTab?0:-1;$('settingsPanel-'+key).hidden=!allowed.includes(key)||key!==settingsTab;}
 if(focus)$('settingsTab-'+settingsTab).focus();
}
$('settingsTabs').addEventListener('click',event=>{const button=event.target.closest('button');if(button?.dataset.settingsTab)selectSettingsTab(button.dataset.settingsTab);});
$('settingsTabs').addEventListener('keydown',event=>{
 if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
 const button=event.target.closest('button');if(!button?.dataset.settingsTab)return;
 const allowed=allowedSettingsTabs(),index=allowed.indexOf(button.dataset.settingsTab);if(!allowed.length)return;
 const next=event.key==='Home'?0:event.key==='End'?allowed.length-1:(index+(event.key==='ArrowRight'?1:-1)+allowed.length)%allowed.length;
 event.preventDefault();selectSettingsTab(allowed[next],true);
});
let editingUser = null, editingUserRevision = 0;
function fillSettingsForm(id, keys, settings){
 const form=$(id);if(!settings||form.dataset.dirty==='1'||form.dataset.revision===String(settings.revision))return;
 for(const key of keys)form.elements.namedItem(key).value=settings[key];form.dataset.revision=String(settings.revision);
}
function renderSettings(){
 const admin=state.user?.role==='admin';$('settingsToggle').hidden=!admin;
 selectSettingsTab(settingsTab);
 for(const id of ['routingSettingsForm','probeSettingsForm','usersSettings'])$(id).hidden=!admin;
 fillSettingsForm('routingSettingsForm',routingKeys,state.settings);
 fillSettingsForm('probeSettingsForm',probeKeys,state.settings);
 fillSettingsForm('routerForm',['source','interface','local_networks'],state.settings);
 $('userRows').innerHTML=admin?(state.users||[]).map(u=>`<tr><td><b>${esc(u.username)}</b>${u.id===state.user.id?`<small>${window.I18n.t('Вы')}</small>`:''}</td><td>${t(u.role==='admin'?'Администратор':'Пользователь')}</td><td><button data-user-edit="${u.id}">${window.I18n.t('Изменить')}</button>${u.id===state.user.id?'':`<button class="danger" data-user-delete="${u.id}">${window.I18n.t('Удалить')}</button>`}</td></tr>`).join(''):'';
}
function readableSettingsError(text){const labels={check_interval:'Интервал проверки',fail_threshold:'Порог ошибок',recover_threshold:'Порог восстановления'};return String(text).replace(/^(check_interval|fail_threshold|recover_threshold): допустимо целое число от (\d+) до (\d+)\.$/,(_,key,min,max)=>t('{0}: допустимо целое число от {1} до {2}.',t(labels[key]),min,max)).replace(/^(check_interval|fail_threshold|recover_threshold): enter an integer from (\d+) to (\d+)\.$/,(_,key,min,max)=>t('{0}: допустимо целое число от {1} до {2}.',t(labels[key]),min,max)).replace(/^(check_interval|fail_threshold|recover_threshold):/,(_,key)=>t(labels[key])+':');}
function formStatus(id, text, error=false){message(id,text);$(id).classList.toggle('error',error);}
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
 $('userDialogTitle').textContent=t(user?'Редактирование пользователя':'Новый пользователь');$('userPasswordLabel').textContent=t(user?'Новый пароль (необязательно)':'Пароль');message('userError','');$('userDialog').showModal();
}
$('addUser').onclick=()=>editUser(null);
$('closeUser').onclick=()=>$('userDialog').close();
$('userDialog').addEventListener('close',()=>{$('userForm').reset();message('userError','');});
document.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;
 if(button.dataset.userEdit)editUser(button.dataset.userEdit);
 if(button.dataset.userDelete){const user=state.users.find(u=>u.id===button.dataset.userDelete);if(!await confirmAction(()=>t('Удалить пользователя «{0}»?',user.username),'Удалить'))return;button.disabled=true;
  try{await api('/api/users/delete',{id:user.id,revision:user.revision});await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}
 }
});
$('userForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter,form=event.target;button.disabled=true;message('userError','');
 try{const data=Object.fromEntries(new FormData(form));if(editingUser){data.id=editingUser;data.revision=editingUserRevision;}await api('/api/users/'+(editingUser?'edit':'add'),data);form.reset();$('userDialog').close();await refresh();}
 catch(error){message('userError',error.message);}finally{button.disabled=false;}
});

document.addEventListener('languagechange',()=>{
 selectPage(page);
 if(state)render();
 renderSubscriptionProfiles();
 $('dialogTitle').textContent=t(editing?'Редактирование профиля':'Новый профиль');
 $('ipListTitle').textContent=t(!canManage()?'Просмотр списка':editingList?'Редактирование списка':'Новый список');
 $('userDialogTitle').textContent=t(editingUser?'Редактирование пользователя':'Новый пользователь');
 $('userPasswordLabel').textContent=t(editingUser?'Новый пароль (необязательно)':'Пароль');
 for(const [id,value]of messages)$(id).textContent=typeof value==='function'?value():t(value);
});
async function loadVersion(){
 try{
  const response=await fetch('/api/version',{signal:AbortSignal.timeout(10000)});
  if(!response.ok)return;
  const info=await response.json();
  if(!/^\d+\.\d+(?:\.\d+)?-[0-9a-f]{7}$/.test(info.version)||info.url!=='https://github.com/QueenDekim/XRay-gateway/tree/'+info.version)return;
  document.querySelectorAll('[data-version-link]').forEach(link=>{link.textContent=info.version;link.setAttribute('href',info.url);link.hidden=false;});
 }catch{}
}
loadVersion();refresh();setInterval(()=>{if(state && !document.hidden)refresh();},5000);
