'use strict';
'require view';
'require rpc';
'require poll';
'require ui';
'require modem5g.common_v5 as common';
'require modem5g.cellular_v3 as cellular';

const getStatus = rpc.declare({
	object: 'luci.modem5g', method: 'get_cell_status', params: ['refresh'], expect: {}
});

function value(input, unit = '') {
	return input == null || input === '' ? '未获取' : String(input) + unit;
}

function addresses(network, key) {
	return (network?.[key] || []).map(row => row.address + '/' + row.mask).join('、');
}

function table(rows) {
	if (!rows.length)
		return E('p', {class: 'm5-note'}, '等待模组返回小区测量');
	return E('div', {style: 'overflow-x:auto'}, E('table', {class: 'm5-cell-table'}, [
		E('thead', E('tr', ['小区', '频段', 'ARFCN', 'PCI', 'RSRP', 'RSRQ', 'SINR'].map(name => E('th', name)))),
		E('tbody', rows.map(row => E('tr', {class: row.serving ? 'm5-serving' : ''}, [
			E('td', row.serving ? '服务小区' : '邻区'),
			E('td', row.band),
			...['arfcn', 'pci', 'rsrp', 'rsrq', 'sinr'].map(key => E('td', value(row[key])))
		])))
	]));
}

function bandsText(bands) {
	const current = cellular.lockMasks(bands?.output).current;
	if (!current)
		return '等待原生频段读回';
	const lte = current.lte.map(band => 'B' + band).join('、');
	const nr = current.nr.map(band => 'n' + band).join('、');
	return (bands.stale ? '上次读回 · ' : '') + 'LTE ' + value(lte) + ' / NR ' + value(nr);
}

return view.extend({
	load() { return getStatus(true); },
	update(data) {
		const cells = data.cells;
		const rows = cellular.parseCells(cells?.serving);
		const serving = cells?.stale ? null : rows.find(row => row.serving);
		const signal = serving || data.signal_sample;
		const net = data.network;
		const lock = data.lock_record;
		const measured = serving ? '服务小区测量' : signal ? '模组信号缓存 · ' + signal.age + ' 秒前' : '等待信号采样';
		const cellAge = cells?.updated ? (cells.stale ? ' · 上次有效测量' : ' · ' + cells.age + ' 秒前') : '';
		this.result.textContent = !data.available ? '模组接口未就绪' :
			data.queued ? '已请求后台刷新' : data.initializing ? '等待蜂窝状态采集' : '小区测量' + cellAge;
		this.content.replaceChildren(
			common.panel('蜂窝状态', E('div', {class: 'm5-grid'}, [
				common.metric('制式', data.rat),
				common.metric('运营商', data.operator),
				common.metric('驻网', data.registration),
				common.metric('SIM 状态', data.sim),
				common.metric('连接', net?.up ? '已连接' : '未连接'),
				common.metric('IPv4', addresses(net, 'ipv4-address')),
				common.metric('IPv6', addresses(net, 'ipv6-address'))
			])),
			common.panel(measured, E('div', {class: 'm5-grid'}, [
				common.metric('RSRP', value(signal?.rsrp, ' dBm')),
				common.metric('RSRQ', value(signal?.rsrq, ' dB')),
				common.metric('SINR', value(signal?.sinr, ' dB'))
			])),
			common.panel('服务小区与邻区', table(rows)),
			common.panel('锁定读回', E('div', [
				E('p', bandsText(data.bands)),
				lock?.mode === 'cell' ? E('p', '本次启动验证的驻留目标 · ARFCN ' +
					value(lock.arfcn) + ' · PCI ' + value(lock.pci)) : null,
				E('a', {class: 'btn', href: L.url('admin', 'modem5g', 'lock')}, '打开网络锁定')
			]))
		);
	},
	render(data) {
		this.result = E('p', {role: 'status'});
		this.content = E('div');
		this.update(data);
		const refresh = ui.createHandlerFn(this, () => getStatus(true).then(result => this.update(result)));
		this.pollStatus = () => document.hidden ? null : getStatus(true).then(result => this.update(result));
		poll.add(this.pollStatus, 15);
		return E('div', {class: 'm5-page'}, [
			common.style(),
			E('h2', '状态与小区'),
			E('button', {type: 'button', class: 'btn', click: refresh}, '刷新信号和小区'),
			this.result, this.content
		]);
	},
	unload() { if (this.pollStatus) poll.remove(this.pollStatus); },
	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
