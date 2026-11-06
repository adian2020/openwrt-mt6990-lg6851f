#!/usr/bin/env python3
"""Exercise upgrade overlay migration on temporary directories, never a device."""
import pathlib
import subprocess
import tempfile
import unittest

HELPER = pathlib.Path(__file__).resolve().parents[2] / 'target/linux/mediatek/mt6990/base-files/lib/functions/lg6851f-upgrade-state.sh'

class UpgradeStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        for name in ('upper/etc/config', 'upper/usr/bin', 'work', 'openwrt-sysupgrade'):
            (self.root / name).mkdir(parents=True)
        (self.root / '.mt6990-extroot-managed').write_text('old-root\n')
        (self.root / 'upper/usr/bin/old-plugin').write_text('old executable')
        (self.root / 'upper/etc/config/network').write_text('old network')
        (self.root / 'upper/etc/config/lg6851f_network_led').write_text("config main 'main'\n option enabled '1'\n")
        (self.root / 'upper/etc/config/system').write_text("package system\nconfig system 'system'\n option hostname 'old'\nconfig led 'wifi'\n option name 'WiFi'\nconfig system 'other'\n option timezone 'old'\n")
        (self.root / 'openwrt-sysupgrade/sysupgrade.tgz').write_bytes(b'backup')

    def migrate(self, mode='reset', uuid='new-root'):
        return subprocess.run(['sh', '-c', '. "$1"; uci() { cat "$2/system"; }; lg6851f_fresh_upgrade_upper "$2" "$3" "$4"', 'test', str(HELPER), str(self.root), uuid, mode], capture_output=True, text=True)

    def test_reset_removes_active_plugins_and_config_but_retains_only_leds(self):
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'upper/usr/bin/old-plugin').exists())
        self.assertFalse((self.root / 'upper/etc/config/network').exists())
        self.assertTrue((self.root / 'upper/etc/config/lg6851f_network_led').exists())
        fragment = (self.root / 'upper/etc/lg6851f-system-leds.pending').read_text()
        self.assertIn("config led 'wifi'", fragment)
        self.assertNotIn('hostname', fragment)
        self.assertNotIn('timezone', fragment)
        self.assertFalse((self.root / 'openwrt-sysupgrade/sysupgrade.tgz').exists())
        self.assertTrue((self.root / 'openwrt-extroot-backups/upgrade-new-root/upper/usr/bin/old-plugin').exists())

    def test_keep_stages_only_backup_and_not_old_program_layer(self):
        self.assertEqual(self.migrate('keep').returncode, 0)
        self.assertTrue((self.root / 'openwrt-sysupgrade/sysupgrade.tgz').exists())
        self.assertFalse((self.root / 'upper/usr/bin/old-plugin').exists())

    def test_repeat_upgrade_keeps_previous_archive(self):
        self.assertEqual(self.migrate().returncode, 0)
        self.assertEqual(self.migrate().returncode, 0)
        self.assertTrue((self.root / 'openwrt-extroot-backups/upgrade-new-root').is_dir())
        self.assertTrue((self.root / 'openwrt-extroot-backups/upgrade-new-root-next').is_dir())

    def test_invalid_mode_or_uuid_is_rejected_without_changes(self):
        for mode, uuid in [('unknown', 'new-root'), ('reset', '../elsewhere')]:
            self.assertNotEqual(self.migrate(mode, uuid).returncode, 0)
            self.assertTrue((self.root / 'upper/usr/bin/old-plugin').exists())

    def test_unmanaged_partition_is_never_changed(self):
        (self.root / '.mt6990-extroot-managed').unlink()
        self.assertNotEqual(self.migrate().returncode, 0)
        self.assertTrue((self.root / 'upper/usr/bin/old-plugin').exists())

if __name__ == '__main__':
    unittest.main()
