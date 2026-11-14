import assert from 'node:assert/strict';
import fs from 'node:fs';import path from 'node:path';import vm from 'node:vm';import {fileURLToPath}from'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),web=path.join(root,'gateway/web');
const html=fs.readFileSync(path.join(web,'pages/login.html'),'utf8');
for(const returnTo of ['/profiles','/settings#updates','//evil.test','https://evil.test']){
 const nodes=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],{value:'',textContent:'',listeners:{},elements:{username:{value:'admin'},password:{value:'private-test-password'}},addEventListener(k,f){this.listeners[k]=f;},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},focus(){this.focused=true;}}]));
 const events={},calls=[];let reply={requires_2fa:true,challenge:'challenge'},target=null;
 const context=vm.createContext({document:{getElementById:id=>nodes[id],querySelectorAll:()=>[],addEventListener(k,f){events[k]=f;}},window:{location:{search:'?next='+encodeURIComponent(returnTo),hash:'',replace(url){target=url;}},I18n:{t:(s)=>s,language:()=> 'ru'}},URLSearchParams,AbortSignal,FormData:class{constructor(form){this.form=form;}*[Symbol.iterator](){for(const [k,v]of Object.entries(this.form.elements))yield[k,v.value];}},fetch:async(url,options)=>{if(!options)return{json:async()=>({version:'1.9.0-abcdef0',url:'https://github.com/QueenDekim/XRay-gateway/tree/1.9.0-abcdef0'})};calls.push({url,body:JSON.parse(options.body)});return{ok:!(reply instanceof Error),json:async()=>reply instanceof Error?{error:reply.message}:reply};}});
 vm.runInContext(fs.readFileSync(path.join(web,'login.js'),'utf8'),context);
 const login=()=>nodes.loginForm.listeners.submit({preventDefault(){},target:nodes.loginForm,submitter:{disabled:false}});
 const factor=()=>nodes.loginFactorForm.listeners.submit({preventDefault(){},target:nodes.loginFactorForm,submitter:{disabled:false}});
 await login();assert.equal(nodes.loginFactorDialog.open,true);assert.equal(nodes.loginCode.focused,true);assert.equal(target,null);
 reply=new Error('Invalid code');await factor();assert.equal(nodes.loginFactorError.textContent,'Invalid code');assert.equal(nodes.loginForm.elements.password.value,'private-test-password');
 nodes.loginBack.onclick();assert.equal(nodes.loginFactorDialog.open,false);assert.equal(nodes.loginForm.elements.username.value,'admin');
 reply={requires_2fa:true,challenge:'next-challenge'};await login();reply={ok:true};nodes.loginCode.value='123456';await factor();
 assert.equal(calls.at(-1).url,'/api/login/2fa');assert.equal(calls.at(-1).body.challenge,'next-challenge');
 assert.equal(target,returnTo.startsWith('//')||returnTo.startsWith('http')?'/overview':returnTo);
 target=null;await login();assert.equal(target,returnTo.startsWith('//')||returnTo.startsWith('http')?'/overview':returnTo);
}
console.log('LOGIN DOCUMENT / SEPARATE MFA MODAL / RETAINED CREDENTIALS / SAFE RETURN URL PASS');
