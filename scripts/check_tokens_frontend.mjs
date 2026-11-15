// Account token controls, exercised without a browser or real credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const html=fs.readFileSync(path.join(root,'gateway/web/pages/account.html'),'utf8');
const nodes={};
for(const [,id] of html.matchAll(/\bid="([^"]+)"/g))nodes[id]={value:'',disabled:false,hidden:false,open:false,dataset:{},listeners:{},addEventListener(k,f){this.listeners[k]=f;},focus(){this.focused=true;},select(){this.selected=true;},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},reset(){nodes.tokenName.value='';nodes.tokenDays.value='90';nodes.tokenNoExpiry.checked=false;}};
const calls=[],events={},messages={};let copied='',accept=true,fail=false,role='operator';
let records=[];
const user={id:'user',role,two_factor_enabled:false};
const context=vm.createContext({$:id=>nodes[id],state:{user},window:{Management:{render(){}},addEventListener(k,f){events[k]=f;}},document:{addEventListener(k,f){events[k]=f;}},
 t:(value,...args)=>args.reduce((text,arg,i)=>text.replace('{'+i+'}',arg),value),esc:value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;'),locale:()=> 'en-US',message(id,text){messages[id]=text;},
 confirmAction:async(text)=>{calls.push({confirm:typeof text==='function'?text():text});return accept;},navigator:{clipboard:{writeText:async value=>{copied=value;}}},Date,
 api:async(path,data)=>{calls.push({path,data});if(path==='/api/account/tokens')return{tokens:records};
  if(path.endsWith('/reissue')){if(fail)throw new Error('Invalid code');records=[{...records[0],id:'replacement-id',prefix:'xg_new'}];return{token:'replacement-secret',user};}
  if(path.endsWith('/create')){if(fail)throw new Error('Invalid code');records=[{id:'test-id',name:data.name,prefix:'xg_test',expires_at:data.no_expiry?null:2000000000,active:true}];return{token:'test-secret',user};}
  if(path.endsWith('/revoke')){if(fail)throw new Error('Invalid code');records=[];return{ok:true,user};}throw new Error(path);}});
