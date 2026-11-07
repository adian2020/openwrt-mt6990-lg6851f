#!/usr/bin/ucode
import * as fs from 'fs';
import * as uloop from 'uloop';
import * as ubus from 'ubus';
import * as uci from 'uci';
import * as core from 'lg6851f.traffic-core';

const BASE = getenv('LG6851F_TRAFFIC_DIR') || '/etc/lg6851f-traffic';
const RUN = getenv('LG6851F_TRAFFIC_RUN') || '/var/run/lg6851f-traffic';
const NET = getenv('LG6851F_TRAFFIC_SYS') || '/sys/class/net';
const BUS = getenv('LG6851F_TRAFFIC_BUS') || 'lg6851f.traffic';
const boot = trim(fs.readfile('/proc/sys/kernel/random/boot_id') || '');

fs.mkdir(BASE, 448); fs.mkdir(RUN, 448);
function read_json(path) {
    let text = fs.readfile(path);
    if (text == null) return null;
    try { return json(text); } catch (e) { die('Invalid traffic database: ' + path + '\n'); }
}
function atomic(path, value) {
    let text = sprintf('%J\n', value), tmp = path + '.new';
    if (fs.writefile(tmp, text) != length(text)) return false;
    fs.chmod(tmp, 384);
    return fs.rename(tmp, path);
}
uloop.init();
const bus = ubus.connect(getenv('LG6851F_TRAFFIC_SOCKET') || null, 2);
if (!bus) die('Traffic ubus connection failed\n');
function ledger(BASE, RUN) {
fs.mkdir(BASE,448); fs.mkdir(RUN,448);
let db = core.restore(read_json(RUN + '/state.json'), read_json(BASE + '/state.json'), time());
if (db.version != 1 || type(db.days) != 'object' || type(db.months) != 'object')
    die('Unsupported traffic database\n');
db.config = core.config(db.config);
let saved_at = 0, storage_error = false, resolved = '', resolve_at = 0;

function resolve_device(now) {
    if (db.config.device) return db.config.device;
    if (now >= resolve_at && now < resolve_at + 30 && resolved) return resolved;
    resolve_at = now;
    let cfg = uci.cursor();
    let explicit = cfg.get('network', 'modem5g', 'data_device');
    let iface = 'modem5g';
    let net = explicit ? null : bus.call('network.interface.' + iface, 'status', {});
    let name = explicit || net?.l3_device || net?.device;
    if (name && match(name, /^[a-zA-Z0-9_.:-]{1,15}$/)) resolved = name;
    return name && match(name, /^[a-zA-Z0-9_.:-]{1,15}$/) ? resolved : '';
}
function snapshot(now) {
    let name = resolve_device(now);
    if (!name) return null;
    let rx = trim(fs.readfile(NET + '/' + name + '/statistics/rx_bytes') || '');
    let tx = trim(fs.readfile(NET + '/' + name + '/statistics/tx_bytes') || '');
    let idx = trim(fs.readfile(NET + '/' + name + '/ifindex') || '');
    if (!match(rx, /^[0-9]+$/) || !match(tx, /^[0-9]+$/) || !match(idx, /^[0-9]+$/)) return null;
    return { device: name, boot: boot, ifindex: int(idx), rx: int(rx), tx: int(tx) };
}
function view(now) {
    let s = core.status(db, now);
    s.storage_error = storage_error;
    s.slot = 0;
    return s;
}
function checkpoint(force) {
    let now = time();
    let ram_ok = atomic(RUN + '/state.json', db);
    if (!ram_ok) storage_error = true;
    if (force || now - saved_at >= 60 || now < saved_at) {
        if (atomic(BASE + '/state.json', db)) { saved_at = now; storage_error = !ram_ok; }
        else storage_error = true;
    }
    atomic(RUN + '/view.json', view(now));
}
function sample(force) {
    let now = time();
    core.advance(db, snapshot(now), now);
    checkpoint(force);
}
function get_data() {
    let days = [], months = [];
    for (let date in reverse(sort(keys(db.days)))) {
        if (length(days) >= 31) break;
        push(days, { date: date, rx: db.days[date].rx, tx: db.days[date].tx });
    }
    for (let date in reverse(sort(keys(db.months)))) {
        if (length(months) >= 12) break;
        push(months, { date: date, rx: db.months[date].rx, tx: db.months[date].tx });
    }
    return { config: db.config, status: view(time()), days: days, months: months };
}
return {
    device: resolve_device,
    sample: sample,
    get: { call: function(req) { return get_data(); } },
    clear: { args: { confirm: false }, call: function(req) {
        // Cancelled/unconfirmed requests do not sample or write anything.
        if (req.args?.confirm !== true) return { ok: 0, error: 'confirmation_required' };
        let now = time(), next = core.clear_records(db, snapshot(now), now);
        // Single event-loop transaction: publish neither RAM state nor the new
        // in-memory ledger until the durable replacement succeeds.
        if (!atomic(BASE + '/state.json', next)) {
            storage_error = true;
            return { ok: 0, error: 'storage_failed' };
        }
        db = next; saved_at = now; storage_error = false;
        checkpoint(false);
        return { ok: 1, data: get_data() };
    } },
    set: { args: { payload: '' }, call: function(req) {
        let input;
        try {
            if (length(req.args.payload || '') > 4096) die('invalid_config');
            input = json(req.args.payload);
            core.config(input);
            if (input.used_gb != null && time() < 1704067200) return { ok: 0, error: 'clock_unsynced' };
        } catch (e) { return { ok: 0, error: 'invalid_config' }; }
        sample(false);
        let previous = db.config, adjustment = db.adjustment, last = db.last, revision = db.revision;
        try { core.update_config(db, input, time()); }
        catch (e) { return { ok: 0, error: 'invalid_config' }; }
        db.revision = (db.revision ?? 0) + 1;
        // Persist the full transaction before acknowledging changed settings.
        if (!atomic(BASE + '/state.json', db)) {
            db.config = previous; db.adjustment = adjustment; db.last = last;
            db.revision = revision;
            storage_error = true;
            return { ok: 0, error: 'storage_failed' };
        }
        resolved = ''; resolve_at = 0;
        sample(true);
        return { ok: 1 };
    } },
    flush: { call: function(req) { sample(true); return { ok: !storage_error }; } }
};
}
const current = ledger(BASE, RUN);
function dispatch(method, req) {
    let slot = req.args?.slot ?? 0;
    if (slot != 0) return {ok:0,error:'invalid_sim'};
    return current[method].call(req);
}
const obj = bus.publish(BUS, {
    get: {args:{slot:0}, call:function(req) {return dispatch('get',req);}},
    set: {args:{slot:0,payload:''}, call:function(req) {return dispatch('set',req);}},
    clear: {args:{slot:0,confirm:false}, call:function(req) {return dispatch('clear',req);}},
    flush: {call:function(req) {return current.flush.call(req);}}
});
if (!obj) die('Traffic publish failed: '+ubus.error()+'\n');
current.sample(true);
let ticker;
ticker = uloop.timer(10000, function() {
    current.sample(false);
    ticker.set(10000);
});
let term = uloop.signal(15, function() { current.sample(true); uloop.end(); });
let intr = uloop.signal(2, function() { current.sample(true); uloop.end(); });
uloop.run();
current.sample(true);
