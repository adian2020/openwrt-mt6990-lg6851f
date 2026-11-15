#!/usr/bin/env python3
"""Run actual slot control shell against ordinary files, never block devices."""
import json,os,pathlib,struct,subprocess,tempfile,unittest,tarfile,re
ROOT=pathlib.Path(__file__).resolve().parents[2]
SOURCE=ROOT/'target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-slotctl'
PLATFORM=ROOT/'target/linux/mediatek/mt6990/base-files/lib/upgrade/platform.sh'
class SlotFixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  for p in ['dev','sys/class/block','proc/self','proc/sys/kernel/random','var/lock','tmp','shared','bin']:(self.root/p).mkdir(parents=True)
  for n,name,size in [(1,'misc',1024),(25,'boot_a',65536),(26,'rootfs_a',262144),(38,'boot_b',65536),(39,'rootfs_b',262144),(46,'user_data',5187456)]:
   d=self.root/f'sys/class/block/mmcblk0p{n}';d.mkdir()
   for f,v in [('partition',str(n)),('size',str(size)),('uevent','PARTNAME='+name),('dev','259:14')]: (d/f).write_text(v+'\n')
   (self.root/f'dev/mmcblk0p{n}').write_bytes(bytes(4096))
  self.misc=self.root/'dev/mmcblk0p1';self.misc.write_bytes(bytes(524288))
  for n in [25,38]:
   d=bytearray(4096);d[:8]=b'ANDROID!';struct.pack_into('<I',d,8,1024);struct.pack_into('<II',d,36,2048,2);(self.root/f'dev/mmcblk0p{n}').write_bytes(d)
  for n in [26,39]:
   d=bytearray(4096);d[:4]=b'hsqs';struct.pack_into('<H',d,28,4);struct.pack_into('<Q',d,40,4096);(self.root/f'dev/mmcblk0p{n}').write_bytes(d)
  record=bytearray(range(32));record[:4]=b'\0'*4;record[4:10]=b'BCAB\x01\x02';record[12:22]=bytes.fromhex('0e020101000f03010100');self.set_record(record)
  (self.root/'proc/sys/kernel/random/boot_id').write_text('12345678-1234-1234-1234-000000000001\n')
  (self.root/'proc/uptime').write_text('180.0 200.0\n')
  (self.root/'proc/cmdline').write_text(f'bootslot=b root={self.root}/dev/mmcblk0p39\n')
  (self.root/'proc/self/mountinfo').write_text(f'42 22 259:14 / {self.root}/shared rw - ext4 /dev/block/by-name/user_data rw\n')
  self.binary('id','#!/bin/sh\necho 0\n');self.binary('ps','#!/bin/sh\nexit 0\n');self.binary('sync','#!/bin/sh\nexit 0\n')
  self.binary('hexdump', '''#!/usr/bin/env python3
import sys,struct
b=sys.stdin.buffer.read()
print(str(struct.unpack('<I',b)[0]) if sys.argv[-1]=='1/4 "%u"' else b.hex(),end='')
''')
  self.binary('dd','''#!/usr/bin/env python3
import sys,os,subprocess,pathlib
args=sys.argv[1:];vals=dict(a.split('=',1) for a in args if '=' in a);root=pathlib.Path(os.environ['FIXTURE'])
write=vals.get('of')==str(root/'dev/mmcblk0p1')
if write:
 with (root/'writes').open('a') as f:f.write(' '.join(args)+'\\n')
 if os.environ.get('FAIL_WRITE')=='1' and not (root/'failed').exists():
  (root/'failed').touch();sys.exit(1)
rc=subprocess.run(['/bin/dd',*args]).returncode
if os.environ.get('MUTATE_BACKUP')=='1' and '/lg6851f-slot-backups/' in vals.get('of','') and vals.get('of','').endswith('.misc'):
 p=root/'dev/mmcblk0p1';b=bytearray(p.read_bytes());b[2072]=77;p.write_bytes(b)
if write and os.environ.get('FOREIGN_WRITE')=='1' and not (root/'changed').exists():
 (root/'changed').touch();p=root/'dev/mmcblk0p1';b=bytearray(p.read_bytes());b[2072]=88;p.write_bytes(b)
sys.exit(rc)
''')
  text=SOURCE.read_text()
  import re
  text=re.sub(r'/(?:dev|sys|proc|var|tmp)/',lambda m:str(self.root/m[0].strip('/'))+'/',text).replace('[ -b ','[ -f ')
  self.script=self.root/'slotctl';self.script.write_text(text)
 def binary(self,name,text):p=self.root/'bin'/name;p.write_text(text);p.chmod(0o755)
 def record(self):return self.misc.read_bytes()[2048:2080]
 def set_record(self,data):
  b=bytearray(self.misc.read_bytes());b[2048:2080]=data;self.misc.write_bytes(b)
 def run_cli(self,*args,**extra):
  r=subprocess.run(['sh',str(self.script),*args],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root),**extra),capture_output=True,text=True)
  try:data=json.loads(r.stdout)
  except Exception:self.fail(f'not JSON: {r.returncode} {r.stdout} {r.stderr}')
  return r,data
 def select(self,target='a',token=None,allow=False,**extra):return self.run_cli('select',target,'--expect',token or self.record().hex(),'--confirm',*(['--allow-vendor-recovery'] if allow else []),**extra)

