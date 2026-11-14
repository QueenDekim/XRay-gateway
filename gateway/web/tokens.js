'use strict';
(() => {
 if(!$('tokenCreateForm'))return;
 let tokens=[],pending=null,busy=false;
 function render(){
  $('tokenList').innerHTML=tokens.map(item=>`<div class="token-row"><div class="token-identity"><b>${esc(item.name)}</b><code>${esc(item.prefix)}</code></div><div class="token-expiry"><span>${esc(t(item.active?'Действует до':'Недействителен'))}</span><time datetime="${new Date(item.expires_at*1000).toISOString()}">${esc(new Date(item.expires_at*1000).toLocaleDateString(locale()))}</time></div><button class="text-button danger" type="button" data-revoke-token="${esc(item.id)}">${esc(t('Отозвать'))}</button></div>`).join('')||`<p class="muted">${t('API-токенов пока нет')}</p>`;
 }
 async function load(){try{tokens=(await api('/api/account/tokens')).tokens;render();}catch(error){message('tokenStatus',error.message);}}
 async function issue(data){
  if(busy)return;busy=true;$('createToken').disabled=true;$('confirmTokenFactor').disabled=true;
  message('tokenStatus','');message('tokenFactorError','');
  try{
   const result=await api('/api/account/tokens/create',data);
   state.user=result.user;window.Management?.render();pending=null;
   if($('tokenFactorDialog').open)$('tokenFactorDialog').close();
   $('tokenCreateForm').reset();$('tokenValue').value=result.token;message('tokenCopyStatus','');
   $('tokenValueDialog').showModal();$('copyTokenValue').focus();await load();
  }catch(error){message($('tokenFactorDialog').open?'tokenFactorError':'tokenStatus',error.message);}
  finally{busy=false;$('createToken').disabled=false;$('confirmTokenFactor').disabled=false;}
 }
 $('tokenCreateForm').addEventListener('submit',event=>{
  event.preventDefault();if(busy||pending)return;
  const data={name:$('tokenName').value.trim(),days:Number($('tokenDays').value)};
  if(state.user.two_factor_enabled){pending=data;message('tokenFactorError','');$('tokenFactorCode').value='';$('tokenFactorDialog').showModal();$('tokenFactorCode').focus();}
  else issue(data);
 });
 $('tokenFactorForm').addEventListener('submit',event=>{event.preventDefault();if(pending)issue({...pending,code:$('tokenFactorCode').value.trim()});});
 $('cancelTokenFactor').onclick=()=>$('tokenFactorDialog').close();
 $('tokenFactorDialog').addEventListener('close',()=>{pending=null;$('tokenFactorCode').value='';message('tokenFactorError','');});
 $('closeTokenValue').onclick=()=>$('tokenValueDialog').close();
 $('tokenValueDialog').addEventListener('close',()=>{$('tokenValue').value='';message('tokenCopyStatus','');});
 $('copyTokenValue').onclick=async()=>{try{await navigator.clipboard.writeText($('tokenValue').value);message('tokenCopyStatus','Скопировано');}catch{$('tokenValue').focus();$('tokenValue').select();message('tokenCopyStatus','Скопируйте выделенный токен');}};
 $('tokenList').addEventListener('click',async event=>{
  const button=event.target.closest('[data-revoke-token]');if(!button||busy)return;
  const item=tokens.find(value=>value.id===button.dataset.revokeToken);if(!item)return;
  if(!await confirmAction(()=>t('Отозвать API-токен «{0}»?',item.name),'Отозвать'))return;
  button.disabled=true;try{await api('/api/account/tokens/revoke',{id:item.id});await load();}catch(error){message('tokenStatus',error.message);}finally{button.disabled=false;}
 });
 window.addEventListener('pagehide',()=>{$('tokenValue').value='';$('tokenFactorCode').value='';pending=null;});
 document.addEventListener('languagechange',render);
 window.ApiTokens={load,render};load();
})();
