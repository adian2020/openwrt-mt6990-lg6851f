'use strict';
import { readfile, glob, basename } from 'fs';

// Independent read-only measurement layer. Fixture root is process environment,
// never a web request argument; no AT, shell, radio or hardware writes here.
const ROOT = getenv('LG6851F_DATA_ROOT') || '';
function text(path) { return trim(readfile(ROOT + path) || ''); }
function num(value) { return match('' + value, /^-?[0-9]+(\.[0-9]+)?$/) ? +value : null; }
function number(path) { return num(text(path)); }
function paths(pattern) { return map(glob(ROOT + pattern) || [], p => substr(p, length(ROOT))); }
export function cached() {
	let row = {};
	for (let line in split(text('/tmp/lg6851f-modem-status.state'), '\n')) {
		let n = index(line, '=');
		if (n > 0) row[substr(line, 0, n)] = substr(line, n + 1);
	}
	return row;
}
export function reading(name) {
	if (index(['cells', 'bands', 'radio-details'], name) < 0) return null;
	let data;
	try { data = json(text('/tmp/lg6851f-modem-' + name + '.json')); } catch (e) { return null; }
	let boot = text('/proc/sys/kernel/random/boot_id');
	if (!boot || type(data) != 'object' || data.boot_id != boot || num(data.updated) == null) return null;
	data.age = time() - data.updated;
	data.stale = data.age < 0 || data.age > 180;
	if(name=='cells' && data.serving){let r=reading('radio-details');if(r)data.serving.carriers=r.parsed?.carriers;}
	return data;
}
export function mask(value) {
	return !value ? null : length(value) > 7 ? substr(value, 0, 3) + '***' + substr(value, -3) : '***';
}
export function ticks(line) {
	let fields = split(trim(line), /\s+/), total = 0;
	if (fields[0] != 'cpu' || length(fields) < 5) return null;
	for (let i = 1; i < length(fields) && i <= 8; i++) total += +fields[i];
	return { total, idle: +fields[4] + +(fields[5] || 0) };
}
export function cpu_percent(previous, current) {
	if (!previous || !current || current.total <= previous.total || current.idle < previous.idle) return null;
	let value = 100.0 * (1.0 - 1.0 * (current.idle - previous.idle) / (current.total - previous.total));
	return value >= 0 && value <= 100 ? value : null;
}
export function traffic_delta(previous, current) {
	if (!previous || !current || previous.boot_id != current.boot_id || previous.device != current.device ||
	    current.at <= previous.at || current.rx == null || current.tx == null ||
	    previous.rx == null || previous.tx == null || current.rx < previous.rx || current.tx < previous.tx) return null;
	let seconds = current.at - previous.at;
	return { rx: 1.0 * (current.rx - previous.rx) / seconds, tx: 1.0 * (current.tx - previous.tx) / seconds };
}
export function rate_sample(device) {
	if (type(device) != 'string' || !match(device, /^[A-Za-z0-9_.:-]{1,15}$/) || device == '..') return null;
	let at = num(split(text('/proc/uptime'), /\s+/)[0]);
	return { device, at, boot_id: text('/proc/sys/kernel/random/boot_id'),
		rx: number('/sys/class/net/' + device + '/statistics/rx_bytes'),
		tx: number('/sys/class/net/' + device + '/statistics/tx_bytes'),
		cpu: ticks(split(text('/proc/stat'), '\n')[0]) };
}
export function global_ipv6(network) {
	return map(filter(network?.['ipv6-address'] || [], row =>
		row.address && match(row.address, /^[23][0-9a-f]*:/i)), row => row.address + '/' + row.mask);
}
export function boot_slot(cmdline) {
 let root=match(cmdline || '', /(^|\s)root=\/dev\/mmcblk0p(26|39)(\s|$)/);
 let suffix=match(cmdline || '', /(^|\s)(androidboot\.)?slot_suffix=_?([ab])(\s|$)/);
 let actual=root ? (root[2]=='26'?'A':'B') : null;
 let declared=suffix ? uc(suffix[3]) : null;
 return actual && declared && actual!=declared ? null : actual || declared;
}
export function ims_registration(value) {
	// TS 27.007 8.71: ext_info is HEX, not a decimal status or a VoNR switch.
	let m=match(value || '', /^\+CIREG:\s*([0-2])\s*,\s*([01])(\s*,\s*([0-9a-fA-F]{1,8}))?\s*$/);
	if(!m)return null;
	let registered=m[2]=='1', caps=registered && m[4]!=null ? int(m[4],16) : null;
	return {registered, capabilities:caps,
		voice:!registered ? false : caps==null ? null : !!(caps&1),
		sms:!registered ? false : caps==null ? null : !!(caps&4)};
}
export function snapshot() {
	let memory = {};
	for (let line in split(text('/proc/meminfo'), '\n')) {
		let m = match(line, /^(MemTotal|MemAvailable|MemFree|Buffers|Cached):\s+(\d+)/);
		if (m) memory[m[1]] = +m[2] * 1024;
	}
	let total = memory.MemTotal, available = memory.MemAvailable;
	let temperatures = [], frequencies = [];
	for (let dir in paths('/sys/class/thermal/thermal_zone*')) {
		let value = number(dir + '/temp');
		if (value != null) push(temperatures, { source: dir, name: text(dir + '/type'), celsius: value / 1000.0, kind: 'thermal' });
	}
	for (let dir in paths('/sys/class/hwmon/hwmon*')) {
		for (let path in paths(dir + '/temp*_input')) {
			let value = number(path);
			if (value != null) push(temperatures, { source: path, name: text(dir + '/name'), label: text(replace(path, /_input$/, '_label')), celsius: value / 1000.0, kind: 'hwmon' });
		}
	}
	// 仅使用标准policy接口；本机实测读取debugfs clk_summary会卡死重启，
	// 不得用全量时钟摘要或调试节点作为缺失频率的回退。
	for (let dir in paths('/sys/devices/system/cpu/cpufreq/policy*')) {
		let current = number(dir + '/scaling_cur_freq'), max = number(dir + '/cpuinfo_max_freq');
		push(frequencies, { policy: basename(dir), current_mhz: current == null ? null : current / 1000.0,
			maximum_mhz: max == null ? null : max / 1000.0 });
	}
	let power_supplies = [];
	for (let dir in paths('/sys/class/power_supply/*'))
		push(power_supplies, { name: basename(dir), type: text(dir + '/type'), status: text(dir + '/status'), capacity: number(dir + '/capacity'),
			online: number(dir + '/online'), voltage_uv: number(dir + '/voltage_now'), current_ua: number(dir + '/current_now') });
	let identity = cached();
	let ims=ims_registration(identity.IMS_CIREG);
	if(ims){ims.updated=num(identity.IMS_UPDATED);ims.age=ims.updated==null ? null : time()-ims.updated;ims.stale=ims.age==null || ims.age<0 || ims.age>600;}
	let radio_details = reading('radio-details'), details = radio_details?.parsed;
	let operators = { '46000': '中国移动', '46002': '中国移动', '46007': '中国移动',
		'46001': '中国联通', '46006': '中国联通', '46009': '中国联通',
		'46003': '中国电信', '46005': '中国电信', '46011': '中国电信' };
	let usage = total && available != null && available <= total ? total - available : null;
	return {
		hostname: text('/proc/sys/kernel/hostname'), model: text('/tmp/sysinfo/model'), board: text('/tmp/sysinfo/board_name'),
		current_slot: boot_slot(text('/proc/cmdline')),
		firmware_id: text('/etc/mt6990-firmware-id'), release: text('/etc/openwrt_release'),
		uptime: num(split(text('/proc/uptime'), /\s+/)[0]),
		cpu_ticks: ticks(split(text('/proc/stat'), '\n')[0]),
		memory: { total, available, used: usage, percent: usage != null ? 100.0 * usage / total : null },
		temperatures, frequencies, power_supplies,
		network_defaults: { ipv4_ttl: number('/proc/sys/net/ipv4/ip_default_ttl'), ipv6_hop_limit: number('/proc/sys/net/ipv6/conf/default/hop_limit') },
		conntrack: { count: number('/proc/sys/net/netfilter/nf_conntrack_count'), maximum: number('/proc/sys/net/netfilter/nf_conntrack_max'), kind: 'linux-conntrack' },
		modem: { rat: identity.RAT || null, rat_raw: identity.RAT_RAW || null, ims,
			operator: operators[identity.OPERATOR] || identity.OPERATOR || null,
			plmn: identity.OPERATOR || null, sim: identity.SIM || null, registered: identity.REGISTERED == 'YES',
			radio: identity.RADIO || null, rsrp: num(identity.RSRP), rsrq: num(identity.RSRQ), sinr: num(identity.SINR),
			updated: num(identity.UPDATED), imei: mask(identity.IMEI), imsi: mask(identity.IMSI), iccid: mask(identity.ICCID),
			model: identity.MODEM_MODEL || null, firmware: identity.MODEM_FIRMWARE || null, phone: mask(identity.PHONE),
			roaming: identity.ROAMING == '1' ? '是' : identity.ROAMING == '0' ? '否' : null },
		advanced: { ca: details?.carriers || null,
			mcs: details ? map(details.carriers || [], row => ({ type: row.type, dl: row.dl_mcs, ul: row.ul_mcs })) : null,
			qci: null, ambr: details?.ambr || null, endc: details?.endc || null, sa_nsa: details?.sa_nsa || null, ppe: null },
		radio_details,
		cells: reading('cells'), bands: reading('bands'),
		capabilities: { apn: true, band_lock: true, cell_lock: true, sms: true, at: true,
			cpu_frequency_read: length(frequencies) > 0, cpu_voltage_write: false, sim_switch: false, sim_slots: 1, android_switch: false,
			usb_role_write: false, battery_control: false, ttl_write: false, sms_forward: false }
	};
}
