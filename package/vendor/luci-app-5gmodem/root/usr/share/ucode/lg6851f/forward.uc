'use strict';

// Pure validation/decoding shared by the authenticated editor and worker.
export function defaults() {
	return { enabled: false, interval: 60, webhook: false, url: '', provider: 'json',
		body: '{"from":"{from}","text":"{text}","time":"{time}","device":"{device}"}',
		smtp: false, host: '', port: 465, tls: 'tls', username: '', password: '', from: '', to: '',
		sms: false, phone: '', blocked: '', keyword: '' };
}
function line(value, maximum) {
	if(type(value)!='string'||length(value)>maximum)return false;
	for(let i=0;i<length(value);i++)if(ord(value,i)<32||ord(value,i)==127)return false;
	return true;
}
function phone(value) { return type(value) == 'string' && !!match(value, /^\+?[0-9]{3,20}$/); }
function email(value) { return line(value, 254) && !!match(value, /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}$/); }
export function validate(input) {
	let result = defaults();
	for (let key, value in result) {
		if (type(value) == 'bool') result[key] = input?.[key] === true || input?.[key] === '1';
		else if (type(value) == 'int') result[key] = +(input?.[key] ?? value);
		else result[key] = input?.[key] ?? value;
	}
	if (result.interval < 30 || result.interval > 600 || result.interval != int(result.interval)) return { error: '采集间隔应为30至600秒' };
	for (let name in ['url','provider','body','host','tls','username','password','from','to','phone','blocked','keyword']) {
		if (type(result[name]) != 'string' || length(result[name]) > (name == 'body' ? 8192 : 2048)) return { error: '配置内容过长或格式错误' };
	}
	if (result.enabled && !result.webhook && !result.smtp && !result.sms) return { error: '请至少启用一种转发渠道' };
	if (result.webhook) {
		if (!line(result.url,2048) || !match(result.url, /^https?:\/\/[^\s\/@#]+([\/\?][^\s#]*)?$/) || index(result.url, '@') >= 0) return { error: 'Webhook地址应为有效的HTTP或HTTPS地址，不使用URL用户名密码' };
		if (index(['json','wecom','dingtalk','telegram','bark','pushplus'],result.provider) < 0) return { error: '推送类型无效' };
		try { if (type(json(result.body)) != 'object') return { error: 'Webhook模板应为JSON对象' }; }
		catch (e) { return { error: 'Webhook模板不是有效JSON' }; }
	}
	if (result.smtp && (!match(result.host,/^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$/) || result.port < 1 || result.port > 65535 || result.port != int(result.port) ||
	    index(['tls','starttls'],result.tls) < 0 || !line(result.username,254) || !line(result.password,1024) || !email(result.from) || !email(result.to))) return { error: '请检查SMTP服务器、TLS方式、端口及收发邮箱' };
	if (result.sms && !phone(result.phone)) return { error: '目标手机号应为3至20位数字，可带+' };
	if (!line(result.keyword,128) || !line(result.blocked,512)) return { error: '过滤条件格式错误' };
	if (length(result.blocked) && length(filter(split(result.blocked,','), item => !phone(trim(item)))) > 0) return { error: '号码黑名单请用英文逗号分隔' };
	return { values: result };
}
function decode(hex) {
	if (!length(hex) || length(hex) % 4 || !match(hex,/^[0-9A-Fa-f]+$/)) return null;
	let out = '';
	for (let i=0; i<length(hex); i+=4) {
		let code=+('0x'+substr(hex,i,4));
		if (code >= 0xd800 && code <= 0xdbff) {
			let low=+('0x'+substr(hex,i+4,4));
			if (i+8>length(hex) || low<0xdc00 || low>0xdfff) return null;
			code=0x10000+(code-0xd800)*1024+(low-0xdc00); i+=4;
		}
		else if (code>=0xdc00 && code<=0xdfff) return null;
		if (code==0) return null;
		out+=uchr(code);
	}
	return out;
}
export function parse_sms(raw) {
	if (type(raw) != 'string' || !match(raw,/(^|\n)OK\s*$/) || match(raw,/(^|\n)(ERROR|\+CMS ERROR|\+CME ERROR)/)) return { error: '短信列表不完整' };
	let records=[], current=null;
	for (let line in split(replace(raw,'\r',''),'\n')) {
		let header=match(line,/^\+CMGL:\s*([0-9]+),"(REC READ|REC UNREAD|STO SENT|STO UNSENT)","([^"]*)","[^"]*","([^"]*)"\s*$/);
		if (header) { current={ index:+header[1], state:header[2], from:header[3], time:header[4], hex:'' }; push(records,current); }
		else if (match(line,/^\+CMGL:/)) return { error: '暂不识别该短信头格式' };
		else if (current && match(line,/^[0-9A-Fa-f]+$/)) current.hex+=line;
		else if (current && length(trim(line)) && trim(line)!='OK') return { error: '短信内容不是UCS2编码' };
	}
	let groups={}, messages=[], incomplete=0;
	for (let row in records) {
		if (index(['REC READ','REC UNREAD'],row.state)<0) continue;
		let sender=decode(row.from);
		if (sender != null && match(sender,/^\+?[0-9]+$/)) row.from=sender;
		let udh=match(row.hex,/^050003([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})/);
		let wide=match(row.hex,/^060804([0-9A-Fa-f]{4})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})/);
		let multipart=wide||udh;
		row.text=decode(substr(row.hex,multipart?(wide?14:12):0));
		if (row.text==null) return { error: '短信UCS2数据无效' };
		if (!multipart) { push(messages,row); continue; }
		let total=+('0x'+multipart[2]), part=+('0x'+multipart[3]);
		if (total<1 || total>32 || part<1 || part>total) return { error: '长短信分片信息无效' };
		let key=row.from+'|'+substr(row.time,0,8)+'|'+uc(multipart[1])+'|'+total;
		let group=groups[key] ||= { from:row.from, time:row.time, total, parts:{}, invalid:false };
		if (group.parts[part] && group.parts[part].text != row.text) group.invalid=true;
		group.parts[part]=row;
	}
	for (let key, group in groups) {
		if (group.invalid || length(keys(group.parts)) != group.total) { incomplete++; continue; }
		let text='';
		for (let part=1; part<=group.total; part++) text+=group.parts[part].text;
		push(messages,{ from:group.from,time:group.parts[1].time,text,index:group.parts[1].index });
	}
	return { messages,incomplete };
}
export function eligible(config,message) {
	let origin=replace(message.from,/^\+/,'');
	if (length(filter(split(config.blocked,','), number => replace(trim(number),/^\+/,'')==origin))) return false;
	return !length(config.keyword) || index(message.text,config.keyword)>=0;
}
export function webhook_body(config,message) {
	let fields={ from:message.from,text:message.text,time:message.time,device:message.device };
	function render(value) {
		if (type(value)=='string') return replace(value,/\{(from|text|time|device)\}/g, (full,name) => fields[name] || '');
		if (type(value)=='array') return map(value,render);
		if (type(value)=='object') { let out={}; for(let key,item in value) out[key]=render(item); return out; }
		return value;
	}
	return render(json(config.body));
}
export function service_ok(provider,raw) {
	if (provider=='json') return true; // Generic endpoint: HTTP 2xx is its contract.
	let data;
	try { data=json(raw); } catch(e) { return false; }
	if (provider=='wecom' || provider=='dingtalk') return type(data?.errcode)=='int' && data.errcode==0;
	if (provider=='telegram') return data?.ok===true;
	return type(data?.code)=='int' && data.code==200;
}
export function sms_parts(message) {
	let text='['+message.from+'] '+message.text;
	let units=[];
	// Decode UTF-8 bytes explicitly; ucode strings and ord() are byte based.
	for(let i=0;i<length(text);i++) {
		let c=ord(text,i), n=c<128?0:c>=0xc2&&c<=0xdf?1:c>=0xe0&&c<=0xef?2:c>=0xf0&&c<=0xf4?3:-1;
		if(n<0 || i+n>=length(text)) return null;
		let code=n==0?c:c&((1<<(6-n))-1);
		for(let j=1;j<=n;j++){let b=ord(text,i+j);if(b<128||b>191)return null;code=code*64+(b&63);}
		if((n==1&&code<128)||(n==2&&code<2048)||(n==3&&code<65536)||code>0x10ffff||(code>=0xd800&&code<=0xdfff))return null;
		i+=n;
		push(units,code>0xffff?sprintf('%04X%04X',0xd800+((code-0x10000)>>10),0xdc00+((code-0x10000)&1023)):sprintf('%04X',code));
	}
	let parts=[],part='';
	for(let unit in units){if(length(part)+length(unit)>240){push(parts,part);part='';}part+=unit;}
	if(length(part))push(parts,part);
	if(length(parts)>20)return null;
	if(length(parts)>1) for(let i=0;i<length(parts);i++){
		let prefix='['+(i+1)+'/'+length(parts)+'] ', encoded='';
		for(let j=0;j<length(prefix);j++)encoded+=sprintf('%04X',ord(prefix,j));
		parts[i]=encoded+parts[i];
	}
	return parts;
}
