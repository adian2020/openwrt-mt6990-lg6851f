#!/usr/bin/env python3
"""Run actual slot control shell against ordinary files, never block devices."""
import json,os,pathlib,struct,subprocess,tempfile,unittest,tarfile
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
 def run_probe(self):
  import re
  text=(ROOT/'scripts/lg6851f-probe-bootloader.sh').read_text()
  text=re.sub(r'/(?:dev|sys|proc|var|tmp)/',lambda m:str(self.root/m[0].strip('/'))+'/',text).replace('[ -b ','[ -f ')
  path=self.root/'probe';path.write_text(text)
  self.binary('dmesg',"#!/bin/sh\necho fixture-kernel\n")
  return subprocess.run(['sh',str(path)],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root)),capture_output=True,text=True)
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
  self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'dev').glob('mmcblk*')});self.assertFalse((self.root/'writes').exists())
 def test_absent_or_oversized_lk_refuses_partition_dump(self):
  r=self.run_probe();self.assertEqual(r.returncode,95)
  self.add_lk(16385);r=self.run_probe();self.assertEqual(r.returncode,27);self.assertFalse(list((self.root/'tmp').glob('*/lk_a.img')))

if __name__=='__main__':unittest.main()
