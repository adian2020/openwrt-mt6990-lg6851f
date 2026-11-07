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
if(!state('reading','正在后台读取无线参数'))exit(1);
let p=fs.popen('/usr/bin/timeout 55 /usr/bin/lg6851f-modem-details 2>&1','r');
let output=p?.read?.('all') || '',code=p?.close?.(),parsed=radio.parse(output);
if(code || !parsed.complete){
 state('error',code==75?'模组通道忙，请稍后重新读取': '无线参数读取失败（退出码 '+(code || 0)+'），未覆盖上次有效缓存');
 exit(1);
}
let result={code:0,output,parsed,updated:time(),boot_id};
if(!publish('/tmp/lg6851f-modem-radio-details.json',result)){
 state('error','无线参数已读取，但保存缓存失败');exit(1);
}
state('complete','无线参数已更新');
// 重建只读看板快照，不再读取模组。
let child=fs.popen('/usr/bin/lg6851f-dashboard-collect >/dev/null 2>&1 </dev/null &','r');child?.close?.();
