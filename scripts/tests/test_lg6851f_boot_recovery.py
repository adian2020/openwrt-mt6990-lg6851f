"""执行恢复脚本的真实分支，只模拟网络/模组传输，不操作实机。"""
import pathlib,os,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
FILES=ROOT/'package/vendor/lg6851f-modem-chain-only/files'
class BootRecoveryTest(unittest.TestCase):
 def down_case(self,enabled='1',auto='1',pending='false'):
  with tempfile.TemporaryDirectory() as name:
   root=pathlib.Path(name);source=(FILES/'usr/sbin/lg6851f-data-watchdog').read_text();source=source[:source.rindex('main "$@"')]
   script=source+'''
log(){ :; }
uci(){ case "$*" in *radio_enabled*) echo "$TEST_ENABLED";; *auto*) echo "$TEST_AUTO";; esac; }
interface_state(){ echo '{}'; }
link_value(){ case "$2" in '@.up') echo false;; '@.pending') echo "$TEST_PENDING";; esac; }
recovery_lock(){ return 0; }
recovery_unlock(){ :; }
timeout(){ echo "$*" >> "$TEST_DIR/calls"; }
sleep(){ rounds=$((rounds+1)); [ "$rounds" -le 6 ] || exit 0; }
rounds=0
main
'''
   p=root/'script';p.write_text(script)
   r=subprocess.run(['sh',str(p)],env=dict(os.environ,TEST_ENABLED=enabled,TEST_AUTO=auto,TEST_PENDING=pending,TEST_DIR=name),capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   return (root/'calls').read_text().splitlines() if (root/'calls').exists() else []
 def test_initial_down_connection_is_retried_without_radio_reset(self):self.assertEqual(self.down_case(),['10 /sbin/ifup modem5g']*2)
 def test_pending_or_user_disabled_connection_is_not_restarted(self):
  for args in [{'pending':'true'},{'enabled':'0'},{'auto':'0'}]:self.assertEqual(self.down_case(**args),[])
 def restart_case(self,radio_rc=0,auto=1):
  with tempfile.TemporaryDirectory() as name:
   root=pathlib.Path(name);(root/'bin').mkdir()
   lib=root/'library';lib.write_text('''lg6851f_radio_transaction(){ echo "radio $*" >> "$TEST_DIR/calls"; return "$TEST_RADIO_RC"; }
lg6851f_ensure_radio_on(){ echo radio-on >> "$TEST_DIR/calls"; }
''')
   for cmd,body in [('uci','case "$*" in *auto*) echo "$TEST_AUTO";; *) echo 1;; esac'),('ubus',"echo '{}'"),('jsonfilter','echo false'),('timeout','echo "$*" >> "$TEST_DIR/calls"; exit 0')]:
    p=root/'bin'/cmd;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
   source=(FILES/'usr/bin/lg6851f-modem-restart').read_text().replace('/lib/functions/lg6851f-radio.sh',str(lib)).replace('/var/lock/lg6851f-modem-recovery.lock',str(root/'lock')).replace('/tmp/lg6851f-modem-restart.state',str(root/'state'))
   p=root/'script';p.write_text(source)
   r=subprocess.run(['sh',str(p)],env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],TEST_DIR=name,TEST_RADIO_RC=str(radio_rc),TEST_AUTO=str(auto)),capture_output=True,text=True)
   self.assertFalse((root/'lock').exists())
   return r.returncode,(root/'state').read_text().strip(),(root/'calls').read_text().splitlines()
 def test_manual_restart_releases_control_before_dial_and_no_duplicate_dial(self):
  self.assertEqual(self.restart_case(),(0,'complete',['10 /sbin/ifdown modem5g','radio --nw_radio_state_set 0','radio-on','10 /sbin/ifup modem5g']))
 def test_failed_radio_off_still_restores_radio_and_dial(self):
  self.assertEqual(self.restart_case(radio_rc=1),(1,'failed',['10 /sbin/ifdown modem5g','radio --nw_radio_state_set 0','radio-on','10 /sbin/ifup modem5g']))
 def test_manual_restart_keeps_user_disconnected_without_auto_dial(self):
  self.assertEqual(self.restart_case(auto=0),(0,'complete',['10 /sbin/ifdown modem5g','radio --nw_radio_state_set 0','radio-on']))
if __name__=='__main__':unittest.main()
