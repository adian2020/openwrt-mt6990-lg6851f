'use strict';
'require baseclass';

// Vendor masks print successive low-to-high 32-bit words, not one big integer.
function maskBands(hex) {
	if (!/^(?:[0-9a-f]{8}){1,4}$/i.test(hex || '')) return null;
	const rows = [];
	for (let word = 0; word < hex.length / 8; word++) {
		const value = parseInt(hex.slice(word * 8, word * 8 + 8), 16);
		for (let bit = 0; bit < 32; bit++)
			if ((value & Math.pow(2, bit)) !== 0) rows.push(word * 32 + bit + 1);
	}
	return rows;
}

function lockMasks(raw) {
	const rows = [];
	const pattern = /lte band info\s*=\s*([0-9a-f]+)[\s\S]*?nr band info\s*=\s*([0-9a-f]+)/ig;
	let match;
	while ((match = pattern.exec(raw || ''))) {
		const lte = maskBands(match[1]), nr = maskBands(match[2]);
		if (lte && nr) rows.push({lte,nr});
	}
	return {current:rows[0] || null, supported:rows[1] || null};
}

function csv(text) {
	const result = [];let field = '', quoted = false;
	for (const char of text) {
		if (char === '"') quoted = !quoted;
		else if (char === ',' && !quoted) {result.push(field.trim());field = '';}
		else field += char;
	}
	if (quoted) return null;
	result.push(field.trim());return result;
}

function integer(text) {return /^\d+$/.test(text || '') ? Number(text) : null;}
function signal(text, kind, rat) {
	const value = integer(text);
	if (value == null || value === 255 || value > 127) return null;
	if (kind === 'rsrp') return value - (rat === 11 ? 156 : 140);
	return value / 2 - (kind === 'rsrq' ? 43 : 23);
}
function nrCandidates(arfcn) {
	// Downlink frequency ranges of this modem's reported NR bands. These are
	// candidates, not a report of the serving band or of carrier aggregation.
	const ranges = [[1,422000,434000],[3,361000,376000],[5,173800,178800],
		[7,524000,538000],[8,185000,192000],[20,158200,164200],
		[28,151600,160600],[38,514000,524000],[40,460000,480000],
		[41,499200,537999],[75,286400,303400],[76,285400,286400],
		[77,620000,680000],[78,620000,653333]];
	return ranges.filter(([,first,last])=>arfcn >= first && arfcn <= last).map(([band])=>band);
}
function parseCells(result) {
	if (result?.code != null && +result.code !== 0) return [];
	const match = (result?.output || '').match(/\+ECELL:\s*([^\r\n]+)/);
	if (!match) return [];
	const fields = csv(match[1]);
	if (!fields) return [];
	const count = integer(fields.shift());
	// Reject partial or unknown records instead of treating empty fields as zero.
	if (count == null || count > 64 || fields.length !== count * 15) return [];
	const rows = [];
	for (let i = 0; i < count; i++) {
		const f = fields.slice(i * 15, i * 15 + 15), rat = integer(f[0]), arfcn = integer(f[14]), pci = integer(f[5]);
		if (![7,11].includes(rat) || arfcn == null || arfcn < 1 || arfcn > 3279165 || pci == null || pci > (rat === 11 ? 1007 : 503)) continue;
		const candidates = rat === 11 ? nrCandidates(arfcn) : [];
		rows.push({serving:i === 0, rat:rat === 11 ? 'nr' : 'lte', bandNo:candidates.length === 1 ? candidates[0] : null,
			band:candidates.length ? candidates.map(n=>'n'+n).join(' / ') : rat === 11 ? 'NR' : 'LTE',
			bandCandidates:candidates, arfcn, pci,
			rsrp:signal(f[6],'rsrp',rat), rsrq:signal(f[7],'rsrq',rat), sinr:signal(f[11],'sinr',rat)});
	}
	return rows;
}

return baseclass.extend({maskBands,lockMasks,parseCells});
