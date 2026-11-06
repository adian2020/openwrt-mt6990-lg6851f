#!/usr/bin/env python3
"""用原生 ucode 验证计数、缺失字段及 APN 操作边界；不连接模组。"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'package/vendor/luci-app-5gmodem'
UCODE = os.environ.get('UCODE') or shutil.which('ucode')


@unittest.skipUnless(UCODE, '需要原生 ucode；可设置 UCODE 和 UCODE_LIBRARY')
class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = pathlib.Path(self.temp.name)

    def write(self, path, value):
        target = self.fixture / path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def run_ucode(self, source, **globals):
        script = self.fixture / 'test.uc'
        script.write_text(source)
        command = [UCODE]
        for library in [os.environ.get('UCODE_LIBRARY'), str(PACKAGE / 'root/usr/share/ucode'), str(self.fixture)]:
            if library:
                command += ['-L', library]
        for key, value in globals.items():
            command += ['-D', key + '=' + json.dumps(value)]
        command.append(str(script))
        env = dict(os.environ, LG6851F_DATA_ROOT=str(self.fixture))
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_measurements_keep_fractions_and_unknowns(self):
        self.write('/proc/meminfo', 'MemTotal: 1000 kB\nMemAvailable: 789 kB\n')
        self.write('/sys/class/thermal/thermal_zone0/type', 'cpu_little0')
        self.write('/sys/class/thermal/thermal_zone0/temp', '56415')
        self.write('/tmp/lg6851f-modem-status.state', 'RSRP=-101\nRSRQ=-10.5\nSINR=18.5\nRAT=5G\nIMEI=123456789000111\n')
        value = self.run_ucode("import * as d from 'lg6851f.dashboard'; printf('%J', d.snapshot());")
        self.assertAlmostEqual(value['memory']['percent'], 21.1)
        self.assertAlmostEqual(value['temperatures'][0]['celsius'], 56.415)
        self.assertEqual(value['modem']['rsrq'], -10.5)
        self.assertEqual(value['modem']['imei'], '123***111')
        self.assertIsNone(value['modem']['updated'])
        self.assertEqual(value['frequencies'], [])
        self.assertTrue(all(v is None for v in value['advanced'].values()))

    def test_rate_baselines_resets_and_cpu_guest_accounting(self):
        value = self.run_ucode("""
            import * as d from 'lg6851f.dashboard';
            let a = { boot_id:'one', device:'ccmni3', at:10, rx:100, tx:200 };
            let b = { boot_id:'one', device:'ccmni3', at:12, rx:301, tx:501 };
            printf('%J', [d.traffic_delta(null, b), d.traffic_delta(a, b),
                d.traffic_delta(a, { ...b, boot_id:'two' }),
                d.traffic_delta(a, { ...b, rx:1 }),
                d.traffic_delta(a, { ...b, device:'ccmni4' }),
                d.cpu_percent({total:1000,idle:800}, {total:1100,idle:875}),
                d.ticks('cpu 100 10 30 800 20 4 6 8 99 88')]);
        """)
        self.assertIsNone(value[0])
        self.assertEqual(value[1], {'rx': 100.5, 'tx': 150.5})
        self.assertEqual(value[2:5], [None, None, None])
        self.assertEqual(value[5], 25)
        self.assertEqual(value[6], {'total': 978, 'idle': 820})

    def test_global_ipv6_excludes_link_local_and_ula(self):
        value = self.run_ucode("""
            import * as d from 'lg6851f.dashboard';
            printf('%J', d.global_ipv6({ 'ipv6-address': [
                {address:'fe80::1',mask:64}, {address:'fd00::1',mask:64},
                {address:'2001:db8::1',mask:64} ] }));
        """)
        self.assertEqual(value, ['2001:db8::1/64'])

    def test_cached_radio_readings_are_bound_to_boot_and_have_age(self):
        self.write('/proc/sys/kernel/random/boot_id', 'test-boot')
        path = '/tmp/lg6851f-modem-cells.json'
        self.write(path, json.dumps(dict(boot_id='test-boot', updated=int(time.time()), serving={'output': '+ECELL: 0'})))
        source = "import * as d from 'lg6851f.dashboard'; printf('%J', d.reading('cells'));"
        self.assertFalse(self.run_ucode(source)['stale'])
        self.write(path, json.dumps(dict(boot_id='test-boot', updated=int(time.time()) - 600)))
        self.assertTrue(self.run_ucode(source)['stale'])
        self.write(path, json.dumps(dict(boot_id='old-boot', updated=int(time.time()))))
        self.assertIsNone(self.run_ucode(source))
        self.write(path, '{broken')
        self.assertIsNone(self.run_ucode(source))

    def rpc(self, method, args=None, **overrides):
        # Only replace the external transport/config adapters. Execute the entire
        # production method implementation in the actual ucode interpreter.
        source = (PACKAGE / 'root/usr/share/rpcd/ucode/luci.modem5g').read_text()
        source = source.replace("from 'fs';", "from 'testfs';").replace("from 'uci';", "from 'testuci';")
        source = source.replace("return { 'luci.modem5g': methods };", "export const rpc_methods = methods;")
        self.write('/rpc-under-test.uc', source)
        self.write('/testfs.uc', """
            export function readfile(path) { return path == '/tmp/sysinfo/board_name' ? TEST_BOARD : path == '/proc/sys/kernel/random/boot_id' ? 'test-boot' : ''; }
            export function glob(path) { return []; }
            export function mkdtemp(path) {return '/tmp/test-reading';}
            export function rmdir(path) {return true;}
            export function unlink(path) {delete TEST_CACHE[path];return true;}
            export function open(path, mode, perm) {
                TEST_CACHE[path] = {perm};
                return {write:function(data) { TEST_CACHE[path].data=data; return length(data); }, close:function() { return true; }};
            }
            export function rename(oldpath, newpath) {TEST_CACHE[newpath]=TEST_CACHE[oldpath];delete TEST_CACHE[oldpath];return true;}
            export function popen(command, mode) {
                push(TEST_COMMANDS, command);
                let output = '{}';
                for (let needle, response in TEST_RESPONSES)
                    if (index(command, needle) >= 0) {output=response;break;}
                return { read: function() { return output; }, close: function() { return 0; } };
            }
        """)
        self.write('/testuci.uc', """
            export function cursor() { return {
                load: function() { return true; },
                get_all: function() { return TEST_UCI; },
                get: function(config, section, key) { return TEST_UCI[key]; },
                changes: function() { return TEST_PENDING; },
                set: function(config, section, key, value) { TEST_UCI[key] = value; return true; },
                delete: function(config, section, key) { delete TEST_UCI[key]; return true; },
                commit: function() { TEST_COMMITTED = true; return true; }
            }; }
        """)
        globals = dict(TEST_BOARD='fiberhome,lg6851f', TEST_UCI={'proto': 'ql_datacall', 'password': 'old-secret'},
                       TEST_PENDING={}, TEST_COMMANDS=[], TEST_COMMITTED=False, TEST_CACHE={}, TEST_RESPONSES={}, METHOD=method, ARGS=args or {})
        globals.update(overrides)
        return self.run_ucode("""
            import { rpc_methods } from 'rpc-under-test';
            let result = rpc_methods[METHOD].call({args: ARGS});
            printf('%J', {result, config:TEST_UCI, committed:TEST_COMMITTED, commands:TEST_COMMANDS, cache:TEST_CACHE});
        """, **globals)

    @staticmethod
    def apn(**updates):
        values = dict(apn='example.net', iptype=3, auth=0, username='', password='', mtu=1500,
                      auto_conf=False, clear_password=False)
        values.update(updates)
        return values

    def test_apn_reads_never_return_password_and_match_proto_defaults(self):
        result = self.rpc('get_apn')['result']
        self.assertNotIn('password', result)
        self.assertTrue(result['password_set'])
        self.assertEqual((result['auto_conf'], result['mtu']), (1, 1500))
        result = self.rpc('get_network')['result']
        self.assertNotIn('old-secret', result['config'])
        self.assertIn("network.modem5g.iptype='3'", result['config'])

    def test_dashboard_does_not_open_vendor_command_channels(self):
        result = self.rpc('get_dashboard')
        self.assertNotIn('password', result['result']['apn'])
        self.assertTrue(result['result']['cached_modem_stale'])
        self.assertTrue(result['commands'])
        for command in result['commands']:
            self.assertNotIn('mipc', command)
            self.assertNotIn('modem5g-at', command)
            self.assertNotIn('lg6851f-modem-lock', command)

    def test_explicit_cell_query_publishes_private_snapshot(self):
        result = self.rpc('get_cells', TEST_RESPONSES={
            'network.interface.modem5g': '{"up":true,"uptime":120}',
            'AT+ECELL': '+ECELL: 0\r\nOK',
            'AT+EINFO?': '+EINFO: 0\r\nOK',
        })
        cache = result['cache']['/tmp/lg6851f-modem-cells.json']
        self.assertEqual(cache['perm'], 0o600)
        data = json.loads(cache['data'])
        self.assertEqual(data['serving']['output'], '+ECELL: 0\r\nOK')
        self.assertEqual(data['boot_id'], 'test-boot')
        self.assertGreater(data['updated'], 0)

    def test_new_writable_bands_and_read_only_n76(self):
        result = self.rpc('set_band_lock', dict(lte=[46], nr=[75]))
        self.assertEqual(result['result']['code'], 0)
        self.assertIn("'apply-bands' '46' '75'", result['commands'][0])
        result = self.rpc('set_band_lock', dict(lte=[46], nr=[76]))
        self.assertEqual(result['result']['code'], 95)
        self.assertEqual(result['commands'], [])

    def test_partial_band_read_does_not_replace_cache(self):
        result = self.rpc('get_locks', TEST_RESPONSES={
            'network.interface.modem5g': '{"up":true,"uptime":120}',
            'lg6851f-modem-lock': 'get band mode success!\nlte band info = 0000000500000000\nnr band info = 000000000000000000002000\nget band mode error!',
        })
        self.assertEqual(result['result']['code'], 5)
        self.assertEqual(result['cache'], {})

    def test_save_preserves_password_and_does_not_apply(self):
        result = self.rpc('set_apn', dict(values=self.apn(), apply=False))
        self.assertEqual(result['result']['code'], 0)
        self.assertEqual(result['config']['password'], 'old-secret')
        self.assertEqual(result['commands'], [])
        self.assertTrue(result['committed'])

    def test_apply_and_explicit_password_clear(self):
        result = self.rpc('set_apn', dict(values=self.apn(clear_password=True), apply=True))
        self.assertNotIn('password', result['config'])
        self.assertEqual(result['result']['code'], 0)
        self.assertEqual(len(result['commands']), 1)
        self.assertIn("'/sbin/ifup' 'modem5g'", result['commands'][0])

    def test_invalid_apn_pending_changes_and_wrong_board_do_not_write(self):
        cases = [
            (dict(values=self.apn(apn='x; reboot')), {}, 22),
            (dict(values=self.apn(mtu=2000)), {}, 22),
            (dict(values=self.apn(password='bad\nvalue')), {}, 22),
            (dict(values=self.apn()), dict(TEST_PENDING={'network': [['set', 'lan', 'ipaddr', '192.0.2.1']]}), 16),
            (dict(values=self.apn()), dict(TEST_BOARD='other,board'), 95),
            (dict(values=self.apn()), dict(TEST_UCI={'proto': 'dhcp'}), 95),
        ]
        for args, options, code in cases:
            with self.subTest(code=code, options=options):
                result = self.rpc('set_apn', args, **options)
                self.assertEqual(result['result']['code'], code)
                self.assertFalse(result['committed'])
                self.assertEqual(result['commands'], [])


if __name__ == '__main__':
    unittest.main()
