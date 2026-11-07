const fs = require('fs');
const path = require('path');
const os = require('os');
const root = path.resolve(__dirname, '../..');
const {chromium} = require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const base=path.join(root, 'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources');
 const common=fs.readFileSync(base+'/modem5g/common_v5.js','utf8');
 const view=fs.readFileSync(base+'/view/modem5g/lock_v20.js','utf8');
 const cells=fs.readFileSync(base+'/modem5g/cellular_v1.js','utf8');
 const css=fs.readFileSync(path.join(root, 'package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css'),'utf8');
 let cols=[];
 for(const width of [390,1280]){
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.setContent('<html><meta name="viewport" content="width=device-width,initial-scale=1"><body><main class="main-right" style="padding:12px;min-width:0"></main></body></html>');
  await page.addStyleTag({content:css});
  await page.evaluate(({common,view,cells})=>{
   window._=x=>x; String.prototype.format=function(...args){let i=0;return this.replace(/%s/g,()=>args[i++]);};
   window.L={bind:(fn,ctx)=>fn.bind(ctx)};
   // Match LuCI dom.attr(): false becomes the attribute string "false".
   // Treating booleans as DOM properties hid the real disabled=false bug.
   window.E=function(tag,attrs={},children=[]){const el=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(v==null)continue;if(typeof v==='function')el.addEventListener(k,v);else el.setAttribute(k,v);}const add=x=>{if(Array.isArray(x))x.forEach(add);else if(x!=null)el.append(x instanceof Node?x:document.createTextNode(String(x)));};add(children);return el;};
   const ui={createHandlerFn:(ctx,fn)=>typeof fn==='function'?fn.bind(ctx):ctx[fn].bind(ctx),addNotification:()=>{}};
   const c=new Function('baseclass','ui','E',common)({extend:x=>x},ui,E);
   const cellular=new Function('baseclass',cells)({extend:x=>x});
   window.rpcCalls=[];
   const v=new Function('view','rpc','ui','common','cellular','E',view)({extend:x=>x},{declare:spec=>(...args)=>{rpcCalls.push({method:spec.method,args});return Promise.resolve({});}},ui,c,cellular,E);
   window.vm=v;
   const row='11,0,0,0,0,23,100,80,0,0,0,100,0,0,627264';
   const masks='lte band info = 0000000500000000\nnr band info = 000000000000000000002000\nlte band info = 880800d5000027a0\nnr band info = 080800d5000001a000003c00';
   window.maskResult={code:0,output:masks};
   document.querySelector('main').append(v.render([{code:0,output:masks}, {serving:{output:'+ECELL: 1,'+row}}]));
  },{common,view,cells});
  await page.waitForTimeout(100);
  const grid=await page.locator('#m5-lte-bands').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);
  cols.push(grid);
  const checked=()=>page.locator('.m5-band input:checked').evaluateAll(rows=>rows.map(row=>(row.closest('#m5-lte-bands')?'B':'n')+row.value));
  if(JSON.stringify(await checked())!==JSON.stringify(['B1','B3','n78']))throw Error('current lock not checked on first paint');
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
  await page.screenshot({path:path.join(os.tmpdir(), `lg6851f-bands-${width}.png`),fullPage:true});
  await page.evaluate(()=>vm.showPane('cell'));
  const measure=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('#m5-pane-cell .m5-lock-action')].map(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))}));
  if(measure.scroll>width+1||measure.buttons.some(x=>x.left<0||x.right>width+1))throw Error(JSON.stringify(measure));
  await page.locator('#m5-cell-candidates tbody tr').first().click();
  if(await page.locator('#m5-lock-arfcn').inputValue()!=='627264')throw Error('cell selection failed');
  if(await page.locator('#m5-lock-band').inputValue()!=='')throw Error('overlapping NR band was guessed');
  if(await page.locator('#m5-lte-bands input').count()!==13||await page.locator('#m5-nr-bands input').count()!==12)throw Error('original band counts not restored');
  if(await page.locator('.m5-band input:disabled').count())throw Error('selectable bands unexpectedly disabled');
  await page.screenshot({path:path.join(os.tmpdir(), `lg6851f-lock-${width}.png`),fullPage:true});
  console.log(`PASS ${width}px: bands=${grid} columns; cell actions fit; cell selection works`);
  await page.close();
 }
 if(cols[1]<=cols[0])throw Error('desktop grid did not expand');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
