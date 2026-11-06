'use strict';

// Parse the verified read-only sample_nw 7, 21, 25/5 and 33 session. No I/O.
function integer(value) {
	return type(value) == 'string' && match(value, /^[0-9]+$/) ? +value : null;
}
function bandwidth(value) {
	let m = match(value || '', /^([0-9]+(\.[0-9]+)?)\s*(M|MHz|K|kHz)$/i);
	if (!m || +m[1] <= 0) return null;
	return +m[1] * (lc(m[3]) == 'k' || lc(m[3]) == 'khz' ? 0.001 : 1.0);
}
function ambr(value) {
	let m = match(value || '', /^([0-9]+(\.[0-9]+)?)\s*(bps|Kbps|Mbps|Gbps)$/i);
	if (!m) return { raw: value || null, bps: null };
	let scales = { bps: 1, kbps: 1000, mbps: 1000000, gbps: 1000000000 };
	return { raw: value, bps: +m[1] * scales[lc(m[3])] };
}
function flag(value) {
	let n = integer(value);
	return n == 0 || n == 1 ? n : null;
}
function positive(value) {
	let n = integer(value);
	return n != null && n > 0 ? n : null;
}
function mcs(value) {
	let n = integer(value);
	return n != null && n <= 31 ? n : null;
}
function cqi(value) {
	let n = integer(value);
	return n != null && n <= 15 ? n : null;
}
function radio_band(fields, rat) {
	let band = positive(fields[rat + '_band']);
	return {
		band,
		dl_arfcn: band ? positive(fields[rat + (rat == 'lte' ? '_dl_earfcn' : '_dl_arfcn')]) : null,
		ul_arfcn: band ? positive(fields[rat + (rat == 'lte' ? '_ul_earfcn' : '_ul_arfcn')]) : null,
		dl_bandwidth_mhz: band ? bandwidth(fields[rat + '_dl_bandwidth']) : null,
		ul_bandwidth_mhz: band ? bandwidth(fields[rat + '_ul_bandwidth']) : null,
		cqi: band ? cqi(fields[rat + '_cqi']) : null
	};
}
function carrier(row, bands) {
	let rat = match(row.type || '', /^NR (PCC|SCC)$/) ? 'nr' : match(row.type || '', /^LTE (PCC|SCC)$/) ? 'lte' : null;
	let band = positive(row.band), arfcn = positive(row.arfcn), pci = integer(row.pci);
	if (!rat || !band || !arfcn || pci == null || pci > (rat == 'nr' ? 1007 : 503)) return null;
	let same = row.prefix == 'pcc' && band == bands[rat].band && arfcn == bands[rat].dl_arfcn;
	return { type: row.type, rat, band, arfcn, pci,
		dl_bandwidth_mhz: same ? bands[rat].dl_bandwidth_mhz : null,
		ul_bandwidth_mhz: same ? bands[rat].ul_bandwidth_mhz : null,
		dl_bandwidth_code: integer(row.dl_bandwidth), ul_bandwidth_code: integer(row.ul_bandwidth),
		dl_mcs: mcs(row.dl_mcs), ul_mcs: mcs(row.ul_mcs),
		cqi: same ? bands[rat].cqi : null,
		dl_modulation_code: integer(row.dl_modulation), ul_modulation_code: integer(row.ul_modulation),
		dl_mimo_code: integer(row.dl_mimo), ul_mimo_code: integer(row.ul_mimo),
		dl_bwp_bandwidth_code: integer(row.dl_bwp_bandwidth), ul_bwp_bandwidth_code: integer(row.ul_bwp_bandwidth)
	};
}

export function parse(output) {
	let raw = type(output) == 'string' ? output : '';
	let section = '', fields = {}, endc = {}, carriers = [], current = null;
	let success = { band: false, ca: false, endc: false };
	let registration = { ok: false, radio_tech: null, reg_state: null, tech_domain: null };
	for (let line in split(raw, '\n')) {
		line = trim(line);
		let command = match(line, /^Cmd Index=([0-9-]+)$/);
		if (command) {
			section = command[1] == '7' ? 'registration' : command[1] == '21' ? 'band' : command[1] == '25' ? 'ca' : command[1] == '33' ? 'endc' : '';
			continue;
		}
		if (section == 'registration') {
			line = replace(line, /^[0-9]+:[A-Za-z_][A-Za-z0-9_]*\(\):\s*/, '');
			if (match(line, /^ret=\s*00000000$/)) registration.ok = true;
			let m = match(line, /^(radio_tech|reg_state|tech_domain)\s*=\s*(.*)$/);
			if (m) registration[m[1]] = trim(m[2]);
		}
		else if (section == 'band') {
			line = replace(line, /^[0-9]+:main\(\):\s*/, '');
			if (line == 'get nw current band information:') success.band = true;
			let m = match(line, /^((lte|nr|wcdma|net|ims)_[a-z_]+)\s*=\s*(.*)$/);
			if (m) fields[m[1]] = trim(m[3]);
		}
		else if (section == 'ca') {
			if (line == 'get all info success!') success.ca = true;
			let m = match(line, /^(pcc|scc)_([a-z_]+)\s*=\s*(.*)$/);
			if (!m) continue;
			if (m[2] == 'type') { current = { prefix: m[1], type: trim(m[3]) }; push(carriers, current); }
			else if (current && current.prefix == m[1]) current[m[2]] = trim(m[3]);
		}
		else if (section == 'endc') {
			if (line == 'get endc status success...') success.endc = true;
			let m = match(line, /^(endc_available|dcnr_restricted)\s*=\s*([0-9]+)$/);
			if (m) endc[m[1]] = m[2];
		}
	}
	let bands = { lte: radio_band(fields, 'lte'), nr: radio_band(fields, 'nr') };
	let rows = filter(map(carriers, row => carrier(row, bands)), row => row != null);
	let session = !!match(raw, /ql_nw_init,\s*ret\s*=\s*00000000/) && !!match(raw, /ql_nw_release success,\s*ret\s*=\s*00000000/);
	let complete = session && success.band && success.ca && success.endc &&
		fields.lte_band != null && fields.nr_band != null && endc.endc_available != null && endc.dcnr_restricted != null;
	let mode = null;
	if (session && registration.ok && registration.tech_domain == '3GPP' &&
	    index(['QL_NW_SERVICE_FULL', 'QL_NW_SERVICE_ROAMING'], registration.reg_state) >= 0) {
		if (registration.radio_tech == 'QL_NW_RADIO_TECH_NR5G') mode = 'SA';
		else if (registration.radio_tech == 'QL_NW_RADIO_TECH_NSA5G') mode = 'NSA';
	}
	return { complete, sections: success, bands, carriers: rows, data_registration: registration,
		ambr: { network: { dl: ambr(fields.net_ambr_dl), ul: ambr(fields.net_ambr_ul) },
			ims: { dl: ambr(fields.ims_ambr_dl), ul: ambr(fields.ims_ambr_ul) } },
		endc: { available: flag(endc.endc_available), restricted: flag(endc.dcnr_restricted) },
		qci: null, sa_nsa: mode,
		// These values are enum codes, not proven units or device capabilities.
		nr_subcarrier_spacing_code: integer(fields.nr_subcarrier_spacing),
		nr_point_a_arfcn: positive(fields.nr_point_a_arfcn)
	};
}
