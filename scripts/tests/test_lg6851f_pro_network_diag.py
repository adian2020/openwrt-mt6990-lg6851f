#!/usr/bin/env python3
"""Run the boot sampler against a temporary filesystem and fake read-only RPCs."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'package/lg6851f/pro-material/pro-network-diag.sh'
BOOT_ID = '9c6d3502-be7b-4d4f-81da-0b4951d1d320'


class NetworkDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shared = self.root / 'p46'
        self.shared.mkdir()
        self.archive = self.shared / 'lg6851f-pro-network-diag'
        self.report = self.archive / f'boot-{BOOT_ID}.txt'
        self.write('tmp/sysinfo/board_name', 'fiberhome,lg6851f\n')
        device = 'sys/class/block/mmcblk0p46/'
        self.write(device + 'partition', '46\n')
        self.write(device + 'size', '5187456\n')
        self.write(device + 'uevent', 'PARTNAME=user_data\n')
        self.write(device + 'dev', '259:14\n')
        self.write('proc/sys/kernel/random/boot_id', BOOT_ID + '\n')
        self.write('proc/uptime', '45.20 65.32\n')
        self.write('proc/cmdline', 'bootslot=b root=/dev/mmcblk0p39\n')
        self.write('etc/mt6990-firmware-id', 'a' * 40 + '\n')
        self.write('sys/class/net/eth0/carrier', '1\n')
        self.write('tmp/lg6851f-vendor618-boot.log', 'STAGE load mt7990\nconfiguration-key\n')
        self.set_mount('rw', 'rw')
        for command, body in {
            'sleep': ':', 'sync': ':', 'dmesg': 'echo "eth0: fixture link event"',
            'logread': ':', 'jsonfilter': 'echo true',
            'ubus': 'case "$*" in *" status "*) echo "{secret:fake-password}";; *) exit 97;; esac',
        }.items():
            self.write('bin/' + command, '#!/bin/sh\n' + body + '\n').chmod(0o755)
        source = re.sub(r'/(?:proc|sys|etc|tmp)/', lambda match: str(self.root) + match[0], SCRIPT.read_text())
        self.script = self.write('sampler', source)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def set_mount(self, options, super_options):
        self.write('proc/self/mountinfo',
                   f'42 22 259:14 / {self.shared} {options} - ext4 /dev/alias {super_options}\n')

    def run_sampler(self):
        return subprocess.run(['sh', self.script], capture_output=True, text=True,
                              env=dict(os.environ, PATH=f'{self.root}/bin:' + os.environ['PATH']))

    def test_records_five_samples_without_exposing_configuration_and_keeps_eight_boots(self):
        self.archive.mkdir()
        for number in range(10):
            (self.archive / f'boot-00000000-0000-0000-0000-{number:012x}.txt').touch()
        result = self.run_sampler()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.report.read_text()
        self.assertEqual(record.count('=== sample uptime='), 5)
        for text in ('bootslot=b', 'root=/dev/mmcblk0p39', 'carrier=1', 'phydev=unavailable',
                     'network.wireless rc=0', 'STAGE load mt7990', 'eth0: fixture link event'):
            self.assertIn(text, record)
        self.assertNotIn('configuration-key', record)
        self.assertNotIn('fake-password', record)
        self.assertEqual(len(list(self.archive.glob('boot-*.txt'))), 8)
        self.assertEqual(self.report.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_sampler().returncode, 0)
        self.assertEqual(self.report.read_text(), record)

    def test_rejects_wrong_partition(self):
        self.write('sys/class/block/mmcblk0p46/uevent', 'PARTNAME=another\n')
        self.assertEqual(self.run_sampler().returncode, 95)
        self.assertFalse(self.archive.exists())

    def test_rejects_read_only_filesystem(self):
        self.set_mount('rw', 'ro')
        self.assertEqual(self.run_sampler().returncode, 75)
        self.assertFalse(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
