// Real LuCI DOM attribute/handler functions with synthetic RPC; no router I/O.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const source=fs.readFileSync(root+'/package/vendor/luci-app-5gmodem/htdocs/luci-static/resources/view/system/lg6851f-slots.js','utf8');
const luci=fs.readFileSync(root+'/feeds/luci/modules/luci-base/htdocs/luci-static/resources/luci.js','utf8');
const uiSource=fs.readFileSync(root+'/feeds/luci/modules/luci-base/htdocs/luci-static/resources/ui.js','utf8');
const attr=luci.match(/\t\tattr\(node, key, val\) \{[\s\S]*?\n\t\t\},/)[0].trim().replace(/,$/,'');
const handler=uiSource.match(/\tcreateHandlerFn\(ctx, fn, \.\.\.args\) \{[\s\S]*?\n\t\},/)[0].trim().replace(/,$/,'');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM||undefined,headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<main></main><aside id="modal"></aside>');
  await page.evaluate(({source,attr,handler})=>{
   window.L={bind:(fn,ctx,...args)=>fn.bind(ctx,...args),hasViewPermission:()=>window.canWrite};
   const dom=new Function('return ({elem:node=>node instanceof Element,'+attr+'})')();
   window.E=(tag,attrs={},children=[])=>{const el=document.createElement(tag);dom.attr(el,attrs);const add=v=>{if(Array.isArray(v))v.forEach(add);else if(v!=null)el.append(v instanceof Node?v:document.createTextNode(String(v)));};add(children);return el;};
   // This reproduces the reported bug using the actual framework function.
   if(!E('button',{disabled:false}).disabled)throw Error('Expected real LuCI disabled=false behavior');
   window.canWrite=true;window.calls=[];window.notices=[];window.readError=false;window.selectError=false;
   window.state={code:0,current:'b',next:'b',control:'1'.repeat(64),slots:{a:{priority:14,retry:0,success:1,upgrade:1,image_headers_ok:true},b:{priority:15,retry:0,success:1,upgrade:1,image_headers_ok:true}}};
   const rpc={declare:spec=>async(...args)=>{
    calls.push({method:spec.method,args});
    if(spec.method==='get_boot_slots'){if(readError)throw Error('synthetic read failure');return structuredClone(state);}
    if(spec.method==='select_boot_slot'){if(selectError)throw Error('synthetic request failure');state.next=args[0];state.control='2'.repeat(64);return {code:0,control:state.control,backup:'/fixture/backup'};}
    throw Error('No real reboot allowed');
   }};
   const ui=new Function('return ({'+handler+'})')();
   ui.addNotification=(title,node,type)=>notices.push({text:node.textContent,type});
   ui.showModal=(title,body)=>document.querySelector('#modal').replaceChildren(E('h2',{},title),...body);
   ui.hideModal=()=>document.querySelector('#modal').replaceChildren();
   window.vm=new Function('view','rpc','ui','E','L',source)({extend:x=>x},rpc,ui,E,L);
   window.mount=()=>document.querySelector('main').replaceChildren(vm.render(structuredClone(state)));mount();
  },{source,attr,handler});
  const button=text=>page.getByRole('button',{name:text,exact:true});
  assert.equal(await button('切换到 A 槽').isEnabled(),true);
  assert.equal(await button('切换到 A 槽').getAttribute('disabled'),null);
  await button('切换到 A 槽').click();assert(await page.getByRole('heading',{name:'确认选择 A 槽'}).isVisible());
  await button('仅设置').click();assert.equal(await page.evaluate(()=>calls.filter(c=>c.method==='select_boot_slot').length),0);
  await page.locator('#modal input[type=checkbox]').check();await page.locator('#modal input[type=text]').fill('A');
  await page.evaluate(()=>window.selectError=true);await button('仅设置').click();
  await page.waitForFunction(()=>notices.some(n=>n.text.includes('synthetic request failure')));assert(await button('仅设置').isEnabled());
  await page.evaluate(()=>window.selectError=false);await button('仅设置').click();
  await page.waitForFunction(()=>!document.querySelector('#modal').children.length);
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.method==='select_boot_slot').at(-1).args),['a','1'.repeat(64),true,false]);
  await button('刷新状态').click();await page.waitForFunction(()=>notices.some(n=>n.text.includes('槽位状态已刷新')));
  await page.evaluate(()=>window.readError=true);await button('刷新状态').click();
  await page.waitForFunction(()=>notices.some(n=>n.text.includes('synthetic read failure')));assert(await button('刷新状态').isEnabled());
  await page.evaluate(()=>{window.readError=false;state.current='a';mount();});assert(await button('切换到 B 槽').isEnabled());
  await page.evaluate(()=>{window.canWrite=false;mount();});assert(await button('切换到 B 槽').isDisabled());
  await page.evaluate(()=>{window.canWrite=true;state.slots.b.image_headers_ok=false;mount();});assert(await button('切换到 B 槽').isDisabled());
  assert.equal(await page.evaluate(()=>calls.some(c=>c.method==='reboot')),false);assert.deepEqual(errors,[]);
  console.log('PASS actual LuCI DOM/handler: enabled switching, confirmation, refresh, transport errors, readonly and invalid headers');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
