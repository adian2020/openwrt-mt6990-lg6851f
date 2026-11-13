// Real ported views and adapter, synthetic RPC only. No router or deliveries.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),assets=root+'/package/vendor/luci-app-5gmodem/htdocs/luci-static/resources';
const files={mu:fs.readFileSync(assets+'/modem5g/mu_v1.js','utf8'),adapter:fs.readFileSync(assets+'/modem5g/sms_mu_v1.js','utf8'),sms:fs.readFileSync(assets+'/view/modem5g/sms_v3.js','utf8'),forward:fs.readFileSync(assets+'/view/modem5g/forward_v2.js','utf8')};
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{for(const width of [320,390,1280])for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(`<html data-darkmode="${theme==='dark'}"><meta name="viewport" content="width=device-width,initial-scale=1"><body><main class="main-right" style="padding:12px;min-width:0"></main><aside id="modal"></aside></body></html>`);
  await page.addStyleTag({content:fs.readFileSync(root+'/package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css','utf8')+fs.readFileSync(assets+'/view/modem5g/sms_v1.css','utf8')});
  await page.evaluate(({mu,adapter,sms,forward})=>{
   window.E=(tag,attrs={},children=[])=>{const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(typeof v==='function')n.addEventListener(k,v);else if(v!=null)n.setAttribute(k,v);}const add=x=>{if(Array.isArray(x))x.forEach(add);else if(x!=null)n.append(x instanceof Node?x:document.createTextNode(String(x)));};add(children);return n;};
   window.L={resolveDefault:(p,d)=>Promise.resolve(p).catch(()=>d),resource:s=>'/assets/'+s,bind:(fn,ctx)=>fn.bind(ctx)};
   window.calls=[];window.polls=[];window.fail=false;window.deleted=false;window.sent=false;
   const poll={add:fn=>polls.push(fn),remove:fn=>{polls=polls.filter(f=>f!==fn);}};
   const ui={showModal:(title,nodes)=>document.querySelector('#modal').replaceChildren(E('h3',{},title),...nodes),hideModal:()=>document.querySelector('#modal').replaceChildren(),addNotification:(title,node)=>{document.body.append(node);return node;}};
   const config={enabled:false,webhook:false,smtp:false,sms:false,method:'webhook',webhook_kind:'webhook',body:'{"text":"{text}"}',url:'https://example.invalid/hook',port:465,interval:60,keyword:'keep',blacklist_keywords:'',template_language:'zh'};
   const rpc={declare:spec=>(...args)=>{
    calls.push({method:spec.method,args});
    switch(spec.method){
     case 'sms_pool_list':return Promise.resolve({ok:true,msgs:deleted?[]:[{id:'m-one',peer:'10086',dir:'mt',status:'unread',time:'2026-11-13 10:20:30',preview:'欢迎使用短信'}],pages:1,total:deleted?0:1,unread:1});
     case 'sms_pool_show':return Promise.resolve({ok:true,text:'From:10086\n---\n欢迎使用短信\n<危险内容>'});
     case 'sms_pool_sync':return Promise.resolve(fail?{ok:false,error:'fixture sync failure'}:{ok:true});
     case 'sms_pool_delete':if(!fail)deleted=true;return Promise.resolve(fail?{ok:false,error:'fixture delete failure'}:{ok:true});
     case 'sms_pool_send':sent=true;return Promise.resolve({ok:true,job:'job'});
     case 'sms_pool_job':return Promise.resolve({running:false,done:sent,ok:sent});
     case 'get_forward_config':return Promise.resolve({values:config,status:{enabled:config.enabled,state:'disabled',history:[]}});
     case 'get_forward_status':return Promise.resolve({enabled:config.enabled,state:'disabled',history:[{time:1790000000,kind:'sms',method:'webhook',result:'sent'}]});
     case 'set_forward_config':window.saved=args[0];Object.assign(config,saved);return Promise.resolve({code:0});
     case 'clear_forward_history':case 'test_forward':case 'retry_forward':return Promise.resolve({code:0});
     default:return Promise.reject(Error('unexpected RPC '+spec.method));
    }
   }};
   const U=new Function('baseclass','rpc','ui',mu)({extend:x=>x},rpc,ui);
   window.M=new Function('baseclass','rpc','ui','U',adapter)({extend:x=>x},rpc,ui,U);
   window.smsVM=new Function('view','poll','M',sms)({extend:x=>x},poll,M);
   window.forwardVM=new Function('view','poll','M',forward)({extend:x=>x},poll,M);
   document.querySelector('main').append(smsVM.render());
  },files);
  await page.locator('.mud-conv').click();await page.waitForFunction(()=>document.querySelector('.mud-bub .bd')?.textContent.includes('<危险内容>'));
  assert.equal(await page.locator('.mud-bub script').count(),0);
  assert.equal(await page.evaluate(()=>calls.some(c=>['list_sms','get_smsc'].includes(c.method))),false,'UI reload must use cached archive only');
  await page.evaluate(()=>fail=true);await page.locator('#mud-sms-sync').click();await page.getByText('fixture sync failure',{exact:true}).waitFor();
  await page.locator('.mud-del').click();await page.locator('#modal').getByRole('button',{name:'仅删本地',exact:true}).click();await page.waitForFunction(()=>document.body.textContent.includes('fixture delete failure'));
  assert.equal(await page.locator('.mud-bub').count(),1);
  await page.locator('#mud-sms-num').fill('10086');await page.locator('#mud-sms-text').fill('中文短信😀');await page.locator('#mud-sms-send').click();
  assert.equal(await page.evaluate(()=>calls.some(c=>c.method==='sms_pool_send')),false,'No send before explicit confirmation');
  await page.locator('#modal').getByRole('button',{name:'取消',exact:true}).click();
  assert.equal(await page.evaluate(()=>calls.some(c=>c.method==='sms_pool_send')),false);
  await page.screenshot({path:`/tmp/lg6851f-mu-sms-${theme}-${width}.png`,fullPage:true});
  await page.evaluate(async()=>{smsVM.unload();document.querySelector('main').replaceChildren(forwardVM.render(await forwardVM.load()));});
  assert.equal(await page.evaluate(()=>polls.length),1);
  assert.equal(await page.locator('#mud-fwd-mode').isVisible(),false);
  assert.equal(await page.locator('#mud-fwd-power_forward_enabled').isDisabled(),true);
  await page.locator('#mud-fwd-method').selectOption('webhook');
  await page.locator('#mud-fwd-preset').selectOption('telegram');await page.locator('#modal').getByRole('button',{name:'确定',exact:true}).click();
  assert.equal(await page.locator('#mud-fwd-webhook_expect').inputValue(),'ok=true');
  await page.locator('#mud-fwd-method').selectOption('dingtalk');await page.locator('#mud-fwd-dingtalk_webhook').fill('https://oapi.dingtalk.com/robot/send?access_token=fixture');
  await page.locator('#mud-fwd-channel_webhook').check();await page.locator('#mud-fwd-enabled').check();
  await page.locator('#mud-fwd-save').click();await page.locator('#modal').getByRole('button',{name:'保存',exact:true}).click();
  await page.waitForFunction(()=>window.saved?.webhook_kind==='dingtalk');
  await page.locator('#mud-fwd-method').selectOption('smtp');
  assert.equal(await page.evaluate(()=>forwardVM.payload().webhook_kind),'dingtalk','Editing SMTP must not switch the active DingTalk transport');
  assert.equal(await page.evaluate(()=>forwardVM.payload().keyword),'keep','Keep pre-existing positive keyword filter');
  await page.locator('#mud-fwd-method').selectOption('sms');assert.equal(await page.locator('#mud-fwd-sms_to_phone').isVisible(),true);
  await page.evaluate(()=>forwardVM.refreshStatus());
  assert((await page.locator('#mud-fwd-history').textContent()).includes('发送成功'));
  await page.screenshot({path:`/tmp/lg6851f-mu-forward-${theme}-${width}.png`,fullPage:true});
  const fit=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));assert(fit.s<=width+1,JSON.stringify(fit));
  await page.evaluate(()=>forwardVM.unload());assert.equal(await page.evaluate(()=>polls.length),0);
  assert.deepEqual(errors,[]);await page.close();console.log(`PASS MU300 SMS/forward ${theme} ${width}px: archive, escaping, failure feedback, confirms, preset, multichannel and cleanup`);
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
