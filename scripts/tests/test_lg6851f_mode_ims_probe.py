"""Exercise the actual one-shot probe with real flock and fake read-only tools."""
import fcntl,os,pathlib,subprocess,tempfile,threading,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/lg6851f-probe-mode-ims.sh'

class ModeImsProbeTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  (self.root/'board').write_text('fiberhome,lg6851f');(self.root/'bin').mkdir()
  for name in ['mipc','at']:
   p=self.root/name;p.write_text('''#!/bin/sh
printf '%s %s\\n' "${0##*/}" "$*" >> "$TEST_DIR/calls"
echo "mock getter $*"
''');p.chmod(0o700)
  p=self.root/'bin/sleep';p.write_text('''#!/bin/sh
if [ "$1" = 1 ];then /bin/sleep 0.01;else
 if /usr/bin/flock -n "$TEST_DIR/lock" -c true;then echo early-release >> "$TEST_DIR/errors";fi
fi
''');p.chmod(0o700)
  source=SCRIPT.read_text().replace('/tmp/sysinfo/board_name',str(self.root/'board')).replace('/usr/bin/mipc_wan_cli',str(self.root/'mipc')).replace('/usr/bin/modem5g-at',str(self.root/'at')).replace('/var/lock/luci-modem5g-control.lock',str(self.root/'lock')).replace('/tmp/lg6851f-modem-control.active',str(self.root/'active')).replace('/var/lock/lg6851f-modem-recovery.lock',str(self.root/'recovery')).replace('/tmp/lg6851f-mode-ims-readonly.XXXXXX',str(self.root/'report.XXXXXX'))
  self.script=self.root/'probe';self.script.write_text(source)
 def run_probe(self,*args):
  return subprocess.run(['sh',str(self.script),*args],env=dict(os.environ,TEST_DIR=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH']),capture_output=True,text=True,timeout=5)
 def test_only_readonly_queries_and_cooldown_ownership(self):
  r=self.run_probe();self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.root/'calls').read_text().splitlines(),['mipc --nw_get_rat','mipc --ims_get_config','mipc --ims_get_status','at AT+QCFG=?','at AT+QCFG="ims"','at AT+QCAINFO','at AT+QNWCFG="nr5g_cainfo"','at AT+EIMSCFG?','at AT+CIREG?'])
  self.assertFalse((self.root/'errors').exists())
  self.assertEqual(len(list(self.root.glob('report.*'))),1)
  self.assertEqual(subprocess.run(['/usr/bin/flock','-n',str(self.root/'lock'),'-c','true']).returncode,0)
 def test_targeted_ims_reads_skip_mipc_contention_and_failed_queries(self):
  with (self.root/'lock').open('w') as fd:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.run_probe('ims-at')
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.root/'calls').read_text().splitlines(),['at AT+EIMSCFG?','at AT+CIREG?'])
  report=next(self.root.glob('report.*'))
  self.assertEqual(report.stat().st_mode&0o777,0o600)
  self.assertIn('模式：ims-at',report.read_text())
 def test_unknown_mode_never_executes_queries(self):
  self.assertEqual(self.run_probe('set-ims').returncode,2)
  self.assertFalse((self.root/'calls').exists())
 def test_persistent_contention_never_executes_queries(self):
  with (self.root/'lock').open('w') as fd:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.run_probe()
  self.assertEqual(r.returncode,75,r.stderr);self.assertFalse((self.root/'calls').exists())
 def test_transient_contention_waits_then_continues(self):
  with (self.root/'lock').open('w') as fd:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   release=threading.Timer(.05,lambda:fcntl.flock(fd,fcntl.LOCK_UN));release.start()
   try:r=self.run_probe()
   finally:release.join()
  self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((self.root/'calls').exists())
 def test_manual_recovery_and_wrong_board_do_not_query(self):
  (self.root/'active').touch();self.assertEqual(self.run_probe().returncode,75)
  self.assertFalse((self.root/'calls').exists())
  (self.root/'active').unlink();(self.root/'board').write_text('other,board')
  self.assertEqual(self.run_probe().returncode,95);self.assertFalse((self.root/'calls').exists())

if __name__=='__main__':unittest.main()
