// Real LuCI DOM/modal helpers, synthetic RPC/clipboard only. No router access.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),assets=root+'/package/vendor/luci-app-5gmodem/htdocs/luci-static/resources';
const guide=fs.readFileSync(assets+'/modem5g/slot_guide_v1.js','utf8');
const view=fs.readFileSync(assets+'/view/system/lg6851f-slots.js','utf8');
const luci=fs.readFileSync(root+'/feeds/luci/modules/luci-base/htdocs/luci-static/resources/luci.js','utf8');
const uiSource=fs.readFileSync(root+'/feeds/luci/modules/luci-base/htdocs/luci-static/resources/ui.js','utf8');
function method(source,name,indent){const match=source.match(new RegExp('^'+indent+name+'\\([^)]*\\) \\{[\\s\\S]*?^'+indent+'\\},','m'));assert(match,name);return match[0].trim().replace(/,$/,'');}
const domMethods=['attr','append','content','create'].map(name=>method(luci,name,'\t\t')).join(',');
const uiMethods=['showModal','hideModal','addNotification','createHandlerFn'].map(name=>method(uiSource,name,'\t')).join(',');
const css=fs.readFileSync(root+'/package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css','utf8');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM||undefined,headless:true,args:['--no-sandbox']});
 try{
  for(const width of [390,1280])for(const dark of [false,true]){
   const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:`<html data-darkmode="${dark}"><meta name="viewport" content="width=device-width,initial-scale=1"><body><main id="maincontent" style="padding:12px"></main><div id="modal_overlay" tabindex="-1"><div class="modal"></div></div></body></html>`}));
   await page.goto('http://lg6851f-guide.test/');await page.addStyleTag({content:css});
   await page.evaluate(async({guide,view,domMethods,uiMethods})=>{
    const dom=new Function('return ({elem:n=>n instanceof Node,registry:{},'+domMethods+'})')();
    window.E=dom.create.bind(dom);window._=text=>text;window.L={bind:(fn,ctx,...args)=>fn.bind(ctx,...args),hasViewPermission:()=>true,env:{}};
    window.ui=new Function('dom','modalDiv','return ({'+uiMethods+'})')(dom,document.querySelector('#modal_overlay'));
    window.G=new Function('baseclass','ui',guide)({extend:x=>x},ui);localStorage.clear();
    window.calls=[];window.copied=[];
    const state={code:0,current:'b',next:'b',control:'1'.repeat(64),slots:{a:{priority:14,retry:0,success:1,upgrade:1,image_headers_ok:true},b:{priority:15,retry:0,success:1,upgrade:1,image_headers_ok:true}}};
    const rpc={declare:spec=>async()=>{calls.push(spec.method);if(spec.method!=='get_boot_slots')throw Error('Guide must never write or reboot');return structuredClone(state);}};
    window.vm=new Function('view','rpc','ui','G',view)({extend:x=>x},rpc,ui,G);
    window.mount=async()=>document.querySelector('main').replaceChildren(vm.render(await vm.load()));await mount();
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
    document.execCommand=command=>{if(command!=='copy'||!document.activeElement.closest('#modal_overlay'))throw Error('Copy must stay in the modal');copied.push(document.activeElement.value);return true;};
   },{guide,view,domMethods,uiMethods});
   const overlay=page.locator('#modal_overlay');
   await page.waitForFunction(()=>document.body.classList.contains('modal-overlay-active'));
   assert.equal(await overlay.locator('h4').textContent(),'注意！！！');
   assert.equal(await overlay.locator('h4').evaluate(n=>getComputedStyle(n).color),'rgb(229, 57, 53)');
   assert.equal(await overlay.locator('pre code').count(),2);
   await page.screenshot({path:`/tmp/lg6851f-slot-guide-${dark?'dark':'light'}-${width}.png`,fullPage:true});
   for(const current of ['a','b']){
    await overlay.locator(`[data-current="${current}"] button`).click();
    await page.waitForFunction(()=>copied.length>0);
    assert.equal(await page.evaluate(()=>copied.at(-1)),await page.evaluate(current=>G.commands(current),current));
   }
   assert.equal(await page.evaluate(()=>copied.length),2,'HTTP fallback must copy each full code block');
   await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push(text)}}));
   await overlay.locator('[data-current="a"] button').click();await page.waitForFunction(()=>copied.length===3);
   assert.equal(await page.evaluate(()=>copied.at(-1)),await page.evaluate(()=>G.commands('a')));
   await page.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('denied');}}});document.execCommand=()=>false;});
   await overlay.locator('[data-current="b"] button').click();
   await page.waitForFunction(()=>document.querySelector('[data-current="b"] .lg6851f-slot-guide-copy-status').textContent.includes('手动复制'));
   const modal=await overlay.locator('.modal').boundingBox();assert(modal.x>=-1&&modal.x+modal.width<=width+1,JSON.stringify(modal));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No horizontal page overflow');
   await overlay.locator('.lg6851f-slot-guide-read input').check();await overlay.getByRole('button',{name:'我已了解，关闭'}).click();
   assert.equal(await page.evaluate(()=>localStorage.getItem(G.preferenceKey)),'1');
   await page.evaluate(()=>mount());await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.body.classList.contains('modal-overlay-active')),false);
   await page.getByRole('button',{name:'原厂固件切换说明',exact:true}).click();assert(await overlay.locator('.lg6851f-slot-guide-read input').isChecked());
   await overlay.locator('.lg6851f-slot-guide-read input').uncheck();await overlay.getByRole('button',{name:'我已了解，关闭'}).click();
   await page.evaluate(()=>mount());await page.waitForFunction(()=>document.body.classList.contains('modal-overlay-active'));
   await overlay.getByRole('button',{name:'我已了解，关闭'}).click();await page.getByRole('button',{name:'刷新状态',exact:true}).click();
   await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.body.classList.contains('modal-overlay-active')),false,'Refresh must not repeat the entry warning');
   assert.deepEqual(await page.evaluate(()=>calls.filter(name=>name!=='get_boot_slots')),[]);
   assert.deepEqual(errors,[]);await page.close();
   console.log(`PASS slot guide ${width}px ${dark?'dark':'light'}: entry modal, red title, HTTP/API copy, stored preference and manual reopening`);
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
