// 使用合成 MT6990 数据验证手机/桌面交互，不连接实机。
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),base=path.join(root,'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const files={};for(const name of ['modem5g/cellular_v3','modem5g/cpe_v3','view/modem5g/dashboard_v5','modem5g/cellular_v1','modem5g/cellular_v2','modem5g/cpe_v2','modem5g/cpe_v1','modem5g/mu_v1','view/modem5g/dashboard_v2','view/modem5g/dashboard_v3','view/modem5g/apn_v2','view/modem5g/traffic_v2'])files[name]=fs.readFileSync(path.join(base,name+'.js'),'utf8');
  files['pwmfan/visual_v1']=fs.readFileSync(path.join(root,'package/vendor/luci-app-pwmfan/htdocs/luci-static/resources/pwmfan/visual_v1.js'),'utf8');
  const old=fs.readFileSync(path.join(__dirname,'test_lg6851f_dashboard_layout.cjs'),'utf8');
  const fixture=old.slice(old.indexOf('const data={'),old.indexOf('window.calls=[]'))+'return data;';
  for(const width of [320,390,768,1280])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('http://lg6851f.test/**',route=>route.fulfill({contentType:'text/html',body:`<html data-darkmode="${theme==='dark'}"><meta name="viewport" content="width=device-width,initial-scale=1"><body><main style="padding:12px;min-width:0"></main><aside id="modal"></aside></body></html>`}));
   await page.goto('http://lg6851f.test/');await page.addStyleTag({content:fs.readFileSync(path.join(root,'package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css'),'utf8')});
   await page.evaluate(({files,fixture})=>{
    window.E=(tag,attrs={},children=[])=>{const el=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(typeof v==='function')el.addEventListener(k,v);else if(v!=null)el.setAttribute(k,v);}const add=x=>{if(Array.isArray(x))x.forEach(add);else if(x!=null)el.append(x instanceof Node?x:document.createTextNode(String(x)));};add(children);return el;};
    window.L={env:{rpctimeout:30},url:s=>'/'+s,resolveDefault:(p,d)=>Promise.resolve(p).catch(()=>d)};
    window._=s=>s;window.calls=[];let ticks=0;window.fanFixture={available:true,pwm:3,manual_pwm:null,tach_available:false,controller:'fan_type=3wire\nactive=pwm5\nstatus=automatic\nspeed_point=low-10khz\n'};
    const data=new Function(fixture)();data.current_slot='B';data.network.data={cid:2,apn:'example.net'};data.qos={cid:2,value:8};data.radio_details.parsed.bler={nr:{dl_raw:6,ul_raw:10},unit:'vendor_raw'};
    data.wireless=[{ssid:'OpenWrt',frequency:2412,channel:1,width:'EHT20',up:true,encryption:'none',hidden:false,country:'CN'},{ssid:'OpenWrt',frequency:5220,channel:44,width:'EHT160',up:true,encryption:'none',hidden:false,country:'CN'}];
    data.temperatures=[{name:'soc_max',celsius:54.9},{name:'cpu_little0',celsius:51},{name:'mt7996_phy0.0',celsius:53.2},{name:'md0',celsius:51.7},{name:'gpu0',celsius:65}];
    // 模拟后台暂未取得新数据：保留实际成功的无线参数和小区。
    data.cells.stale=data.radio_details.stale=true;
    data.traffic={totals:{rx:12340000000,tx:3400000000},clock_ok:true,today_used:500000000,month_used:15000000000,remaining:85000000000};
    let traffic={config:{plan_name:'测试套餐',monthly_gb:100,daily_gb:0,reset_day:1,count_mode:'total',device:''},status:{...data.traffic,available:true,updated_at:1794038969,cycle_used:15e9,cycle_start:'2026-11-01',cycle_end:'2026-12-01',today:{rx:400e6,tx:100e6},monthly_limit:100e9},days:[],months:[]};
    let profiles=[{id:'one',name:'运营商接入点',apn:'example.net',pdptype:'IPV4V6',auth:'none',current:true}];
    const rpc={declare:spec=>(...args)=>{calls.push({method:spec.method,args});switch(spec.method){
     case'get_status':return window.fanFailure?Promise.reject(Error('synthetic fan read failure')):Promise.resolve(structuredClone(fanFixture));
     case'get_dashboard':return Promise.resolve(structuredClone(data));
     case'get_rates':ticks++;return Promise.resolve({device:'ccmni3',boot_id:'test',at:ticks*2,rx:ticks*1001,tx:ticks*501,cpu:{total:ticks*100,idle:ticks*75}});
     case'get_sim_identity':return Promise.resolve({imei:args[0]?'123456789000111':'123***111'});
     case'apn_get':return Promise.resolve({ok:1,current:profiles[0],data_sim:0,connected:true,profiles:structuredClone(profiles)});
     case'apn_set':{const p=JSON.parse(args[1]);if(args[0]==='save')profiles.push({...p,id:'two'});return Promise.resolve({ok:1});}
     case'traffic_get':return Promise.resolve(structuredClone(traffic));
     case'traffic_clear':traffic.status.today_used=traffic.status.month_used=traffic.status.cycle_used=0;return Promise.resolve({ok:1,data:structuredClone(traffic)});
     case'traffic_set':traffic.config=JSON.parse(args[0]);return Promise.resolve({ok:1});
     default:return Promise.resolve({code:0,output:'测试请求'});
    }}};
    const ui={hideModal:()=>document.querySelector('#modal').replaceChildren(),showModal:(title,body)=>document.querySelector('#modal').replaceChildren(E('h2',{},title),...body),addNotification:()=>document.createElement('div')};
    window.pollFns=[];
    const cache={},poll={add:fn=>pollFns.push(fn),remove:fn=>{pollFns=pollFns.filter(v=>v!==fn);}};
    function module(name){if(cache[name])return cache[name];const src=files[name],args=[],values=[];
     for(const m of src.matchAll(/'require ([\w.]+)(?: as (\w+))?';/g)){const dep=m[1],alias=m[2]||dep.replace(/\./g,'_');args.push(alias);values.push(({view:{extend:x=>x},baseclass:{extend:x=>x},rpc,ui,poll})[dep]||module(dep.replace(/\./g,'/')));}
     return cache[name]=new Function(...args,src)(...values);
    }
    window.mount=async name=>{window.vm?.unload?.();const view=Object.assign({},module('view/modem5g/'+name+(name==='dashboard'?'_v5':'_v2')));window.vm=view;document.querySelector('main').replaceChildren(view.render(await view.load()));};
   },{files,fixture});
   const fit=async label=>{const r=await page.evaluate(()=>({w:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right}))}));if(r.scroll>width+1)await page.screenshot({path:'/tmp/lg6851f-fan-layout-overflow.png',fullPage:true});assert(r.scroll<=width+1,label+JSON.stringify(r));};
   await page.evaluate(()=>mount('dashboard'));await fit('dashboard');
   assert.equal(await page.locator('#mud-fan-name').textContent(),'安静');
   const positions=await page.evaluate(()=>{
    const r=s=>{const v=document.querySelector(s).getBoundingClientRect();return {left:v.left,right:v.right,top:v.top,bottom:v.bottom,cx:(v.left+v.right)/2};};
    return {hero:r('.mud-hero'),info:r('.mud-hero-l'),signal:r('.mud-hero-r'),fan:r('.mud-fan'),label:r('.mud-fan-label'),art:r('#mud-fan-visual')};
   });
   assert(positions.label.bottom<=positions.art.top,'Fan label must be above the animation');
   assert(positions.fan.right<=positions.hero.right&&positions.fan.top>=positions.hero.top,'Fan outside hero');
   if(width>600){assert(Math.abs(positions.signal.cx-positions.hero.cx)<2,'Desktop signal not centered');assert(positions.fan.left>positions.signal.right,'Desktop fan must be to the right of signal');}
   else{assert(positions.fan.left>=positions.info.right,'Mobile fan overlaps network information');assert(positions.signal.top>=Math.max(positions.info.bottom,positions.fan.bottom),'Mobile signal must remain beneath info/fan');}
   assert.equal(await page.locator('#mud-fan-visual .lgfan').evaluate(n=>getComputedStyle(n).backgroundColor),'rgba(0, 0, 0, 0)');
   assert.equal(await page.locator('#mud-fan-visual img').count(),0,'Do not place an opaque GIF rectangle in the hero');
   for(const [point,name,period]of [['medium','标准模式','1.2'],['high','强风','0.7'],['low','安静','1.6']]){
    await page.evaluate(async p=>{fanFixture.controller=fanFixture.controller.replace(/speed_point=\w+-10khz/,'speed_point='+p+'-10khz');await vm.refreshFan();},point);
    assert.equal(await page.locator('#mud-fan-name').textContent(),name);
    assert.equal(await page.locator('#mud-fan-visual .lgfan').getAttribute('data-period'),period);
    const actual=await page.locator('#mud-fan-visual .lgfan-rotor').evaluate(async n=>{const a=n.getAnimations()[0];await a.ready;return 1.6/a.playbackRate;});
    assert(Math.abs(actual-Number(period))<1e-6,'Fan animation did not match the confirmed mode');
   }
   const palette=await page.locator('#mud-fan-visual .lgfan-rim').evaluate(async n=>{const a=n.getAnimations()[0];await a.ready;a.pause();a.currentTime=0;const start=getComputedStyle(n).backgroundImage;a.currentTime=1400;const end=getComputedStyle(n).backgroundImage,transform=getComputedStyle(n).transform;a.play();return {start,end,transform};});
   assert.notEqual(palette.start,palette.end,'Chameleon palette must actually change');assert.equal(palette.transform,'none','Do not rotate a fixed rainbow');
   const background=await page.locator('#mud-fan-visual .lgfan-case').evaluate(n=>getComputedStyle(n).backgroundImage);
   await page.evaluate(()=>document.documentElement.dataset.darkmode=document.documentElement.dataset.darkmode==='true'?'false':'true');
   assert.notEqual(await page.locator('#mud-fan-visual .lgfan-case').evaluate(n=>getComputedStyle(n).backgroundImage),background,'Fan casing must follow theme changes');
   await page.evaluate(d=>document.documentElement.dataset.darkmode=String(d),theme==='dark');
   await page.evaluate(async()=>{fanFailure=true;await vm.refreshFan();});
   assert.equal(await page.locator('#mud-fan-name').textContent(),'未获取');assert.equal(await page.locator('#mud-fan-visual .lgfan-rotor').evaluate(n=>getComputedStyle(n).animationPlayState),'paused');
   await page.evaluate(async()=>{fanFailure=false;await vm.refreshFan();});
   await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.lgfan-rotor').evaluate(n=>getComputedStyle(n).animationName),'none');await page.emulateMedia({reducedMotion:'no-preference'});
   assert(!(await page.evaluate(()=>calls.some(c=>['set_pwm','restore_auto'].includes(c.method)))),'Dashboard must not issue fan control writes');
   const getRates=()=>page.locator('#mud-dl,#mud-ul').allTextContents();const first=await getRates();assert(first.every(x=>/^\d.*\/s$/.test(x)),'numeric first rates');
   await page.evaluate(()=>mount('dashboard'));assert.deepEqual(await getRates(),first);assert.equal(await page.locator('#mud-dl').getAttribute('title'),'最近一次真实速率');
   assert.equal(await page.locator('#mud-rx').textContent(),'12.34 GB');assert.equal(await page.locator('#mud-tr-day').textContent(),'500 MB');assert.equal(await page.locator('#mud-qci').textContent(),'8');assert.equal(await page.locator('#mud-slot').textContent(),'当前槽位：B槽');
   assert.equal(await page.locator('#mud-batt,#mud-wusb,#mud-msisdn,#mud-freqs').count(),0);assert.equal(await page.locator('#mud-temps span').first().evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)');
   assert.equal(await page.locator('#mud-ambr').textContent(),'256 Mbps / 12.8 Mbps');
   assert.equal(await page.locator('#mud-ssid').textContent(),'OpenWrt');assert.equal(await page.locator('#mud-chan').textContent(),'44 (5 GHz-EHT160)');
   assert.equal(await page.locator('#mud-wenc').textContent(),'none');assert.equal(await page.locator('#mud-whid').textContent(),'否');assert.equal(await page.locator('#mud-wcountry').textContent(),'cn');
   assert((await page.locator('#mud-clist').textContent()).includes('↑1200.9 Mbps · ↓1134.2 Mbps'));
   assert.deepEqual(await page.locator('#mud-temps span').allTextContents(),['SoC 54.9°C','CPU 51.0°C','WiFi 53.2°C','调制解调器 51.7°C']);
   assert((await page.locator('#mud-cellline').textContent()).startsWith('n78 · PCI 321'));
   assert.equal(await page.locator('#mud-bw').textContent(),'100 MHz');const metrics=await page.locator('#mud-radio-metrics').textContent();assert(metrics.includes('MCS 下/上'));assert(metrics.includes('0 / 28'));assert(!metrics.includes('载波聚合'));assert(metrics.includes('NR BLER 下/上'));assert(metrics.includes('6 / 10'));assert(!metrics.includes('6%'));
   assert.equal(await page.locator('#mud-btn-modem').isEnabled(),true);
   await page.evaluate(()=>vm.paint({...vm.data,modem:{...vm.data.modem,rat:'4G'}}));assert((await page.locator('#mud-rat').textContent()).startsWith('4G'),'旧NR缓存不得覆盖当前4G制式');
   assert(!(await page.evaluate(()=>calls.some(r=>['get_cells','get_radio_details','request_radio_details'].includes(r.method)))),'dashboard load must not issue modem queries');
   await page.locator('#mud-btn-reboot').click();await page.locator('#modal').getByRole('button',{name:'取消',exact:true}).click();assert(!(await page.evaluate(()=>calls.some(r=>r.method==='dashboard_action'))));
   await page.screenshot({path:'/workspace/outputs/lg6851f-dashboard-fan-'+theme+'-'+width+'.png',fullPage:true});
   await page.locator('.mud-hero').screenshot({path:'/workspace/outputs/lg6851f-dashboard-fan-hero-'+theme+'-'+width+'.png'});
   await page.evaluate(()=>{window.previousFanTask=vm.fanTask;});
   await page.evaluate(()=>mount('apn'));await fit('apn');
   assert(!(await page.evaluate(()=>pollFns.includes(previousFanTask))),'Fan polling must stop on navigation');
   await page.getByRole('button',{name:'添加接入点',exact:true}).click();await page.locator('#modal input').nth(0).fill('测试专网');await page.locator('#modal input').nth(1).fill('private.test');await page.locator('#modal').getByRole('button',{name:'保存',exact:true}).click();await page.getByText('测试专网',{exact:true}).waitFor();
   assert(await page.locator('.apn-item button').filter({hasText:'切换'}).isEnabled(),'APN selection not disabled by false attr');await fit('apn saved');
   await page.evaluate(()=>mount('traffic'));await fit('traffic');assert.equal(await page.locator('#mud-tr-today').textContent(),'500 MB');
   await page.locator('#mud-tr-clear').click();await page.locator('#modal').getByRole('button',{name:'取消',exact:true}).click();assert.equal(await page.evaluate(()=>calls.filter(r=>r.method==='traffic_clear').length),0);
   await page.locator('#mud-tr-clear').click();await page.locator('#modal').getByRole('button',{name:'清空',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#mud-tr-today').textContent==='0 B');assert.equal(await page.evaluate(()=>calls.filter(r=>r.method==='traffic_clear').length),1);
   assert.deepEqual(errors,[]);await page.close();
  }
  console.log('通过：320/390/768/1280px白天夜间看板、风扇布局/同步/主题、首帧速率、账本和原有控制');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
