// Offline browser test: production dashboard/helpers, synthetic data, no router.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const assets=path.join(root,'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources');
const files={};
for(const name of ['modem5g/cellular_v3','modem5g/cpe_v3','modem5g/mu_v1','view/modem5g/dashboard_v4','view/modem5g/dashboard_v5'])
 files[name]=fs.readFileSync(path.join(assets,name+'.js'),'utf8');
files.fan=fs.readFileSync(path.join(root,'package/vendor/luci-app-pwmfan/htdocs/luci-static/resources/pwmfan/visual_v1.js'),'utf8');
const css=fs.readFileSync(path.join(root,'package/vendor/luci-theme-aurora/htdocs/luci-static/aurora/main.css'),'utf8');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM||undefined,headless:true,args:['--no-sandbox']});
 try{
  for(const version of [4,5])for(const width of [360,390,1280])for(const dark of [false,true]){
   const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.setContent(`<html data-darkmode="${dark}"><meta name="viewport" content="width=device-width,initial-scale=1"><body><main style="padding:12px"></main></body></html>`);
   await page.addStyleTag({content:css});
   await page.evaluate(({files,version})=>{
    window.E=(tag,attrs={},children=[])=>{const el=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(typeof v==='function')el.addEventListener(k,v);else if(v!=null)el.setAttribute(k,v);}const add=v=>{if(Array.isArray(v))v.forEach(add);else if(v!=null)el.append(v instanceof Node?v:document.createTextNode(String(v)));};add(children);return el;};
    window.L={url:p=>'/'+p,hasViewPermission:()=>true,env:{}};
    const baseclass={extend:x=>x},rpc={declare:()=>()=>{throw Error('Unexpected RPC');}},ui={};
    const cellular=new Function('baseclass',files['modem5g/cellular_v3'])(baseclass);
    const C=new Function('baseclass','rpc','ui','cellular',files['modem5g/cpe_v3'])(baseclass,rpc,ui,cellular);
    const M=new Function('baseclass','rpc','ui',files['modem5g/mu_v1'])(baseclass,rpc,ui);
    const F=new Function('baseclass','rpc',files.fan)(baseclass,rpc);
    window.vm=new Function('view','poll','rpc','ui','C','M','F',files['view/modem5g/dashboard_v'+version])({extend:x=>x},{add:()=>{},remove:()=>{}},rpc,ui,C,M,F);
    window.data={current_slot:'B',modem:{},network:{},temperatures:[],memory:{},boot_confirmation:{state:'pending'}};
    document.querySelector('main').append(vm.render({data,current:null,rate:null,cpu:null,cached:false,fan:null}));
   },{files,version});
   for(const [state,label]of [['pending','待确认'],['waiting','确认中'],['confirmed','已完成'],['failed','失败'],['unknown','未获取']]){
    await page.evaluate(state=>vm.paint({...data,boot_confirmation:{state,exit_code:state==='failed'?75:0}}),state);
    assert.equal(await page.locator('#mud-boot-confirm').textContent(),'系统启动就绪确认：'+label);
    assert.equal(await page.locator('#mud-slot').textContent(),'当前槽位：B槽');
    const status=await page.locator('#mud-boot-confirm').boundingBox(),slot=await page.locator('#mud-slot').boundingBox();
    assert(status.x+status.width<=slot.x+1,`status must stay left of slot: v${version}/${width}/${dark}`);
    assert(slot.x+slot.width<=width,`slot exceeds viewport: v${version}/${width}/${dark}`);
   }
   assert.equal(await page.locator('#mud-slot').evaluate(el=>getComputedStyle(el).fontSize),'14px');
   await page.evaluate(()=>vm.paint({...data,current_slot:'A',boot_confirmation:{state:'confirmed',exit_code:0}}));
   assert.equal(await page.locator('#mud-slot').textContent(),'当前槽位：A槽');
   assert.deepEqual(errors,[]);await page.close();
  }
  console.log('PASS dashboards v4/v5: live boot status, A/B slots, 360/390/1280px, light/dark');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
