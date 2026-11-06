#!/usr/bin/env python3
"""运行真实查询脚本；用本地假程序代替模组，并检查菜单与锁关闭时序。"""
import fcntl
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'package/vendor/lg6851f-modem-chain-only/files/usr/bin/lg6851f-modem-details'


class ReadOnlyDetailsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'board').write_text('fiberhome,lg6851f\n')
        sample = self.root / 'sample'
        sample.write_text('#!/bin/sh\ncat > ' + shlex.quote(str(self.root / 'input')) + '\nprintf "mock getter\\n"\nexit "$TEST_STATUS"\n')
        sample.chmod(0o700)
        cooldown = self.root / 'cooldown'
        cooldown.write_text('#!/bin/sh\nif /usr/bin/flock -n ' + shlex.quote(str(self.root / 'lock')) +
                            ' -c true; then echo released; else echo held; fi > ' + shlex.quote(str(self.root / 'cooldown-state')) + '\n')
        cooldown.chmod(0o700)
        source = HELPER.read_text().replace('/tmp/sysinfo/board_name', str(self.root / 'board'))
        source = source.replace('/usr/bin/sample_nw', str(sample)).replace('/var/lock/luci-modem5g-control.lock', str(self.root / 'lock'))
        source = source.replace('/bin/sleep', str(cooldown))
        self.script = self.root / 'wrapper'
        self.script.write_text(source)

    def run_helper(self, status=0):
        return subprocess.run(['sh', str(self.script)], env=dict(os.environ, TEST_STATUS=str(status)), text=True, capture_output=True)

    def test_only_verified_getters_and_lock_held_through_cooldown(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'input').read_text().splitlines(), ['0', '7', '21', '25', '5', '33', '1', '-1'])
        self.assertEqual((self.root / 'cooldown-state').read_text().strip(), 'held')
        self.assertEqual(subprocess.run(['/usr/bin/flock', '-n', str(self.root / 'lock'), '-c', 'true']).returncode, 0)

    def test_vendor_error_is_preserved_after_cooldown(self):
        self.assertEqual(self.run_helper(74).returncode, 74)
        self.assertEqual((self.root / 'cooldown-state').read_text().strip(), 'held')

    def test_busy_channel_never_starts_sample(self):
        with (self.root / 'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_helper().returncode, 75)
        self.assertFalse((self.root / 'input').exists())

    def test_other_board_never_starts_sample(self):
        (self.root / 'board').write_text('other,board')
        self.assertEqual(self.run_helper().returncode, 95)
        self.assertFalse((self.root / 'input').exists())


if __name__ == '__main__':
    unittest.main()
