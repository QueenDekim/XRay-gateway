import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const web=path.join(root,'gateway/web');
const layout=fs.readFileSync(path.join(web,'index.html'),'utf8');
const sample={user:{id:'admin',username:'admin',display_name:'Admin',role:'admin',revision:1,preferences:{}},username:'admin',users:[],settings:{revision:1,gateway:'192.168.50.20',host:'192.168.50.10',source:'192.168.50.0/24',interface:'bridge',local_networks:'192.168.50.0/24',probe_url:'https://www.gstatic.com/generate_204',check_interval:10,fail_threshold:3,recover_threshold:2},csrf:'test',profiles:[],ip_lists:[],totals:{},direct:{},history:[],checks:{},ready:true,uptime:10,since:1,selected:'direct',updates:{current:'1.9.0-abcdef0',configured:true,settings:{auto_install:false,check_interval_hours:6},available:null,job:null}};
for(const name of ['overview','profiles','iplists','routeros','settings','account','wiki']){
 const state=structuredClone(sample);
 const html=layout.replace('{{PAGE_CONTENT}}',fs.readFileSync(path.join(web,'pages/'+name+'.html'),'utf8')).replace('{{PAGE_NAME}}',name).replace('{{PAGE_STATE}}',JSON.stringify(state));
 const nodes={};
 function node(attrs={}){return {textContent:'',innerHTML:'',value:'',checked:false,hidden:false,attributes:{...attrs},dataset:Object.fromEntries(Object.entries(attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),v])),listeners:{},classList:{toggle(){}},elements:{namedItem(k){return this[k]??={value:'',checked:false};}},setAttribute(k,v){this.attributes[k]=v;},getAttribute(k){return this.attributes[k]??null;},removeAttribute(k){delete this.attributes[k];},addEventListener(k,v){this.listeners[k]=v;},reset(){},focus(){},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();}};}
 function attrs(tag){return Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));}
 for(const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g))nodes[match[1]]=node(attrs(match[0]));
 nodes.pageState.textContent=JSON.stringify(state);
 for(const form of html.matchAll(/<form\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/form>/g))for(const input of form[2].matchAll(/<(?:input|select|textarea)\b[^>]*name="([^"]+)"/g))nodes[form[1]].elements.namedItem(input[1]);
 const links=[...html.matchAll(/<a[^>]*data-page="([^"]+)"[^>]*>/g)].map(m=>nodes[attrs(m[0]).id]||node(attrs(m[0])));
 const events={},windowEvents={},location={pathname:name==='wiki'?'/wiki/profiles':'/'+name,hash:name==='settings'?'#users':name==='account'?'#security':'',assign(url){this.redirect=url;},replace(url){this.redirect=url;},reload(){this.reloaded=true;}};
 const document={documentElement:{dataset:{page:name}},getElementById:id=>nodes[id]||null,addEventListener(k,v){(events[k]??=[]).push(v);},dispatchEvent(e){for(const f of events[e.type]||[])f(e);},querySelectorAll(selector){if(selector==='nav [data-page], .account-actions [data-page]')return links;if(selector==='[data-version-link]')return[nodes.appVersion];if(selector==='[data-language-select]')return nodes.languageSelect?[nodes.languageSelect]:[];return[];}};
 let calls=[];
 const sandbox={document,window:{location,history:{replaceState(a,b,url){location.hash=url.includes('#')?'#'+url.split('#')[1]:'';}},XrayMessages:JSON.parse(fs.readFileSync(path.join(web,'locales.json'),'utf8')),addEventListener(k,v){(windowEvents[k]??=[]).push(v);}},localStorage:{getItem(){return'ru';},setItem(){}},matchMedia:()=>({matches:false}),CustomEvent:class{constructor(type){this.type=type;}},setInterval(){},setTimeout(){},clearTimeout(){},FormData:class{},AbortSignal,console,Date,Uint8Array,atob,btoa,ResizeObserver:class{observe(){}},fetch:async(url)=>{calls.push(url);return{ok:true,json:async()=>url==='/api/state'?state:url==='/api/version'?{version:'1.9.0-abcdef0',url:'https://github.com/QueenDekim/XRay-gateway/tree/1.9.0-abcdef0'}:url==='/api/routeros/config'?{host:'router',port:22,username:'panel',auth:'key',configured:false}:url==='/api/routeros/jobs'?{jobs:[]}:url==='/api/routeros/terminal/open'?{id:'term'}:url.startsWith('/api/routeros/terminal/term')?{closed:true,cursor:0,data:''}:{} };}};
 sandbox.window.Terminal=class{cols=100;rows=30;buffer={active:{baseY:0}};loadAddon(){}open(){}onData(){}focus(){}write(data,done){done?.();}};sandbox.window.FitAddon={FitAddon:class{fit(){}}};
 const context=vm.createContext(sandbox);
 for(const script of ['i18n.js','theme.js','app.js','terminal-stream.js','management.js','updates.js'])vm.runInContext(fs.readFileSync(path.join(web,script),'utf8'),context,{filename:script});
 for(const f of events.DOMContentLoaded||[])f();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(location.redirect,undefined,name+': unexpected document redirect');
 assert.equal(nodes[name+'Page'].hidden,false,name+': page hidden');
 if(name==='settings'){assert.equal(nodes['settingsPanel-users'].hidden,false);assert.equal(location.hash,'#users');}
 if(name==='account'){assert.equal(nodes['accountPanel-security'].hidden,false);assert.equal(location.hash,'#security');}
 assert.ok(!html.includes('id="loginForm"'),name+': login leaked into authenticated page');
 for(const other of ['overview','profiles','iplists','routeros','settings','account','wiki'])if(other!==name)assert.ok(!html.includes('id="'+other+'Page"'),name+': unrelated page shipped');
 vm.runInContext('render();',context);assert.equal(location.redirect,undefined);
}
console.log('SEVEN INDEPENDENT DOCUMENTS / NO LOGIN FLASH / HASH TABS / PAGE-SCOPED SCRIPTS PASS');
