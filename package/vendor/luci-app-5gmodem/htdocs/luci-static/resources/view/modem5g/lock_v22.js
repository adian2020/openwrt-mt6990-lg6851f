'use strict';
/* Shared ECELL parsing and actual current/supported mask readback. */
'require view';
'require rpc';
'require ui';
'require poll';
'require modem5g.mu_v1 as M';
'require modem5g.common_v5 as common';
'require modem5g.cellular_v3 as cellular';

const getLocks = rpc.declare({ object: 'luci.modem5g', method: 'get_locks', expect: {} });
const getLockCache = rpc.declare({ object: 'luci.modem5g', method: 'get_lock_cache', params: [ 'refresh' ], expect: {} });
const getLockRequest = rpc.declare({ object: 'luci.modem5g', method: 'get_lock_request', params: ['request_id'], expect: {} });
const getCells = rpc.declare({ object: 'luci.modem5g', method: 'get_cells', expect: {} });
const setBands = rpc.declare({ object: 'luci.modem5g', method: 'set_band_lock', params: [ 'lte', 'nr' ] });
const resetBands = rpc.declare({ object: 'luci.modem5g', method: 'reset_band_lock' });
const setCell = rpc.declare({ object: 'luci.modem5g', method: 'set_cell_lock', params: [ 'arfcn', 'pci', 'rat', 'band' ] });
const clearCell = rpc.declare({ object: 'luci.modem5g', method: 'clear_cell_lock' });

const getDashboard=rpc.declare({object:'luci.modem5g',method:'get_dashboard',expect:{}});
const setMode=rpc.declare({object:'luci.modem5g',method:'set_network_mode',params:['mode']});
const getFairQos=rpc.declare({object:'luci.modem5g',method:'get_fair_qos',expect:{}});
const setFairQos=rpc.declare({object:'luci.modem5g',method:'set_fair_qos',params:['enabled']});
const setRoaming=rpc.declare({object:'luci.modem5g',method:'set_data_roaming',params:['enabled']});
const LTE = [ 1, 3, 5, 7, 8, 20, 28, 32, 38, 40, 41, 42, 43 ];
const NR = [ 1, 3, 5, 7, 8, 20, 28, 38, 40, 41, 75, 76, 77, 78 ];

function checks(id, prefix, values) {
	const check = v => {
		const label=E('label', { 'class': 'm5-band' }, [
			E('input', { type: 'checkbox', value: v, change: function() {
				this.closest('label').classList.toggle('is-selected', this.checked);
				this.dispatchEvent(new CustomEvent('modem-bands-edited', {bubbles:true}));
			} }),
			E('span', {}, `${prefix}${v}`)
		]);
		if(prefix==='n'&&v===76){label.querySelector('input').disabled=true;label.title='模组支持，但厂商工具不接受手动设置；使用恢复默认保留该频段';}
		return label;
	};
	return E('div', { id: id, 'class': 'm5-band-grid' }, values.map(check));
}

function selected(id) {
	return Array.from(document.querySelectorAll(`#${id} input:checked:not(:disabled)`)).map(el => +el.value);
}

function setChecked(id, values) {
	let wanted = new Set(values.map(Number));
	document.querySelectorAll(`#${id} input`).forEach(el => {
		el.checked = wanted.has(+el.value);
		el.closest('label').classList.toggle('is-selected', el.checked);
	});
}

function sameBands(actual, wanted) {
	return actual.length == wanted.length && actual.every((v, i) => v == wanted[i]);
}

function parsedLockState(result) {
	let raw = common.resultText(result), masks = cellular.lockMasks(raw);
	let state = { raw, lte: masks.current?.lte || [], nr: masks.current?.nr || [], supported: masks.supported };
	let saved = raw.match(/SAVED_LOCK_STATE[\s\S]*?MODE=([^\r\n]+)/);
	state.mode = saved ? saved[1].trim() : 'unknown';
	for (let key of [ 'STATUS', 'RAT', 'ARFCN', 'PCI', 'BAND', 'OP_ID', 'PHASE', 'RESULT_CODE', 'NETWORK' ]) {
		let m = raw.match(new RegExp(`^${key}=([^\\r\\n]+)`, 'm'));
		if (m) state[key.toLowerCase()] = m[1].trim();
	}
	if (!state.lte.length) {
		let requested = raw.match(/^LTE=([0-9,]+)$/m);
		if (requested) state.lte = requested[1].split(',').map(Number);
	}
	if (!state.nr.length) {
		let requested = raw.match(/^NR=([0-9,]+)$/m);
		if (requested) state.nr = requested[1].split(',').map(Number);
	}
	return state;
}

const parseCells = result => cellular.parseCells(result);

function candidateTable(rows) {
	if (!rows.length) return E('p', { 'class': 'm5-note' }, _('No cell measurements are currently available.'));
	return E('div', { 'class': 'm5-table-scroll' }, E('table', { 'class': 'm5-cell-table' }, [
		E('thead', {}, E('tr', {}, [ _('Type'), _('Band'), _('ARFCN'), _('PCI'), _('RSRP'), _('RSRQ'), _('SINR'), '操作' ].map(x => E('th', {}, x)))),
		E('tbody', {}, rows.map(r => E('tr', { 'class': r.serving ? 'm5-serving' : '', click: function() {
			document.getElementById('m5-lock-arfcn').value = r.arfcn;
			document.getElementById('m5-lock-pci').value = r.pci;
			document.getElementById('m5-lock-rat').value = r.rat;
			document.getElementById('m5-lock-rat').dispatchEvent(new Event('change'));
			document.getElementById('m5-lock-band').value = r.bandNo || '';
			document.getElementById('m5-lock-result').textContent =
				_('Cell selected: %s / PCI %s. It has not been applied yet.').format(r.arfcn, r.pci);
		} }, [
			E('td', {}, r.serving ? _('Serving') : _('Neighbor')), E('td', {}, r.band), E('td', {}, r.arfcn), E('td', {}, r.pci),
			E('td', {}, r.rsrp == null ? '-' : `${r.rsrp} dBm`), E('td', {}, r.rsrq == null ? '-' : `${r.rsrq} dB`),
			E('td', {}, r.sinr == null ? '-' : `${r.sinr} dB`), E('td',{},E('button',{type:'button','class':'mud-btn m5-lock-action',click:function(e){e.stopPropagation();this.closest('tr').click();this.dispatchEvent(new CustomEvent('modem-cell-apply',{bubbles:true}));}},'锁定'))
		])))
	]));
}

