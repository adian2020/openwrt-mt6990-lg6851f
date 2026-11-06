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
                let output = '{}', code = 0;
                for (let needle, response in TEST_RESPONSES)
                    if (index(command, needle) >= 0) {
                        output=type(response)=='object' ? response.output : response;
                        code=type(response)=='object' ? response.code : 0;
                        break;
                    }
                return { read: function() { return output; }, close: function() { return code; } };
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
            self.assertNotIn('lg6851f-modem-details', command)

    @staticmethod
    def radio_report():
        return '''ql_nw_init, ret = 00000000
Cmd Index=21
100:main():get nw current band information:
101:main():lte_band = 0
102:main():nr_band = 78
103:main():nr_dl_bandwidth = 100M
104:main():nr_ul_bandwidth = 100M
105:main():nr_dl_arfcn = 640000
106:main():nr_ul_arfcn = 639388
107:main():nr_cqi = 11
108:main():net_ambr_dl = 256000 Kbps
109:main():net_ambr_ul = 12800 Kbps
110:main():ims_ambr_dl = 512000 Kbps
111:main():ims_ambr_ul = 512000 Kbps
Cmd Index=25
get all info success!
pcc_type = NR PCC
pcc_band = 78
pcc_pci = 321
pcc_arfcn = 640000
pcc_dl_bandwidth = 11
pcc_ul_bandwidth = 11
pcc_dl_mcs = 0
pcc_ul_mcs = 28
pcc_dl_modulation = 1
pcc_ul_modulation = 1
pcc_dl_mimo = 2
pcc_ul_mimo = 2
Cmd Index=33
get endc status success...
endc_available = 0
dcnr_restricted = 0
Cmd Index=1
ql_nw_release success, ret = 00000000
'''

    def parse_radio(self, report):
        return self.run_ucode("import * as r from 'lg6851f.radio'; printf('%J',r.parse(REPORT));", REPORT=report)

    def test_radio_units_zero_mcs_and_distinct_ims_ambr(self):
        data = self.parse_radio(self.radio_report())
        self.assertTrue(data['complete'])
        self.assertEqual(len(data['carriers']), 1)
        row = data['carriers'][0]
        self.assertEqual((row['dl_bandwidth_mhz'], row['ul_bandwidth_mhz']), (100, 100))
        self.assertEqual((row['dl_mcs'], row['ul_mcs']), (0, 28))
        self.assertEqual(data['ambr']['network']['ul']['bps'], 12800000)
        self.assertEqual(data['ambr']['ims']['ul']['bps'], 512000000)
        self.assertEqual(row['dl_modulation_code'], 1)
        self.assertEqual(row['cqi'], 11)
        self.assertIsNone(data['qci'])
        self.assertIsNone(data['sa_nsa'])
        self.assertEqual(data['endc'], {'available': 0, 'restricted': 0})

    def test_repeated_scc_rows_never_inherit_primary_fields(self):
        extra = '''scc_type = NR SCC
scc_band = 41
scc_pci = 111
scc_arfcn = 520000
scc_dl_bandwidth = 11
scc_dl_mcs = 9
scc_type = NR SCC
scc_band = 78
scc_pci = 222
scc_arfcn = 640000
scc_dl_bandwidth = 11
'''
        data = self.parse_radio(self.radio_report().replace('Cmd Index=33', extra+'Cmd Index=33'))
        self.assertEqual(len(data['carriers']), 3)
        for row in data['carriers'][1:]:
            self.assertIsNone(row['ul_mcs'])
            self.assertIsNone(row['dl_bandwidth_mhz'])
            self.assertIsNone(row['cqi'])
        self.assertEqual(data['carriers'][1]['dl_mcs'], 9)
        self.assertIsNone(data['carriers'][2]['dl_mcs'])

    def test_radio_missing_units_and_enum_codes_are_not_mhz(self):
        report = self.radio_report().replace('100M', '11').replace('12800 Kbps', '12800 unknown')
        data = self.parse_radio(report)
        self.assertIsNone(data['carriers'][0]['dl_bandwidth_mhz'])
        self.assertEqual(data['carriers'][0]['dl_bandwidth_code'], 11)
        self.assertIsNone(data['ambr']['network']['ul']['bps'])
        self.assertIsNone(self.parse_radio('')['endc']['available'])

    def test_mode_requires_successful_current_data_registration(self):
        registration='''Cmd Index=7
3444:main():ret= 00000000
502:print_nw_reg_status():tech_domain = 3GPP
503:print_nw_reg_status():radio_tech = QL_NW_RADIO_TECH_NR5G
505:print_nw_reg_status():reg_state = QL_NW_SERVICE_FULL
'''
        report=self.radio_report().replace('Cmd Index=21',registration+'Cmd Index=21')
        self.assertEqual(self.parse_radio(report)['sa_nsa'],'SA')
        self.assertEqual(self.parse_radio(report.replace('TECH_NR5G','TECH_NSA5G'))['sa_nsa'],'NSA')
        self.assertIsNone(self.parse_radio(report.replace('ret= 00000000','ret= 80000001'))['sa_nsa'])
        self.assertIsNone(self.parse_radio(report.replace('SERVICE_FULL','SERVICE_SEARCHING'))['sa_nsa'])
        self.assertIsNone(self.parse_radio(report.replace('TECH_NR5G','TECH_LTE'))['sa_nsa'])

    def test_explicit_radio_query_caches_complete_data_only(self):
        replies = {'network.interface.modem5g': '{"up":true,"uptime":120}',
                   'lg6851f-modem-details': self.radio_report()}
        result = self.rpc('get_radio_details', TEST_RESPONSES=replies)
        cache = result['cache']['/tmp/lg6851f-modem-radio-details.json']
        self.assertEqual(cache['perm'], 0o600)
        data = json.loads(cache['data'])
        self.assertTrue(data['parsed']['complete'])
        self.assertEqual(data['parsed']['carriers'][0]['dl_mcs'], 0)
        replies['lg6851f-modem-details'] = self.radio_report().replace('get all info success!', 'get ca failed')
        result = self.rpc('get_radio_details', TEST_RESPONSES=replies)
        self.assertEqual(result['result']['code'], 5)
        self.assertEqual(result['cache'], {})
        replies['lg6851f-modem-details'] = {'output': 'channel busy', 'code': 75}
        result = self.rpc('get_radio_details', TEST_RESPONSES=replies)
        self.assertEqual(result['result']['code'], 75)
        self.assertEqual(result['cache'], {})

    def test_initializing_radio_query_never_opens_vendor_session(self):
        result = self.rpc('get_radio_details')
        self.assertEqual(result['result']['code'], 11)
        self.assertFalse(any('lg6851f-modem-details' in row for row in result['commands']))

    def test_dashboard_exposes_radio_snapshot_with_zero_mcs_and_age(self):
        self.write('/proc/sys/kernel/random/boot_id', 'test-boot')
        self.write('/tmp/lg6851f-modem-radio-details.json', json.dumps({
            'boot_id': 'test-boot', 'updated': int(time.time()), 'parsed': self.parse_radio(self.radio_report())}))
        data = self.run_ucode("import * as d from 'lg6851f.dashboard'; printf('%J',d.snapshot());")
        self.assertFalse(data['radio_details']['stale'])
        self.assertEqual(data['advanced']['mcs'][0]['dl'], 0)
        self.assertEqual(data['advanced']['ambr']['network']['ul']['bps'], 12800000)
        self.assertIsNone(data['advanced']['qci'])
        self.assertIsNone(data['advanced']['sa_nsa'])

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
        result = self.rpc('set_band_lock', dict(lte=[1], nr=[75]))
        self.assertEqual(result['result']['code'], 0)
        self.assertIn("'apply-bands' '1' '75'", result['commands'][0])
        result = self.rpc('set_band_lock', dict(lte=[1], nr=[76]))
        self.assertEqual(result['result']['code'], 95)
        self.assertEqual(result['commands'], [])
        result = self.rpc('set_band_lock', dict(lte=[46], nr=[75]))
        self.assertEqual(result['result']['code'], 95)
        self.assertEqual(result['commands'], [])

    def test_radio_rpc_always_uses_shared_verified_control(self):
        for enabled in [True, False]:
            result = self.rpc('set_radio', dict(enabled=enabled))
            self.assertEqual(result['result']['code'], 0)
            self.assertEqual(len(result['commands']), 1)
            self.assertIn("'/usr/bin/lg6851f-radio-control' '"+str(int(enabled))+"'",result['commands'][0])
            self.assertNotIn('nw_radio_state_set',result['commands'][0])

    def test_cell_lock_rejects_wrong_pci_and_non_device_bands(self):
        for rat,band,pci in [('nr',78,'1008'),('lte',1,'504'),('nr',79,'1'),('lte',46,'1'),('nr',76,'1')]:
            with self.subTest(rat=rat,band=band,pci=pci):
                result=self.rpc('set_cell_lock',dict(rat=rat,band=band,pci=pci,arfcn=640000))
                self.assertNotEqual(result['result']['code'],0)
                self.assertEqual(result['commands'],[])
        for rat,band,arfcn in [('nr',78,640000),('lte',1,100)]:
            result=self.rpc('set_cell_lock',dict(rat=rat,band=band,pci='0',arfcn=arfcn))
            self.assertEqual(result['result']['code'],0)
            self.assertIn("'set-cell'",result['commands'][0])

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
