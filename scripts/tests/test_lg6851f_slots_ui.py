#!/usr/bin/env python3
"""Exercise the actual LuCI view with DOM/RPC fixtures; never reboot anything."""
import pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
VIEW=ROOT/'package/vendor/luci-app-5gmodem/htdocs/luci-static/resources/view/system/lg6851f-slots.js'
class SlotViewTest(unittest.TestCase):
 def test_confirmation_restore_risk_readonly_stale_state_and_reboot(self):
  script=r'''
const assert=require('assert'),fs=require('fs');
const source=fs.readFileSync(process.argv[1],'utf8');
class Element {
 constructor(tag,attrs,children){this.tag=tag;this.attrs=attrs||{};this.children=Array.isArray(children)?children:[children];this.value='';this.checked=false;}
 appendChild(n){this.children.push(n);}
 replaceWith(n){this.replacement=n;}
}
const E=(...args)=>new Element(...args),calls=[],notices=[];
let modal=null,canWrite=true,selectError=0,reconnected=false,selection=1;
const state={code:0,current:'b',next:'b',control:'1'.repeat(64),slots:{a:{priority:14,retry:0,success:1,upgrade:1,image_headers_ok:true},b:{priority:15,retry:4,success:1,upgrade:1,image_headers_ok:true}}};
const rpc={declare:spec=>async(...args)=>{calls.push({method:spec.method,args});if(spec.method==='get_boot_slots')return state;if(spec.method==='reboot')return {};if(selectError)return {code:75,error:'changed'};state.next=args[0];state.control=String(++selection).repeat(64);return {code:0,control:state.control,backup:'/data/lg6851f-slot-backups/fixture',rebooted:false};}};
const ui={showModal:(title,nodes)=>{modal=nodes;},hideModal:()=>{modal=null;},createHandlerFn:(self,fn)=>(...args)=>fn.call(self,...args),addNotification:(a,b,c)=>notices.push(c),awaitReconnect:()=>{reconnected=true;}};
const document={querySelector:()=>new Element('div')};
const view=new Function('view','rpc','ui','E','L','window','document',source)({extend:x=>x},rpc,ui,E,{hasViewPermission:()=>canWrite},{location:{host:'192.168.1.1'}},document);
function walk(nodes){return (Array.isArray(nodes)?nodes:[nodes]).flatMap(n=>n instanceof Element?[n,...walk(n.children)]:[]);}
function button(text){return walk(modal).find(n=>n.tag==='button'&&n.children[0]===text);}
function confirm(letter){const inputs=walk(modal).filter(n=>n.tag==='input');inputs[0].checked=true;inputs[1].value=letter;}
(async()=>{
 const rendered=view.render(state);assert(walk(rendered).some(n=>n.tag==='table'));
 view.confirmSlot('a');await button('仅设置').attrs.click();assert(!calls.some(x=>x.method==='select_boot_slot'));
 confirm('B');await button('仅设置').attrs.click();assert(!calls.some(x=>x.method==='select_boot_slot'));
 confirm('A');selectError=75;await button('设置并重启').attrs.click();assert(!calls.some(x=>x.method==='reboot'));assert(modal);assert(notices.includes('error'));
 selectError=0;await button('仅设置').attrs.click();assert(!modal);assert(!calls.some(x=>x.method==='reboot'));
 const selected=calls.filter(x=>x.method==='select_boot_slot').at(-1);assert.deepEqual(selected.args,['a','1'.repeat(64),true,true]);
 view.confirmSlot('b');confirm('b');await button('设置并重启').attrs.click();assert(calls.some(x=>x.method==='reboot'));assert(reconnected);
 canWrite=false;const readonly=view.render(state);assert(walk(readonly).filter(n=>n.tag==='button'&&String(n.children[0]).startsWith('选择 ')).every(n=>n.attrs.disabled));
 const failed=view.render({code:5,error:'fixture'});assert(!walk(failed).some(n=>n.tag==='table'));
 console.log('PASS real view confirmation, stale state, risk acknowledgement, select-only/reboot and read-only controls');
})().catch(e=>{console.error(e);process.exit(1);});
'''
  result=subprocess.run(['node','-e',script,str(VIEW)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
