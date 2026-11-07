#!/usr/bin/ucode
'use strict';
import { readfile, popen, open, mkdtemp, rename, unlink, rmdir } from 'fs';
if (index(['fiberhome,lg6851f','fiberhome_lg6851f'],trim(readfile('/tmp/sysinfo/board_name')||''))<0) exit(95);
const boot=trim(readfile('/proc/sys/kernel/random/boot_id')||'');
function publish(path,data){
 let directory=mkdtemp('/tmp/lg6851f-lock-reading.XXXXXX');
 if(!directory)die('Cannot create lock cache directory');
 let file=open(directory+'/reading','wx',0o600),text=sprintf('%J',{...data,boot_id:boot,updated:time()});
 let ok=file&&file.write(text)==length(text)&&file.close()&&rename(directory+'/reading',path);
 unlink(directory+'/reading');rmdir(directory);
 if(!ok)die('Cannot publish lock cache');
}
function capture(command){let pipe=popen(command+' 2>&1','r');return {output:trim(pipe?.read?.('all')||''),code:pipe?.close?.()||0};}
function collect(){
 let network=capture('/usr/bin/timeout 5 /bin/ubus call network.interface.modem5g status'),state;
 try{state=json(network.output);}catch(e){}
 if(network.code||!state?.up||+state.uptime<30)return {code:11,output:'等待蜂窝网络完成启动后再读取锁定状态'};
 for(let daemon in ['atcid','mtk_netagent','scd','ql_netd','ql_ril_service'])
  if(capture('/usr/bin/timeout 2 /bin/pidof '+daemon).code)return {code:11,output:'等待模组服务完成启动'};
 let result=capture('/usr/bin/timeout 45 /usr/bin/lg6851f-modem-lock get');
 if(result.code)return result;
 if(length(split(result.output,'get band mode success!'))!=3||length(split(result.output,'lte band info'))!=3||length(split(result.output,'nr band info'))!=3)
  return {code:5,output:'未完整读回当前频段与模组能力，请点击读取重试'};
 publish('/tmp/lg6851f-modem-bands.json',result);
 return {code:0,output:'锁定状态已读取'};
}
publish('/tmp/lg6851f-lock-refresh.json',{status:'reading'});
let result=collect();
publish('/tmp/lg6851f-lock-refresh.json',{status:result.code?'error':'complete',...result});
