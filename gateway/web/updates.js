'use strict';
(() => {
 let data=null,firstVersion=null,timer=null;
 const phases=new Set(['queued','pulling','backing_up','installing','verifying','rollback']);
 const names={queued:'В очереди',pulling:'Загрузка образов',backing_up:'Резервное копирование',installing:'Установка',verifying:'Проверка',rollback:'Откат',done:'Обновление установлено',error:'Ошибка обновления'};
 function render(value){
  if(!value)return;data=value;if(firstVersion&&firstVersion!==data.current){window.location.reload();return;}firstVersion??=data.current;
  const busy=phases.has(data.job?.status),available=data.available,admin=canManage();
  $('updateNotice').hidden=!available&&!busy;
  $('updateNoticeVersion').textContent=available?.tag||data.job?.tag||'';
  $('updateNoticeVersion').href=available?.url||'https://github.com/QueenDekim/XRay-gateway/tags';
  $('updateNoticeInstall').hidden=!admin;$('updateNoticeInstall').disabled=!available||busy||!data.configured;
  if($('updateCurrent')){
   $('updateCurrent').textContent=data.current;$('updateAvailable').textContent=available?.tag||'—';
   message('updatesStatus',data.error||(data.checking?'Проверка обновлений…':!data.configured?'Служба обновления не подключена.':available?'Доступна новая версия':'Установлена актуальная версия'));
   $('installUpdate').disabled=!admin||!available||busy||!data.configured;$('checkUpdates').disabled=data.checking||busy;
   const form=$('updateSettingsForm');if(form.dataset.dirty!=='1'&&data.settings){$('autoInstallUpdates').checked=data.settings.auto_install;$('updateCheckInterval').value=data.settings.check_interval_hours;}
   $('updateJobPanel').hidden=!data.job;
   if(data.job){message('updateJobStatus',names[data.job.status]||data.job.status);$('updateJobLog').textContent=(data.job.logs||[]).map(text=>t(text)).join('\n');}
  }
  if(busy&&!timer)timer=setTimeout(poll,1500);
 }
 async function poll(){timer=null;try{render(await api('/api/updates'));}catch{timer=setTimeout(poll,2000);}}
 async function install(){
  if(!canManage()||!data?.available||!data.configured||phases.has(data.job?.status))return;
  const tag=data.available.tag;if(!await confirmAction(()=>t('Установить версию {0}? Шлюз будет перезапущен.',tag),'Обновить'))return;
  try{await api('/api/updates/install',{tag});await poll();}catch(error){notice(error.message);}
 }
 $('updateNoticeInstall').onclick=install;
 if($('installUpdate'))$('installUpdate').onclick=install;
 if($('checkUpdates'))$('checkUpdates').onclick=async()=>{try{render(await api('/api/updates/check',{}));if(!timer)timer=setTimeout(poll,1000);}catch(error){message('updatesStatus',error.message);}};
 if($('updateSettingsForm')){
  $('updateSettingsForm').addEventListener('input',()=>{$('updateSettingsForm').dataset.dirty='1';});
  $('updateSettingsForm').addEventListener('submit',async event=>{event.preventDefault();if(!canManage())return;const button=event.submitter;button.disabled=true;try{const result=await api('/api/updates/settings',{auto_install:$('autoInstallUpdates').checked,check_interval_hours:Number($('updateCheckInterval').value)});delete event.target.dataset.dirty;render(result);message('updateSettingsStatus','Настройки сохранены');}catch(error){message('updateSettingsStatus',error.message);}finally{button.disabled=false;}});
 }
 document.addEventListener('languagechange',()=>{if(data)render(data);});window.Updates={render,install};if(state?.updates)render(state.updates);
})();
