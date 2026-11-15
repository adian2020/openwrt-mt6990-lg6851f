#!/usr/bin/env python3
"""Run real late-boot confirmation against files, never devices or a router."""
import json
import os
import pathlib
import re
import subprocess
import unittest

from test_lg6851f_slotctl import SlotFixture, ROOT

SOURCE = ROOT/'target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-confirm-boot'
INIT = ROOT/'target/linux/mediatek/mt6990/base-files/etc/init.d/lg6851f-boot-confirm'


class BootConfirmTest(SlotFixture):
 def setUp(self):
  super().setUp()
  for name in ['rom/etc','tmp/sysinfo']:(self.root/name).mkdir(parents=True,exist_ok=True)
  (self.root/'rom/etc/mt6990-firmware-id').write_text('a'*40+'\n')
  (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f\n')
  self.boot_id=(self.root/'proc/sys/kernel/random/boot_id').read_text().strip()
  self.ready=self.root/'tmp/lg6851f-init-complete';self.ready.write_text(self.boot_id+' 20\n');self.ready.chmod(0o600)
  self.binary('uname','#!/bin/sh\necho 6.18.44\n')
  self.binary('logger','#!/bin/sh\nprintf "%s\\n" "$*" >> "$FIXTURE/log"\n')
  self.binary('df',"#!/bin/sh\nprintf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 99999 1 99998 1%% /fixture\\n'\n")
  self.binary('jsonfilter',r'''#!/usr/bin/env python3
import sys,json
args=sys.argv[1:];data=json.loads(args[args.index('-s')+1]);expr=args[args.index('-e')+1]
values=[data]
for key in expr.removeprefix('@.').split('.'):
 values=[v for item in values for v in (list(item.values()) if key=='*' and isinstance(item,dict) else [item[key]] if isinstance(item,dict) and key in item else [])]
if not values:sys.exit(1)
for value in values:print(json.dumps(value,separators=(',',':')) if isinstance(value,(dict,list,bool)) else str(value))
''')
  self.binary('ubus',r'''#!/usr/bin/env python3
import os,json,pathlib,sys
r=pathlib.Path(os.environ['FIXTURE']);tick=int((r/'tick').read_text()) if (r/'tick').exists() else 0
if (r/'bad-core').exists() or os.environ.get('CORE_FAIL')=='1':sys.exit(1)
args=sys.argv[1:]
if args[-2:]==['service','list']:
 pids=[101,102,103]
 if (r/'restarted').exists():pids[0]=201
 print(json.dumps({name:{'instances':{'main':{'running':True,'pid':pid}}} for name,pid in zip(['network','rpcd','uhttpd'],pids)}))
elif args[-2:]==['network.interface','dump']:print('{"interface":[]}')
else:raise RuntimeError('unexpected ubus command '+repr(args))
''')
  self.binary('sleep',r'''#!/usr/bin/env python3
import os,pathlib,sys
r=pathlib.Path(os.environ['FIXTURE']);p=r/'proc/uptime';value=float(p.read_text().split()[0])+int(sys.argv[1]);p.write_text(f'{value} 1000.0\n'.replace('\\n','\n'))
t=r/'tick';tick=(int(t.read_text()) if t.exists() else 0)+1;t.write_text(str(tick))
if tick==1:
 if os.environ.get('MUTATE_CONTROL')=='1':
  p=r/'dev/mmcblk0p1';b=bytearray(p.read_bytes());b[2072]=77;p.write_bytes(b)
 if os.environ.get('MUTATE_BOOT')=='1':(r/'proc/sys/kernel/random/boot_id').write_text('changed-boot\n')
''')
  text=re.sub(r'/(?:dev|sys|proc|var|tmp|rom)/',lambda m:str(self.root/m[0].strip('/'))+'/',SOURCE.read_text()).replace('[ -b ','[ -f ')
  # Compare the real unprivileged fixture owner; retain the ownership check.
  text=text.replace('[ "$3" = 0 ]',f'[ "$3" = {os.getuid()} ]')
  # Advance virtual uptime, not wall time; shorten only the failure budget.
  text=text.replace(' + 600)', ' + 40)')
  self.script=self.root/'confirm';self.script.write_text(text)
  self.evidence=self.root/'shared/lg6851f-boot-confirm'
 def run_confirm(self,*args,**extra):
  return subprocess.run(['sh',str(self.script),*args],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root),**extra),capture_output=True,text=True,timeout=20)
 def statuses(self):return [json.loads(p.read_text()) for p in self.evidence.glob('boot-*/status.json')]
 def current_status(self):return json.loads((self.evidence/('boot-'+self.boot_id)/'status.json').read_text())
 def test_both_slots_change_only_their_retry_and_persist_original(self):
  for slot,index,pa,pb,rootpart in [('a',13,15,14,26),('b',18,14,15,39)]:
   with self.subTest(slot=slot):
    b=bytearray(self.record());b[12]=pa;b[17]=pb;b[13]=3;b[18]=4;self.set_record(b)
    (self.root/'proc/cmdline').write_text(f'bootslot={slot} root={self.root}/dev/mmcblk0p{rootpart}\n')
    before=self.misc.read_bytes();r=self.run_confirm();self.assertEqual(r.returncode,0,(r.stdout,r.stderr,(self.root/'log').read_text()))
    expected=bytearray(before);expected[2048+index]=0;self.assertEqual(self.misc.read_bytes(),expected)
    data=self.current_status();self.assertEqual(data['status'],'confirmed');self.assertEqual(data['before'],before[2048:2080].hex());self.assertGreaterEqual(data['uptime'],180)
    folder=self.evidence/('boot-'+self.boot_id);self.assertEqual((folder/'before.bin').read_bytes(),before[2048:2080]);self.assertEqual(folder.stat().st_mode&0o777,0o700);self.assertEqual((folder/'before.bin').stat().st_mode&0o777,0o600)
    writes=(self.root/'writes').read_text();self.assertEqual(len(writes.splitlines()),1);self.assertIn(f'seek={2048+index} count=1',writes)
    # A service restart must never erase a newly changed counter this boot.
    changed=bytearray(self.record());changed[index]=2;self.set_record(changed)
    self.assertEqual(self.run_confirm().returncode,0);self.assertEqual(self.record()[index],2);self.assertEqual((self.root/'writes').read_text(),writes)
    # Simulate a new boot UUID for the other independent slot scenario.
    (self.root/'tmp/lg6851f-boot-confirm.attempted').rmdir();(self.root/'writes').unlink()
    self.boot_id='12345678-1234-1234-1234-000000000002'
    (self.root/'proc/sys/kernel/random/boot_id').write_text(self.boot_id+'\n');self.ready.write_text(self.boot_id+' 20\n')
 def test_zero_retry_records_health_without_any_misc_write(self):
  b=bytearray(self.record());b[18]=0;self.set_record(b);before=self.misc.read_bytes()
  r=self.run_confirm();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.misc.read_bytes(),before);self.assertFalse((self.root/'writes').exists());self.assertEqual(self.statuses()[0]['status'],'confirmed')
 def test_incomplete_init_bad_receipt_or_early_boot_keeps_retry(self):
  for receipt,uptime in [('',180),('',0),('wrong 20\n',180)]:
   self.ready.write_text(receipt);(self.root/'proc/uptime').write_text(f'{uptime}.0 0.0\n')
   r=self.run_confirm();self.assertEqual(r.returncode,75,r.stderr);self.assertFalse((self.root/'writes').exists());self.assertFalse(self.evidence.exists())
 def test_upgrade_or_untrusted_receipt_never_acknowledges(self):
  self.ready.chmod(0o666)
  self.assertEqual(self.run_confirm().returncode,75);self.ready.chmod(0o600)
  self.ready.unlink();self.ready.symlink_to(self.root/'proc/sys/kernel/random/boot_id')
  self.assertEqual(self.run_confirm().returncode,75);self.ready.unlink();self.ready.write_text(self.boot_id+' 20\n');self.ready.chmod(0o600)
  marker=self.root/'tmp/sysupgrade';marker.touch()
  self.assertEqual(self.run_confirm().returncode,75);marker.unlink()
  self.binary('ps',"#!/bin/sh\necho '12 root /lib/upgrade/stage2 /tmp/firmware.bin'\n")
  self.assertEqual(self.run_confirm().returncode,75);self.assertFalse((self.root/'writes').exists())
 def test_failed_core_or_pid_change_before_write_never_acknowledges(self):
  r=self.run_confirm(CORE_FAIL='1');self.assertEqual(r.returncode,75);self.assertFalse((self.root/'writes').exists())
  self.binary('sync','#!/bin/sh\ntouch "$FIXTURE/restarted"\n')
  r=self.run_confirm();self.assertEqual(r.returncode,75,r.stderr);self.assertFalse((self.root/'writes').exists());self.assertEqual(self.current_status()['status'],'refused')
 def test_wrong_layout_kernel_identity_priority_or_current_slot_never_writes(self):
  checks=[(self.root/'tmp/sysinfo/board_name','other'),(self.root/'sys/class/block/mmcblk0p1/size','10'),(self.root/'rom/etc/mt6990-firmware-id','not-a-build'),(self.root/'proc/cmdline',f'bootslot=b root={self.root}/dev/mmcblk0p26')]
  for path,bad in checks:
   old=path.read_text();path.write_text(bad);r=self.run_confirm();self.assertEqual(r.returncode,95,r.stderr);path.write_text(old)
  b=bytearray(self.record());b[12]=15;b[17]=14;self.set_record(b);self.assertEqual(self.run_confirm().returncode,95)
  self.binary('uname','#!/bin/sh\necho 5.4.238\n');self.assertEqual(self.run_confirm().returncode,95);self.assertFalse((self.root/'writes').exists())
 def test_manual_change_or_different_boot_aborts_without_clearing(self):
  self.binary('sync',r'''#!/usr/bin/env python3
import pathlib,os
r=pathlib.Path(os.environ['FIXTURE'])
if not (r/'mutated').exists():
 (r/'mutated').touch()
 if os.environ.get('MUTATE_CONTROL')=='1':
  p=r/'dev/mmcblk0p1';b=bytearray(p.read_bytes());b[2072]=77;p.write_bytes(b)
 if os.environ.get('MUTATE_BOOT')=='1':(r/'proc/sys/kernel/random/boot_id').write_text('changed-boot\n')
''')
  for i,args in enumerate([dict(MUTATE_CONTROL='1'),dict(MUTATE_BOOT='1')],10):
   self.boot_id=f'12345678-1234-1234-1234-{i:012x}';(self.root/'proc/sys/kernel/random/boot_id').write_text(self.boot_id+'\n');self.ready.write_text(self.boot_id+' 20\n')
   (self.root/'mutated').unlink(missing_ok=True)
   r=self.run_confirm(**args);self.assertEqual(r.returncode,75,r.stderr);self.assertFalse((self.root/'writes').exists())
 def test_upgrade_lock_readonly_shared_or_directory_link_refuses_write(self):
  lock=self.root/'tmp/lg6851f-bootctrl.lock';lock.mkdir();self.assertEqual(self.run_confirm().returncode,75);lock.rmdir()
  mount=self.root/'proc/self/mountinfo';original=mount.read_text();mount.write_text(original.replace(' rw ',' ro '));self.assertEqual(self.run_confirm().returncode,75);mount.write_text(original)
  self.evidence.symlink_to(self.root/'shared',target_is_directory=True);self.assertEqual(self.run_confirm().returncode,22);self.assertFalse((self.root/'writes').exists())
 def test_backup_race_or_service_failure_during_sync_refuses_write(self):
  p=self.root/'bin/dd';old=p.read_text();p.write_text(old.replace("rc=subprocess.run(['/bin/dd',*args]).returncode", "rc=subprocess.run(['/bin/dd',*args]).returncode\nif vals.get('of','').endswith('/before.bin'):\n p=root/'dev/mmcblk0p1';b=bytearray(p.read_bytes());b[2072]=77;p.write_bytes(b)"))
  r=self.run_confirm();self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'writes').exists());p.write_text(old)
  # New boot and fresh evidence; services fail after durable metadata sync.
  self.boot_id='12345678-1234-1234-1234-000000000003';(self.root/'proc/sys/kernel/random/boot_id').write_text(self.boot_id+'\n');self.ready.write_text(self.boot_id+' 20\n')
  self.binary('sync','#!/bin/sh\ntouch "$FIXTURE/bad-core"\n')
  r=self.run_confirm();self.assertEqual(r.returncode,75);self.assertFalse((self.root/'writes').exists());self.assertIn('refused',[s['status'] for s in self.statuses()])
 def test_failed_write_does_not_retry_or_claim_confirmation(self):
  before=self.misc.read_bytes();r=self.run_confirm(FAIL_WRITE='1');self.assertEqual(r.returncode,5);self.assertEqual(self.misc.read_bytes(),before);self.assertEqual(self.statuses()[0]['status'],'write-failed')
  count=(self.root/'writes').read_text();self.assertEqual(self.run_confirm().returncode,0);self.assertEqual((self.root/'writes').read_text(),count)
 def test_foreign_readback_is_preserved_without_whole_record_rollback(self):
  r=self.run_confirm(FOREIGN_WRITE='1');self.assertEqual(r.returncode,5);self.assertEqual(self.record()[24],88);self.assertEqual(self.statuses()[0]['status'],'readback-failed');self.assertEqual(len((self.root/'writes').read_text().splitlines()),1)
 def test_service_has_no_respawn_and_evidence_retention_keeps_current(self):
  text=INIT.read_text();self.assertIn('START=99',text);self.assertIn('STOP=00',text);self.assertNotIn('procd_set_param respawn',text)
  self.evidence.mkdir()
  for i in range(1,10):
   d=self.evidence/f'boot-00000000-0000-0000-0000-{i:012x}';d.mkdir();(d/'status.json').write_text('{}');os.utime(d,(2000000000,2000000000))
  r=self.run_confirm();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(list(self.evidence.glob('boot-*'))),8);self.assertTrue((self.evidence/('boot-'+self.boot_id)).exists())
 def test_completed_init_before_120_seconds_is_confirmed_without_a_timer(self):
  (self.root/'proc/uptime').write_text('45.0 0.0\n')
  r=self.run_confirm();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.current_status()['uptime'],45);self.assertFalse((self.root/'tick').exists())
  writes=(self.root/'writes').read_bytes();self.ready.rename(str(self.ready)+'.shutdown')
  self.assertEqual(self.run_confirm('--shutdown').returncode,0);self.assertEqual((self.root/'writes').read_bytes(),writes)
 def test_orderly_shutdown_confirms_both_current_slots_with_proven_init(self):
  for slot,index,pa,pb,part in [('a',13,15,14,26),('b',18,14,15,39)]:
   b=bytearray(self.record());b[12]=pa;b[17]=pb;b[13]=3;b[18]=3;self.set_record(b)
   (self.root/'proc/cmdline').write_text(f'bootslot={slot} root={self.root}/dev/mmcblk0p{part}\n');(self.root/'proc/uptime').write_text('45.0 0.0\n')
   self.ready.rename(str(self.ready)+'.shutdown');self.binary('ps',"#!/bin/sh\necho '12 root /etc/init.d/rcS K shutdown'\n")
   before=self.misc.read_bytes();r=self.run_confirm('--shutdown');self.assertEqual(r.returncode,0,r.stderr)
   expected=bytearray(before);expected[2048+index]=0;self.assertEqual(self.misc.read_bytes(),expected);self.assertEqual(self.current_status()['confirmation'],'shutdown')
   (self.root/'tmp/lg6851f-boot-confirm.attempted').rmdir();pathlib.Path(str(self.ready)+'.shutdown').unlink()
   self.boot_id='12345678-1234-1234-1234-000000000004';(self.root/'proc/sys/kernel/random/boot_id').write_text(self.boot_id+'\n');self.ready.write_text(self.boot_id+' 20\n');self.ready.chmod(0o600)
 def test_shutdown_cannot_bypass_init_core_or_upgrade_guards(self):
  self.assertEqual(self.run_confirm('--shutdown').returncode,75)
  self.ready.rename(str(self.ready)+'.shutdown')
  self.assertEqual(self.run_confirm('--shutdown',CORE_FAIL='1').returncode,75)
  (self.root/'tmp/sysupgrade').touch();self.assertEqual(self.run_confirm('--shutdown').returncode,75);self.assertFalse((self.root/'writes').exists())
 def test_shutdown_can_finish_prepared_unattempted_evidence_without_replacing_backup(self):
  self.binary('sync','#!/bin/sh\ntouch "$FIXTURE/bad-core"\n');self.assertEqual(self.run_confirm().returncode,75)
  before=(self.evidence/('boot-'+self.boot_id)/'before.bin').read_bytes();self.binary('sync','#!/bin/sh\nexit 0\n');(self.root/'bad-core').unlink()
  self.ready.rename(str(self.ready)+'.shutdown');r=self.run_confirm('--shutdown');self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.evidence/('boot-'+self.boot_id)/'before.bin').read_bytes(),before);self.assertEqual(self.current_status()['confirmation'],'shutdown')


if __name__ == '__main__':unittest.main()
