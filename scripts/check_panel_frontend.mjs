// Code-level rendering checks without launching or controlling a browser.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(root, 'gateway/web/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'gateway/web/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'gateway/web/style.css'), 'utf8');
const paletteRules=[...css.matchAll(/^(:root(?:\[data-(?:design|theme)="[a-z]+"\])*) \{([^}]+)\}/gm)];
function luminance(hex){const c=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;}
function contrast(a,b){const [lo,hi]=[luminance(a),luminance(b)].sort((a,b)=>a-b);return(hi+.05)/(lo+.05);}
for(const design of ['titan','paper','console','contour'])for(const theme of ['light','dark']){
 const colors={};
 for(const [,selector,body]of paletteRules){
  const d=selector.match(/data-design="([^"]+)"/),t=selector.match(/data-theme="([^"]+)"/);
  if(d&&d[1]!==design||t&&t[1]!==theme)continue;
  for(const [,key,value]of body.matchAll(/--([\w-]+):\s*(#[\da-f]{6})\s*;/g))colors[key]=value;
 }
 for(const surface of ['paper','surface','raised'])for(const text of ['ink','secondary'])assert.ok(contrast(colors[text],colors[surface])>=4.5,`${design}/${theme}: ${text} on ${surface}`);
 assert.ok(contrast(colors['side-muted'],colors.sidebar)>=4.5,`${design}/${theme}: sidebar text`);
 assert.ok(contrast(colors.accent,colors.paper)>=3,`${design}/${theme}: graph contrast`);
}
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
assert.equal(new Set(ids).size, ids.length);
const nodes = Object.fromEntries(ids.map(id => [id, {
  textContent: '', innerHTML: '', value: '', hidden: false, attributes: {}, dataset: {}, listeners: {},
  classList: { values: new Set(), toggle(name, enabled) { enabled ? this.values.add(name) : this.values.delete(name); } }, setAttribute(name, value) { this.attributes[name] = value; },
  addEventListener(name, fn) { this.listeners[name] = fn; },
  focus() { this.focused = true; },
  reset() { for(const v of Object.values(this.elements))if(v && typeof v==='object')v.value=''; },
  showModal() { this.open=true; }, close() { this.open=false; },
  elements: { namedItem(name) { return this[name] ||= { value:'', checked:false }; } },
}]));
const navButtons = [...html.match(/<nav>[\s\S]*?<\/nav>/)[0].matchAll(/data-page="([^"]+)"/g)].map(m => ({
  dataset: { page: m[1] }, classList: { values: new Set(), toggle(name, enabled) { enabled ? this.values.add(name) : this.values.delete(name); } },
}));
nodes.settingsToggle.dataset.page = 'settings';
const settingsNames=['appearance','routing','probes','users','security'];
for(const name of settingsNames)nodes['settingsTab-'+name].dataset.settingsTab=name;
const appearanceInputs=[...html.matchAll(/<input type="radio" name="(design|colorScheme)" value="([^"]+)"[^>]*>/g)].map(m=>({name:m[1],value:m[2],checked:false}));
const documentEvents = {};
const windowEvents = {}, storage = new Map();
const context = vm.createContext({
  document: { hidden: false, documentElement:{dataset:{}}, getElementById(id) { assert.ok(nodes[id], `Unknown DOM id: ${id}`); return nodes[id]; },
    querySelectorAll(selector) {
      if(selector === 'nav [data-page], .account-actions [data-page]')return [...navButtons, nodes.settingsToggle];
      if(selector.startsWith('#appearanceForm input'))return appearanceInputs.filter(input=>selector.includes(`name="${input.name}"`));
      return [];
    },
    addEventListener(name, fn) { (documentEvents[name] ||= []).push(fn); },
    dispatchEvent(event) { for(const fn of documentEvents[event.type]||[])fn(event); } },
  window: { addEventListener(name, fn) { (windowEvents[name] ||= []).push(fn); } },
  localStorage: { getItem:key=>storage.get(key), setItem:(key,value)=>storage.set(key,value) },
  matchMedia:()=>({matches:false}), CustomEvent:class { constructor(type){this.type=type;} },
  setInterval() {}, fetch: async () => ({ ok: false, status: 401, json: async () => ({ error: 'login' }) }),
  AbortSignal, Date, console,
});
vm.runInContext(fs.readFileSync(path.join(root,'gateway/web/theme.js'),'utf8'),context);
vm.runInContext(source, context);
for(const fn of documentEvents.DOMContentLoaded||[])fn();
assert.equal(context.document.documentElement.dataset.design,'titan');
assert.equal(context.document.documentElement.dataset.theme,'light');
await new Promise(resolve => setImmediate(resolve));
const sample = {
  username: 'admin', ready: true, totals: { uplink: 1024, downlink: 2048 },
  user: { id:'user_admin', username:'admin', role:'admin', revision:1 },
  users: [{ id:'user_admin', username:'admin', role:'admin', revision:1 }, { id:'user_operator', username:'<ops>', role:'operator', revision:1 }],
  settings: { revision:1, gateway:'192.168.50.20', host:'192.168.50.10', source:'192.168.50.0/24', interface:'bridge',
    local_networks:'192.168.50.0/24', probe_url:'https://www.gstatic.com/generate_204', check_interval:10, fail_threshold:3, recover_threshold:2 },
  selected: 'primary', uptime: 120, since: Date.now() / 1000 - 30, stats_since: Date.now() / 1000,
  checks: { primary: { healthy: true } }, direct: {},
  profiles: [{ id: 'primary', name: '<test>', enabled: true, address: 'example.org', port: 443,
    transport: 'tcp', priority: 1, health: { ok: true, latency_ms: 200 }, stats: { checks: 4, successful_checks: 3 } }],
  history: [{ at: 1, uplink_bps: 12, downlink_bps: 20 }, { at: 2, uplink_bps: 8, downlink_bps: 40 }],
  ip_lists: [{ id: 'project', name: '<Project>', version: 1, addresses: ['1.1.1.1', '2606:4700:4700::1111'] }],
};
vm.runInContext(`state = ${JSON.stringify(sample)}; render(); selectPage('profiles');`, context);
// Optional real render fixture for static CSS cascade inspection, without a browser.
if(process.env.XRAY_UI_FIXTURE){
 let fixture=html;
 for(const id of ['overviewProfiles','ipListCards','profileRows','userRows']){
  const pattern=new RegExp(`(<(div|tbody)[^>]*id="${id}"[^>]*>)[\\s\\S]*?(<\\/\\2>)`);
  fixture=fixture.replace(pattern,(_,open,tag,close)=>open+nodes[id].innerHTML+close);
 }
 fs.writeFileSync(process.env.XRAY_UI_FIXTURE,fixture);
}
assert.equal(nodes.totalDown.textContent, '2.0 КиБ');
assert.ok(nodes.overviewProfiles.innerHTML.includes('&lt;test&gt;'));
assert.ok(nodes.profileRows.innerHTML.includes('Активен'));
assert.equal(nodes.profilesPage.hidden, false);
assert.equal(nodes.overviewPage.hidden, true);
assert.equal(nodes.settingsToggle.attributes['aria-pressed'], 'false');
assert.ok(navButtons.find(b => b.dataset.page === 'profiles').classList.values.has('active'));
assert.equal(nodes.coreStatus.textContent, 'Xray работает');
assert.ok(!html.match(/<nav>[\s\S]*?<\/nav>/)[0].includes('data-page="settings"'));
for (const id of ['settingsToggle', 'themeToggle', 'logout']) {
  const buttonHtml = html.match(new RegExp(`<button id="${id}"[\\s\\S]*?<\\/button>`))[0];
  assert.ok(buttonHtml.includes('aria-label="'));
  assert.ok(buttonHtml.includes('class="ui-icon'));
  assert.equal(buttonHtml.replace(/<[^>]*>/g, '').trim(), '', `${id} must be icon only`);
}
assert.ok(html.includes('<div class="core-status"><span id="coreStatus"'));
vm.runInContext('state.ready = false; render();', context);
assert.equal(nodes.coreStatus.textContent, 'Xray недоступен');
assert.ok(nodes.coreStatus.classList.values.has('bad'));
assert.ok(nodes.downLine.attributes.d.includes('C'));
assert.ok(nodes.downArea.attributes.d.endsWith('Z'));
const setAppearance=(name,value)=>nodes.appearanceForm.listeners.change({target:{name,value}});
const linePaths=new Set();
for(const design of ['titan','paper','console','contour']){
 for(const colorScheme of ['light','dark']){
  setAppearance('design',design);setAppearance('colorScheme',colorScheme);
  assert.equal(context.document.documentElement.dataset.design,design);
  assert.equal(context.document.documentElement.dataset.theme,colorScheme);
  assert.equal(storage.get('xray-design'),design);
  assert.equal(storage.get('xray-theme'),colorScheme);
  assert.equal(appearanceInputs.find(input=>input.name==='design'&&input.checked).value,design);
  assert.equal(appearanceInputs.find(input=>input.name==='colorScheme'&&input.checked).value,colorScheme);
  assert.equal(nodes.trafficChart.dataset.renderer,design);
  if(design==='titan'){assert.ok(nodes.downLine.attributes.d.includes('C'));assert.ok(nodes.downArea.attributes.d);}
  if(design==='paper'){assert.ok(nodes.downLine.attributes.d.includes('L'));assert.equal((nodes.trafficMarkers.innerHTML.match(/<circle /g)||[]).length,4);assert.equal(nodes.downArea.attributes.d,'');}
  if(design==='console'){assert.ok(nodes.downLine.attributes.d.includes('H'));assert.ok(nodes.downLine.attributes.d.includes('V'));assert.equal(nodes.trafficMarkers.innerHTML,'');}
  if(design==='contour'){assert.equal(nodes.downLine.attributes.d,'');assert.equal((nodes.trafficBars.innerHTML.match(/<rect /g)||[]).length,4);}
  assert.equal(nodes.chartPeak.textContent,'Шкала до 40 Б/с');
  assert.ok(!['downLine','upLine','downArea'].some(id=>/NaN|Infinity/.test(nodes[id].attributes.d)));
 }
 linePaths.add(nodes.downLine.attributes.d);
}
assert.equal(linePaths.size,4);
setAppearance('design','titan');
vm.runInContext('state.history = []; state.profiles = []; render();', context);
assert.equal(nodes.downArea.attributes.d, '');
assert.equal(nodes.downLine.attributes.d, '');
assert.equal(nodes.trafficMarkers.innerHTML,'');
assert.equal(nodes.trafficBars.innerHTML,'');
assert.ok(nodes.overviewProfiles.innerHTML.includes('Профилей нет'));
assert.ok(nodes.ipListCards.innerHTML.includes('&lt;Project&gt;'));
assert.ok(nodes.ipListCards.innerHTML.includes('2606:4700:4700::1111'));
assert.equal(nodes.routerList.value, 'project');
assert.equal(nodes.manualDestinations.hidden, true);
assert.ok(!html.includes('footnote') && !html.includes('placeholder='));
assert.ok(html.includes('rel="icon" type="image/png" href="/favicon.png"'));
assert.equal((html.match(/class="brand-icon"/g)||[]).length,2);
assert.ok(!html.includes('minlength="12"'));
assert.equal((html.match(/minlength="8"/g)||[]).length,3);
const routerFormHtml = html.match(/<form id="routerForm"[\s\S]*?<\/form>/)[0];
assert.ok(!routerFormHtml.includes('name="gateway"') && !routerFormHtml.includes('name="host"'));
assert.equal(nodes.routerForm.elements.source.value, '192.168.50.0/24');
assert.equal(nodes.routingSettingsForm.elements.gateway.value, '192.168.50.20');
assert.ok(nodes.userRows.innerHTML.includes('&lt;ops&gt;'));
nodes.routingSettingsForm.elements.gateway.value='192.168.50.99';
nodes.routingSettingsForm.listeners.input();
vm.runInContext("state.settings.revision=2; renderSettings();", context);
// A click on the nested SVG must reach the existing page navigation handler.
for (const listener of documentEvents.click) await listener({ target: { closest: () => nodes.settingsToggle } });
assert.equal(nodes.settingsPage.hidden, false);
assert.equal(nodes.settingsToggle.attributes['aria-pressed'], 'true');
assert.ok(nodes.settingsToggle.classList.values.has('active'));
assert.ok(navButtons.every(b => !b.classList.values.has('active')));
assert.equal(nodes.pageName.textContent, 'Настройки');
assert.equal(nodes['settingsPanel-appearance'].hidden,false);
for(const name of settingsNames){
 nodes.settingsTabs.listeners.click({target:{closest:()=>nodes['settingsTab-'+name]}});
 assert.equal(nodes['settingsPanel-'+name].hidden,false);
 assert.equal(nodes['settingsTab-'+name].attributes['aria-selected'],'true');
 assert.equal(nodes['settingsTab-'+name].tabIndex,0);
 assert.equal(settingsNames.filter(key=>!nodes['settingsPanel-'+key].hidden).length,1);
}
let prevented=false;
nodes.settingsTabs.listeners.keydown({key:'Home',target:{closest:()=>nodes['settingsTab-security']},preventDefault(){prevented=true;}});
assert.ok(prevented);assert.equal(nodes['settingsPanel-appearance'].hidden,false);
assert.ok(nodes['settingsTab-appearance'].focused);
vm.runInContext("selectPage('overview');", context);
assert.equal(nodes.settingsToggle.attributes['aria-pressed'], 'false');
assert.ok(!nodes.settingsToggle.classList.values.has('active'));
assert.equal(nodes.routingSettingsForm.elements.gateway.value, '192.168.50.99');
assert.equal(nodes.routingSettingsForm.dataset.revision, '1');
context.FormData = class { constructor(form) { this.form=form; } *[Symbol.iterator]() { yield* Object.entries(this.form?.testData || { destinations:'1.1.1.1\n2606:4700:4700::1111' }); } };
context.fetch = async (url, options) => { assert.equal(url,'/api/settings');assert.equal(JSON.parse(options.body).revision,1);return {ok:false,status:400,json:async()=>({error:'Настройки изменились'})}; };
await nodes.routingSettingsForm.listeners.submit({preventDefault(){},submitter:{disabled:false},target:nodes.routingSettingsForm});
assert.equal(nodes.routingSettingsStatus.textContent,'Настройки изменились');
vm.runInContext("state.user.role='operator'; state.users=[]; renderSettings();", context);
assert.equal(nodes.routingSettingsForm.hidden,true);
assert.equal(nodes.probeSettingsForm.hidden,true);
assert.equal(nodes.usersSettings.hidden,true);
assert.equal(nodes.userRows.innerHTML,'');
assert.equal(nodes['settingsTab-routing'].hidden,true);
assert.equal(nodes['settingsTab-probes'].hidden,true);
assert.equal(nodes['settingsTab-users'].hidden,true);
vm.runInContext("selectSettingsTab('routing');",context);
assert.equal(nodes['settingsPanel-appearance'].hidden,false);
nodes.settingsTabs.listeners.keydown({key:'ArrowRight',target:{closest:()=>nodes['settingsTab-appearance']},preventDefault(){}});
assert.equal(nodes['settingsPanel-security'].hidden,false);
vm.runInContext("state.user.role='admin'; state.history=[{at:1,uplink_bps:0,downlink_bps:0}]; renderTraffic();",context);
assert.equal((nodes.trafficMarkers.innerHTML.match(/<circle /g)||[]).length,2);
assert.equal(nodes.downArea.attributes.d,'');
// Curves and their control points stay inside the plot, including sharp spikes and flat intervals.
vm.runInContext("state.history=Array.from({length:90},(_,i)=>({at:i,uplink_bps:i%3?0:500,downlink_bps:i%2?100000:0}));renderTraffic();",context);
const coords=nodes.downLine.attributes.d.match(/-?\d+(?:\.\d+)?/g).map(Number);
for(let i=0;i<coords.length;i+=2){assert.ok(coords[i]>=0&&coords[i]<=1000);assert.ok(coords[i+1]>=10&&coords[i+1]<=278);}
assert.equal(vm.runInContext("trafficSamples([{at:1,uplink_bps:Infinity,downlink_bps:1}]).length",context),0);
const ipv6Warning = 'IPv6-адреса выгружены в address-list. Маршрутизация IPv6 через VPN не настроена.';
context.fetch = async () => ({ ok:true, json:async () => ({ script:'mixed script', warnings:[ipv6Warning] }) });
await nodes.routerForm.listeners.submit({ preventDefault() {}, submitter:{ disabled:false }, target:{} });
assert.ok(nodes.copyStatus.textContent.includes(ipv6Warning));
context.window.isSecureContext=true;
context.navigator = { clipboard:{ async writeText(value) { assert.equal(value, 'mixed script'); } } };
await nodes.copyRouter.onclick();
assert.ok(nodes.copyStatus.textContent.includes(ipv6Warning));
context.fetch = async (url, options) => {
  assert.equal(url, '/api/logout');assert.equal(options.method, 'POST');
  return { ok: true, json: async () => ({ ok: true }) };
};
await nodes.logout.onclick();
assert.equal(nodes.loginView.hidden, false);
assert.equal(nodes.appView.hidden, true);
const themeButton=nodes.themeToggle;
themeButton.innerHTML='<svg>moon</svg><svg>sun</svg>';
setAppearance('colorScheme','light');themeButton.listeners.click();
assert.equal(context.document.documentElement.dataset.theme,'dark');
assert.equal(themeButton.attributes['aria-label'],'Включить светлую тему');
assert.equal(themeButton.innerHTML,'<svg>moon</svg><svg>sun</svg>');
themeButton.listeners.click();assert.equal(context.document.documentElement.dataset.theme,'light');
assert.equal(themeButton.attributes['aria-label'],'Включить тёмную тему');
for(const fn of windowEvents.storage)fn({key:'xray-design',newValue:'paper'});
assert.equal(context.document.documentElement.dataset.design,'paper');
for(const fn of windowEvents.storage)fn({key:'xray-design',newValue:'unknown'});
assert.equal(context.document.documentElement.dataset.design,'titan');
// Reload restores both preferences before CSS; private/blocked storage still has safe defaults.
function reloadAppearance(storageApi, systemDark){
 const doc={documentElement:{dataset:{}},getElementById(){return null;},querySelectorAll(){return [];},addEventListener(){}};
 vm.runInNewContext(fs.readFileSync(path.join(root,'gateway/web/theme.js'),'utf8'),{
  document:doc,localStorage:storageApi,matchMedia:()=>({matches:systemDark}),window:{addEventListener(){}},
 });return doc.documentElement.dataset;
}
storage.set('xray-design','console');storage.set('xray-theme','dark');
assert.deepEqual({...reloadAppearance({getItem:key=>storage.get(key)},false)},{design:'console',theme:'dark'});
assert.deepEqual({...reloadAppearance({getItem(){throw new Error('blocked');}},true)},{design:'titan',theme:'dark'});
console.log('FRONTEND / EIGHT APPEARANCES / FOUR CHART RENDERERS / SETTINGS TABS / ROLES / STORAGE / CRUD / ESCAPING PASS');
