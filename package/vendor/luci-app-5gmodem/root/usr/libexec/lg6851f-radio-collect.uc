import * as fs from 'fs';
import * as radio from 'lg6851f.radio';
const boot_id=trim(fs.readfile('/proc/sys/kernel/random/boot_id') || '');
function publish(path,data){
 let dir=fs.mkdtemp('/tmp/lg6851f-radio.XXXXXX');if(!dir)return false;
 let file=dir+'/value.json',text=sprintf('%J\n',data);
 let ok=fs.writefile(file,text)==length(text)&&fs.rename(file,path);
 fs.unlink(file);fs.rmdir(dir);return ok;
}
function state(status,message){
 return publish('/tmp/lg6851f-radio-request.json',{status,message,boot_id,updated:time()});
}
function capture(command){let p=fs.popen(command+' 2>&1','r');let output=p?.read?.('all')||'',code=p?.close?.();return {output,code:code ?? 5};}
let netraw=capture("/bin/ubus -t 2 call network.interface.modem5g status"),net;
try{net=json(netraw.output);}catch(e){}
if(!net?.up || (net.uptime ?? 0)<5)exit(0);
if(fs.stat('/tmp/lg6851f-modem-control.active') || fs.stat('/var/lock/lg6851f-modem-recovery.lock'))exit(75);
let scope=(net.l3_device||'')+':'+(net.data?.cid||'')+':'+(net.data?.apn||'');
let old=null;try{old=json(fs.readfile('/tmp/lg6851f-modem-radio-details.json')||'null');}catch(e){}
if(old?.scope && old.scope!=scope){for(let name in ['cells','radio-details','qos'])fs.unlink('/tmp/lg6851f-modem-'+name+'.json');old=null;}
let cells=capture("/usr/bin/timeout 12 /usr/bin/modem5g-at 'AT+ECELL'");
if(cells.code==0 && match(cells.output,/\+ECELL:/))publish('/tmp/lg6851f-modem-cells.json',{serving:cells,updated:time(),boot_id,scope});
// 直接读取当前上网CID，禁止用IMS承载或常量8填充。
let cid=int(net.data?.cid),qos=null;
if(cid>0 && cid<=32 && net.data?.apn!='ims'){
 let r=capture('/usr/bin/timeout 12 /usr/bin/modem5g-at '+"'AT+C5GQOSRDP="+cid+"'");
 let parsed=r.code==0?radio.parse_qos(r.output,cid):null;
 if(parsed)qos={...parsed,updated:time(),boot_id,scope};
 if(qos)publish('/tmp/lg6851f-modem-qos.json',qos);
}
// 自动轮询复用同一个厂商采集器；新数据失败时不覆盖旧结果。
let automatic=ARGV[0]=='--auto';
if(automatic && (net.uptime ?? 0)<30)exit(0);
if(automatic && old?.boot_id==boot_id && old.scope==scope && time()-old.updated>=0 && time()-old.updated<120)exit(0);
if(!state('reading','正在后台读取无线参数'))exit(1);
let result=capture('/usr/bin/timeout -k 10 75 /usr/bin/lg6851f-modem-details'),parsed=radio.parse(result.output);
if(result.code || !parsed.complete){
 state('error',result.code==75?'模组通道忙，将自动重试':'无线参数读取未完成，保留上次成功数据');exit(1);
}
result={...result,parsed,updated:time(),boot_id,scope};
if(!publish('/tmp/lg6851f-modem-radio-details.json',result)){state('error','保存无线参数失败');exit(1);}
state('complete','无线参数已更新');
let child=fs.popen('/usr/bin/lg6851f-dashboard-collect >/dev/null 2>&1 </dev/null &','r');child?.close?.();
