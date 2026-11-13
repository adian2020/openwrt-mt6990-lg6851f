#!/usr/bin/ucode
'use strict';
import { open, readfile, popen, mkdir, chmod, unlink, stat } from 'fs';
import * as store from 'lg6851f.sms-store';
import * as sms from 'lg6851f.sms';
import * as forward from 'lg6851f.forward';
const REQUEST='/tmp/lg6851f-sms-sync-request';
const BOOT=trim(readfile('/proc/sys/kernel/random/boot_id')||'');
function quote(s){return "'"+replace(''+s,"'","'\\''")+"'";}
function load(path){try{return json(readfile(path)||'null');}catch(e){return null;}}
function capture(argv,seconds){let p=popen('/usr/bin/timeout '+seconds+' '+join(' ',map(argv,quote))+' 2>/dev/null','r'),text=p?.read('all')||'',code=p?.close();return {text,code:code??5};}
function monotonic(){return +(split(readfile('/proc/uptime')||'0',' ')[0]);}
function ready(){
 if(!store.identity())return false;
 if(stat('/var/lock/lg6851f-modem-recovery.lock')||stat('/tmp/lg6851f-modem-control.active'))return false;
 let r=capture(['/bin/ubus','call','network.interface.modem5g','status'],3),n;try{n=json(r.text);}catch(e){return false;}
 // Never delay the first data call. SMS collection begins once it has settled.
 if(r.code||n?.pending)return false;
 if(n?.up)return +n.uptime>=30;
 // SMS also works with data dialing disabled once the radio is registered.
 let source='\n'+(readfile('/tmp/lg6851f-modem-status.state')||''),updated=match(source,/\nUPDATED=([0-9]+)/),uptime=+(split(readfile('/proc/uptime')||'0',' ')[0]);
 return uptime>=120&&updated&&time()-+updated[1]>=0&&time()-+updated[1]<90&&match(source,/\nREGISTERED=YES(\r?\n|$)/)&&match(source,/\nRADIO=[^\n]*_ON(\r?\n|$)/);
}
function sync_pool(){
 if(!ready())return {ok:false,error:'等待蜂窝网络稳定后同步'};
 let sim=store.identity(),r=capture(['/usr/bin/lg6851f-sms-list'],42);
 if(r.code!=0)return {ok:false,error:'短信通道忙或读取失败，稍后自动重试'};
 let parsed=forward.parse_sms(r.text);
 if(parsed.error||sim!=store.identity())return {ok:false,error:parsed.error||'SIM已变化，未采用旧数据'};
 let saved=store.ingest(sim,parsed,null);if(!saved.ok)return saved;
 let previous=load(store.SNAPSHOT),capacity=previous?.boot_id==BOOT&&previous?.sim==sim?previous.capacity:null;
 if(!capacity||time()-capacity.at>120){
  let caplock=open('/var/lock/lg6851f-sms-operation.lock','a',0o600);
  if(caplock?.lock('xn')){
   let cp=capture(['/usr/bin/modem5g-at','AT+CPMS?'],12),m=match(cp.text,/\+CPMS:\s*"[^"]*",([0-9]+),([0-9]+)/)||match(cp.text,/\+CPMS:\s*([0-9]+),([0-9]+)/);
   if(cp.code==0&&m&&+m[1]<=+m[2]&&+m[2]>0)capacity={at:time(),used:+m[1],total:+m[2]};
   caplock.close();
  }else if(caplock)caplock.close();
 }
 store.atomic(store.SNAPSHOT,{boot_id:BOOT,sim,updated:time(),raw:r.text,capacity});return {ok:true};
}
function public_job(){
 let j=load(store.JOB);if(!j)return {running:false,done:false};
 if(j.running&&(j.boot_id!=BOOT||monotonic()-(j.started_mono??0)>650))return {running:false,done:true,ok:false,error:'上次任务被中断或超时，请核对后再操作，未自动重复发送'};
 return {running:!!j.running,done:!!j.done,ok:!!j.ok,error:j.error||'',kind:j.kind,id:j.id,busy:!!j.busy};
}
function queue(kind,input){
 let lock=open('/var/lock/lg6851f-sms-job.lock','a',0o600);if(!lock?.lock('xn'))return {ok:false,error:'短信任务正在排队'};
 let action=function(){
  let worker=open('/var/lock/lg6851f-sms-worker.lock','a',0o600);if(!worker?.lock('xn'))return {ok:false,error:'短信处理进程尚未退出，请稍后重试'};worker.close();
  if(public_job().running)return {ok:false,error:'已有短信任务正在处理，请稍后重试'};
  if(kind=='send'){
   if(!sms.number(input?.number))return {ok:false,error:'号码应为3至20位数字，可带+'};
   let encoded=sms.outgoing(input?.text);if(encoded.error)return {ok:false,error:encoded.error};
  }else if(!sms.valid_id(input?.id))return {ok:false,error:'短信编号无效'};
  let id=trim(readfile('/proc/sys/kernel/random/uuid')||'');if(!match(id,/^[a-f0-9-]{36}$/))die('无法创建短信任务编号');
  store.atomic(store.JOB,{id,kind,input,started:time(),started_mono:monotonic(),boot_id:BOOT,running:true,done:false});
  let r=capture(['/sbin/start-stop-daemon','-S','-b','-x','/usr/bin/ucode','--','/usr/libexec/lg6851f-sms-pool.uc','work',id],5);
  if(r.code!=0){store.atomic(store.JOB,{id,kind,started:time(),started_mono:monotonic(),boot_id:BOOT,running:false,done:true,ok:false,error:'无法启动短信任务'});return {ok:false,error:'无法启动短信任务'};}
  return {ok:true,job:id};
 };let result;try{result=action();}catch(e){lock.close();die(e);}lock.close();return result;
}
function send(job){
 let input=job.input,sim=store.identity();if(!sim)return {ok:false,error:'等待SIM身份就绪'};
 let encoded=sms.outgoing(input.text);if(encoded.error)return {ok:false,error:encoded.error};
 let reserved=store.reserve(job.id,input.number,input.text,encoded.parts);if(!reserved.ok)return reserved;
 let confirmed=true,error='';
 for(let i=0;i<length(encoded.parts);i++){
  if(store.identity()!=sim){confirmed=false;error='SIM已变化，停止后续分段';break;}
  let pending=store.part_state(job.id,i,'inflight');if(!pending.ok)die(pending.error);
  let argv=['/usr/bin/modem5g-sms-send'];if(encoded.encoding=='ucs2')push(argv,'--ucs2');push(argv,input.number,encoded.parts[i]);
  let r=capture(argv,28),ok=r.code==0&&index(r.text,'official qlril API')>=0;
  let saved=store.part_state(job.id,i,ok?'sent':r.code==75?'busy':'uncertain');if(!saved.ok)die(saved.error);
  if(!ok){confirmed=false;error=r.code==75?'短信通道忙，当前分段未提交；已成功分段不会自动重发':'模组未确认提交，请先核对收件端，未自动重发';break;}
 }
 let result=store.finish(job.id,confirmed,sim);if(!result.ok)return result;
 return {ok:confirmed,error};
}
function delete_sim(job){
 let old=store.load().messages[job.input.id];if(!old)return {ok:false,error:'短信已不存在'};
 if(!length(old.indices||[]))return store.remove(old.id);
 let lock=open('/var/lock/lg6851f-sms-operation.lock','a',0o600);if(!lock?.lock('xn'))return {ok:false,error:'短信通道忙，请稍后重试'};
 let action=function(){
  if(store.identity()!=old.sim)return {ok:false,error:'SIM已变化，未删除'};
  // Re-read under the same operation lock; indices alone are unsafe after SIM reuse.
  for(let cmd in ['AT+CMGF=1','AT+CSCS="UCS2"'])if(capture(['/usr/bin/modem5g-at',cmd],12).code!=0)return {ok:false,error:'无法确认SIM短信，未删除'};
  let r=capture(['/usr/bin/modem5g-at','AT+CMGL="ALL"'],12),parsed=forward.parse_sms(r.text);
  if(r.code||parsed.error)return {ok:false,error:'无法确认当前SIM短信，未删除'};
  let row=filter(parsed.messages,m=>sms.id(old.sim,m)==old.id)[0];
  if(!row||store.identity()!=old.sim)return {ok:false,error:'SIM原短信已不存在或内容变化，未删除其他短信'};
  for(let index in row.indices||[row.index]){
   if(!match(''+index,/^[0-9]{1,6}$/))die('SIM索引无效');
   let d=capture(['/usr/bin/modem5g-at','AT+CMGD='+index],12);
   if(d.code||!match(d.text,/(^|\n)OK\s*$/))return {ok:false,error:'SIM删除未完成，请重新同步核对'};
  }
  return store.remove(old.id);
 };let result;try{result=action();}catch(e){lock.close();die(e);}lock.close();return result;
}
function main(){
 let board=trim(readfile('/tmp/sysinfo/board_name')||'');if(index(['fiberhome,lg6851f','fiberhome_lg6851f'],board)<0)return {ok:false,error:'不支持此设备'};
 let cmd=ARGV[0],input=load(ARGV[1]);
 if(cmd=='list')return store.list(input?.page||1);
 if(cmd=='show')return store.show(input?.id);
 if(cmd=='job')return public_job();
 if(cmd=='sync'){let f=open(REQUEST,'w',0o600);if(!f)return {ok:false,error:'无法排队同步任务'};f.close();return {ok:true,queued:true};}
 if(cmd=='send')return queue('send',input);
 if(cmd=='delete')return input?.sim?queue('delete',input):store.remove(input?.id);
 if(cmd=='work'){
  let worker=open('/var/lock/lg6851f-sms-worker.lock','a',0o600);if(!worker?.lock('xn'))return {ok:false,error:'短信处理进程仍在运行'};
  let job=load(store.JOB);if(!job||job.id!=ARGV[1]||!job.running||job.boot_id!=BOOT)return {ok:false,error:'任务已失效'};
  let result;try{result=job.kind=='send'?send(job):delete_sim(job);}catch(e){result={ok:false,error:'短信处理被中断，请核对结果；未自动重复操作'};}
  store.atomic(store.JOB,{id:job.id,kind:job.kind,started:job.started,started_mono:job.started_mono,boot_id:BOOT,...result,running:false,done:true});return result;
 }
 if(cmd!='run')return {ok:false,error:'无效操作'};
 let daemon=open('/var/lock/lg6851f-sms-pool-daemon.lock','a',0o600);if(!daemon?.lock('xn'))return {ok:false,error:'短信归档服务已运行'};
 mkdir('/etc/lg6851f-sms',0o700);chmod('/etc/lg6851f-sms',0o700);
 for(;;){try{unlink(REQUEST);let r=sync_pool();store.atomic('/tmp/lg6851f-sms-pool-status.json',{...r,updated:time(),boot_id:BOOT});}catch(e){store.atomic('/tmp/lg6851f-sms-pool-status.json',{ok:false,error:'短信归档失败，已保留原文件',updated:time(),boot_id:BOOT});}
  for(let i=0;i<30;i++){sleep(1000);if(readfile(REQUEST)!=null)break;}
 }
}
try{printf('%J\n',main());}catch(e){printf('%J\n',{ok:false,error:'无法读取或保存短信数据，已保留原文件'});exit(5);}
