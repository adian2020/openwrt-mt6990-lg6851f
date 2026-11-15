#!/usr/bin/env python3
"""Exercise the real shared-P46 archive and standalone reader without devices."""
import gzip
import os
import pathlib
import re
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT/'target/linux/mediatek/mt6990/base-files/usr/bin/lg6851f-archive-ab-report'
COLLECTOR = ROOT/'scripts/lg6851f-collect-ab-failure.sh'

class SharedFixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
  self.root=pathlib.Path(self.temp.name)
  for path in ['p46','overlay','tmp/sysinfo','proc/sys/kernel/random','proc/self','sys/class/block/mmcblk0p46','sys/fs/pstore','bin','etc']:
   (self.root/path).mkdir(parents=True)
  self.dev=self.root/'sys/class/block/mmcblk0p46'
  for name,value in [('partition','46'),('size','5187456'),('uevent','PARTNAME=user_data'),('dev','259:14')]:
   (self.dev/name).write_text(value+'\n')
  (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f')
  (self.root/'proc/cmdline').write_text('bootslot=a root=/dev/mmcblk0p26\n')
  (self.root/'proc/uptime').write_text('120.0 300.0\n')
  (self.root/'proc/mounts').write_text('pstore /sys/fs/pstore pstore rw 0 0\n')
  (self.root/'etc/mt6990-firmware-id').write_text('fixture-source\n')
  (self.root/'etc/openwrt_release').write_text("DISTRIB_RELEASE='fixture'\n")
  self.mount()
  self.binary('df',"printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999 1 99998 1%% /fixture\\n'")
  self.binary('logger',':')
  self.binary('dmesg',"printf 'fixture kernel without a panic\\n'")
 def binary(self,name,body):
  p=self.root/'bin'/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o700);return p
 def mount(self,options='rw,relatime',mountpoint='p46',device='259:14',fs='ext4',fsroot='/'):
  (self.root/'proc/self/mountinfo').write_text(f'42 22 {device} {fsroot} {self.root/mountpoint} {options} - {fs} /dev/block/by-name/user_data {options}\n')
 def fixture_script(self,text):
  return re.sub(r'/(?:tmp|proc|sys|etc)/',lambda match:str(self.root/match[0].strip('/'))+'/',text)
 def run_script(self,path,index=1):
  (self.root/'proc/sys/kernel/random/boot_id').write_text(f'12345678-1234-1234-1234-{index:012x}')
  return subprocess.run(['sh',str(path)],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH']),capture_output=True,text=True)

class ArchiveTest(SharedFixture):
 def setUp(self):
  super().setUp()
  self.collector=self.binary('collect','printf "fixture boot and crash evidence\\n" > '+str(self.root/'tmp/lg6851f-ab-failure.txt'))
  text=self.fixture_script(SOURCE.read_text()).replace('/usr/bin/lg6851f-collect-ab-failure',str(self.collector)).replace('\nsync\n','\n:\n')
  self.run=self.root/'run';self.run.write_text(text)
  self.reports=self.root/'p46/lg6851f-ab-reports';self.tool=self.root/'p46/lg6851f-ab-tools/collect-ab-failure.sh'
 def run_report(self,index=1):return self.run_script(self.run,index)
 def test_persist_compress_deduplicate_and_bound_reports(self):
  for i in range(1,11):
   result=self.run_report(i);self.assertEqual(result.returncode,0,result.stderr)
  files=list(self.reports.glob('boot-*.txt.gz'));self.assertEqual(len(files),8)
  for path in files:
   self.assertEqual(gzip.decompress(path.read_bytes()),b'fixture boot and crash evidence\n');self.assertEqual(path.stat().st_mode&0o777,0o600)
  self.assertEqual(self.tool.read_bytes(),self.collector.read_bytes());self.assertEqual(self.tool.stat().st_mode&0o777,0o700)
  before={p.name:p.read_bytes() for p in files};self.assertEqual(self.run_report(10).returncode,0)
  self.assertEqual(before,{p.name:p.read_bytes() for p in files})
 def test_current_report_survives_clock_reset_relative_to_old_files(self):
  for i in range(1,9):self.assertEqual(self.run_report(i).returncode,0)
  for path in self.reports.glob('*.gz'):os.utime(path,(time.time()+999999,time.time()+999999))
  self.assertEqual(self.run_report(9).returncode,0)
  self.assertTrue((self.reports/'boot-12345678-1234-1234-1234-000000000009.txt.gz').exists())
  self.assertEqual(len(list(self.reports.glob('*.gz'))),8)
 def test_wrong_overlay_readonly_partial_or_missing_shared_mount_never_archives(self):
  for kwargs in [dict(options='ro'),dict(mountpoint='overlay',device='7:0'),dict(fsroot='/upper'),dict(fs='tmpfs')]:
   self.mount(**kwargs);self.assertEqual(self.run_report().returncode,75);self.assertFalse(self.reports.exists());self.assertFalse(self.tool.exists())
  (self.root/'proc/self/mountinfo').write_text('')
  self.assertEqual(self.run_report().returncode,75)
 def test_extroot_mount_of_the_real_shared_device_is_accepted(self):
  self.mount(mountpoint='overlay');result=self.run_report();self.assertEqual(result.returncode,0,result.stderr)
  self.assertTrue(list((self.root/'overlay/lg6851f-ab-reports').glob('*.gz')))
  self.assertFalse(self.reports.exists())
 def test_identity_mismatch_never_writes(self):
  for field,bad in [('partition','39'),('size','262144'),('uevent','PARTNAME=rootfs_b')]:
   p=self.dev/field;before=p.read_text();p.write_text(bad+'\n')
   self.assertEqual(self.run_report().returncode,95);self.assertFalse(self.tool.exists());p.write_text(before)
 def test_low_space_and_external_directory_links_are_rejected(self):
  self.binary('df',"printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999 99000 999 99%% /fixture\\n'")
  self.assertEqual(self.run_report().returncode,28);self.assertFalse(self.tool.exists());self.assertFalse(list(self.reports.glob('*.gz')))
  self.reports.rmdir();self.reports.symlink_to(self.root/'overlay',target_is_directory=True)
  self.assertEqual(self.run_report().returncode,22);self.assertFalse(list((self.root/'overlay').iterdir()))
 def test_tool_refreshes_without_replacing_same_boot_report(self):
  self.assertEqual(self.run_report().returncode,0);report=next(self.reports.glob('*.gz'));before=report.read_bytes()
  self.collector.write_text(self.collector.read_text()+'# updated reader\n')
  self.assertEqual(self.run_report().returncode,0);self.assertEqual(report.read_bytes(),before);self.assertEqual(self.tool.read_bytes(),self.collector.read_bytes())

class CollectorTest(SharedFixture):
 def setUp(self):
  super().setUp()
  self.run=self.root/'reader';self.run.write_text(self.fixture_script(COLLECTOR.read_text()))
  runtime=self.root/'p46/MT6990_RUNTIME_LOGS';runtime.mkdir()
  (runtime/'runtime.log').write_text('firmware_id=real-historical-source\nLG6851F_BOOT_STAGE fixture-stage\n')
  (self.root/'p46/lg6851f-ab-reports').mkdir()
  (self.root/'p46/lg6851f-ab-reports/boot-fixture.txt.gz').write_bytes(b'fixture')
  upgrade=self.root/'p46/openwrt-sysupgrade';upgrade.mkdir()
  (upgrade/'upgrade-trace.log').write_text('COMPLETE fixture upgrade\n')
  (self.root/'p46/.mt6990-firmware-id').write_text('history-not-current-slot\n')
 def test_standalone_reader_finds_stock_alias_and_preserves_public_evidence(self):
  self.mount(options='ro')
  before={str(p):p.read_bytes() for p in (self.root/'p46').rglob('*') if p.is_file()}
  result=self.run_script(self.run);self.assertEqual(result.returncode,0,result.stderr)
  report=(self.root/'tmp/lg6851f-ab-failure.txt').read_text()
  for text in ['collector_version=2','real-historical-source','fixture-stage','boot-fixture.txt.gz','COMPLETE fixture upgrade','history-not-current-slot']:
   self.assertIn(text,report)
  self.assertEqual(before,{str(p):p.read_bytes() for p in (self.root/'p46').rglob('*') if p.is_file()})
 def test_unmounted_or_wrong_partition_does_not_scan_other_storage(self):
  (self.root/'proc/self/mountinfo').write_text('')
  self.assertEqual(self.run_script(self.run).returncode,0)
  self.assertIn('未找到其完整ext4挂载',(self.root/'tmp/lg6851f-ab-failure.txt').read_text())
  (self.dev/'uevent').write_text('PARTNAME=other\n')
  self.assertEqual(self.run_script(self.run).returncode,0)
  text=(self.root/'tmp/lg6851f-ab-failure.txt').read_text();self.assertIn('P46身份未通过',text);self.assertNotIn('real-historical-source',text)
 def test_installed_reader_matches_standalone_source(self):
  self.assertEqual(COLLECTOR.read_bytes(),(ROOT/'target/linux/mediatek/mt6990/base-files/usr/bin/lg6851f-collect-ab-failure').read_bytes())

if __name__=='__main__':unittest.main()
