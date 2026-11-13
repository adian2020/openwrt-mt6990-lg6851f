const fs = require('fs');
const path = require('path');
const os = require('os');
const root = path.resolve(__dirname, '../..');
const {chromium} = require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const base=path.join(root, 'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources');
 const common=fs.readFileSync(base+'/modem5g/common_v5.js','utf8');
 const view=fs.readFileSync(base+'/view/modem5g/lock_v22.js','utf8');
 const mu=fs.readFileSync(base+'/modem5g/mu_v1.js','utf8');
 const cells=fs.readFileSync(base+'/modem5g/cellular_v3.js','utf8');
 const css=fs.readFileSync(path.join(root, 'package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css'),'utf8');
 let cols=[];
 for(const width of [390,1280]){
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.setContent('<html><meta name="viewport" content="width=device-width,initial-scale=1"><body><main class="main-right" style="padding:12px;min-width:0"></main><aside id="modal"></aside></body></html>');
  await page.addStyleTag({content:css});
  await page.evaluate(({common,view,cells,mu})=>{
   window._=x=>x; String.prototype.format=function(...args){let i=0;return this.replace(/%s/g,()=>args[i++]);};
   window.L={env:{rpctimeout:30},bind:(fn,ctx)=>fn.bind(ctx)};
   // Match LuCI dom.attr(): false becomes the attribute string "false".
   // Treating booleans as DOM properties hid the real disabled=false bug.
   window.E=function(tag,attrs={},children=[]){const el=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(v==null)continue;if(typeof v==='function')el.addEventListener(k,v);else el.setAttribute(k,v);}const add=x=>{if(Array.isArray(x))x.forEach(add);else if(x!=null)el.append(x instanceof Node?x:document.createTextNode(String(x)));};add(children);return el;};
   const ui={createHandlerFn:(ctx,fn)=>typeof fn==='function'?fn.bind(ctx):ctx[fn].bind(ctx),addNotification:()=>{},showModal:(title,body)=>document.querySelector('#modal').replaceChildren(...body),hideModal:()=>document.querySelector('#modal').replaceChildren()};
   const c=new Function('baseclass','ui','E',common)({extend:x=>x},ui,E);
   const cellular=new Function('baseclass',cells)({extend:x=>x});
   window.rpcCalls=[];
   const m=new Function('baseclass','rpc','ui',mu)({extend:x=>x},{declare:()=>()=>Promise.resolve({})},ui);
   const v=new Function('view','rpc','ui','common','cellular','E','M','poll',view)({extend:x=>x},{declare:spec=>(...args)=>{
    rpcCalls.push({method:spec.method,args});if(spec.method==='set_fair_qos')return Promise.resolve({code:0,enabled:args[0],stopped:!args[0]});if(spec.method==='set_band_lock')return Promise.resolve({code:0,request_id:'single-rat'});
    if(spec.method==='get_lock_request'&&window.jobStates?.length){
     window.earlyFeedback=window.earlyFeedback||document.getElementById('m5-lock-result').textContent.includes('已读回验证');
     return Promise.resolve(window.jobStates.shift());
    }
    return Promise.resolve({});
   }},ui,c,cellular,E,m,{add:()=>{},remove:()=>{}});
   window.vm=v;
   const row='11,0,0,0,0,23,100,80,0,0,0,100,0,0,627264';
   const lte='7,0,0,460,11,123,55,65,255,255,11,82,255,,1300';
   const masks='lte band info = 0000000500000000\nnr band info = 000000000000000000002000\nlte band info = 880800d5000027a0\nnr band info = 080800d5000001a000003c00';
   window.maskResult={code:0,output:masks};
   document.querySelector('main').append(v.render([{code:0,output:masks}, {serving:{output:'+ECELL: 2,'+row+','+lte}}]));
  },{common,view,cells,mu});
  await page.waitForTimeout(100);
  await page.evaluate(()=>vm.paintHero({modem:{rat:'5G'},radio_details:{parsed:{sa_nsa:'SA',carriers:[]}},apn:{data_roaming:false}}));
  if(await page.locator('[data-network-mode="sa"]').getAttribute('aria-pressed')!=='true')throw Error('SA serving mode not highlighted');
  if(!await page.locator('[data-network-mode="nsa"]').isEnabled())throw Error('NSA mode still disabled');
  if(await page.getByRole('button',{name:'EN-DC',exact:true}).count())throw Error('unsupported EN-DC control still shown');
  if(await page.locator('#mu-fair-qos').getAttribute('aria-pressed')!=='false')throw Error('QoS should be off');
  await page.locator('#mu-fair-qos').click();
  if(await page.evaluate(()=>rpcCalls.some(r=>r.method==='set_fair_qos')))throw Error('QoS enabled before confirmation');
  await page.locator('#modal').getByRole('button',{name:'取消',exact:true}).click();
  await page.locator('#mu-fair-qos').click();await page.locator('#modal').getByRole('button',{name:'确认开启',exact:true}).click();
  if(await page.locator('#mu-fair-qos').getAttribute('aria-pressed')!=='true')throw Error('QoS enable did not reflect RPC');
  await page.locator('#mu-fair-qos').click();
  if(await page.locator('#mu-fair-qos').getAttribute('aria-pressed')!=='false')throw Error('QoS disable did not reflect RPC');
  const grid=await page.locator('#m5-lte-bands').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);
  cols.push(grid);
  const checked=()=>page.locator('.m5-band input:checked').evaluateAll(rows=>rows.map(row=>(row.closest('#m5-lte-bands')?'B':'n')+row.value));
  if(JSON.stringify((await checked()).sort())!==JSON.stringify(['B1','B3','n78']))throw Error('current lock not checked on first paint');
  const band=page.locator('#m5-lte-bands label').filter({hasText:/^B5$/});
  const before=await band.locator('span').evaluate(el=>getComputedStyle(el).backgroundColor);
  await band.click();
  if(!await band.locator('input').isChecked())throw Error('band cannot be selected with native LuCI attributes');
  if(await band.locator('span').evaluate(el=>getComputedStyle(el).backgroundColor)===before)throw Error('band has no visual click feedback');
  if(!await page.locator('#m5-band-draft').innerText().then(text=>text.includes('B5')))throw Error('pending selection not visible');
  await page.evaluate(()=>vm.syncLocks(maskResult));
  if(!await band.locator('input').isChecked())throw Error('background status overwrote pending selection');
  await band.click();
  if(await band.locator('input').isChecked())throw Error('band cannot be deselected');
  if(await page.evaluate(()=>rpcCalls.some(row=>row.method==='set_band_lock')))throw Error('selection changed modem without apply');
  await page.evaluate(()=>vm.load());
  if(await page.evaluate(()=>rpcCalls.some(row=>['get_locks','get_cells'].includes(row.method))))throw Error('page load issued a blocking modem read');
  if(!await page.locator('#m5-lock-result').innerText().then(text=>text.includes('B1 B3')&&text.includes('n78')))throw Error('current lock result box missing');
  await page.screenshot({path:path.join(os.tmpdir(), `lg6851f-mu-locks-${width}.png`),fullPage:true});
  await page.evaluate(()=>vm.showPane('cell'));
  const measure=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('#m5-pane-cell .m5-lock-action')].map(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))}));
  if(measure.scroll>width+1||measure.buttons.some(x=>x.left<0||x.right>width+1))throw Error(JSON.stringify(measure));
  await page.locator('#m5-cell-candidates tbody tr').first().click();
  if(await page.locator('#m5-lock-arfcn').inputValue()!=='627264')throw Error('cell selection failed');
  if(await page.locator('#m5-lock-band').inputValue()!=='')throw Error('overlapping NR band was guessed');
  await page.locator('#m5-cell-candidates tbody tr').nth(1).click();
  if(await page.locator('#m5-lock-band').inputValue()!=='3'||await page.locator('#m5-lock-rat').inputValue()!=='lte'||await page.locator('#m5-lock-arfcn').inputValue()!=='1300')throw Error('LTE EARFCN did not select B3');
  if(!await page.locator('#m5-cell-candidates tbody tr').nth(1).innerText().then(text=>text.includes('B3')))throw Error('LTE candidate table omitted band');
  if(await page.locator('#m5-lte-bands input').count()!==13||await page.locator('#m5-nr-bands input').count()!==14)throw Error('original band counts not restored');
  if(await page.locator('.m5-band input:disabled').count()!==1||!await page.locator('#m5-nr-bands input[value="76"]').isDisabled())throw Error('n76 must stay read-only');
  await page.evaluate(async()=>{
   const timer=window.setTimeout;window.setTimeout=(fn,ms,...args)=>timer(fn,ms===2000?0:ms,...args);
   const id='lg6851f-lock-job.test';
   const state=(op,phase,active=false,status='verified',code=0)=>({active,code:0,output:`SAVED_LOCK_STATE\nOP_ID=${op}\nMODE=bands\nSTATUS=${status}\nPHASE=${phase}\nRESULT_CODE=${code}\nLTE=1,3\nNR=78\n`});
   const verify=s=>s.mode==='bands'&&s.status==='verified';
   try{
    window.earlyFeedback=false;
    window.jobStates=[state('lg6851f-lock-job.previous','complete'),state(id,'restoring_data',true),state(id,'complete')];
    await vm.runAction(()=>Promise.resolve({code:0,request_id:id}),[],()=>{},verify);
    if(jobStates.length||!earlyFeedback)throw Error('verified masks were not shown before network recovery');
    window.jobStates=[state(id,'complete')];
    await vm.runAction(()=>Promise.resolve({code:0,request_id:id}),[],()=>{},verify);
    if(jobStates.length)throw Error('already completed operation required seeing active state');
    window.jobStates=[state(id,'failed',false,'failed',5)];
    await vm.runAction(()=>Promise.resolve({code:0,request_id:id}),[],()=>{},verify);
    if(!document.getElementById('m5-lock-result').textContent.includes('退出码：5')||vm.busy)throw Error('operation failure did not report promptly');
   }finally{window.setTimeout=timer;}
  });
  await page.evaluate(async()=>{
   document.querySelector('#m5-nr-bands input[value="1"]').click();
   window.jobStates=[{code:0,active:false,output:'SAVED_LOCK_STATE\nOP_ID=single-rat\nMODE=bands\nSTATUS=verified\nPHASE=complete\nRESULT_CODE=0\nLTE=1,3\nNR=1,78\n'}];
   await vm.applySingleBands('nr');
  });
  await page.locator('#modal button').filter({hasText:/^应用$/}).click();
  await page.waitForFunction(()=>rpcCalls.some(r=>r.method==='set_band_lock'));
  const applied=await page.evaluate(()=>rpcCalls.filter(r=>r.method==='set_band_lock').at(-1));
  if(JSON.stringify(applied.args)!==JSON.stringify([[1,3],[1,78]]))throw Error('per-RAT apply overwrote other bands');
  if(!await page.getByRole('button',{name:'VoNR：等待接口核实',exact:true}).isDisabled())throw Error('unverified voice control became enabled');
  await page.screenshot({path:path.join(os.tmpdir(), `lg6851f-lock-${width}.png`),fullPage:true});
  console.log(`PASS ${width}px: bands=${grid} columns; cell actions fit; cell selection works`);
  await page.close();
 }
 if(cols[1]<=cols[0])throw Error('desktop grid did not expand');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