return view.extend({
	busy: false,
	setSupported(supported) {
		const changed=JSON.stringify(this.supported)!==JSON.stringify(supported);
		this.supported = supported;
		for (const [rat,prefix] of [['lte','B'],['nr','n']]) {
			const target = document.getElementById(`m5-${rat}-bands`);
			if (target && changed && !this.dirty) target.replaceWith(checks(`m5-${rat}-bands`, prefix, (rat=='lte'?LTE:NR).filter(v=>supported[rat].includes(v))));
		}
		const note = document.getElementById('m5-supported-summary');
		if (note) note.textContent = '本机LTE 13个、NR 14个候选频段；n76为只读，恢复默认可保留该频段。';
		this.updateBandSelect();
	},
	updateBandSelect() {
		const rat = document.getElementById('m5-lock-rat')?.value || 'nr';
		const values = (rat == 'lte' ? LTE : NR).filter(v=>!this.supported||this.supported[rat].includes(v));
		const select = document.getElementById('m5-lock-band');
		const pci = document.getElementById('m5-lock-pci');
		if (pci) pci.max = rat == 'nr' ? 1007 : 503;
		const arfcn=document.getElementById('m5-lock-arfcn');if(arfcn)arfcn.min=rat=='nr'?1:0;
		if (select) select.replaceChildren(E('option', {value:''}, '请选择频段'), ...values.filter(v => rat != 'nr' || v != 76).map(v => E('option', {value:v}, (rat == 'lte' ? 'B' : 'n') + v)));
	},
	load() { return Promise.all([getLockCache(true),getDashboard(),getFairQos()]).then(([data,frame,qos])=>[data.bands||{},data.cells||{},data.refresh||{},frame,qos]); },
	updateDraft() {
		this.dirty=true;
		const target=document.getElementById('m5-band-draft');
		if(target)target.textContent='待应用：'+selected('m5-lte-bands').map(v=>'B'+v).join(' ')+' · '+selected('m5-nr-bands').map(v=>'n'+v).join(' ')+'（尚未写入模组）';
	},
	async followRefresh() {
		const generation=++this.refreshGeneration;
		for(let attempt=0;attempt<35;attempt++){
			await new Promise(resolve=>window.setTimeout(resolve,2000));
			if(generation!==this.refreshGeneration||!document.getElementById('m5-lock-summary'))return;
			const data=await getLockCache(false);
			if(generation!==this.refreshGeneration)return;
			if(data.bands){
				document.getElementById('m5-lock-state').textContent=common.resultText(data.bands);
				this.syncLocks(data.bands);
			}
			if(data.refresh?.status==='complete'){
				document.getElementById('m5-lock-result').textContent='锁定状态已读取；当前已锁 LTE：'+(this.lockState?.lte.map(v=>'B'+v).join(' ')||'无')+' / NR：'+(this.lockState?.nr.map(v=>'n'+v).join(' ')||'无');
				return;
			}
			if(data.refresh?.status==='error')throw Error(data.refresh.output||'锁定状态读取失败，请重试');
		}
		throw Error('后台读取尚未完成，请稍后点击读取重试');
	},
	setBusyLegacy(active) {
		this.busy = active;
		document.querySelectorAll('.m5-lock-action').forEach(el => { el.disabled = active; });
		let state = document.getElementById('m5-lock-progress');
		if (state) state.textContent = active ? _('Modem operation in progress; please wait…') : _('Ready');
	},
	showResult(result, sync, verify, refresh) {
		document.getElementById('m5-lock-result').textContent = common.resultText(result);
		if (!result || +result.code != 0)
			throw new Error(common.resultText(result));
		return (refresh || getLocks)().then(state => {
			document.getElementById('m5-lock-state').textContent = common.resultText(state);
			this.syncLocks(state);
			if (verify && !verify(parsedLockState(state)))
				throw new Error(_('The modem did not report the requested lock state. The operation was not confirmed.'));
			sync?.();
			return state;
		});
	},
	waitForOperation(verify, requestId, sync) {
		let seenActive = false, inactiveAfterActive = 0, attempts = 0, shownVerified=false;
		const phases={queued:'任务已提交',waiting_recovery:'等待现有恢复任务结束',waiting_control:'等待模组控制通道',stopping_data:'暂停数据连接',applying_bands:'写入频段',verifying_bands:'回读验证频段',restoring_bands:'恢复默认频段',applying_cell:'写入小区锁定',verifying_cell:'核对实际服务小区',clearing_cell:'清除小区锁定',verified:'设置已读回确认',restoring_data:'恢复数据连接'};
		let poll = () => getLockRequest(requestId||'').then(state => {
			if(state.code)throw Error(state.error||common.resultText(state));
			const parsed=parsedLockState(state),matches=!verify||verify(parsed);
			if(requestId&&parsed.op_id===requestId){
				if(phases[parsed.phase])document.getElementById('m5-lock-progress').textContent=phases[parsed.phase];
				if(parsed.status==='accepted'&&parsed.phase==='verified')document.getElementById('m5-lock-progress').textContent='模组已接受清除请求';
				if(matches&&parsed.status==='verified'&&!shownVerified){
					shownVerified=true;this.dirty=false;this.syncLocks(state);sync?.();
					const setting=parsed.mode==='cell'?(parsed.rat==='lte'?'B':'n')+parsed.band+' / ARFCN '+parsed.arfcn+' / PCI '+parsed.pci:parsed.lte.map(v=>'B'+v).join(' ')+' · '+parsed.nr.map(v=>'n'+v).join(' ');
					document.getElementById('m5-lock-result').textContent='设置已读回验证：'+setting+'\n'+(phases[parsed.phase]||'正在完成操作');
				}
				if(parsed.phase==='failed'||parsed.phase==='complete'&&+parsed.result_code!==0)
					throw Error((shownVerified?'锁定设置已验证，但后续联网恢复失败。':'锁定操作未完成。')+'阶段：'+parsed.phase+'，退出码：'+parsed.result_code);
				if(parsed.phase==='complete'){
					if(matches)return state;
					throw Error('操作已结束，但读回结果与请求不一致');
				}
			}
			seenActive = seenActive || state.active === true || /OPERATION_ACTIVE/.test(common.resultText(state));
			if (!requestId && seenActive && !state.active && matches)
				return state;
			if (!requestId && seenActive && !state.active && ++inactiveAfterActive >= 3)
				throw new Error(_('The modem finished the operation but did not report the requested lock state.'));
			if (state.active) inactiveAfterActive = 0;
			if (++attempts >= (this.modeOperation ? 180 : 60))
				throw new Error(_('The modem operation did not finish within the verification window.'));
			return new Promise(resolve => window.setTimeout(resolve, 2000)).then(poll);
		});
		return poll();
	},
	refreshCellsAfterOperation(attempt) {
		attempt = attempt || 0;
		return new Promise(resolve => window.setTimeout(resolve, attempt ? 5000 : 20000)).then(() => getCells()).then(result => {
			let rows = parseCells(result.serving);
			if (!rows.length && attempt < 6)
				return this.refreshCellsAfterOperation(attempt + 1);
			let target = document.getElementById('m5-cell-candidates');
			if (target && rows.length)
				target.replaceChildren(candidateTable(rows));
		}).catch(() => {
			if (attempt < 6) return this.refreshCellsAfterOperation(attempt + 1);
		});
	},
	syncCandidatesToVerifiedState(result) {
		let state = parsedLockState(result);
		let target = document.getElementById('m5-cell-candidates');
		if (!target) return;
		if (state.mode == 'cell') {
			let bandNo = +state.band || 0;
			target.replaceChildren(candidateTable([ {
				serving: true,
				rat: state.rat || 'nr',
				bandNo,
				band: `${state.rat == 'lte' ? 'B' : 'n'}${bandNo}`,
				arfcn: +state.arfcn,
				pci: +state.pci,
				rsrp: null
			} ]));
		} else if (state.mode == 'none') {
			target.replaceChildren(E('p', { 'class': 'm5-note' }, _('Mobile network re-registered; refreshing actual serving and neighbor cells…')));
		}
	},
	syncLocksLegacy(result) {
		let state = parsedLockState(result);
		this.lockState=state;
		if (state.supported) this.setSupported(state.supported);
		if(!this.dirty){
			setChecked('m5-lte-bands', state.lte);
			setChecked('m5-nr-bands', state.nr);
		}
		let badge = document.getElementById('m5-lock-summary');
		if (badge) badge.textContent = state.mode == 'cell' ? `${_('Cell lock')}: ${String(state.rat || '').toUpperCase()} ${state.band?(state.rat==='lte'?'B':'n')+state.band+' · ':''}${state.arfcn ?? '-'} / PCI ${state.pci == '65535' ? _('Any') : (state.pci ?? '-')}` :
			state.mode == 'none' ? _('Cell lock cleared and state refreshed') :
			state.mode == 'bands' ? _('Band lock applied and verified') :
			(state.lte.length || state.nr.length) ? `${_('Current bands')}: ${state.lte.map(x => 'B' + x).join(' ')} · ${state.nr.map(x => 'n' + x).join(' ')}` : _('Lock state unavailable');
		if(badge&&result.stale)badge.textContent+='（缓存已过期，正在等待重新读取）';
		if (state.mode == 'cell') {
			document.getElementById('m5-lock-rat').value = state.rat || 'nr';
			this.updateBandSelect();
			document.getElementById('m5-lock-band').value = state.band || 0;
			document.getElementById('m5-lock-arfcn').value = state.arfcn ?? '';
			document.getElementById('m5-lock-pci').value = state.pci == '65535' ? '' : (state.pci || '');
		}
	},
	runAction(fn, args, sync, verify, refresh) {
		if (this.busy) return Promise.resolve();
		++this.refreshGeneration;
		let oldRpcTimeout = L.env.rpctimeout;
		L.env.rpctimeout = 40;
		document.getElementById('m5-lock-result').textContent = _('Request sent; waiting for modem verification…');
		this.setBusy(true);
		let rpcCall = fn(...(args || [])).then(result => {
			if (!result || +result.code != 0) throw new Error(common.resultText(result));
			return result;
		});
		return rpcCall.then(result=>this.waitForOperation(verify,result.request_id,sync)).then(state => {
			document.getElementById('m5-lock-state').textContent = common.resultText(state);
			this.dirty=false;this.syncLocks(state);
			this.syncCandidatesToVerifiedState(state);
			sync?.();
			this.refreshCellsAfterOperation();
			return state;
		}).catch(e => {
			document.getElementById('m5-lock-result').textContent=e.message||String(e);
			common.callError(_('Band and Cell Lock'), e);
		}).finally(() => { L.env.rpctimeout = oldRpcTimeout; this.setBusy(false); });
	},
	readLocks() {
		if (this.busy) return Promise.resolve();
		this.setBusy(true);
		this.dirty=false;
		return getLockCache(true).then(()=>this.followRefresh()).catch(e => {
			document.getElementById('m5-lock-result').textContent=e.message;
			common.callError(_('Band and Cell Lock'),e);
		}).finally(() => this.setBusy(false));
	},
	showPane(name) {
		document.querySelectorAll('.m5-lock-pane').forEach(el => { el.hidden = el.id != `m5-pane-${name}`; });
		document.querySelectorAll('.m5-tabs button').forEach(el => el.classList.toggle('active', el.dataset.pane == name));
	},
	applyBands() {
		let self = this;
		let lte = selected('m5-lte-bands'), nr = selected('m5-nr-bands');
		if (!lte.length || !nr.length)
			return ui.addNotification(null, E('p', {}, _('Select at least one LTE band and one NR band.')));
		return ui.showModal(_('Confirm band lock'), [
			E('p', {}, '应用会暂时中断蜂窝，频段锁和小区锁不能同时使用。手动列表不含只读n76/B46，恢复默认可恢复这些能力位。'),
			E('div', { 'class': 'right' }, [
				E('button', { 'class': 'btn', click: ui.hideModal }, _('Cancel')),
				E('button', { 'class': 'btn cbi-button-negative', click: function(ev) { ev.preventDefault(); ui.hideModal(); return self.runAction(setBands, [ lte, nr ], () => { setChecked('m5-lte-bands', lte); setChecked('m5-nr-bands', nr); document.getElementById('m5-lock-result').textContent = _('Band lock applied and verified'); }, state => state.mode == 'bands' && state.status == 'verified' && sameBands(state.lte, lte) && sameBands(state.nr, nr)); } }, _('Apply band lock'))
			])
		]);
	},
	applyCell() {
		let self = this;
		let arfcnText=document.getElementById('m5-lock-arfcn').value.trim(),arfcn=+arfcnText;
		let pci = document.getElementById('m5-lock-pci').value.trim();
		let rat = document.getElementById('m5-lock-rat').value, band = +document.getElementById('m5-lock-band').value;
		if (!/^\d+$/.test(arfcnText)||!Number.isInteger(arfcn) || arfcn < (rat=='lte'?0:1) || arfcn > 3279165 || (pci && (!/^\d+$/.test(pci) || +pci > (rat == 'nr' ? 1007 : 503))))
			return ui.addNotification(null, E('p', {}, '请输入有效频点；PCI 范围为 LTE 0–503、NR 0–1007，可留空。'));
		if (!band) return ui.addNotification(null, E('p', {}, _('Select the radio type and band for this cell.')));
		return ui.showModal(_('Confirm cell lock'), [
			E('p', {}, _('A wrong cell lock can disconnect mobile data. Verify the ARFCN and PCI in the serving/neighbor list first.')),
			E('div', { 'class': 'right' }, [
				E('button', { 'class': 'btn', click: ui.hideModal }, _('Cancel')),
				E('button', { 'class': 'btn cbi-button-negative', click: function(ev) { ev.preventDefault(); ui.hideModal(); return self.runAction(setCell, [ arfcn, pci, rat, band ], () => { document.getElementById('m5-lock-result').textContent = _('Cell lock applied and verified'); }, state => state.mode == 'cell' && state.status == 'verified' && state.rat == rat && +state.arfcn == arfcn && +state.pci == +(pci || 65535) && +state.band == band, getLockRequest); } }, _('Apply cell lock'))
			])
		]);
	},
	renderLegacy(data) {
		let locks = data[0] || {}, cells = data[1] || {}, candidates = parseCells(cells.serving);
		this.dirty=false;this.refreshGeneration=0;
		let page = E('div', { 'class': 'm5-page m5-lock-page', 'style': 'padding-bottom:5rem' }, [ common.style(), common.extraStyle(),
			E('style',{},'.m5-lock-page .m5-band-grid{grid-template-columns:repeat(4,minmax(0,1fr))!important}.m5-lock-page .m5-band input:checked+span,.m5-lock-page .m5-band.is-selected span{background:#2563eb!important;color:#fff!important;border-color:#1d4ed8!important;box-shadow:0 0 0 1px #1d4ed8}.m5-lock-page .m5-band input:focus-visible+span{outline:2px solid #2563eb;outline-offset:3px}.m5-lock-page .m5-band span{min-height:44px;display:flex;align-items:center;justify-content:center}@container(min-width:950px){.m5-lock-page .m5-band-grid{grid-template-columns:repeat(6,minmax(0,1fr))!important}}'),
			E('h2', {}, _('Band and Cell Lock')),
			E('p', { 'class': 'm5-note' }, _('This page uses the modem vendor RIL. Changes may interrupt service. Restore defaults if the modem cannot register.')),
			E('p', { id: 'm5-lock-summary', 'class': 'm5-live' }, _('Reading current lock state…')),
			E('p', { id: 'm5-lock-progress', 'class': 'm5-live' }, _('Ready')),
			E('div', { 'class': 'm5-tabs' }, [
				E('button', { 'class': 'btn active', 'data-pane': 'bands', click: ui.createHandlerFn(this, function() { this.showPane('bands'); }) }, _('Band lock')),
				E('button', { 'class': 'btn', 'data-pane': 'cell', click: ui.createHandlerFn(this, function() { this.showPane('cell'); }) }, _('Cell lock'))
			]),
			E('div', { id: 'm5-pane-bands', 'class': 'm5-lock-pane' }, common.panel(_('4G / 5G band lock'), E('div', {}, [
				E('h4', {}, _('LTE bands')), checks('m5-lte-bands', 'B', LTE),
				E('h4', {}, _('NR bands')), checks('m5-nr-bands', 'n', NR),
				E('p', { id: 'm5-supported-summary', 'class': 'm5-note' }, 'LTE 13 个 / NR 12 个频段；选中立即高亮，点击应用后才写入模组。'),
				E('p', { id: 'm5-band-draft', 'class': 'm5-live', 'aria-live':'polite' }, ''),
				E('div', { 'class': 'm5-lock-footer' }, [
					E('button', { 'class': 'btn cbi-button m5-lock-action', click: ui.createHandlerFn(this, 'readLocks') }, _('Read')),
					E('button', { 'class': 'btn cbi-button cbi-button-apply m5-lock-action', click: ui.createHandlerFn(this, 'applyBands') }, _('Apply band lock')),
					E('button', { 'class': 'btn cbi-button cbi-button-negative m5-lock-action', 'style': 'grid-column:1/-1', click: ui.createHandlerFn(this, function() { return this.runAction(resetBands, [], () => { setChecked('m5-lte-bands', LTE); setChecked('m5-nr-bands', NR); document.getElementById('m5-lock-result').textContent = _('All supported bands restored and state refreshed'); }, state => state.mode == 'none'); }) }, _('Clear band lock / restore defaults'))
				])
			]))),
			E('div', { id: 'm5-pane-cell', 'class': 'm5-lock-pane', hidden: true }, [
			common.panel(_('Cell lock'), E('div', { 'class': 'm5-form' }, [
				E('label', { 'for': 'm5-lock-rat' }, _('Radio type')), E('select', { id: 'm5-lock-rat', change: function() {
					this.dispatchEvent(new CustomEvent('modem-rat-change', {bubbles:true}));
				} }, [ E('option', { value: 'nr' }, '5G NR'), E('option', { value: 'lte' }, '4G LTE') ]),
				E('label', { 'for': 'm5-lock-band' }, _('Band')), E('select', { id: 'm5-lock-band' }, [E('option', {value:''}, '请选择频段'), ...NR.filter(v => v != 76).map(v => E('option', { value: v }, 'n' + v))]),
				E('label', { 'for': 'm5-lock-arfcn' }, _('Channel number (ARFCN)')), E('input', { id: 'm5-lock-arfcn', type: 'number', min: 1, max: 3279165, placeholder: _('Select a cell below or enter its ARFCN') }),
				E('label', { 'for': 'm5-lock-pci' }, _('Physical cell ID (PCI, optional)')), E('input', { id: 'm5-lock-pci', type: 'number', min: 0, max: 1007, placeholder: _('Select a cell below or enter its PCI') }),
				E('span'), E('div', { 'class': 'm5-lock-footer' }, [
					E('button', { 'class': 'btn cbi-button cbi-button-apply m5-lock-action', click: ui.createHandlerFn(this, 'applyCell') }, _('Apply cell lock')),
					E('button', { 'class': 'btn cbi-button cbi-button-negative m5-lock-action', click: ui.createHandlerFn(this, function() { return this.runAction(clearCell, [], () => { document.getElementById('m5-lock-arfcn').value = ''; document.getElementById('m5-lock-pci').value = ''; document.getElementById('m5-lock-result').textContent = _('Cell lock cleared and state refreshed'); }, state => state.mode == 'none', getLockRequest); }) }, _('Clear cell lock'))
				]), E('span')
			])),
				common.panel(_('Serving and neighbor cell candidates'), E('div', {}, [
					E('p', { 'class': 'm5-note' }, _('Tap a serving or neighbor cell to fill ARFCN and PCI automatically. ARFCN identifies the channel; PCI identifies the physical cell.')),
					E('button',{'class':'btn m5-lock-action',click:ui.createHandlerFn(this,async function(){
						if(this.busy)return;this.setBusy(true);
						try{const result=await getCells();if(result.initializing||result.serving?.code)throw Error(result.serving?.output||'小区暂不可用');document.getElementById('m5-cell-candidates').replaceChildren(candidateTable(parseCells(result.serving)));}
						catch(error){common.callError(_('Band and Cell Lock'),error);}finally{this.setBusy(false);}
					})},'读取当前小区'),
					E('div', { id: 'm5-cell-candidates' }, candidateTable(candidates))
				]))]),
			common.panel(_('Current lock state and operation result'), E('pre', { id: 'm5-lock-result', 'class': 'm5-raw' }, locks.output?'当前 LTE：'+parsedLockState(locks).lte.map(v=>'B'+v).join(' ')+'\n当前 NR：'+parsedLockState(locks).nr.map(v=>'n'+v).join(' '):'页面已就绪，正在后台读取当前锁定状态…')),
			E('details', { 'class': 'm5-panel' }, [ E('summary', {}, _('Current lock state and operation result')), E('pre', { id: 'm5-lock-state', 'class': 'm5-raw' }, common.resultText(locks)) ])
		]);
		page.addEventListener('modem-rat-change', () => this.updateBandSelect());
		page.addEventListener('modem-bands-edited',()=>this.updateDraft());
		requestAnimationFrame(() => {
			this.syncLocks(locks);
			if(['pending','reading'].includes(data[2]?.status)){
				document.getElementById('m5-lock-progress').textContent='页面已就绪，正在后台读取锁定状态…';
				this.followRefresh().catch(e=>{if(document.getElementById('m5-lock-result'))document.getElementById('m5-lock-result').textContent=e.message;}).finally(()=>{if(document.getElementById('m5-lock-progress')&&!this.busy)document.getElementById('m5-lock-progress').textContent=_('Ready');});
			}
		});
		return page;
	},
	setBusy(active){this.setBusyLegacy(active);const e=document.getElementById('mu-reapply');if(e)e.disabled=active||this.lockState?.mode!=='cell';},
	syncLocks(result){
	 this.syncLocksLegacy(result);
     const raw=common.resultText(result),mode=raw.match(/The current nwomde:\s*(QL_NW_MODE_[A-Z0-9_]+)/)?.[1],disable=raw.match(/The current NR Disable Mode:\s*(DISABLE_NSA_AND_SA|DISABLE_NSA|DISABLE_SA|NEITHER_IS_DISABLED)/)?.[1];
     this.policyMode=mode==='QL_NW_MODE_LTE'?'lte':mode==='QL_NW_MODE_NR5G'?'sa':mode==='QL_NW_MODE_LTE_NR5G'&&disable==='DISABLE_SA'?'nsa':['QL_NW_MODE_WCDMA_LTE_NR5G','QL_NW_MODE_LTE_NR5G'].includes(mode)&&disable==='NEITHER_IS_DISABLED'?'auto':null;
     this.policyLabel=mode==='QL_NW_MODE_LTE_NR5G'&&disable==='NEITHER_IS_DISABLED'?'配置：4/5G自动选择；SA、NSA均允许。':null;
     if(this.lastFrame)this.paintHero(this.lastFrame);
	 const box=document.getElementById('mu-locked');if(!box)return;
	 const s=this.lockState;
	 box.replaceChildren(s.mode==='cell'?E('tr',{},[(s.rat==='lte'?'B':'n')+s.band,s.pci==='65535'?'任意':s.pci,s.arfcn,'—','—','—'].map(v=>E('td',{},v))):E('tr',{},E('td',{colspan:6},s.mode==='unknown'?'锁定状态尚未确认':'暂无小区锁定')));
	 const e=document.getElementById('mu-reapply');if(e)e.disabled=this.busy||s.mode!=='cell';
	},
	async applySingleBands(rat) {
		if(this.busy)return;
		const other=rat==='nr'?'lte':'nr';
		if(!this.lockState?.[other]?.length)return ui.addNotification(null,E('p',{},'请先读取当前锁定状态，避免改变另一制式的设置。'));
		const wanted=selected('m5-'+rat+'-bands');
		if(!wanted.length)return ui.addNotification(null,E('p',{},'请选择要锁定的频段；恢复默认请使用下方恢复按钮。'));
		if(this.lockState[other].some(v=>other==='nr'?v===76:v===46))return ui.addNotification(null,E('p',{},'另一制式当前包含只读频段，现有接口无法保持完整掩码单独修改。请明确选择两制式频段后使用同时应用，或恢复默认。'));
		const chosen=wanted;
		const values={nr:rat==='nr'?chosen:this.lockState.nr,lte:rat==='lte'?chosen:this.lockState.lte};
		ui.showModal('确认频段锁定',[E('p',{},'蜂窝网络会短暂中断，仅更新所选制式，保留另一制式当前频段。手动列表不含只读n76/B46，恢复默认可恢复这些能力位。'),E('div',{'class':'right'},[
		 E('button',{'class':'btn',click:ui.hideModal},'取消'),E('button',{'class':'btn cbi-button-apply',click:()=>{ui.hideModal();this.runAction(setBands,[values.lte,values.nr],null,s=>s.mode==='bands'&&s.status==='verified'&&sameBands(s.nr,values.nr)&&sameBands(s.lte,values.lte));}},'应用')])]);
	},
	paintQos(state) {
      this.fairQos=state;const b=this.muRoot?.querySelector('#mu-fair-qos');if(!b)return;
      const on=!!(state.enabled&&!state.stopped);
      b.textContent='蜂窝 QoS：'+(on?'开启':'关闭');b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));
    },
    async changeQos(){
      const enabled=!(this.fairQos?.enabled&&!this.fairQos?.stopped);
      const run=async()=>{ui.hideModal();this.setBusy(true);try{const r=await setFairQos(enabled);this.paintQos(r);if(r.code)throw Error(common.resultText(r));}catch(e){common.callError('蜂窝 QoS',e);}finally{this.setBusy(false);}};
      if(!enabled)return run();
      ui.showModal('手动开启蜂窝 QoS',[E('p',{},'此前启用CAKE/IFB高速下载曾触发内核卡死。此功能默认关闭；开启后需自行观察稳定性，可随时关闭。'),E('div',{'class':'right'},[E('button',{'class':'btn',click:ui.hideModal},'取消'),E('button',{'class':'btn cbi-button-negative',click:run},'确认开启')])]);
    },
    paintHero(frame) {
        this.lastFrame=frame;
		if(!this.muRoot?.isConnected)return;
		const current=this.policyMode||(frame.modem?.rat==='4G'?'lte':frame.radio_details?.parsed?.sa_nsa==='SA'?'sa':frame.radio_details?.parsed?.sa_nsa==='NSA'?'nsa':null);
        this.muRoot.querySelectorAll('[data-network-mode]').forEach(b=>{const on=b.dataset.networkMode===current;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));b.title=this.policyMode?'模组读回的配置模式':'当前驻网类型，尚未读回配置模式';});
        this.muRoot.querySelector('#mu-network-policy').textContent=this.policyLabel||'优先显示模组读回的配置模式；配置未读到时高亮当前驻网类型。';
        const roaming=this.muRoot.querySelector('#mu-roaming');if(roaming){const known=typeof frame.apn?.data_roaming==='boolean';roaming.disabled=this.busy||!known;roaming.textContent='数据漫游：'+(known?(frame.apn.data_roaming?'开启':'关闭'):'未获取');roaming.classList.toggle('on',known&&frame.apn.data_roaming);}
        const ims=frame.modem?.ims;
        this.muRoot.querySelector('#mu-ims-status').textContent=ims?'IMS：'+(ims.registered?'已注册':'未注册')+(ims.voice===true?' · 语音可用':'')+(ims.sms===true?' · 短信可用':'')+(ims.stale?'（缓存）':''):'IMS：未获取';
        const m=frame.modem||{},r=frame.radio_details?.parsed,cells=cellular.parseCells({...frame.cells?.serving,carriers:r?.carriers}),c=cells.find(x=>x.serving),p=r?.carriers?.find(x=>x.type==='NR PCC')||r?.carriers?.[0];
		this.muRoot.querySelector('#mu-lock-rat').textContent=(m.rat!=='4G'&&r?.sa_nsa?'5G '+r.sa_nsa:['4G','5G'].includes(m.rat)?m.rat:c?.rat==='nr'?'5G':c?.rat==='lte'?'4G':'正在注册')+' · '+(m.operator||'未获取');
		this.muRoot.querySelector('#mu-lock-cellline').textContent=c?c.band+' · PCI '+c.pci+' · ARFCN '+c.arfcn+(p?.dl_bandwidth_mhz!=null?' · '+p.dl_bandwidth_mhz+' MHz':''):'小区数据更新中';
		this.muRoot.querySelector('#mu-lock-rsrp').textContent=(c?.rsrp??m.rsrp)==null?'未获取':(c?.rsrp??m.rsrp).toFixed(1)+' dBm';
		this.muRoot.querySelector('#mu-lock-chips').textContent='RSRQ '+(c?.rsrq??m.rsrq??'—')+'　SINR '+(c?.sinr??m.sinr??'—');
		this.muRoot.querySelector('#mu-lock-ca').replaceChildren(...(r?.carriers||[]).map((v,i)=>E('tr',{},[i+1,(v.rat==='nr'?'NR n':'LTE B')+v.band,v.arfcn,v.pci,v.dl_bandwidth_mhz==null?'—':v.dl_bandwidth_mhz+' MHz',v.ul_bandwidth_mhz==null?'—':v.ul_bandwidth_mhz+' MHz',v.dl_mcs??'—',v.ul_mcs??'—'].map(x=>E('td',{},x)))));
		if(cells.length&&!this.busy)this.muRoot.querySelector('#m5-cell-candidates').replaceChildren(candidateTable(cells));
	},
	unload(){this.refreshGeneration++;if(this.muPoll)poll.remove(this.muPoll);},
	render(data) {
		M.injectCss();
		const legacy=this.renderLegacy(data),nodes={};legacy.querySelectorAll('[id]').forEach(n=>nodes[n.id]=n);
		const take=id=>nodes[id],button=(text,fn,extra={})=>E('button',{'class':'mud-btn m5-lock-action',type:'button',click:fn,...extra},text);
		const disabled=text=>button(text,()=>{},{'class':'mud-btn',disabled:true,title:'当前MT6990尚无已验证的对应控制接口'});
		const section=(title,body)=>E('div',{'class':'mud-sec'},[E('h3',{},title),body]);
		const bandPanel=rat=>E('div',{},[E('div',{'class':'mud-r'},[E('span',{},rat==='nr'?'NR 频段':'LTE 频段'),E('span',{},'按本机能力读取')]),take('m5-'+rat+'-bands'),E('div',{'class':'mud-ctl',style:'grid-template-columns:repeat(3,minmax(0,1fr));margin-top:8px'},[
		 button('应用 '+rat.toUpperCase()+' 频段',()=>this.applySingleBands(rat)),button('全选',()=>{setChecked('m5-'+rat+'-bands',this.supported?.[rat]||(rat==='nr'?NR:LTE));this.updateDraft();}),button('全不选',()=>{setChecked('m5-'+rat+'-bands',[]);this.updateDraft();})])]);
        const mode=(label,value)=>button(label,()=>ui.showModal('确认网络模式',[E('p',{},'更改后蜂窝网络可能短暂中断，将读取原设置并验证模式和SA/NSA限制；失败时尝试恢复原设置。'),E('button',{'class':'btn',click:ui.hideModal},'取消'),E('button',{'class':'btn cbi-button-apply',click:async()=>{ui.hideModal();this.setBusy(true);this.modeOperation=true;try{const r=await setMode(value);if(r.code)throw Error(common.resultText(r));await this.waitForOperation(null,r.request_id);await getLockCache(true);await this.followRefresh();take('m5-lock-result').textContent='网络模式已读回确认，数据连接恢复流程已完成。';}catch(e){common.callError('网络模式',e);}finally{this.modeOperation=false;this.setBusy(false);}}},'应用')]),{'data-network-mode':value,'aria-pressed':'false'});

		const page=E('div',{'class':'mud mud-locks m5-lock-page'},[common.style(),
		 E('style',{},'.mud-locks .m5-band-grid{display:flex!important;flex-wrap:wrap;gap:6px}.mud-locks .m5-band{margin:0}.mud-locks .m5-band span{min-height:0!important;padding:3px 10px!important;border-radius:999px!important;font-size:13px}.mud-locks .m5-band input:checked+span,.mud-locks .m5-band.is-selected span{background:var(--brand,#009b96)!important;color:white!important}.mud-locks .m5-lock-summary{margin:8px 0}.mud-locks .mud-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.mud-locks .mud-form label{display:flex;flex-direction:column;gap:5px}.mud-locks input,.mud-locks select{width:100%;min-width:0}.mud-locks .mud-scroll{overflow:auto}.mud-locks .m5-cell-table{min-width:640px}.mud-locks .mud-note{margin-top:8px}@media(max-width:600px){.mud-locks .mud-form{grid-template-columns:1fr 1fr}.mud-locks .mud-cols{display:grid;grid-template-columns:1fr}.mud-locks .mud-ctl{grid-template-columns:repeat(2,minmax(0,1fr))!important}}'),
		 E('div',{'class':'mud-card mud-hero'},[E('div',{'class':'mud-hero-l'},[E('div',{'class':'mud-sub'},'当前驻网'),E('b',{id:'mu-lock-rat'},'正在读取'),E('div',{id:'mu-lock-cellline','class':'mud-cellline'},'')]),E('div',{'class':'mud-hero-r'},[E('div',{id:'mu-lock-rsrp','class':'mud-rsrp'},'—'),E('div',{id:'mu-lock-chips','class':'mud-chips'},'')])]),
		 E('div',{'class':'m5-lock-summary'},[take('m5-lock-summary'),take('m5-lock-progress')]),
		 section('载波聚合',E('div',{'class':'mud-scroll'},E('table',{'class':'mud-table'},[E('thead',{},E('tr',{},['载波','制式/频段','ARFCN','PCI','下行频宽','上行频宽','下行MCS','上行MCS'].map(x=>E('th',{},x)))),E('tbody',{id:'mu-lock-ca'},[])]))),
         section('网络模式',E('div',{},[E('div',{style:'display:flex;justify-content:space-between;align-items:start;gap:16px;flex-wrap:wrap'},[E('div',{},[E('div',{'class':'mud-ctl',style:'grid-template-columns:repeat(4,1fr);max-width:560px'},[mode('自动','auto'),mode('仅4G','lte'),mode('5G SA','sa'),mode('5G NSA','nsa')]),button('刷新锁定状态',()=>this.readLocks())]),button('蜂窝 QoS：读取中',()=>this.changeQos(),{id:'mu-fair-qos','aria-pressed':'false'})]),E('p',{id:'mu-network-policy','class':'mud-note'},'优先显示模组读回的配置模式；配置未读到时高亮当前驻网类型。') ])),
         section('数据漫游 · VoLTE · VoNR',E('div',{},[E('div',{'class':'mud-ctl'},[button('数据漫游：读取中',()=>{const enabled=!this.lastFrame?.apn?.data_roaming;ui.showModal('确认数据漫游',[E('p',{},'更改会重新加载蜂窝数据配置，可能短暂断网。'),E('button',{'class':'btn',click:ui.hideModal},'取消'),E('button',{'class':'btn cbi-button-apply',click:async()=>{ui.hideModal();try{const r=await setRoaming(enabled);if(r.code)throw Error(common.resultText(r));}catch(e){common.callError('数据漫游',e);}}},'应用')]);},{id:'mu-roaming'}),disabled('VoLTE：等待接口核实'),disabled('VoNR：等待接口核实')]),E('p',{id:'mu-ims-status','class':'mud-note'},'IMS：未获取')])),

		 section('频段锁定',E('div',{},[E('div',{'class':'mud-cols'},[bandPanel('nr'),bandPanel('lte')]),take('m5-supported-summary'),take('m5-band-draft'),button('同时应用所选 NR / LTE',()=>this.applyBands())])),
		 section('邻区与小区锁定',E('div',{},[E('div',{'class':'mud-sub'},'锁定小区'),E('div',{'class':'mud-scroll'},E('table',{'class':'mud-table'},[E('thead',{},E('tr',{},['制式/频段','PCI','频点','RSRP','RSRQ','SINR'].map(x=>E('th',{},x)))),E('tbody',{id:'mu-locked'},[])])),E('div',{'class':'mud-ctl',style:'max-width:560px'},[button('填入当前服务小区',()=>{const row=this.muRoot.querySelector('#m5-cell-candidates .m5-serving');if(row)row.click();}),button('解除小区锁定',()=>this.runAction(clearCell,[],null,s=>s.mode==='none',getLockRequest),{'class':'mud-btn warn m5-lock-action'}),button('重新应用',()=>{if(!this.busy)this.applyCell();},{id:'mu-reapply','class':'mud-btn',disabled:true})]),
		 E('div',{'class':'mud-form',style:'margin-top:16px'},[['制式','m5-lock-rat'],['频段','m5-lock-band'],['ARFCN','m5-lock-arfcn'],['PCI（可留空）','m5-lock-pci']].map(([title,id])=>E('label',{},[E('span',{},title),take(id)]))),
		 E('div',{'class':'mud-ctl',style:'margin-top:10px;max-width:400px'},[button('应用小区锁定',()=>this.applyCell()),button('重新读取小区',async()=>{const r=await getCells();take('m5-cell-candidates').replaceChildren(candidateTable(parseCells(r.serving)));})]),E('div',{'class':'mud-scroll'},take('m5-cell-candidates')),
		 E('p',{'class':'mud-note'},'应用会暂时中断蜂窝，须等待实际回读确认；恢复全部支持频段请使用下方恢复默认。') ])),
		 section('清除全部蜂窝锁定',button('恢复默认频段并清除小区锁定',()=>this.runAction(resetBands,[],null,s=>s.mode==='none'),{'class':'mud-btn warn m5-lock-action'})),
		 section('当前锁定状态与操作结果',take('m5-lock-result')),E('details',{},[E('summary',{},'工程信息'),take('m5-lock-state')])
		]);
		page.addEventListener('modem-cell-apply',()=>this.applyCell());page.addEventListener('modem-rat-change',()=>this.updateBandSelect());page.addEventListener('modem-bands-edited',()=>this.updateDraft());
		this.muRoot=page;
		this.muPoll=()=>Promise.all([getDashboard(),getFairQos()]).then(([frame,qos])=>{this.paintHero(frame);this.paintQos(qos);}).catch(()=>{});
		requestAnimationFrame(()=>{this.paintHero(data[3]||{});this.paintQos(data[4]||{});poll.add(this.muPoll,5);});
		return page;
	},

	handleSaveApply: null, handleSave: null, handleReset: null
});
