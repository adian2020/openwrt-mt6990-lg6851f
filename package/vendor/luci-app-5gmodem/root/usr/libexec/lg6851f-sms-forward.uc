#!/usr/bin/ucode
'use strict';
import { open, readfile, rename, mkdir, chmod, mkdtemp, unlink, rmdir } from 'fs';
import { cursor } from 'uci';
import * as forward from 'lg6851f.forward';
import * as sms from 'lg6851f.sms';

const CONFIG='lg6851f_sms_forward';
const LEDGER='/etc/lg6851f-sms-forward/state.json';
const STATUS='/tmp/lg6851f-sms-forward-status.json';
const TEST='/tmp/lg6851f-sms-forward-test';
const RETRY='/tmp/lg6851f-sms-forward-retry';
function quote(value) { return "'"+replace(''+value,"'","'\\''")+"'"; }
function run(argv,seconds) { return system('/usr/bin/timeout '+(seconds||35)+' '+join(' ',map(argv,quote))+' >/dev/null 2>&1'); }
function atomic(path,value) {
	let dir=mkdtemp(replace(path,/\/[^\/]+$/,'')+'/.lg6851f-forward-write.XXXXXX');
	// Destination may be persistent: use a same-directory file for atomic rename.
	if(!dir)die('无法创建转发临时目录');
	let temp=dir+'/value', data=sprintf('%J',value), file=open(temp,'wx',0o600);
	let ok=file && file.write(data)==length(data) && file.close() && chmod(temp,0o600) && rename(temp,path);
	unlink(temp);rmdir(dir);
	if(!ok)die('无法保存短信转发状态');
	if(path==LEDGER && system('/bin/sync')!=0)die('无法同步短信去重记录');
}
function load_json(path) { try { return json(readfile(path)||'null'); } catch(e) { return null; } }
function config() {
	let uci=cursor(); uci.load(CONFIG);
	let raw=uci.get_all(CONFIG,'main')||{},checked=forward.validate(raw);
    return {...forward.defaults(),...raw,...(checked.values||{})};
}
function status(value) {
    let status_lock=open('/var/lock/lg6851f-sms-forward-status.lock','a',0o600);if(!status_lock?.lock('x'))die('状态记录忙');
    try{
	let previous=load_json(STATUS)||{}, results=previous.results||{};
	let history=previous.history||[];
	if(value.channel){results[value.channel]={state:value.state,reason:value.message||'',at:value.last_at||time()};if(index(['sent','failed','uncertain','retry','blocked'],value.state)>=0)unshift(history,{time:time(),kind:value.test?'test':'sms',method:value.channel,result:value.state});}
	history=slice(history,0,30);
	atomic(STATUS,{...previous,...value,results,history,updated:time(),boot_id:trim(readfile('/proc/sys/kernel/random/boot_id')||'')});
    }catch(e){status_lock.close();die(e);}status_lock.close();
}
function hash(value,dir) {
	let file=open(dir+'/hash','w',0o600);
	if(!file||file.write(value)!=length(value)||!file.close())die('无法计算短信去重标识');
	if(system('/usr/bin/sha256sum '+quote(dir+'/hash')+' >'+quote(dir+'/hash.out'))!=0)die('缺少SHA256工具');
	let result=match(readfile(dir+'/hash.out')||'',/^([0-9a-f]{64}) /);
	if(!result)die('短信去重标识无效');
	return result[1];
}
function cfgline(name,value) { return name+' = "'+replace(replace(replace(''+value,'\\','\\\\'),'"','\\"'),'\n','\\n')+'"\n'; }
function deliver(config,channel,message,key,dir,part) {
	if(channel=='sms') {
		if(replace(part.phone,/^\+/,'')==replace(message.from,/^\+/,''))return {state:'blocked',reason:'已拦截转发到原发件人'};
		let code=run(['/usr/bin/modem5g-sms-send','--ucs2',part.phone,part.hex],28);
		return code==0?{state:'sent'}:code==75?{state:'retry',reason:'短信发送接口忙'}:code==2?{state:'failed',reason:'短信编码或长度无效'}:{state:'uncertain',reason:'短信未确认提交，请人工核对后重试'};
	}
	let request='silent\nshow-error\nconnect-timeout = 10\nmax-time = '+(channel=='webhook'?config.webhook_timeout:25)+'\nmax-filesize = 65536\n';
	request+=cfgline('output',dir+'/response');
	if(channel=='webhook') {
        let method=config.webhook_method,url=config.url,payload='',content=config.webhook_content_type;
        message={...message,device:config.nickname||message.device};
        if(config.webhook_kind=='dingtalk'){
            method='POST';content='application/json';url=config.dingtalk_webhook;
            payload=sprintf('%J',{msgtype:'text',text:{content:forward.decorated(config,message,config.dingtalk_forward_device_info).text}});
            if(config.dingtalk_secret){let timestamp=''+time()+'000';url+='&timestamp='+timestamp+'&sign='+sms.urlencode(b64enc(sms.hmac256(config.dingtalk_secret,timestamp+'\n'+config.dingtalk_secret)));}
        }else if(method=='GET')url=replace(url,/\{(from|text|time|sim|device|kind)\}/g,(full,k)=>sms.urlencode(({from:message.from,text:message.text,time:message.time,sim:'SIM',device:message.device,kind:message.test?'test':'sms'})[k]||''));
        else payload=content=='application/json'?sprintf('%J',forward.webhook_body(config,message)):forward.template(config,message,content=='application/x-www-form-urlencoded'?sms.urlencode:null);
        let file=open(dir+'/payload','w',0o600);if(!file||file.write(payload)!=length(payload)||!file.close())return {state:'failed',reason:'无法保存发送内容'};
        request+='proto = "=http,https"\nrequest = "'+method+'"\n';
        request+=cfgline('url',url)+cfgline('header','Content-Type: '+content+'; charset=utf-8')+cfgline('header','Idempotency-Key: '+key);
        for(let header in split(config.webhook_headers,'\n'))if(length(trim(header)))request+=cfgline('header',header);
        if(method=='POST')request+=cfgline('data-binary','@'+dir+'/payload');
        request+='write-out = "%{http_code}"\n';
	}
	else {
		let mime='From: '+config.from+'\r\nTo: '+config.to+'\r\nSubject: =?UTF-8?B?'+b64enc(forward.title(config)+' '+message.from)+'?=\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\nMessage-ID: <'+key+'@lg6851f.local>\r\n\r\n';
		let encoded=b64enc(forward.decorated(config,message,config.smtp_forward_device_info).text);
		for(let i=0;i<length(encoded);i+=76)mime+=substr(encoded,i,76)+'\r\n';
		let file=open(dir+'/payload','w',0o600);
		if(!file||file.write(mime)!=length(mime)||!file.close())return {state:'failed',reason:'无法保存邮件内容'};
		request+='proto = "=smtp,smtps"\nssl-reqd\n';
		request+=cfgline('url',(config.tls=='tls'?'smtps://':'smtp://')+config.host+':'+config.port)+cfgline('mail-from',config.from)+cfgline('mail-rcpt',config.to)+cfgline('upload-file',dir+'/payload');
		if(length(config.username))request+=cfgline('user',config.username+':'+config.password);
	}
	let file=open(dir+'/curl.conf','w',0o600);
	if(!file||file.write(request)!=length(request)||!file.close())return {state:'failed',reason:'无法保存投递参数'};
	let code=system('/usr/bin/timeout '+(channel=='webhook'?config.webhook_timeout+5:30)+' /usr/bin/curl --config '+quote(dir+'/curl.conf')+' >'+quote(dir+'/http')+' 2>/dev/null');
	if(channel=='smtp'&&code==67)return {state:'failed',reason:'邮箱服务器拒绝登录，请检查授权码'};
	if(index([35,60],code)>=0)return {state:'failed',reason:'TLS连接或证书校验失败'};
	if(code!=0) return index([5,6,7],code)>=0?{state:'retry',reason:'服务器暂时无法连接'}:{state:'uncertain',reason:'服务器未确认投递，请人工核对后重试'};
	if(channel=='smtp')return {state:'sent'};
	let http=+(readfile(dir+'/http')||'0');
	if(http>=200&&http<300&&(config.webhook_kind=='dingtalk'?forward.service_ok('dingtalk',readfile(dir+'/response')||''):forward.expected(config,readfile(dir+'/response')||'')))return {state:'sent'};
	return http==429||http>=500?{state:'retry',reason:'服务器繁忙或返回错误'}:{state:'failed',reason:'服务器拒绝或未确认成功'};
}
function cycle(config,dir) {
	let state=load_json(LEDGER), test=trim(readfile(TEST)||'');
	if(state && readfile(RETRY)) {
		for(let key,job in state.jobs)for(let channel in ['webhook','smtp','sms'])for(let item in job[channel]||[]) {
			if(index(['uncertain','failed','inflight','retry'],item.state)>=0){item.state='retry';item.next=0;item.attempts=0;}
		}
		atomic(LEDGER,state);unlink(RETRY);
	}
	let source=readfile('/tmp/lg6851f-modem-status.state')||'', identity=match(source,/(^|\n)ICCID=([^\r\n]+)/);
	if(!test&&!identity){status({state:'waiting_sim',message:'等待SIM身份与短信服务就绪'});return;}
	let sim=hash(identity?identity[2]:'test',dir), revision=config.revision||'initial';
	let messages=[], incomplete=0;
	if(!test) {
		let code=system('/usr/bin/lg6851f-sms-list >'+quote(dir+'/list')+' 2>/dev/null');
		if(code!=0){status({state:'source_unavailable',message:'短信接口暂不可用，稍后重试'});return;}
		let parsed=forward.parse_sms(readfile(dir+'/list'));
		if(parsed.error){status({state:'source_unavailable',message:parsed.error});return;}
		messages=parsed.messages;incomplete=parsed.incomplete;
	}
	else {
		unlink(TEST);
		messages=[{from:'LG6851F',time:''+time(),text:'这是一条短信转发测试消息。',test,device:trim(readfile('/proc/sys/kernel/hostname')||'OpenWrt')}];
	}
	// A test never replaces the real SIM's durable baseline.
	if(!state || state.version!=1)state={version:1,source:null,jobs:{}};
	let source_key=sim+':'+revision, first=state.source!=source_key, present={};
	for(let message in messages) {
		message.device=trim(readfile('/proc/sys/kernel/hostname')||'OpenWrt');
		let key=hash(sprintf('%J',[sim,message.from,message.time,message.text,message.test||'']),dir);
		present[key]=true;
		if(!test&&first){state.jobs[key] ||= {baseline:true,at:time()};continue;}
		if(state.jobs[key]?.baseline || (!test&&!forward.eligible(config,message)))continue;
		let job=state.jobs[key] ||= {at:time()};
		for(let channel in ['webhook','smtp','sms']) {
			if(!config[channel])continue;
			let encoded=channel=='sms'?forward.sms_parts(forward.decorated(config,message,config.sms_forward_device_info)):null;
			let parts=channel=='sms'?(encoded?[]:null):[''];
			if(encoded)for(let phone in split(config.phone,'\n'))for(let hex in encoded)push(parts,{phone,hex});
			if(!parts){job[channel]=[{state:'failed',reason:'短信超过20段或编码无效'}];atomic(LEDGER,state);status({state:'failed',channel,message:job[channel][0].reason});continue;}
			let results=job[channel] ||= [];
			for(let i=0;i<length(parts);i++) {
				let old=results[i];
				if(old?.state=='inflight'){results[i]={...old,state:'uncertain',reason:'上次发送被中断，请核对后人工重试'};atomic(LEDGER,state);status({state:'uncertain',channel,message:results[i].reason});}
				if(old?.state=='sent'||old?.state=='blocked')continue;
				if(old && old.state!='retry')break;
				if(old && (old.next>time() || old.attempts>=5))break;
				results[i]={state:'inflight',attempts:(old?.attempts||0)+1,at:time()};
				atomic(LEDGER,state); // Durable reservation before any external effect.
				let result=deliver(config,channel,message,key+'-'+channel+'-'+i,dir,parts[i]);
				if(result.state=='retry'&&results[i].attempts>=5)result={state:'failed',reason:'已达到5次自动尝试上限，请检查配置后人工重试'};
				results[i]={...results[i],...result,next:time()+min(3600,60*(1<<(results[i].attempts-1)))};
				atomic(LEDGER,state);
				status({state:result.state,channel,message:result.reason||'服务器或模组已确认提交',last_at:time(),part:i+1,parts:length(parts),test:!!test});
				if(result.state!='sent'&&result.state!='blocked')break;
			}
		}
	}
	if(!test&&first){state.source=source_key;atomic(LEDGER,state);status({state:'ready',message:'已有短信已建立基线，等待新增短信',incomplete});}
	else if(!length(messages))status({state:'ready',message:'等待新增短信',incomplete});
	else if(!test){let previous=load_json(STATUS)||{};status({source_checked_at:time(),incomplete,state:index(['sent','retry','failed','uncertain','blocked'],previous.state)>=0?previous.state:'ready'});}
	// Keep a bounded rolling ledger. Entries still present in the inbox survive.
	let ids=keys(state.jobs);
	if(!test&&length(ids)>2048) {
		let removable=sort(filter(ids,key=>!present[key]),(a,b)=>(state.jobs[a].at||0)-(state.jobs[b].at||0)), count=length(ids);
		for(let key in removable){if(count<=2048)break;delete state.jobs[key];count--;}
		if(count<length(ids))atomic(LEDGER,state);
	}
	if(length(keys(state.jobs))>4096){status({state:'storage_full',message:'去重记录已达上限，停止转发；请检查收件箱和转发记录'});die('短信转发去重记录已达上限');}
}

