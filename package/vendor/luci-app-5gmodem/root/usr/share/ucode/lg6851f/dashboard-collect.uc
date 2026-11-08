'use strict';
import { popen, readfile, glob } from 'fs';
import { cursor } from 'uci';
import * as dashboard from 'lg6851f.dashboard';
let deadline=0;
function quote(value){return "'"+replace(''+value,"'","'\\''")+"'";}
function capture(argv){
 if(time()>=deadline)return {code:124,output:''};
 let pipe=popen('/usr/bin/timeout 2 '+join(' ',map(argv,quote))+' 2>/dev/null','r');
 let output=pipe?.read?.('all')||'', code=pipe?.close?.();
 return {output,code:code ?? 5};
}
function read_json_command(argv){let r=capture(argv);try{return r.code==0?json(r.output):null;}catch(e){return null;}}
function network_state(){return read_json_command(['/bin/ubus','call','network.interface.modem5g','status']);}
function apn_values(){let u=cursor();u.load('network');let v=u.get_all('network','modem5g')||{};return {apn:v.apn||'',proto:v.proto,mtu:+(v.mtu||1500),password_set:!!v.password};}
export function parse_info(text){
 let channel=match(text,/Channel:\s*([0-9]+)/),frequency=match(text,/\(([0-9.]+) GHz\)/),power=match(text,/Tx-Power:\s*(-?[0-9.]+) dBm/);
 let mode=match(text,/HT Mode:\s*([^\r\n]+)/);
 return {channel:channel?+channel[1]:null,frequency:frequency?+frequency[1]*1000:null,txpower:power?+power[1]:null,width:mode?trim(mode[1]):null};
}
export function parse_clients(text){
 let rows=[],current=null;
 for(let line in split(text,'\n')){
  let head=match(line,/^([0-9A-Fa-f:]{17})\s+(-?[0-9]+) dBm/);
  if(head){current={mac:head[1],signal:+head[2]};push(rows,current);continue;}
  let rate=match(line,/^\s*(RX|TX):\s*([0-9.]+) (MBit|kBit)\/s/);
  if(current&&rate)current[rate[1]=='RX'?'rx':'tx']={rate:+rate[2]*(rate[3]=='MBit'?1000:1)};
 }
 return {results:rows};
}
// 只匹配mDNS主机记录里的真实地址，不用服务名或MAC猜机型。
function has_address(value,address,depth){
 if(depth>4)return false;
 if(type(value)=='string')return value==address;
 if(type(value)=='array'){for(let v in value)if(has_address(v,address,depth+1))return true;}
 else if(type(value)=='object'){for(let k,v in value)if(has_address(v,address,depth+1))return true;}
 return false;
}
export function mdns_name(hosts,address){
 if(!address || type(hosts)!='object')return null;
 let found=null;
 for(let name,row in hosts){
  if(!has_address(row,address,0))continue;
  let n=replace(name,/\.local\.?$/i,'');
  if(!match(n,/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,252}$/))continue;
  if(found && lc(found)!=lc(n))return null;
  found=n;
 }
 return found;
}
export function collect(publish) {
	deadline=time()+18;
	let data = dashboard.snapshot();
	let previous=null;try{previous=json(readfile('/tmp/lg6851f-dashboard-v2.json')||'null');}catch(e){}
	if(previous?.boot_id!=trim(readfile('/proc/sys/kernel/random/boot_id')||''))previous=null;
	for(let k in ['network','lan','wireless','clients','leases','storage','ipv6_global'])if(previous?.[k]!=null)data[k]=previous[k];
	publish(data, "system");
	let current_network=network_state();if(current_network!=null)data.network=current_network;
	data.ipv6_global = dashboard.global_ipv6(data.network);
	data.apn = apn_values();
	if(data.network?.up && data.network?.data?.apn != null)data.apn.apn=data.network.data.apn;
	let current_lan=read_json_command([ '/bin/ubus', 'call', 'network.interface.lan', 'status' ]);if(current_lan!=null)data.lan=current_lan;
	let wireless = read_json_command([ '/bin/ubus', 'call', 'network.wireless', 'status' ]);
	publish(data, "network");
	let next_wireless=[],next_clients=[],clients_ok=true;
	for (let radio, entry in wireless || {}) {
		for (let iface in entry.interfaces || []) {
			if (length(next_wireless) >= 8) break;
			let dev = iface.ifname;
			if (!dev || !match(dev, /^[A-Za-z0-9_.:-]{1,15}$/)) continue;
			// Do not call rpcd's own iwinfo object from its request path.
			let raw_info=capture(['/usr/bin/iwinfo',dev,'info']);
			let info=raw_info.code==0?parse_info(raw_info.output):null;
			let old=filter(previous?.wireless||[],w=>w.device==dev)[0];
			push(next_wireless, { radio, device: dev, up: entry.up, ssid: iface.config?.ssid || info?.ssid,
				channel: info?.channel ?? old?.channel, frequency: info?.frequency ?? old?.frequency, txpower: info?.txpower ?? old?.txpower,
				width: info?.width ?? old?.width,
				country: info?.country || entry.config?.country, encryption: iface.config?.encryption,
				hidden: !!+iface.config?.hidden, information_available: info != null });
			let raw_clients=capture(['/usr/bin/iwinfo',dev,'assoclist']);
			let clients=raw_clients.code==0?parse_clients(raw_clients.output):null;if(clients==null)clients_ok=false;
			for (let row in clients?.results || [])
				push(next_clients, { device: dev, mac: row.mac, signal: row.signal,
					rx_kbit: row.rx?.rate, tx_kbit: row.tx?.rate, connected: row.connected_time });
		}
	}
	if(wireless!=null){data.wireless=next_wireless;if(clients_ok)data.clients=next_clients;data.wireless_updated=time();data.wireless_error=!clients_ok;}else data.wireless_error=true;
	publish(data, "wireless");
	let lease_text=readfile('/tmp/dhcp.leases');
	if(lease_text!=null)data.leases = [];
	for (let line in split(trim(lease_text || ''), '\n')) {
		let fields = split(line, /\s+/);
		if (length(fields) >= 4) push(data.leases, { expires: +fields[0], mac: fields[1], address: fields[2], hostname: fields[3]=='*'?null:fields[3] });
	}
	let hints=read_json_command(['/bin/ubus','-t','2','call','luci-rpc','getHostHints']);
	for(let l in data.leases||[])if(!l.hostname){let h=hints?.[lc(l.mac||'')]||hints?.[uc(l.mac||'')];if(h?.name && h.name!='*')l.hostname=h.name;else {let old=filter(previous?.leases||[],x=>lc(x.mac)==lc(l.mac))[0];if(old?.hostname && old.hostname!='*')l.hostname=old.hostname;}}
	let cfg=cursor();cfg.foreach('dhcp','host',h=>{
	 let macs=type(h.mac)=='array'?h.mac:split(h.mac||'',/\s+/);
	 for(let l in data.leases||[])if(!l.hostname && h.name && h.name!='*' && index(map(macs,m=>lc(m)),lc(l.mac||''))>=0)l.hostname=h.name;
	});
	// 发现操作只在后台执行，每分钟发起一次刷新；不写入静态租约。
	data.mdns_requested_at=previous?.mdns_requested_at||0;
	if(time()-data.mdns_requested_at<0 || time()-data.mdns_requested_at>=60){
	 if(read_json_command(['/bin/ubus','-t','2','call','umdns','update'])!=null)data.mdns_requested_at=time();
	}
	let mdns=read_json_command(['/bin/ubus','-t','2','call','umdns','hosts','{"array":true}']);
	for(let l in data.leases||[])if(!l.hostname){let name=mdns_name(mdns,l.address);if(name){l.hostname=name;l.hostname_source='mdns';}}
	let storage = capture([ '/bin/df', '-Pk', '/overlay' ], 5);
	let rows = split(trim(storage.output), '\n');
	let columns = split(trim(rows[length(rows) - 1] || ''), /\s+/);
	if(storage.code == 0 && length(columns) >= 6)data.storage = {
		device: columns[0], total: +columns[1] * 1024, used: +columns[2] * 1024,
		available: +columns[3] * 1024, percent: +replace(columns[4], '%', ''), mount: '/overlay'
	};
	data.usb = map(glob('/sys/class/udc/*') || [], path => ({ controller: replace(path, /^.*\//, ''), state: trim(readfile(path + '/state') || '') }));
	data.cache_age = data.modem.updated == null ? null : time() - data.modem.updated;
	data.cached_modem_stale = data.cache_age == null || data.cache_age < 0 || data.cache_age > 180;
	publish(data, "complete");
	return data;
}
