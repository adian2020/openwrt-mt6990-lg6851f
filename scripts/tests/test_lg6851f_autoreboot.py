"""执行真实计划生成逻辑；只用临时crontab，不执行重启。"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'package/vendor/luci-app-autoreboot'


class AutoRebootTest(unittest.TestCase):
    def apply(self, schedules, previous='', action='start_service'):
        with tempfile.TemporaryDirectory() as name:
            root = pathlib.Path(name)
            (root/'bin').mkdir()
            (root/'crontab').write_text(previous)
            crontab = root/'bin/crontab'
            crontab.write_text('#!/bin/sh\nif [ "$1" = -l ]; then cat "$TEST_ROOT/crontab"; else cp "$1" "$TEST_ROOT/crontab"; fi\n')
            crontab.chmod(0o755)
            source = (PACKAGE/'root/etc/init.d/autoreboot').read_text().replace('/var/lock/autoreboot.lock', str(root/'lock')).replace('/tmp/autoreboot.XXXXXX', str(root/'autoreboot.XXXXXX'))
            config = '\nconfig_load() { :; }\nlogger() { :; }\n'
            config += 'config_foreach() {\n'
            for i in range(len(schedules)):
                config += f' "$1" schedule{i}\n'
            config += ' return 0;\n}\n'
            config += 'config_get() {\n case "$2:$3" in\n'
            for i, schedule in enumerate(schedules):
                for key, value in schedule.items():
                    # JSON strings are test data passed via environment, not shell code.
                    envkey = f'VALUE_{i}_{key}'
                    config += f' schedule{i}:{key}) export "$1=${{{envkey}}}";;\n'
            config += ' *) export "$1=${4:-}";;\n esac\n}\nconfig_get_bool() { config_get "$@"; }\n'
            script = root/'script'
            script.write_text(source+config+'\n'+action+'\n')
            env = dict(os.environ, TEST_ROOT=name, PATH=str(root/'bin')+':'+os.environ['PATH'])
            for i, schedule in enumerate(schedules):
                for key, value in schedule.items():
                    env[f'VALUE_{i}_{key}'] = str(value)
            result = subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True)
            self.assertFalse(list(root.glob('autoreboot.*')), '临时计划必须清理')
            return result.returncode, (root/'crontab').read_text()

    def schedule(self, **updates):
        return dict(enabled='1', minute='15', hour='3', day='*', month='*', week='1-5', **updates)

    def test_default_off_and_system_menu(self):
        self.assertIn("option enabled '0'", (PACKAGE/'root/etc/config/autoreboot').read_text())
        menu = json.loads((PACKAGE/'root/usr/share/luci/menu.d/luci-app-autoreboot.json').read_text())
        self.assertEqual(menu['admin/system/autoreboot']['action']['path'], 'autoreboot')
        self.assertEqual(self.apply([{'enabled':'0'}], '7 * * * * other-job\n'), (0, '7 * * * * other-job\n'))

    def test_enabled_schedule_keeps_unrelated_jobs(self):
        old = '7 * * * * other-job\n0 2 * * 0 /sbin/reboot #autoreboot_old\n'
        code, cron = self.apply([self.schedule()], old)
        self.assertEqual(code, 0)
        self.assertEqual(cron, '7 * * * * other-job\n15 3 * * 1-5 sleep 5 && /sbin/reboot #autoreboot_schedule0\n')

    def test_multiple_schedules_and_reload_replace_owned_rows(self):
        schedules = [self.schedule(), {**self.schedule(), 'minute':'*/15', 'hour':'0,12'}]
        code, cron = self.apply(schedules, '0 0 * * * /sbin/reboot #autoreboot_previous\n', 'reload_service')
        self.assertEqual(code, 0)
        self.assertEqual(len(cron.splitlines()), 2)
        self.assertIn('*/15 0,12 * * 1-5', cron)

    def test_invalid_config_preserves_previous_schedule(self):
        previous = '0 2 * * 0 /sbin/reboot #autoreboot_old\n'
        for updates in [{'minute':'60'}, {'hour':'24'}, {'week':'6-1'}, {'month':'0'}, {'day':'32'}, {'minute':'*/0'}, {'minute':'0\n* * * * /bin/false'}, {'hour':'$(false)'}]:
            with self.subTest(updates=updates):
                code, cron = self.apply([{**self.schedule(), **updates}], previous, 'reload_service')
                self.assertNotEqual(code, 0)
                self.assertEqual(cron, previous)

    def test_disable_or_stop_removes_only_owned_entries(self):
        old = '7 * * * * other-job\n0 2 * * 0 /sbin/reboot #autoreboot_old\n'
        for action in ['start_service', 'stop_service']:
            self.assertEqual(self.apply([{'enabled':'0'}], old, action), (0, '7 * * * * other-job\n'))


if __name__ == '__main__':
    unittest.main()
