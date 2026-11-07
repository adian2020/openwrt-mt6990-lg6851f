// 离线浏览器使用合成数据；验证手机布局和控制确认，不连接路由器。
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const base = path.join(root, 'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources');

(async () => {
 const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
 try {
  const files = {};
  for (const name of ['modem5g/common_v5','modem5g/cellular_v1','modem5g/cpe_v1','view/modem5g/network_v4','view/modem5g/dashboard_v1','view/modem5g/apn_v1','view/modem5g/panels_v1','view/modem5g/forward_v1'])
   files[name] = fs.readFileSync(path.join(base,name+'.js'),'utf8');
  const css = fs.readFileSync(path.join(root,'package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css'),'utf8');
  for (const width of [390,1280]) {
   const page = await browser.newPage({viewport:{width,height:900}});
   const errors = [];page.on('pageerror',error=>errors.push(error.message));
   await page.route('http://lg6851f.test/**',route=>route.fulfill({contentType:'text/html',body:'<html><meta name="viewport" content="width=device-width,initial-scale=1"><body><main style="padding:12px;min-width:0"></main><aside id="modal"></aside></body></html>'}));
   await page.goto('http://lg6851f.test/');
   await page.addStyleTag({content:css});
   await page.evaluate(files=>{
    window.E=function(tag,attrs={},children=[]){
     const el=document.createElement(tag);
     for(const[k,v]of Object.entries(attrs)){
      if(typeof v==='function')el.addEventListener(k,v);
      else if(typeof v==='boolean')el[k]=v;
      else if(v!=null)el.setAttribute(k,v);
     }
     const add=value=>{if(Array.isArray(value))value.forEach(add);else if(value!=null)el.append(value instanceof Node?value:document.createTextNode(String(value)));};add(children);return el;
    };
    window.L={env:{requestpath:['admin','modem5g','sim'],rpctimeout:20},bind:(fn,ctx)=>fn.bind(ctx)};
    window._=value=>value;
    const data={modem:{rat:'5G',operator:'测试运营商',rsrp:-101,rsrq:-10.5,sinr:18.5,imei:'123***111'},
     network:{up:true,l3_device:'ccmni3','ipv4-address':[{address:'192.0.2.2',mask:29}]},
     memory:{percent:21.1,used:211000,total:1000000},temperatures:[{kind:'thermal',name:'cpu_little0',celsius:56.415}],
     cells:{age:5,stale:false,serving:{code:0,output:'+ECELL: 1,11,0,0,460,11,321,55,65,255,255,11,82,255,,640000'}},apn:{apn:'example.net'},wireless:[{device:'phy0-ap0',ssid:'测试无线网络',channel:36,frequency:5180,txpower:23,encryption:'psk2'}],
     clients:[{device:'phy0-ap0',mac:'02:00:00:00:00:01',signal:-46,rx_kbit:1200900,tx_kbit:1134200}],
     leases:[{hostname:'synthetic-device',address:'192.0.2.3',mac:'02:00:00:00:00:01'}],cached_modem_stale:false,cache_age:5,
     radio_details:{age:15,stale:false,parsed:{carriers:[{type:'NR PCC',rat:'nr',band:78,pci:321,arfcn:640000,
      dl_bandwidth_mhz:100,ul_bandwidth_mhz:100,dl_mcs:0,ul_mcs:28,cqi:11,dl_modulation_code:1,ul_modulation_code:1,dl_mimo_code:2,ul_mimo_code:2}],
      ambr:{network:{dl:{bps:256000000},ul:{bps:12800000}},ims:{dl:{bps:512000000},ul:{bps:512000000}}},endc:{available:0,restricted:0},sa_nsa:'NSA',data_registration:{ok:true,radio_tech:'QL_NW_RADIO_TECH_NSA5G'}}}};
    window.calls=[];let ticks=0;
    const rpc={declare:spec=>(...args)=>{
     calls.push({method:spec.method,args});
     if(spec.method==='get_dashboard')return Promise.resolve(window.pendingDashboard?{initializing:true,modem:{},network:{},cached_modem_stale:true}:data);
     if(spec.method==='get_network')return Promise.resolve({status:JSON.stringify(data.network),config:"network.modem5g.apn='example.net'"});
     if(spec.method==='get_apn')return Promise.resolve({proto:'ql_datacall',apn:'example.net',iptype:3,auth:0,mtu:1500,auto_conf:0,password_set:true});
     if(spec.method==='get_rates'){ticks++;return Promise.resolve({device:'ccmni3',boot_id:'test',at:ticks*2,rx:ticks*1001,tx:ticks*501,cpu:{total:ticks*100,idle:ticks*75}});}
     if(spec.method==='get_sim_identity')return Promise.resolve({imei:args[0]?'123456789000111':'123***111'});
     if(spec.method==='get_radio_details')return new Promise(resolve=>{window.resolveRadio=resolve;});
     if(spec.method==='get_forward_config')return Promise.resolve({values:{enabled:false,webhook:false,smtp:false,sms:false,interval:60,provider:'json',tls:'tls',port:465,body:'{}'},status:{state:'idle'}});
     if(spec.method==='get_forward_status')return Promise.resolve({enabled:false,state:'disabled'});
     return Promise.resolve({code:0,output:'测试操作完成'});
    }};
    const ui={hideModal:()=>document.querySelector('#modal').replaceChildren(),showModal:(title,body)=>document.querySelector('#modal').replaceChildren(E('h2',{},title),...body),addNotification:()=>{},
     createHandlerFn:(ctx,method,...args)=>event=>(typeof method==='function'?method:ctx[method]).apply(ctx,[...args,event])};
    const cellular=new Function('baseclass',files['modem5g/cellular_v1'])({extend:x=>x});
    const C=new Function('baseclass','rpc','ui','cellular','E',files['modem5g/cpe_v1'])({extend:x=>x},rpc,ui,cellular,E);
    const poll={add:()=>{}};
    window.mount=async name=>{
     const common=new Function('baseclass','ui','E',files['modem5g/common_v5'])({extend:x=>x},ui,E);
     const view=name==='network'?new Function('view','rpc','ui','common','poll','E',files['view/modem5g/network_v4'])({extend:x=>x},rpc,ui,common,poll,E):name==='forward'?new Function('view','rpc','ui','poll','C','E',files['view/modem5g/forward_v1'])({extend:x=>x},rpc,ui,poll,C,E):new Function('view','poll','ui','C','E',files['view/modem5g/'+name+'_v1'])({extend:x=>x},poll,ui,C,E);
     window.vm=view;document.querySelector('main').replaceChildren(view.render(await view.load()));
     await Promise.resolve();await Promise.resolve();
    };
   },files);
   const fit = async label=>{
    const measure=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth,offscreen:[...document.querySelectorAll('main button')].some(el=>el.getBoundingClientRect().right>innerWidth+1)}));
    if(measure.scroll>width+1||measure.offscreen)throw Error(`${label} ${width}: ${JSON.stringify(measure)}`);
   };
   await page.evaluate(()=>mount('dashboard'));
   const rateValues=()=>page.locator('main section').filter({has:page.locator('h3').filter({hasText:/^(下载速率|上传速率)$/})}).locator('.cpe-metric strong').allTextContents();
   const initialRates=await rateValues();
   if(initialRates.length!==2||initialRates.some(value=>!/^\d.*\/s$/.test(value)))throw Error('first dashboard paint has no measured rates');
   const beforeReload=await page.evaluate(()=>calls.filter(row=>row.method==='get_rates').length);
   await page.evaluate(()=>mount('dashboard'));
   if(JSON.stringify(await rateValues())!==JSON.stringify(initialRates))throw Error('last measured rates not restored');
   if(!await page.locator('main').getByText('最近一次速率',{exact:true}).count())throw Error('cached rate is not identified');
   if(await page.evaluate(()=>calls.filter(row=>row.method==='get_rates').length)!==beforeReload+1)throw Error('refresh waited for a second sample despite valid cache');
   for(const invalid of ['boot','device','expired','counter-reset','malformed']){
    await page.evaluate(kind=>{
     const key='lg6851f-dashboard-rates-v1',cache=JSON.parse(sessionStorage.getItem(key));
     if(kind==='boot')cache.sample.boot_id='old-boot';
     if(kind==='device')cache.sample.device='old-interface';
     if(kind==='expired')cache.sample.at-=60;
     if(kind==='counter-reset')cache.sample.rx+=1e9;
     cache.rate={rx:999999999,tx:999999999};
     sessionStorage.setItem(key,kind==='malformed'?'invalid json':JSON.stringify(cache));
    },invalid);
    await page.evaluate(()=>mount('dashboard'));
    if(await page.locator('main').getByText('最近一次速率',{exact:true}).count())throw Error('invalid rate cache reused: '+invalid);
    if((await rateValues()).some(value=>!/^\d.*\/s$/.test(value)||value.includes('GiB')))throw Error('invalid cache prevented fresh measured rates: '+invalid);
   }
   await page.evaluate(async()=>{
    const descriptor=Object.getOwnPropertyDescriptor(window,'sessionStorage');
    Object.defineProperty(window,'sessionStorage',{configurable:true,get(){throw Error('Storage blocked');}});
    try{await mount('dashboard');}finally{Object.defineProperty(window,'sessionStorage',descriptor);}
   });
   if((await rateValues()).some(value=>!/^\d.*\/s$/.test(value)))throw Error('blocked browser storage prevented measured rates');
   await page.evaluate(()=>vm.sample());
   await fit('dashboard');
   const text=await page.locator('main').innerText();
   if(!text.includes('-10.5 dB')||!text.includes('25.0%')||!text.includes('未取得全球 IPv6'))throw Error('measurement text mismatch');
   if(!text.includes('640000')||!text.includes('n77 / n78'))throw Error('cell sample missing/incorrect');
   if(await page.evaluate(()=>calls.some(row=>row.method==='get_cells')))throw Error('dashboard issued an automatic AT query');
   if(await page.evaluate(()=>calls.some(row=>row.method==='get_radio_details')))throw Error('dashboard issued an automatic vendor query');
   if(!text.includes('100 MHz / 100 MHz')||!text.includes('0 / 28')||!text.includes('12.8 Mbit/s'))throw Error('radio units/zero MCS mismatch');
   const qci=await page.locator('dt').filter({hasText:/^QCI$/}).evaluate(el=>el.nextElementSibling.textContent);
   if(qci!=='未获取')throw Error('CQI was shown as QCI');
   const mode=()=>page.locator('dt').filter({hasText:/^当前 SA \/ NSA$/}).evaluate(el=>el.nextElementSibling.textContent);
   if(await mode()!=='NSA')throw Error('current data-registration mode missing');
   await page.evaluate(()=>{vm.data.radio_details.stale=true;vm.paint(vm.data);});
   if(await mode()!=='未获取')throw Error('expired mode shown as current');
   await page.evaluate(()=>{vm.data.radio_details.stale=false;vm.paint(vm.data);});
   await page.getByRole('button',{name:'读取高级参数',exact:true}).click();
   if(!await page.getByRole('button',{name:'读取中…',exact:true}).isDisabled())throw Error('radio read not locked in UI');
   await page.evaluate(()=>{void vm.readRadioDetails();});
   if(await page.evaluate(()=>calls.filter(row=>row.method==='get_radio_details').length)!==1)throw Error('duplicate radio read');
   await page.evaluate(()=>resolveRadio({code:0}));
   await page.getByRole('button',{name:'读取高级参数',exact:true}).waitFor();
   if(await page.evaluate(()=>L.env.rpctimeout)!==20)throw Error('RPC timeout not restored');
   await page.getByRole('button',{name:'关闭射频',exact:true}).click();
   if(await page.evaluate(()=>calls.some(row=>row.method==='set_radio')))throw Error('radio changed without confirmation');
   await page.locator('#modal').getByRole('button',{name:'取消',exact:true}).click();
   await page.getByRole('button',{name:'开启射频',exact:true}).click();
   await page.locator('#modal').getByRole('button',{name:'确认执行',exact:true}).click();
   if(await page.evaluate(()=>L.env.rpctimeout)!==20)throw Error('radio action timeout not restored');
   if(await page.evaluate(()=>calls.filter(row=>row.method==='set_radio'&&row.args[0]===true).length)!==1)throw Error('dashboard radio action missing');
   await page.evaluate(()=>mount('apn'));
   await fit('apn');
   await page.getByRole('button',{name:'仅保存',exact:true}).click();
   if(await page.evaluate(()=>calls.some(row=>row.method==='set_apn')))throw Error('APN changed without confirmation');
   await page.locator('#modal').getByRole('button',{name:'确认执行',exact:true}).click();
   const save=await page.evaluate(()=>calls.find(row=>row.method==='set_apn'));
   if(save.args[1]!==false||save.args[0].password!=='')throw Error('save-only/password contract mismatch');
   await page.evaluate(()=>mount('panels'));
   await fit('sim');
   if((await page.locator('main').innerText()).includes('123456789000111'))throw Error('SIM identity revealed by default');
   await page.getByRole('button',{name:'显示完整号码',exact:true}).click();
   if(!(await page.locator('main').innerText()).includes('123456789000111'))throw Error('explicit identity reveal failed');
   for (const key of ['device','settings','cpu','ttl','traffic']) {
    await page.evaluate(async key=>{L.env.requestpath[2]=key;await mount('panels');},key);
    await fit(key);
   }
   await page.evaluate(()=>mount('network'));
   await fit('original dial-up page');
   await page.getByRole('button',{name:'Radio on',exact:true}).click();
   if(await page.evaluate(()=>calls.filter(row=>row.method==='set_radio'&&row.args[0]===true).length)!==2)throw Error('original dial-up page bypassed shared radio RPC');
   await page.evaluate(()=>{document.querySelector('#m5-net-state details').open=true;vm.updateNetwork({status:JSON.stringify({up:true,'ipv4-address':[{address:'192.0.2.9'}]})});});
   if(!(await page.locator('#m5-net-state').innerText()).includes('192.0.2.9')||!await page.locator('#m5-net-state details').evaluate(el=>el.open))throw Error('dial-up refresh lost new address or expanded details');
   if(errors.length)throw Error(errors.join('\n'));
   console.log(`PASS ${width}px: dashboard/APN/panels/forward fit; explicit actions and identity reveal verified`);
   await page.evaluate(()=>mount('forward'));
   await fit('forward');
   if(await page.evaluate(()=>calls.some(row=>['set_forward_config','test_forward','retry_forward'].includes(row.method))))throw Error('forward page sent a message or changed settings on load');
   await page.locator('#fwd-provider').selectOption('wecom');
   await page.getByRole('button',{name:'填入模板',exact:true}).click();
   if(!(await page.locator('#fwd-body').inputValue()).includes('{text}'))throw Error('forward template lost placeholders');
   await page.locator('#fwd-enabled').check();
   await page.locator('#fwd-webhook').check();
   await page.getByRole('button',{name:'保存并应用',exact:true}).click();
   const forwardSave=await page.evaluate(()=>calls.find(row=>row.method==='set_forward_config'));
   if(!forwardSave?.args[0].enabled||!forwardSave.args[0].webhook||forwardSave.args[0].provider!=='wecom')throw Error('forward settings were not saved');
   await page.evaluate(()=>{window.pendingDashboard=true;return mount('dashboard');});
   await fit('pending dashboard');
   if(!(await page.locator('main').innerText()).includes('后台正在采集状态'))throw Error('pending dashboard still waits instead of opening');
   await page.close();
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
