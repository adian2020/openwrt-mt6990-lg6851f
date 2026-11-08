#!/usr/bin/env python3
"""运行真实查询脚本；用本地假程序代替模组，并检查菜单与锁关闭时序。"""
import fcntl
import os
import pathlib
import shlex
import subprocess
import tempfile
import threading
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
        sample.write_text('#!/bin/sh\nwhile IFS= read -r line; do echo "$line"; [ "$line" != -1 ] || break; done > ' + shlex.quote(str(self.root / 'input')) + '\nprintf "mock getter\\n"\nexit "$TEST_STATUS"\n')
        sample.chmod(0o700)
        cooldown = self.root / 'cooldown'
        cooldown.write_text('#!/bin/sh\n[ "$1" != 1 ] || { /bin/sleep 0.03; exit; }\nif /usr/bin/flock -n ' + shlex.quote(str(self.root / 'lock')) +
                            ' -c true; then echo released; else echo held; fi > ' + shlex.quote(str(self.root / 'cooldown-state')) + '\n')
        cooldown.chmod(0o700)
        # 只允许目标 BusyBox 支持的选项，避免主机 util-linux 掩盖兼容问题。
        flock = self.root / 'flock'
        flock.write_text('#!/bin/sh\ncase "$1" in -n|-u) exec /usr/bin/flock "$@";; *) echo unsupported-option >&2; exit 64;; esac\n')
        flock.chmod(0o700)
        source = HELPER.read_text().replace('/tmp/sysinfo/board_name', str(self.root / 'board'))
        source = source.replace('/usr/bin/flock', str(flock))
        source = source.replace('/usr/bin/sample_nw', str(sample)).replace('/var/lock/luci-modem5g-control.lock', str(self.root / 'lock'))
        source = source.replace('/bin/sleep', str(cooldown))
        source = source.replace('/tmp/lg6851f-modem-control.active', str(self.root/'control.active'))
        source = source.replace('/var/lock/lg6851f-modem-recovery.lock', str(self.root/'recovery.lock'))
        self.script = self.root / 'wrapper'
        self.script.write_text(source)

    def run_helper(self, status=0, args=()):
        return subprocess.run(['sh', str(self.script), *args], env=dict(os.environ, TEST_STATUS=str(status)), text=True, capture_output=True)

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

    def test_busy_channel_can_be_acquired_after_owner_releases(self):
        with (self.root / 'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = threading.Timer(0.15, lambda: fcntl.flock(lock, fcntl.LOCK_UN))
            release.start()
            try:
                self.assertEqual(self.run_helper().returncode, 0)
            finally:
                release.join()
        self.assertTrue((self.root / 'input').exists())

    def test_background_bler_unregisters_before_release(self):
        result=self.run_helper(args=('--with-bler',))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.root/'input').read_text().splitlines(),['0','7','21','25','5','33','45','1','45','0','1','-1'])
        self.assertEqual((self.root/'cooldown-state').read_text().strip(),'held')

    def test_failed_background_session_attempts_cleanup_and_keeps_failure(self):
        result=self.run_helper(74,args=('--with-bler',))
        self.assertEqual(result.returncode,74,result.stderr)
        self.assertEqual((self.root/'input').read_text().splitlines(),['0','45','0','1','-1'])
        self.assertEqual((self.root/'cooldown-state').read_text().strip(),'held')

    def test_background_collection_yields_to_user_control(self):
        (self.root/'control.active').touch()
        self.assertEqual(self.run_helper(args=('--with-bler',)).returncode,75)
        self.assertFalse((self.root/'input').exists())

if __name__ == '__main__':
    unittest.main()
