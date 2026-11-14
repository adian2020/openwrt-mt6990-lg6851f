#!/usr/bin/env python3
"""Run the overlay report wrapper with synthetic files and no block devices."""
import gzip
import os
import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SOURCE=ROOT/'target/linux/mediatek/mt6990/base-files/usr/bin/lg6851f-archive-ab-report'
class ArchiveTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  for path in ['overlay','tmp/sysinfo','proc/sys/kernel/random','bin']:(self.root/path).mkdir(parents=True)
  (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f')
  (self.root/'proc/mounts').write_text(f'/dev/loop0 {self.root}/overlay ext4 rw 0 0\n')
  self.script=SOURCE.read_text()
  for prefix in ['/tmp/','/proc/','/overlay']:self.script=self.script.replace(prefix,str(self.root/prefix.lstrip('/'))+('/' if prefix.endswith('/') else ''))
  self.collector=self.root/'bin/collect';self.collector.write_text('#!/bin/sh\nprintf "fixture boot and crash evidence\\n" > '+str(self.root/'tmp/lg6851f-ab-failure.txt')+'\n');self.collector.chmod(0o700)
  self.script=self.script.replace('/usr/bin/lg6851f-collect-ab-failure',str(self.collector)).replace('\nsync\n','\n:\n')
  (self.root/'run').write_text(self.script)
  for name,source in [('df',"printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999 1 99998 1%% /fixture\\n'"),('logger',':')]:
   p=self.root/'bin'/name;p.write_text('#!/bin/sh\n'+source+'\n');p.chmod(0o700)
 def run_report(self,index=1):
  (self.root/'proc/sys/kernel/random/boot_id').write_text(f'12345678-1234-1234-1234-{index:012x}')
  return subprocess.run(['sh',str(self.root/'run')],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH']),capture_output=True,text=True)
 def test_persist_compress_deduplicate_and_bound_reports(self):
  for i in range(1,11):
   result=self.run_report(i);self.assertEqual(result.returncode,0,result.stderr)
  files=list((self.root/'overlay/lg6851f-ab-reports').glob('boot-*.txt.gz'));self.assertEqual(len(files),8)
  for path in files:
   self.assertEqual(gzip.decompress(path.read_bytes()),b'fixture boot and crash evidence\n');self.assertEqual(path.stat().st_mode&0o777,0o600)
  before={p.name:p.read_bytes() for p in files};self.run_report(10)
  self.assertEqual(before,{p.name:p.read_bytes() for p in files})
 def test_current_report_survives_clock_reset_relative_to_old_files(self):
  import time
  for i in range(1,9):self.assertEqual(self.run_report(i).returncode,0)
  for path in (self.root/'overlay/lg6851f-ab-reports').glob('*.gz'):os.utime(path,(time.time()+999999,time.time()+999999))
  self.assertEqual(self.run_report(9).returncode,0)
  self.assertTrue((self.root/'overlay/lg6851f-ab-reports/boot-12345678-1234-1234-1234-000000000009.txt.gz').exists())
  self.assertEqual(len(list((self.root/'overlay/lg6851f-ab-reports').glob('*.gz'))),8)
 def test_readonly_or_missing_overlay_never_writes(self):
  (self.root/'proc/mounts').write_text(f'/dev/loop0 {self.root}/overlay ext4 ro 0 0\n')
  self.assertEqual(self.run_report().returncode,75);self.assertFalse((self.root/'overlay/lg6851f-ab-reports').exists())
if __name__=='__main__':unittest.main()
