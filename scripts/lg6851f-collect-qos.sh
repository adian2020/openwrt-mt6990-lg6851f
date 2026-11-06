#!/bin/sh
# Diagnostic only: ql-netd list/APN/QoS getters and sample_nw registration.
# No create/start/stop/config setter, no interface restart, no polling.
set -u
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in
fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '不支持此设备'; exit 95 ;; esac
command -v ucode >/dev/null || { echo '缺少 ucode'; exit 2; }
[ ! -e /tmp/lg6851f-modem-control.active ] || { echo '模组控制正在进行，请稍后重试'; exit 75; }
umask 077
probe_dir="$(mktemp -d /tmp/lg6851f-qos.XXXXXX)" || exit 5
locked=0
cleanup() {
	if [ "$locked" = 1 ]; then sleep 6; flock -u 9; fi
	rm -f "$probe_dir/probe.uc"
	rmdir "$probe_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
exec 9>/var/lock/luci-modem5g-control.lock
flock -n 9 || { echo '模组通道忙，请稍后重试'; exit 75; }
locked=1

cat > "$probe_dir/probe.uc" <<'UCODE'
'use strict';
import { connect, error } from 'ubus';
import { cursor } from 'uci';

let report = { probe_version: 1, at: time(), requests: [], call_list: [], qos: null };
function finish(reason, code) {
	report.status = reason;
	printf('%J\n', report);
	exit(code);
}
function hex(data) {
	let result = '';
	for (let i = 0; i < length(data); i++) result += sprintf('%02x', ord(data, i));
	return result;
}
function u32(data, offset) {
	if (offset < 0 || offset + 4 > length(data)) return null;
	return ord(data, offset) + ord(data, offset+1) * 256 + ord(data, offset+2) * 65536 + ord(data, offset+3) * 16777216;
}
function stringz(data) { return split(data, chr(0))[0]; }
let bus = connect('/var/run/ubus/ubus.sock', 5);
if (!bus) finish('UBUS_CONNECT_FAILED', 5);
let network = bus.call('network.interface.modem5g', 'status');
let cid = network?.data?.cid;
if (!network?.up || +network.uptime < 30) finish('NETWORK_NOT_SETTLED', 11);
if (!match('' + cid, /^[0-9]{1,2}$/) || +cid > 20) finish('INVALID_ACTIVE_CID', 22);
cid = +cid;
let config = cursor();
config.load('network');
let expected_apn = config.get('network', 'modem5g', 'apn');
report.network = { cid, device: network.l3_device, expected_apn };

function request(id, argument) {
	// Native ucode appends one string terminator. Three bytes plus that NUL
	// are exactly the SDK's four-byte little-endian input, including zeros.
	if (index([8,12,13], id) < 0 || argument < 0 || argument > 20) finish('INVALID_READ_REQUEST', 22);
	let data = chr(argument) + chr(0) + chr(0);
	let response = bus.call('ql-netd', 'datacall', { id, len: 4, data });
	let row = { command: id, argument, expected_request_hex: hex(data) + '00',
		cmd: response?.cmd, result: response?.result, data_len: response?.data_len,
		received_bytes: type(response?.data) == 'string' ? length(response.data) : null,
		data_hex: type(response?.data) == 'string' ? hex(response.data) : null };
	push(report.requests, row);
	if (!response) { row.ubus_error = error(); return null; }
	if (response.cmd != id || response.result == null || response.result != 0 ||
	    type(response.data_len) != 'int' || response.data_len < 0 || response.data_len > 1024 || type(response.data) != 'string') return null;
	let bytes = response.data;
	// Native ubus removes one trailing byte from STRING fields. Do not invent
	// that byte: decode only complete leading fields and preserve actual hex.
	if (length(bytes) == response.data_len - 1) row.omitted_final_byte = true;
	else if (length(bytes) != response.data_len) return null;
	return { data: bytes, declared_length: response.data_len };
}

let list = request(8, 0);
if (list == null || length(list.data) < 4) finish('SDK_LIST_READ_FAILED', 5);
let count = u32(list.data, 0);
if (count > 28 || list.declared_length < 4 + 36 * count || length(list.data) < 4 + 36 * count - 1) finish('SDK_LIST_LAYOUT_UNCONFIRMED', 5);
for (let i = 0; i < count; i++) {
	let offset = 4 + 36 * i;
	push(report.call_list, { id: u32(list.data, offset), name: stringz(substr(list.data, offset+4, 32)) });
}
if (!length(filter(report.call_list, row => row.id == cid))) finish('ACTIVE_CID_NOT_IN_SDK_LIST', 95);

let apn = request(12, cid);
if (apn == null || apn.declared_length < 151 || length(apn.data) < 150 || ord(apn.data, 0) != 1 || index(substr(apn.data, 1), chr(0)) < 0) finish('SDK_APN_UNCONFIRMED', 5);
report.sdk_apn = stringz(substr(apn.data, 1, 150));
if (type(expected_apn) != 'string' || !length(expected_apn) || lc(report.sdk_apn) != lc(expected_apn))
	finish('SDK_APN_DIFFERS_FROM_ACTIVE_CONFIG', 95);

let qos = request(13, cid);
if (qos == null || qos.declared_length != 24 || length(qos.data) < 23) finish('QOS_READ_OR_LAYOUT_UNCONFIRMED', 5);
let class_id = u32(qos.data, 0);
let after = bus.call('network.interface.modem5g', 'status');
if (!after?.up || after.data?.cid == null || +after.data.cid != cid || after.l3_device != network.l3_device || +after.uptime < +network.uptime)
	finish('DATA_CONNECTION_CHANGED_DURING_READ', 75);
if (class_id == null || class_id < 1 || class_id > 255) finish('QOS_CLASS_UNAVAILABLE', 5);
report.qos = { class_id, source: 'ql_data_call_get_qos_info', cid, apn: report.sdk_apn,
	bandwidth_fields: '保留十六进制原值，尚未验证单位；不替换已确认的网络/IMS AMBR' };
finish('QOS_CLASS_READ', 0);
UCODE

timeout 30 ucode "$probe_dir/probe.uc"
probe_rc=$?
sleep 6
if [ "$probe_rc" != 11 ] && [ -x /usr/bin/sample_nw ]; then
	printf '\n=== 厂商当前数据注册状态（只读第7项） ===\n'
	printf '0\n7\n1\n-1\n' | timeout 20 /usr/bin/sample_nw |
		awk '/^Cmd Index=|ql_nw_init,.*ret|ql_nw_release success|radio_tech[[:space:]]*=|reg_state[[:space:]]*=|tech_domain[[:space:]]*=|\):ret=/ { print }'
fi
exit "$probe_rc"
