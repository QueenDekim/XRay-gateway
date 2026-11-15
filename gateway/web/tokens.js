'use strict';
(() => {
 if(!$('tokenCreateForm'))return;
 let tokens=[],pending=null,busy=false;
 function expiryMode(){const never=$('tokenNoExpiry').checked;$('tokenDays').disabled=never;$('tokenDays').required=!never;}
 function expiry(item){
  const never=item.expires_at===null;
  const label=item.active?(never?'Без окончания':'Действует до'):'Недействителен';
  const detail=never?(item.active?'':`<span>${esc(t('Без окончания'))}</span>`):`<time datetime="${new Date(item.expires_at*1000).toISOString()}">${esc(new Date(item.expires_at*1000).toLocaleDateString(locale()))}</time>`;
  return `<span>${esc(t(label))}</span>${detail}`;
 }
 function render(){
  $('tokenList').innerHTML=tokens.map(item=>`<div class="token-row"><div class="token-identity"><b>${esc(item.name)}</b><code>${esc(item.prefix)}</code></div><div class="token-expiry">${expiry(item)}</div><div class="token-actions"><button class="text-button" type="button" data-reissue-token="${esc(item.id)}" ${item.expires_at!==null&&item.expires_at*1000<=Date.now()?'disabled':''}>${esc(t('Перевыпустить'))}</button><button class="text-button danger" type="button" data-revoke-token="${esc(item.id)}">${esc(t('Отозвать'))}</button></div></div>`).join('')||`<p class="muted">${t('API-токенов пока нет')}</p>`;
 }
 async function load(){try{tokens=(await api('/api/account/tokens')).tokens;render();}catch(error){message('tokenStatus',error.message);}}
 async function perform(action,data){
  if(busy)return;busy=true;$('createToken').disabled=true;$('confirmTokenFactor').disabled=true;
  message('tokenStatus','');message('tokenFactorError','');
  try{
   const result=await api('/api/account/tokens/'+action,data);
   state.user=result.user;window.Management?.render();pending=null;
   if($('tokenFactorDialog').open)$('tokenFactorDialog').close();
   if(action==='create'){$('tokenCreateForm').reset();expiryMode();}
   if(result.token){$('tokenValue').value=result.token;message('tokenCopyStatus','');$('tokenValueDialog').showModal();$('copyTokenValue').focus();}
   else message('tokenStatus','Токен отозван');
   await load();
  }catch(error){message($('tokenFactorDialog').open?'tokenFactorError':'tokenStatus',error.message);}
  finally{busy=false;$('createToken').disabled=false;$('confirmTokenFactor').disabled=false;}
 }
 async function start(action,data,item=null){
  if(busy||pending)return;
  const label=action==='revoke'?'Отозвать':action==='reissue'?'Перевыпустить':'Создать токен';
  if(state.user.two_factor_enabled){
   pending={action,data};message('tokenFactorError','');message('tokenFactorTitle',action==='revoke'?'Отзыв токена':action==='reissue'?'Перевыпуск токена':'Подтвердите выпуск токена');
   message('tokenFactorTarget',item?.name||data.name);message('confirmTokenFactor',label);
   $('tokenFactorCode').value='';$('tokenFactorDialog').showModal();$('tokenFactorCode').focus();
  }else{
   if(action!=='create'&&!await confirmAction(()=>t(action==='revoke'?'Отозвать API-токен «{0}»?':'Перевыпустить API-токен «{0}»? Старый токен перестанет работать.',item.name),label))return;
   await perform(action,data);
  }
 }
 $('tokenCreateForm').addEventListener('submit',event=>{
  event.preventDefault();
  const data={name:$('tokenName').value.trim(),...($('tokenNoExpiry').checked?{no_expiry:true}:{days:Number($('tokenDays').value)})};
  start('create',data);
 });
 $('tokenFactorForm').addEventListener('submit',event=>{event.preventDefault();if(pending)perform(pending.action,{...pending.data,code:$('tokenFactorCode').value.trim()});});
 $('cancelTokenFactor').onclick=()=>$('tokenFactorDialog').close();
 $('tokenFactorDialog').addEventListener('close',()=>{pending=null;$('tokenFactorCode').value='';message('tokenFactorError','');message('tokenFactorTarget','');});
 $('closeTokenValue').onclick=()=>$('tokenValueDialog').close();
 $('tokenValueDialog').addEventListener('close',()=>{$('tokenValue').value='';message('tokenCopyStatus','');});
 $('copyTokenValue').onclick=async()=>{try{await navigator.clipboard.writeText($('tokenValue').value);message('tokenCopyStatus','Скопировано');}catch{$('tokenValue').focus();$('tokenValue').select();message('tokenCopyStatus','Скопируйте выделенный токен');}};
 $('tokenList').addEventListener('click',async event=>{
  const button=event.target.closest('[data-revoke-token], [data-reissue-token]');if(!button||button.disabled||busy||pending)return;
  const action=button.dataset.reissueToken?'reissue':'revoke',id=button.dataset.reissueToken||button.dataset.revokeToken;
  const item=tokens.find(value=>value.id===id);if(item)await start(action,{id},item);
 });
 window.addEventListener('pagehide',()=>{$('tokenValue').value='';$('tokenFactorCode').value='';pending=null;});
 document.addEventListener('languagechange',render);
 $('tokenNoExpiry').addEventListener('change',expiryMode);expiryMode();
 window.ApiTokens={load,render};load();
})();