let command=ARGV[0], lock=open('/var/lock/lg6851f-sms-forward.lock','a',0o600);
if(command=='get') {
	let value=config();value.password_set=!!value.password;value.password='';value.dingtalk_secret_set=!!value.dingtalk_secret;value.dingtalk_secret='';
	printf('%J\n',{values:value,status:load_json(STATUS)||{state:'idle'}});exit(0);
}
if(command=='clear'){let state_lock=open('/var/lock/lg6851f-sms-forward-status.lock','a',0o600);if(!state_lock?.lock('xn')){printf('%J\n',{code:75,error:'转发处理中，请稍后清空记录'});exit(75);}let previous=load_json(STATUS)||{};atomic(STATUS,{...previous,history:[]});printf('%J\n',{code:0});exit(0);}
if(command=='status'){let value=config();printf('%J\n',{...(load_json(STATUS)||{state:'idle'}),enabled:value.enabled,state:value.enabled?(load_json(STATUS)?.state||'idle'):'disabled'});exit(0);}
if(command=='set') {
	let editor=open('/var/lock/lg6851f-sms-forward-editor.lock','a',0o600);
	if(!editor?.lock('xn')){printf('%J\n',{code:75,error:'配置正在保存'});exit(75);}
	let input=load_json(ARGV[1]), previous=config();
	if(input && !input.password && !input.clear_password)input.password=previous.password;
	if(input && !input.dingtalk_secret && !input.clear_dingtalk_secret)input.dingtalk_secret=previous.dingtalk_secret;
	let validated=forward.validate(input);
	if(validated.error){printf('%J\n',{code:22,error:validated.error});exit(22);}
	run(['/etc/init.d/lg6851f-sms-forward','stop'],45);
	if(!lock?.lock('xn')){printf('%J\n',{code:75,error:'转发任务仍在退出，请稍后重试'});exit(75);}
	unlink(TEST);unlink(RETRY);
	let uci=cursor();uci.load(CONFIG);
	let values=validated.values;
	for(let key,value in values)uci.set(CONFIG,'main',key,type(value)=='bool'?(value?'1':'0'):''+value);
	uci.set(CONFIG,'main','revision',trim(readfile('/proc/sys/kernel/random/uuid')||''));
	if(!uci.save(CONFIG)||!uci.commit(CONFIG)||!chmod('/etc/config/'+CONFIG,0o600))die('保存配置失败');
	lock.close();
	if(run(['/etc/init.d/lg6851f-sms-forward','start'],5)!=0){printf('%J\n',{code:5,error:'配置已保存，但转发服务启动失败，请检查系统日志'});exit(5);}
	printf('%J\n',{code:0,output:'配置已保存；已有短信将建立基线，不补发历史短信'});exit(0);
}
if(command=='test'||command=='retry') {
	if(!config().enabled){printf('%J\n',{code:22,error:'请先保存并启用转发'});exit(22);}
	let file=open(command=='test'?TEST:RETRY,'wx',0o600);
	if(!file){printf('%J\n',{code:75,error:'已有测试正在等待发送'});exit(75);}
	file.write(trim(readfile('/proc/sys/kernel/random/uuid')||''));file.close();
	printf('%J\n',{code:0,output:command=='test'?'测试已排队，将在下一个采集周期实际发送，请查看投递状态':'重试已排队，将在下一个采集周期处理'});exit(0);
}
if(command!='run')exit(2);
if(!lock?.lock('xn'))exit(75);
mkdir('/etc/lg6851f-sms-forward',0o700);chmod('/etc/lg6851f-sms-forward',0o700);
let board=trim(readfile('/tmp/sysinfo/board_name')||'');
if(index(['fiberhome,lg6851f','fiberhome_lg6851f'],board)<0)exit(95);
for(;;) {
	let value=config(), checked=forward.validate(value);
	if(checked.error){status({state:'invalid_config',message:checked.error});exit(22);}
	if(!value.enabled){status({state:'disabled',message:'短信转发已关闭'});exit(0);}
	let dir=mkdtemp('/tmp/lg6851f-forward-send.XXXXXX');
	if(!dir)die('无法创建短信转发临时目录');
	let failed=false;
	try { cycle(value,dir); }
	catch(e) { failed=true;try {status({state:'storage_failed',message:'转发状态保存失败，已停止投递'});} catch(status_error) {} }
	for(let name in ['hash','hash.out','list','payload','curl.conf','response','http'])unlink(dir+'/'+name);
	rmdir(dir);
	if(failed)exit(5);
	sleep(value.interval*1000);
}
