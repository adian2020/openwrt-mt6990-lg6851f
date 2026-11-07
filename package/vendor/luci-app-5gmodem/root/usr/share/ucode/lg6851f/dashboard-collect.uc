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
 return {output,code:code||0};
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
export function collect(publish) {
	deadline=time()+18;
	let data = dashboard.snapshot();
	publish(data, "system");
	data.network = network_state();
	data.ipv6_global = dashboard.global_ipv6(data.network);
	data.apn = apn_values();
	if(data.network?.up && data.network?.data?.apn != null)data.apn.apn=data.network.data.apn;
	data.lan = read_json_command([ '/bin/ubus', 'call', 'network.interface.lan', 'status' ]);
	let wireless = read_json_command([ '/bin/ubus', 'call', 'network.wireless', 'status' ]);
	publish(data, "network");
	data.wireless = []; data.clients = [];
	for (let radio, entry in wireless || {}) {
		for (let iface in entry.interfaces || []) {
			if (length(data.wireless) >= 8) break;
			let dev = iface.ifname;
			if (!dev || !match(dev, /^[A-Za-z0-9_.:-]{1,15}$/)) continue;
			// Do not call rpcd's own iwinfo object from its request path.
			let raw_info=capture(['/usr/bin/iwinfo',dev,'info']);
			let info=raw_info.code==0?parse_info(raw_info.output):null;
			push(data.wireless, { radio, device: dev, up: entry.up, ssid: iface.config?.ssid || info?.ssid,
				channel: info?.channel, frequency: info?.frequency, txpower: info?.txpower,
				width: info?.width,
				country: info?.country || entry.config?.country, encryption: iface.config?.encryption,
				hidden: !!+iface.config?.hidden, information_available: info != null });
			let raw_clients=capture(['/usr/bin/iwinfo',dev,'assoclist']);
			let clients=raw_clients.code==0?parse_clients(raw_clients.output):null;
			for (let row in clients?.results || [])
				push(data.clients, { device: dev, mac: row.mac, signal: row.signal,
					rx_kbit: row.rx?.rate, tx_kbit: row.tx?.rate, connected: row.connected_time });
		}
	}
	publish(data, "wireless");
	data.leases = [];
	for (let line in split(trim(readfile('/tmp/dhcp.leases') || ''), '\n')) {
		let fields = split(line, /\s+/);
		if (length(fields) >= 4) push(data.leases, { expires: +fields[0], mac: fields[1], address: fields[2], hostname: fields[3] });
	}
	let storage = capture([ '/bin/df', '-Pk', '/overlay' ], 5);
	let rows = split(trim(storage.output), '\n');
	let columns = split(trim(rows[length(rows) - 1] || ''), /\s+/);
	data.storage = storage.code == 0 && length(columns) >= 6 ? {
		device: columns[0], total: +columns[1] * 1024, used: +columns[2] * 1024,
		available: +columns[3] * 1024, percent: +replace(columns[4], '%', ''), mount: '/overlay'
	} : null;
	data.usb = map(glob('/sys/class/udc/*') || [], path => ({ controller: replace(path, /^.*\//, ''), state: trim(readfile(path + '/state') || '') }));
	data.cache_age = data.modem.updated == null ? null : time() - data.modem.updated;
	data.cached_modem_stale = data.cache_age == null || data.cache_age < 0 || data.cache_age > 180;
	publish(data, "complete");
	return data;
}
