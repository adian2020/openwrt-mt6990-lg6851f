// Synthetic status and RPC only: no connection to a router or its fan.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),pkg=path.join(root,'package/vendor/luci-app-pwmfan');
const control=fs.readFileSync(pkg+'/htdocs/luci-static/resources/view/pwmfan/control_v5.js','utf8');
const panel=fs.readFileSync(pkg+'/htdocs/luci-static/resources/view/pwmfan/panel_v7.js','utf8');
const po=fs.readFileSync(pkg+'/po/zh_Hans/pwmfan.po','utf8'),translations={};
for(const m of po.matchAll(/^msgid (".*")\nmsgstr (".*")/gm))translations[JSON.parse(m[1])]=JSON.parse(m[2]);
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  for(const width of [390,1280])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.setContent('<html><meta name="viewport" content="width=device-width,initial-scale=1"><body><main class="main-right" style="padding:12px;min-width:0"></main></body></html>');
   await page.addStyleTag({content:fs.readFileSync(root+'/package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css','utf8')+`body{background:${theme==='dark'?'#161722':'#f6faff'}!important;color:${theme==='dark'?'#eee':'#252b35'}!important}*{box-sizing:border-box}`});
   await page.evaluate(({control,panel,translations})=>{
    window._=s=>translations[s]||s;
    String.prototype.format=function(...args){let i=0;return this.replace(/%%|%(?:\.(\d+))?([sdf])/g,(m,p,t)=>{if(m==='%%')return '%';let v=args[i++];return t==='s'?String(v):t==='f'?Number(v).toFixed(p||0):Math.trunc(v);});};
    window.E=(tag,attrs={},children=[])=>{const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(typeof v==='function')n.addEventListener(k,v);else if(v!=null)n.setAttribute(k,v);}const add=v=>{if(Array.isArray(v))v.forEach(add);else if(v!=null)n.append(v instanceof Node?v:document.createTextNode(String(v)));};add(children);return n;};
    window.L={bind:(fn,ctx,...args)=>fn.bind(ctx,...args),resolveDefault:(p,d)=>Promise.resolve(p).catch(()=>d)};
    window.calls=[];window.notifications=[];window.polls=[];
    window.fanStatus={available:true,pwm:3,manual_pwm:null,rpm:0,tach_available:false,temperatures:[{name:'cpu_little0',temp:51000}],controller:'fan_type=3wire\nactive=pwm5\nstatus=automatic\nspeed_point=low-10khz\ntemperature=53000\nthreshold=8\n',pwm_values:[{pwm:100},{pwm:3}]};
    const poll={add:fn=>polls.push(fn),remove:fn=>{polls= polls.filter(v=>v!==fn);}};
    const rpc={declare:spec=>(...args)=>{calls.push({method:spec.method,args});
     if(spec.method==='get_status')return Promise.resolve(structuredClone(fanStatus));
     const action=()=>{if(window.fail)return {success:false,error:'synthetic fan failure'};fanStatus.manual_pwm=spec.method==='set_pwm'?args[0]:null;return {success:true,status:structuredClone(fanStatus)};};
     if(window.hold)return new Promise(resolve=>{window.release=()=>resolve(action());});
     return Promise.resolve(action());
    }};
    const ui={addNotification:(title,text)=>notifications.push(text.textContent),createHandlerFn:(ctx,name,...args)=>ev=>ctx[name](...args,ev)};
    const base=new Function('baseclass','poll','rpc','ui',control)({extend:x=>x},poll,rpc,ui);
    window.vm=new Function('view','pwmfan',panel)({extend:x=>x},base);
    document.querySelector('main').append(vm.render(fanStatus));
    window.setApplied=value=>{const points={115:['low',8,'silent'],180:['medium',10,'standard'],220:['high',12,'performance']},p=points[value];fanStatus.manual_pwm=value;fanStatus.controller=`fan_type=3wire\nactive=pwm5\ndirection=hardware-10khz-raw\nstatus=manual-${p[2]}\nspeed_point=${p[0]}-10khz\nthreshold=${p[1]}\n`;vm.update(fanStatus);};
   },{control,panel,translations});
   await page.waitForFunction(()=>document.querySelector('#pwmfan-fan').dataset.level==='0');
   const drawing=()=>page.locator('#pwmfan-fan');
   const speed=()=>page.locator('.pwmfan-rotor').evaluate(n=>getComputedStyle(n).animationDuration);
   assert.equal(await speed(),'2.8s');assert.equal(await page.locator('#pwmfan-auto').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('#pwmfan-bar').evaluate(n=>n.style.width),'32%');
   assert((await page.locator('#pwmfan-rpm').textContent()).includes('无转速反馈'));
   assert.equal(await page.locator('.pwmfan-speed').count(),3);
   assert.deepEqual(await page.locator('.pwmfan-speed').allTextContents(),['安静','标准模式','强风']);
   for(const [value,level,period]of [[115,'0','2.8s'],[180,'1','1.2s'],[220,'2','0.45s']]){
    const previous=await drawing().getAttribute('data-level');
    await page.locator(`[data-pwm="${value}"]`).click();
    await page.waitForFunction(v=>document.querySelector(`[data-pwm="${v}"]`).getAttribute('aria-pressed')==='true',value);
    assert.equal(await drawing().getAttribute('data-level'),previous,'Do not animate an unapplied request');
    if(value!==115)assert.equal(await page.locator('#pwmfan-mode-hint').textContent(),'正在切换档位…');
    await page.evaluate(v=>setApplied(v),value);
    assert.equal(await drawing().getAttribute('data-level'),level);assert.equal(await speed(),period);
    assert.equal(await page.locator('#pwmfan-mode-hint').textContent(),'手动风量');
   }
   assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.method==='set_pwm').map(c=>c.args[0])),[115,180,220]);
   await page.evaluate(()=>{window.fail=true;});await page.locator('[data-pwm="115"]').click();
   await page.waitForFunction(()=>notifications.includes('synthetic fan failure'));
   assert.equal(await drawing().getAttribute('data-level'),'2');assert.equal(await page.locator('[data-pwm="220"]').getAttribute('aria-pressed'),'true');
   await page.evaluate(()=>{window.fail=false;window.hold=true;});await page.locator('[data-pwm="180"]').click();
   assert.equal(await page.locator('.pwmfan-actions button:disabled').count(),4);
   await page.evaluate(()=>{release();window.hold=false;});
   await page.waitForFunction(()=>!document.querySelector('[data-pwm="180"]').disabled);
   await page.evaluate(()=>setApplied(180));
   await page.locator('#pwmfan-auto').click();
   await page.waitForFunction(()=>document.querySelector('#pwmfan-auto').getAttribute('aria-pressed')==='true');
   await page.evaluate(()=>{fanStatus.controller=fanStatus.controller.replace('manual-standard','automatic');vm.update(fanStatus);});
   assert.equal(await speed(),'1.2s');assert.equal(await page.locator('#pwmfan-mode-hint').textContent(),'自动温控');
   await page.evaluate(()=>vm.update({...fanStatus,stalled:true}));
   assert.equal(await drawing().getAttribute('data-level'),'unknown');assert.equal(await page.locator('.pwmfan-rotor').evaluate(n=>getComputedStyle(n).animationPlayState),'paused');
   await page.evaluate(()=>vm.update({available:false}));assert.equal(await page.locator('.pwmfan-actions button:disabled').count(),4);
   await page.evaluate(()=>setApplied(180));
   assert.equal(await page.locator('.pwmfan-actions button:disabled').count(),0);
   const fit=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert(fit.scroll<=width+1,JSON.stringify(fit));
   await page.waitForTimeout(350); // Let Aurora's button color transition settle before visual checks.
   assert.equal(await page.locator('.pwmfan-head h2').evaluate(n=>getComputedStyle(n).color),await page.locator('.pwmfan-page').evaluate(n=>getComputedStyle(n).color));
   assert.equal(await page.locator('[data-pwm="180"]').evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(0, 125, 134)');
   await page.screenshot({path:`/tmp/lg6851f-fan-${theme}-${width}.png`,fullPage:true});
   await page.evaluate(()=>vm.update({available:true,pwm:100,manual_pwm:180,tach_available:true,rpm:1400,controller:'fan_type=4wire\nactive=pwm5\nstatus=manual\npwm0=100\npwm5=180\ndirection=direct\n'}));
   assert.equal(await drawing().getAttribute('data-level'),'1','Use active PWM5 output rather than inactive PWM0');
   await page.evaluate(()=>vm.update({available:true,pwm:100,manual_pwm:null,tach_available:true,rpm:2200,controller:'fan_type=4wire\nactive=pwm0\nstatus=automatic\npwm0=100\ndirection=inverse\n'}));
   assert.equal(await drawing().getAttribute('data-level'),'2','Respect inverse automatic PWM polarity');
   await page.emulateMedia({reducedMotion:'reduce'});
   assert.equal(await page.locator('.pwmfan-rotor').evaluate(n=>getComputedStyle(n).animationName),'none');
   await page.evaluate(()=>vm.unload());assert.equal(await page.evaluate(()=>polls.length),0);
   assert.deepEqual(errors,[]);await page.close();
   console.log(`PASS fan ${theme} ${width}px: three speeds, confirmed output, failures, auto, stall, reduced motion and unload`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
