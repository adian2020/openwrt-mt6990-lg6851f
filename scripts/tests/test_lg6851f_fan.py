#!/usr/bin/env python3
"""Exercise PWM status with an isolated fs module; never access real hardware."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'package/vendor/luci-app-pwmfan'


class FanStatusTest(unittest.TestCase):
    def test_direct_menu_and_hidden_legacy_redirect(self):
        menu = json.loads((PACKAGE/'root/usr/share/luci/menu.d/luci-app-pwmfan.json').read_text())
        self.assertEqual(menu['admin/pwmfan']['action'], dict(type='view', path='pwmfan/panel_v8'))
        self.assertNotIn('title', menu['admin/pwmfan/control'])
        self.assertEqual(menu['admin/pwmfan/control']['action'], dict(type='alias', path='admin/pwmfan'))

    def test_dashboard_can_only_read_fan_status(self):
        modem=ROOT/'package/vendor/luci-app-5gmodem'
        acl=json.loads((modem/'root/usr/share/rpcd/acl.d/luci-app-5gmodem.json').read_text())['luci-app-5gmodem']
        self.assertEqual(acl['read']['ubus']['luci.pwmfan'], ['get_status'])
        self.assertNotIn('luci.pwmfan', acl['write']['ubus'])
        self.assertIn('+luci-app-pwmfan', (modem/'Makefile').read_text())

    def test_shared_mode_reader_distinguishes_actual_output_and_pending_request(self):
        source=PACKAGE/'htdocs/luci-static/resources/pwmfan/visual_v1.js'
        script="""
const fs=require('fs'),source=fs.readFileSync(process.argv[1],'utf8');
const f=new Function('baseclass','rpc',source)({extend:x=>x},{declare:()=>()=>{throw Error('No real RPC in parser test');}});
const rows=JSON.parse(process.argv[2]);console.log(JSON.stringify(rows.map(f.describe)));
"""
        cases=[dict(available=True,manual_pwm=220,controller='fan_type=3wire\nstatus=automatic\nspeed_point=low-10khz\n'),
               dict(available=True,pwm=100,controller='fan_type=4wire\nstatus=manual\nactive=pwm5\npwm5=180\n'),
               dict(available=True,pwm=100,controller='status=automatic\ndirection=inverse\n'),
               dict(available=True,stalled=True,pwm=180,controller='status=manual\n'),
               dict(available=True,controller='fan_type=3wire\nstatus=register-failsafe\nspeed_point=high-10khz\n'),
               dict(available=False,pwm=220)]
        run=subprocess.run(['node','-e',script,str(source),json.dumps(cases)],capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stderr)
        rows=json.loads(run.stdout)
        self.assertEqual([r['level'] for r in rows],[0,1,2,None,None,None])
        self.assertEqual(rows[0]['name'],'安静')
        self.assertEqual(rows[3]['name'],'已停止')
        self.assertEqual(rows[5]['name'],'未获取')

    def test_status_reports_only_allowed_manual_targets_without_writing_hardware(self):
        ucode = os.environ.get('UCODE') or shutil.which('ucode')
        self.assertTrue(ucode, 'Run with UCODE and UCODE_LIBRARY pointing at the native host build')
        source = (PACKAGE/'root/usr/share/rpcd/ucode/luci.pwmfan').read_text()
        source = source.replace("from 'fs'", "from 'fan_test_fs'").replace("return { 'luci.pwmfan': methods };", "export const object = { 'luci.pwmfan': methods };")
        with tempfile.TemporaryDirectory() as name:
            folder = pathlib.Path(name)
            (folder/'fan.uc').write_text(source)
            (folder/'fan_test_fs.uc').write_text('''
export function readfile(path) { return MOCKFS[path] ?? null; }
export function writefile() { die('Status getter must never write hardware or configuration'); }
export function glob(path) { return path=='/sys/class/hwmon/hwmon*' ? ['/sys/class/hwmon/hwmon0'] : []; }
''')
            (folder/'test.uc').write_text("import {object} from 'fan';printf('%J',object['luci.pwmfan'].get_status.call());")
            for manual, expected in [('115\n', 115), ('180\n', 180), ('220\n', 220), ('\n', None), ('20\n', None), ('garbage', None), (None, None)]:
                with self.subTest(manual=manual):
                    data={'/tmp/sysinfo/board_name':'fiberhome,lg6851f\n',
                          '/sys/class/hwmon/hwmon0/name':'pwmfan\n',
                          '/sys/class/hwmon/hwmon0/pwm1':'115\n',
                          '/tmp/lg6851f-fan-control.manual':manual}
                    cmd=[ucode, '-L', name, '-L', os.environ['UCODE_LIBRARY'], '-D', 'MOCKFS='+json.dumps(data), str(folder/'test.uc')]
                    run=subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    result=json.loads(run.stdout)
                    self.assertEqual(result['manual_pwm'], expected)
                    self.assertEqual(result['pwm'], 115)  # Applied output stays distinct from the requested target.


if __name__ == '__main__':
    unittest.main()