class SlotTest(SlotFixture):
 def test_activity_guard_does_not_match_its_actual_grep_process(self):
  pattern=re.search(r"grep -Eq '([^']+)'",SOURCE.read_text()).group(1)
  process=subprocess.Popen(['grep','-Eq',pattern],stdin=subprocess.PIPE)
  try:
   row=subprocess.check_output(['ps','ww','-p',str(process.pid),'-o','pid=,args='],text=True)
  finally:
   process.stdin.close();process.wait(timeout=5)
  (self.root/'ps-row').write_text(row);self.binary('ps','#!/bin/sh\ncat "$FIXTURE/ps-row"\n')
  result,data=self.select('a');self.assertEqual(result.returncode,0,(result.stderr,data));self.assertEqual(self.record()[12],15)
 def test_activity_guard_still_blocks_real_boot_and_upgrade_processes(self):
  before=self.misc.read_bytes();self.binary('ps','#!/bin/sh\ncat "$FIXTURE/ps-row"\n')
  for command in ['/bin/sh /etc/init.d/rcS S boot','/bin/sh /etc/init.d/zmtk_boot_done start','zmtk_boot_done start','/sbin/sysupgrade /tmp/fw.bin','/sbin/upgraded','/bin/sh /lib/upgrade/stage2','/bin/sh /lib/upgrade/do_stage2']:
   with self.subTest(command=command):
    (self.root/'ps-row').write_text('123 root '+command+'\n');result,data=self.select('a');self.assertEqual(result.returncode,75,data);self.assertEqual(self.misc.read_bytes(),before)
  self.assertFalse((self.root/'writes').exists())
 def test_process_read_failure_or_upgrade_marker_cannot_bypass_guard(self):
  self.binary('ps','#!/bin/sh\nexit 1\n');before=self.misc.read_bytes();result,data=self.select('a');self.assertEqual(result.returncode,75,data);self.assertEqual(self.misc.read_bytes(),before)
  self.binary('ps','#!/bin/sh\nexit 0\n');(self.root/'tmp/sysupgrade').touch();result,data=self.select('a');self.assertEqual(result.returncode,75,data);self.assertEqual(self.misc.read_bytes(),before)
 def test_show_uses_actual_cmdline_not_priority(self):
  b=bytearray(self.record());b[12]=15;b[17]=14;self.set_record(b)
  before=self.misc.read_bytes();r,d=self.run_cli('show');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual((d['current'],d['next']),('b','a'));self.assertEqual(self.misc.read_bytes(),before);self.assertFalse((self.root/'writes').exists())
 def test_select_each_slot_changes_only_priorities_and_target_retry(self):
  for target,changed in [('a',{12,13,17}),('b',{12,17,18})]:
   before=self.record();r,d=self.select(target);self.assertEqual(r.returncode,0,(r.stderr,d));after=self.record()
   self.assertTrue(all(before[i]==after[i] for i in range(32) if i not in changed));self.assertFalse(d['rebooted']);self.assertEqual(pathlib.Path(d['backup']).read_bytes(),before);self.assertEqual(pathlib.Path(d['backup']+'.misc').stat().st_size,524288)
   self.assertEqual((after[12],after[17]),(15,14) if target=='a' else (14,15));self.assertEqual(after[13 if target=='a' else 18],0)
 def test_invalid_layout_magic_or_version_never_writes(self):
  before=self.misc.read_bytes();p=self.root/'sys/class/block/mmcblk0p1/size';p.write_text('other')
  r,d=self.select();self.assertEqual(r.returncode,95);self.assertEqual(self.misc.read_bytes(),before)
  p.write_text('1024');record=bytearray(self.record());record[4]=0;self.set_record(record);r,d=self.run_cli('show');self.assertEqual(r.returncode,95);self.assertFalse((self.root/'writes').exists())
 def test_bad_images_and_cmdline_mismatch_rejected(self):
  (self.root/'dev/mmcblk0p25').write_bytes(bytes(4096));r,d=self.select();self.assertEqual(r.returncode,95)
  (self.root/'proc/cmdline').write_text(f'bootslot=b root={self.root}/dev/mmcblk0p26');r,d=self.run_cli('show');self.assertEqual(r.returncode,95);self.assertFalse((self.root/'writes').exists())
 def test_stale_token_missing_confirm_and_injection_rejected(self):
  for args in [('select','a'),('select','a','--expect','0'*64,'--confirm'),('select','a;reboot','--expect',self.record().hex(),'--confirm')]:
   r,d=self.run_cli(*args);self.assertNotEqual(r.returncode,0)
  self.assertFalse((self.root/'writes').exists())
 def test_vendor_restore_risk_requires_explicit_acceptance_and_is_not_hidden(self):
  b=bytearray(self.record());b[18]=4;self.set_record(b)
  r,d=self.select();self.assertEqual(r.returncode,13);self.assertFalse((self.root/'writes').exists())
  r,d=self.select(allow=True);self.assertEqual(r.returncode,0,(r.stderr,d));self.assertTrue(d['vendor_recovery_risk']);self.assertEqual(self.record()[18],4)
 def test_unconfirmed_target_success_requires_risk_acceptance(self):
  b=bytearray(self.record());b[14]=0;self.set_record(b);r,d=self.select();self.assertEqual(r.returncode,13)
 def test_unavailable_readonly_or_wrong_shared_storage_refuses_unbacked_write(self):
  p=self.root/'proc/self/mountinfo';original=p.read_text()
  for value in ['',original.replace(' rw ',' ro '),original.replace('259:14','7:1')]:
   p.write_text(value);r,d=self.select();self.assertEqual(r.returncode,75);self.assertFalse((self.root/'writes').exists())
 def test_busy_lock_and_stock_startup_are_rejected(self):
  lock=self.root/'tmp/lg6851f-bootctrl.lock';lock.mkdir();r,d=self.select();self.assertEqual(r.returncode,75);lock.rmdir()
  self.binary('ps',"#!/bin/sh\necho '1 root /etc/rc.d/S99zmtk_boot_done boot'\n");r,d=self.select();self.assertEqual(r.returncode,75);self.assertFalse((self.root/'writes').exists())
 def test_failed_write_restores_original_and_keeps_backup(self):
  before=self.record();r,d=self.select(FAIL_WRITE='1');self.assertEqual(r.returncode,5,d);self.assertEqual(self.record(),before);self.assertIn('已读回确认恢复',d['error']);self.assertTrue(list((self.root/'shared/lg6851f-slot-backups').glob('bootctrl.*')))
 def test_foreign_changes_are_not_overwritten_by_rollback(self):
  r,d=self.select(FOREIGN_WRITE='1');self.assertEqual(r.returncode,5);self.assertEqual(self.record()[24],88);self.assertIn('未覆盖未知状态',d['error'])
 def test_backup_race_is_detected_before_control_write(self):
  r,d=self.select(MUTATE_BACKUP='1');self.assertEqual(r.returncode,75);self.assertFalse((self.root/'writes').exists());self.assertEqual(self.record()[24],77)
 def test_runtime_upgrade_and_selector_share_lock(self):
  text=PLATFORM.read_text().replace('/tmp/',str(self.root/'tmp')+'/')
  script=self.root/'upgrade';script.write_text(text+'\nlg6851f_do_locked_upgrade(){ echo upgrade-called; }; platform_do_upgrade fixture\n')
  lock=self.root/'tmp/lg6851f-bootctrl.lock';lock.mkdir()
  r=subprocess.run(['sh',str(script)],capture_output=True,text=True);self.assertNotEqual(r.returncode,0);self.assertNotIn('upgrade-called',r.stdout)
  lock.rmdir();r=subprocess.run(['sh',str(script)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);self.assertIn('upgrade-called',r.stdout);self.assertFalse(lock.exists())
class ProbeTest(SlotFixture):
 def run_probe(self,deadline=None,args=()):
  import re
  text=(ROOT/'scripts/lg6851f-probe-bootloader.sh').read_text()
  text=re.sub(r'/(?:dev|sys|proc|var|tmp)/',lambda m:str(self.root/m[0].strip('/'))+'/',text).replace('[ -b ','[ -f ')
  if deadline is not None:text=text.replace('sleep 12','sleep '+str(deadline))
  path=self.root/'probe';path.write_text(text)
  self.binary('timeout',"#!/bin/sh\ntouch \"$FIXTURE/timeout-called\"\nexit 99\n")
  self.binary('dmesg',"#!/bin/sh\necho fixture-kernel\n")
  return subprocess.run(['sh',str(path),*args],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root)),capture_output=True,text=True,timeout=8)
 def add_lk(self,sectors=1024):
  sys=self.root/'sys/class/block/mmcblk0p23';sys.mkdir()
  (sys/'uevent').write_text('PARTNAME=lk_a\nDEVNAME=mmcblk0p23\n')
  (sys/'size').write_text(str(sectors)+'\n')
  path=self.root/'dev/mmcblk0p23';path.write_bytes(b'LK-FIXTURE'+bytes(1024*512-10));return path
 def test_only_lk_is_copied_into_tmp_and_block_files_stay_unchanged(self):
  lk=self.add_lk();before={p.name:p.read_bytes() for p in (self.root/'dev').glob('mmcblk*')}
  r=self.run_probe();self.assertEqual(r.returncode,0,r.stderr)
  archives=list((self.root/'tmp').glob('lg6851f-bootchain.*.tar.gz'));self.assertEqual(len(archives),1)
  with tarfile.open(archives[0]) as t:self.assertEqual(t.extractfile('./lk_a.img').read(),lk.read_bytes());self.assertIn('./identity.txt',t.getnames())
  self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'dev').glob('mmcblk*')});self.assertFalse((self.root/'writes').exists());self.assertFalse((self.root/'timeout-called').exists())
 def test_missing_block_device_creates_diagnostic_archive_and_visible_stage(self):
  lk=self.add_lk();lk.unlink()
  r=self.run_probe();self.assertEqual(r.returncode,95);self.assertIn('device:lk_a',r.stderr);self.assertIn('.tar.gz',r.stderr)
  archive=next((self.root/'tmp').glob('lg6851f-bootchain.*.tar.gz'))
  with tarfile.open(archive) as t:
   status=t.extractfile('./status.txt').read().decode();self.assertIn('exit_code=95',status);self.assertIn('completed_lk_images=0',status)
 def slow_read(self,ignore_term):
  p=self.root/'bin/dd';text=p.read_text()
  code="if vals.get('of','').endswith('lk_a.img'):\n import time,signal\n pathlib.Path(vals['of']).write_bytes(b'partial-LK')\n"
  if ignore_term:code+=" signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
  code+=" time.sleep(60)\n"
  p.write_text(text.replace("rc=subprocess.run(['/bin/dd',*args]).returncode",code+"rc=subprocess.run(['/bin/dd',*args]).returncode"))
 def test_read_ignoring_term_is_stopped_by_escalation(self):
  self.add_lk();self.slow_read(True)
  r=self.run_probe(deadline=0.2);self.assertEqual(r.returncode,124);self.assertIn('read:lk_a',r.stderr);self.assertFalse((self.root/'timeout-called').exists())
 def test_dd_error_preserves_actual_code_and_partial_evidence(self):
  self.add_lk();p=self.root/'bin/dd';text=p.read_text()
  p.write_text(text.replace("rc=subprocess.run(['/bin/dd',*args]).returncode","if vals.get('of','').endswith('lk_a.img'):\n pathlib.Path(vals['of']).write_bytes(b'failed-read');sys.exit(7)\nrc=subprocess.run(['/bin/dd',*args]).returncode"))
  r=self.run_probe();self.assertEqual(r.returncode,7);self.assertIn('read:lk_a',r.stderr)
 def test_timeout_preserves_partial_dump_and_marks_it_incomplete(self):
  self.add_lk()
  self.slow_read(False)
  r=self.run_probe(deadline=0.2);self.assertEqual(r.returncode,124);self.assertIn('read:lk_a',r.stderr)
  archive=next((self.root/'tmp').glob('lg6851f-bootchain.*.tar.gz'))
  with tarfile.open(archive) as t:
   self.assertIn('./lk_a.img.partial',t.getnames());self.assertNotIn('./lk_a.img',t.getnames());self.assertIn('status=incomplete',t.extractfile('./status.txt').read().decode())
 def test_early_identity_failure_still_prints_archive_outside_redirected_report(self):
  (self.root/'proc/uptime').unlink()
  r=self.run_probe();self.assertNotEqual(r.returncode,0);self.assertIn('阶段=identity',r.stderr);self.assertIn('.tar.gz',r.stderr)
  self.assertTrue(list((self.root/'tmp').glob('lg6851f-bootchain.*.tar.gz')))
 def test_absent_or_oversized_lk_refuses_partition_dump(self):
  r=self.run_probe();self.assertEqual(r.returncode,95)
  self.add_lk(16385);r=self.run_probe();self.assertEqual(r.returncode,27);self.assertFalse(list((self.root/'tmp').glob('*/lk_a.img')))
 def add_boot_areas(self):
  for n in [0,1]:
   name=f'mmcblk0boot{n}';sys=self.root/'sys/class/block'/name;sys.mkdir()
   for f,v in [('uevent',f'DEVNAME={name}\nDEVTYPE=disk\nMAJOR=179\nMINOR={8+n}'),('dev',f'179:{8+n}'),('size','4096'),('force_ro','1')]:
    (sys/f).write_text(v+'\n')
   (self.root/'dev'/name).write_bytes(bytes([n+1])*(2*1024*1024))
 def test_explicit_preloader_mode_reads_only_bounded_prefixes_and_keeps_force_ro(self):
  self.add_boot_areas();lk=self.add_lk()
  before={p.name:p.read_bytes() for p in (self.root/'dev').glob('mmcblk*')}
  r=self.run_probe(args=('--preloader',));self.assertEqual(r.returncode,0,r.stderr)
  archive=next((self.root/'tmp').glob('lg6851f-bootchain.*.tar.gz'))
  with tarfile.open(archive) as t:
   self.assertNotIn('./lk_a.img',t.getnames())
   for n in [0,1]:self.assertEqual(t.extractfile(f'./mmcblk0boot{n}.prefix.img').read(),before[f'mmcblk0boot{n}'][:1048576])
   status=t.extractfile('./status.txt').read().decode();self.assertIn('mode=preloader',status);self.assertIn('completed_preloader_prefixes=2',status);self.assertIn('not full partition backups',status)
  self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'dev').glob('mmcblk*')})
  for n in [0,1]:self.assertEqual((self.root/f'sys/class/block/mmcblk0boot{n}/force_ro').read_text(),'1\n')
  self.assertFalse((self.root/'writes').exists());self.assertFalse((self.root/'timeout-called').exists())
 def test_preloader_requires_verified_layout_and_boot_area_identity(self):
  self.add_boot_areas();p=self.root/'sys/class/block/mmcblk0p46/size';p.write_text('1')
  r=self.run_probe(args=('--preloader',));self.assertEqual(r.returncode,95);self.assertIn('preloader-layout',r.stderr)
  self.assertFalse(list((self.root/'tmp').glob('*/*.prefix.img')))
  p.write_text('5187456');p=self.root/'sys/class/block/mmcblk0boot0/dev';p.write_text('8:8')
  r=self.run_probe(args=('--preloader',));self.assertEqual(r.returncode,95);self.assertFalse(list((self.root/'tmp').glob('*/*.prefix.img')))
 def test_preloader_oversize_or_missing_boot_area_does_not_dump(self):
  self.add_boot_areas();p=self.root/'sys/class/block/mmcblk0boot0/size';p.write_text('16385')
  r=self.run_probe(args=('--preloader',));self.assertEqual(r.returncode,27);self.assertFalse(list((self.root/'tmp').glob('*/*.prefix.img')))
  p.write_text('4096');(self.root/'dev/mmcblk0boot0').unlink()
  r=self.run_probe(args=('--preloader',));self.assertEqual(r.returncode,95);self.assertFalse(list((self.root/'tmp').glob('*/*.prefix.img')))
 def test_unknown_probe_mode_is_rejected(self):
  r=self.run_probe(args=('--write',));self.assertEqual(r.returncode,22);self.assertFalse(list((self.root/'tmp').glob('lg6851f-bootchain.*')))

if __name__=='__main__':unittest.main()
