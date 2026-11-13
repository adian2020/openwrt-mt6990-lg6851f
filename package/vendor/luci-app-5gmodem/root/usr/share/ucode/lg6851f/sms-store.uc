'use strict';
import { readfile, stat, open, mkdir, chmod, mkdtemp, rename, unlink, rmdir } from 'fs';
import { sha256 } from 'digest';
import * as sms from 'lg6851f.sms';

export const FILE='/etc/lg6851f-sms/pool.json';
export const SNAPSHOT='/tmp/lg6851f-sms-snapshot.json';
export const JOB='/tmp/lg6851f-sms-current-job.json';
const LOCK='/var/lock/lg6851f-sms-pool.lock';

export function atomic(path,value) {
 let dir=replace(path,/\/[^\/]+$/,'');mkdir(dir,0o700);if(index(path,'/etc/')==0)chmod(dir,0o700);
 let data=sprintf('%J',value);if(length(data)>8388608)die('短信存储达到8MiB上限，请先导出或清理');
 let tmp=mkdtemp(dir+'/.sms-write.XXXXXX');if(!tmp)die('无法创建短信存储临时目录');
 let f=open(tmp+'/data','wx',0o600),ok=f&&f.write(data)==length(data)&&f.close()&&chmod(tmp+'/data',0o600)&&rename(tmp+'/data',path);
 unlink(tmp+'/data');rmdir(tmp);if(!ok)die('无法保存短信存储');
 if(index(path,'/etc/')==0&&system('/bin/sync')!=0)die('无法同步短信存储');
}
export function load() {
 let raw=readfile(FILE);
 if(raw==null){if(stat(FILE))die('无法读取已有短信存储');return {version:1,messages:{},hidden:{},outbox:{},updated:0};}
 let pool;try{pool=json(raw);}catch(e){die('短信存储损坏，已保留原文件，请勿重复初始化');}
 if(pool?.version!=1||type(pool.messages)!='object'||type(pool.hidden)!='object'||type(pool.outbox)!='object')die('短信存储格式不受支持，已保留原文件');
 return pool;
}
export function edit(fn) {
 let lock=open(LOCK,'a',0o600);if(!lock?.lock('xn'))return {ok:false,code:75,error:'短信存储正在更新，请稍后重试'};
 let result;try{let pool=load();result=fn(pool);if(result?.write){delete result.write;pool.updated=time();atomic(FILE,pool);}}catch(e){lock.close();die(e);}lock.close();return result;
}
export function identity() {
 let raw=readfile('/tmp/lg6851f-modem-status.state')||'',m=match('\n'+raw,/\nICCID=([^\r\n]+)/);
 return m&&length(trim(m[1]))?sha256(trim(m[1])):null;
}
function values_array(object){return map(keys(object),key=>object[key]);}
export function list(page) {
 page=+page;if(page<1||page>500||page!=int(page))return {ok:false,error:'页码无效'};
 let snapshot;try{snapshot=json(readfile(SNAPSHOT)||'null');}catch(e){}
 let capacity=snapshot?.sim==identity()&&snapshot?.boot_id==trim(readfile('/proc/sys/kernel/random/boot_id')||'')?snapshot.capacity:null;
 let pool=load(),all=sort(values_array(pool.messages),(a,b)=>b.time>a.time?1:b.time<a.time?-1:(b.created||0)-(a.created||0)),n=length(all);
 return {ok:true,page,pages:max(1,int((n+9)/10)),total:n,unread:length(filter(all,m=>m.status=='unread')),
  msgs:map(slice(all,(page-1)*10,page*10),m=>({id:m.id,peer:m.peer,dir:m.dir,time:m.time,status:m.status,preview:sms.preview(m.text)})),
  sim_seen:capacity?.at||0,sim_used:capacity?.used??null,sim_total:capacity?.total??null};
}
export function show(id) {
 if(!sms.valid_id(id))return {ok:false,error:'短信编号无效'};
 return edit(pool=>{
  let m=pool.messages[id];if(!m)return {ok:false,error:'短信已删除或不存在'};
  let unread=m.status=='unread';m.status='read';
  return {ok:true,write:unread,text:'From: '+m.peer+'\nDate: '+m.time+'\n---\n'+m.text,message:m};
 });
}
export function remove(id) {
 if(id!='all'&&!sms.valid_id(id))return {ok:false,error:'短信编号无效'};
 return edit(pool=>{
  let ids=id=='all'?keys(pool.messages):[id];
  for(let key in ids){if(pool.messages[key])pool.hidden[key]=time();delete pool.messages[key];}
  if(length(keys(pool.hidden))>16384)return {ok:false,error:'本地删除标记已达上限，请先备份数据'};
  return {ok:true,write:true};
 });
}
export function ingest(sim,parsed,capacity) {
 if(!sim||parsed.error)return {ok:false,error:parsed.error||'等待SIM标识'};
 return edit(pool=>{
  let changed=false;
  for(let row in parsed.messages){
   let id=sms.id(sim,row),old=pool.messages[id];
   if(pool.hidden[id])continue;
   if(!old){
    if(length(keys(pool.messages))>=4096)return {ok:false,error:'本地短信已达4096条，请先备份或清理'};
    pool.messages[id]={id,sim,peer:row.from,time:sms.display_time(row.time),raw_time:row.time,text:row.text,dir:row.dir||'mt',status:row.state=='REC UNREAD'?'unread':'read',indices:row.indices||[row.index],created:time()};changed=true;
   }else if(sprintf('%J',old.indices)!=sprintf('%J',row.indices||[row.index])){old.indices=row.indices||[row.index];changed=true;}
  }
  if(capacity&&pool.sim_seen!=capacity.at){pool.sim_seen=capacity.at;pool.sim_used=capacity.used;pool.sim_total=capacity.total;changed=true;}
  if(pool.source!=sim){pool.source=sim;changed=true;}
  return {ok:true,write:changed};
 });
}
export function reserve(job,number,text,parts) {
 return edit(pool=>{
  if(pool.outbox[job])return {ok:false,error:'此发送任务已经处理，未重复发送'};
  if(length(keys(pool.outbox))>=128)return {ok:false,error:'发送记录已满，请保留数据并检查未确认任务'};
  pool.outbox[job]={state:'inflight',number,text,parts:map(parts,()=>({state:'pending'})),created:time()};
  return {ok:true,write:true};
 });
}
export function part_state(job,index,state) {
 return edit(pool=>{let out=pool.outbox[job];if(!out||!out.parts[index])return {ok:false,error:'发送预留记录缺失'};out.parts[index]={state,at:time()};return {ok:true,write:true};});
}
function date_string(value){let t=localtime(value);return sprintf('%04d-%02d-%02d %02d:%02d:%02d',t.year,t.mon,t.mday,t.hour,t.min,t.sec);}
export function finish(job,confirmed,sim) {
 return edit(pool=>{
  let out=pool.outbox[job];if(!out)return {ok:false,error:'发送预留记录缺失'};
  out.state=confirmed?'sent':'uncertain';out.finished=time();
  if(confirmed){
   let row={dir:'mo',from:out.number,text:out.text,time:job},id=sms.id(sim,row);
   if(length(keys(pool.messages))>=4096)return {ok:false,write:true,error:'发送已提交但本地归档已满，请勿重复发送'};
   pool.messages[id]={id,sim,peer:out.number,text:out.text,time:date_string(out.created),raw_time:'',dir:'mo',status:'read',indices:[],created:out.created};
  }
  // Only fully confirmed old reservations can be pruned. Uncertain ones remain evidence.
  let sent=sort(filter(keys(pool.outbox),key=>pool.outbox[key].state=='sent'),(a,b)=>pool.outbox[a].created-pool.outbox[b].created);
  while(length(sent)>64)delete pool.outbox[shift(sent)];
  return {ok:true,write:true};
 });
}
