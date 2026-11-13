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
        self.assertEqual(menu['admin/pwmfan']['action'], dict(type='view', path='pwmfan/panel_v7'))
        self.assertNotIn('title', menu['admin/pwmfan/control'])
        self.assertEqual(menu['admin/pwmfan/control']['action'], dict(type='alias', path='admin/pwmfan'))

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