vm.runInContext(fs.readFileSync(path.join(root,'gateway/web/tokens.js'),'utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));await tick();
const submit=()=>nodes.tokenCreateForm.listeners.submit({preventDefault(){}});
nodes.tokenName.value='Automation';nodes.tokenDays.value='30';submit();await tick();
assert.deepEqual(JSON.parse(JSON.stringify(calls.find(v=>v.path?.endsWith('/create')).data)),{name:'Automation',days:30});
assert.equal(nodes.tokenValue.value,'test-secret');assert.equal(nodes.tokenValueDialog.open,true);
await nodes.copyTokenValue.onclick();assert.equal(copied,'test-secret');
nodes.closeTokenValue.onclick();assert.equal(nodes.tokenValue.value,'');
nodes.tokenName.value='Permanent';nodes.tokenNoExpiry.checked=true;nodes.tokenNoExpiry.listeners.change();
assert.equal(nodes.tokenDays.disabled,true);assert.equal(nodes.tokenDays.required,false);
submit();await tick();
assert.deepEqual(JSON.parse(JSON.stringify(calls.filter(v=>v.path?.endsWith('/create')).at(-1).data)),{name:'Permanent',no_expiry:true});
assert.ok(nodes.tokenList.innerHTML.includes('Без окончания'));assert.ok(!nodes.tokenList.innerHTML.includes('<time'));
assert.equal(nodes.tokenNoExpiry.checked,false);assert.equal(nodes.tokenDays.disabled,false);assert.equal(nodes.tokenDays.required,true);
nodes.closeTokenValue.onclick();
nodes.tokenNoExpiry.checked=true;nodes.tokenNoExpiry.listeners.change();nodes.tokenNoExpiry.checked=false;nodes.tokenNoExpiry.listeners.change();
assert.equal(nodes.tokenDays.disabled,false);assert.equal(nodes.tokenDays.value,'90');
user.two_factor_enabled=true;nodes.tokenName.value='<Monitor>';nodes.tokenDays.value='90';
const before=calls.filter(v=>v.path?.endsWith('/create')).length;submit();await tick();
assert.equal(nodes.tokenFactorDialog.open,true);assert.equal(nodes.tokenFactorCode.focused,true);
assert.equal(calls.filter(v=>v.path?.endsWith('/create')).length,before);
nodes.cancelTokenFactor.onclick();assert.equal(nodes.tokenName.value,'<Monitor>');assert.equal(nodes.tokenFactorCode.value,'');
submit();nodes.tokenFactorCode.value='bad';fail=true;
await nodes.tokenFactorForm.listeners.submit({preventDefault(){}});await tick();
assert.equal(nodes.tokenFactorDialog.open,true);assert.equal(nodes.tokenName.value,'<Monitor>');assert.equal(messages.tokenFactorError,'Invalid code');
fail=false;nodes.tokenFactorCode.value='654321';await nodes.tokenFactorForm.listeners.submit({preventDefault(){}});await tick();
assert.equal(calls.filter(v=>v.path?.endsWith('/create')).at(-1).data.code,'654321');
assert.equal(nodes.tokenFactorDialog.open,false);assert.equal(nodes.tokenFactorCode.value,'');
assert.ok(nodes.tokenList.innerHTML.includes('&lt;Monitor&gt;'));
assert.ok(!nodes.tokenList.innerHTML.includes('test-secret'));
events.pagehide();assert.equal(nodes.tokenValue.value,'');
let button={dataset:{reissueToken:'test-id'},disabled:false};
await nodes.tokenList.listeners.click({target:{closest:()=>button}});
assert.equal(nodes.tokenFactorDialog.open,true);assert.equal(calls.filter(v=>v.path?.endsWith('/reissue')).length,0);
nodes.cancelTokenFactor.onclick();assert.equal(calls.filter(v=>v.path?.endsWith('/reissue')).length,0);
await nodes.tokenList.listeners.click({target:{closest:()=>button}});nodes.tokenFactorCode.value='654322';
await nodes.tokenFactorForm.listeners.submit({preventDefault(){}});await tick();
assert.equal(calls.filter(v=>v.path?.endsWith('/reissue')).at(-1).data.code,'654322');
assert.equal(nodes.tokenValue.value,'replacement-secret');nodes.closeTokenValue.onclick();
button={dataset:{revokeToken:'replacement-id'},disabled:false};
await nodes.tokenList.listeners.click({target:{closest:()=>button}});
assert.equal(nodes.tokenFactorDialog.open,true);assert.equal(calls.filter(v=>v.path?.endsWith('/revoke')).length,0);
fail=true;nodes.tokenFactorCode.value='invalid';await nodes.tokenFactorForm.listeners.submit({preventDefault(){}});await tick();
assert.equal(nodes.tokenFactorDialog.open,true);assert.ok(nodes.tokenList.innerHTML.includes('replacement-id'));
fail=false;nodes.tokenFactorCode.value='654323';await nodes.tokenFactorForm.listeners.submit({preventDefault(){}});await tick();
assert.equal(calls.filter(v=>v.path?.endsWith('/revoke')).at(-1).data.code,'654323');
assert.ok(nodes.tokenList.innerHTML.includes('API-токенов пока нет'));
// Accounts without MFA still confirm destructive operations in the shared dialog.
user.two_factor_enabled=false;nodes.tokenName.value='Again';submit();await tick();nodes.closeTokenValue.onclick();
button={dataset:{revokeToken:'test-id'},disabled:false};accept=false;
const count=calls.filter(v=>v.path?.endsWith('/revoke')).length;
await nodes.tokenList.listeners.click({target:{closest:()=>button}});assert.equal(calls.filter(v=>v.path?.endsWith('/revoke')).length,count);
accept=true;await nodes.tokenList.listeners.click({target:{closest:()=>button}});assert.equal(calls.filter(v=>v.path?.endsWith('/revoke')).length,count+1);
console.log('API TOKEN UI / MFA CREATE-REISSUE-REVOKE / RETAINED INPUT / ONE-TIME SECRET / COPY / NO EXPIRY / CONFIRMATIONS PASS');
