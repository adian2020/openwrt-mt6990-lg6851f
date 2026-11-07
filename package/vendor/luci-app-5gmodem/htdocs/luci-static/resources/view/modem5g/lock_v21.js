'use strict';
/* Shared ECELL parsing and actual current/supported mask readback. */
'require view';
'require rpc';
'require ui';
'require modem5g.common_v5 as common';
'require modem5g.cellular_v1 as cellular';

const getLocks = rpc.declare({ object: 'luci.modem5g', method: 'get_locks', expect: {} });
const getLockCache = rpc.declare({ object: 'luci.modem5g', method: 'get_lock_cache', params: [ 'refresh' ], expect: {} });
const getLockRequest = rpc.declare({ object: 'luci.modem5g', method: 'get_lock_request', params: ['request_id'], expect: {} });
const getCells = rpc.declare({ object: 'luci.modem5g', method: 'get_cells', expect: {} });
const setBands = rpc.declare({ object: 'luci.modem5g', method: 'set_band_lock', params: [ 'lte', 'nr' ] });
const resetBands = rpc.declare({ object: 'luci.modem5g', method: 'reset_band_lock' });
const setCell = rpc.declare({ object: 'luci.modem5g', method: 'set_cell_lock', params: [ 'arfcn', 'pci', 'rat', 'band' ] });
const clearCell = rpc.declare({ object: 'luci.modem5g', method: 'clear_cell_lock' });

const LTE = [ 1, 3, 5, 7, 8, 20, 28, 32, 38, 40, 41, 42, 43 ];
const NR = [ 1, 3, 5, 7, 8, 20, 28, 38, 40, 41, 77, 78 ];

function checks(id, prefix, values) {
	const check = v => {
		return E('label', { 'class': 'm5-band' }, [
			E('input', { type: 'checkbox', value: v, change: function() {
				this.closest('label').classList.toggle('is-selected', this.checked);
				this.dispatchEvent(new CustomEvent('modem-bands-edited', {bubbles:true}));
			} }),
			E('span', {}, `${prefix}${v}`)
		]);
	};
	return E('div', { id: id, 'class': 'm5-band-grid' }, values.map(check));
}

function selected(id) {
	return Array.from(document.querySelectorAll(`#${id} input:checked:not(:disabled)`)).map(el => +el.value);
}

function setChecked(id, values) {
	let wanted = new Set(values.map(Number));
	document.querySelectorAll(`#${id} input`).forEach(el => {
		el.checked = !el.disabled && wanted.has(+el.value);
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
		E('thead', {}, E('tr', {}, [ _('Type'), _('Band'), _('ARFCN'), _('PCI'), _('RSRP'), _('RSRQ'), _('SINR') ].map(x => E('th', {}, x)))),
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
			E('td', {}, r.sinr == null ? '-' : `${r.sinr} dB`)
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
		if (note) note.textContent = '选择界面恢复原有 LTE 13 个 / NR 12 个频段；实际能力与完整掩码见下方状态框。恢复默认按模组完整能力校验。';
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
	load() { return getLockCache(true).then(data=>[data.bands||{},data.cells||{},data.refresh||{}]); },
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
	setBusy(active) {
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
			if (++attempts >= 60)
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
	syncLocks(result) {
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
			E('p', {}, _('Applying a band lock interrupts mobile data while the modem re-registers. Band lock and cell lock must not be enabled at the same time.')),
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
	render(data) {
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
	handleSaveApply: null, handleSave: null, handleReset: null
});
