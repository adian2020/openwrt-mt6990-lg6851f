#!/usr/bin/env python3
"""Run the production transaction with real flock and mocked modem/netifd."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'package/vendor/lg6851f-modem-chain-only/files/usr/bin/lg6851f-modem-lock'


class LockTransactionTest(unittest.TestCase):
    def run_case(self,scenario='success',action=None):
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name)
            job=root/'lg6851f-lock-job.test';job.mkdir()
            (root/'network').write_text('true\n')
            (root/'state').write_text('MODE=bands\nSTATUS=verified\nLTE=7\nNR=77\n')
            old_state=(root/'state').read_text()
            (root/'ifdown').write_text('#!/bin/sh\necho false > "$TEST_DIR/network"\n')
            (root/'ifup').write_text('''#!/bin/sh
if ! /usr/bin/flock -n "$TEST_DIR/control.lock" -c true; then
 echo 'ifup blocked by parent control lock' >> "$TEST_DIR/errors"; exit 70
fi
if [ "$TEST_SCENARIO" = success ]; then
 grep -q 'OP_ID=lg6851f-lock-job.test' "$TEST_DIR/state" || exit 91
 grep -q 'STATUS=verified' "$TEST_DIR/state" || exit 92
 grep -q 'STATUS=verified' "$TEST_DIR/lg6851f-lock-job.test/state" || exit 93
 grep -q 'PHASE=restoring_data' "$TEST_DIR/lg6851f-lock-job.test/state" || exit 94
fi
[ "$TEST_SCENARIO" != network_fail ] || exit 70
echo true > "$TEST_DIR/network"
''')
            for binary in ['ifdown','ifup']:(root/binary).chmod(0o700)
            source=SCRIPT.read_text().replace('/var/lock/luci-modem5g-control.lock',str(root/'control.lock')).replace('/var/lock/lg6851f-modem-recovery.lock',str(root/'recovery')).replace('/etc/modem5g-lock.state',str(root/'state')).replace('/tmp/lg6851f-modem-control.active',str(root/'active')).replace('JOB_DIR="/tmp/$REQUEST_ID"','JOB_DIR="$TEST_DIR/$REQUEST_ID"').replace('/sbin/ifdown',str(root/'ifdown')).replace('/sbin/ifup',str(root/'ifup'))
            prefix,main=source.split('action="${1:-}"',1)
            mocks=r'''
network_up() { cat "$TEST_DIR/network"; }
set_mode_rat() {
 case "$1" in 3) menu=1;;15)menu=2;;19)menu=3;;21)menu=4;;*)return 22;;esac
 echo "$menu" > "$TEST_DIR/pending-mode"
}
wait_cli_idle() { return 0; }
wait_network_up() { [ "$TEST_SCENARIO" != network_fail ]; }
run_sample() {
 input="$(cat)"
 case "$input" in
 *18*)
  menu="$(cat "$TEST_DIR/pending-mode")";disabled=$(printf '%s\n' "$input" | sed -n '3p')
  printf '%s %s\n' "$menu" "$disabled" > "$TEST_DIR/mode-values"
  printf 'set nr disable mode success!\n'; return 0;;
 *55*)
  values="$(cat "$TEST_DIR/mode-values" 2>/dev/null || echo '4 3')"
  [ "$TEST_SCENARIO" != mode_bad_readback ] || values='4 3'
  case "$values" in '4 3') mode=QL_NW_MODE_WCDMA_LTE_NR5G;disabled=NEITHER_IS_DISABLED;; '3 2') mode=QL_NW_MODE_LTE_NR5G;disabled=DISABLE_SA;; '2 1') mode=QL_NW_MODE_NR5G;disabled=DISABLE_NSA;; '1 0') mode=QL_NW_MODE_LTE;disabled=DISABLE_NSA_AND_SA;; *) return 5;; esac
  printf 'The current nwomde: \n%s\nThe current NR Disable Mode: \n%s\n' "$mode" "$disabled";return 0;;
 esac
 case "$input" in *19*)
  if [ "$TEST_SCENARIO" = bad_readback ]; then echo 'lte band info = 0000004000000000'; else echo 'lte band info = 0000000500000000'; fi
  echo 'nr band info = 000000000000000000002000' ;;
 *) printf 'set or restore band success!\nset or restore band success!\n' ;;
 esac
}
'''
            result=subprocess.run(['sh','-c',prefix+mocks+'\naction="${1:-}"'+main,'test','--request-id','lg6851f-lock-job.test',*(action or ['apply-bands','1,3','78'])],env=dict(os.environ,TEST_DIR=name,TEST_SCENARIO=scenario),capture_output=True,text=True,timeout=10)
            return result,{p.name:p.read_text() for p in root.iterdir() if p.is_file()},(job/'state').read_text(),old_state

    def test_modes_verify_sa_nsa_lte_and_restore_data_without_changing_band_state(self):
        for name,values in [('sa','2 1'),('nsa','3 2'),('lte','1 0'),('auto','4 3')]:
            with self.subTest(mode=name):
                result,files,progress,old=self.run_case('mode_success',['set-mode',name])
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                self.assertEqual(files['mode-values'].strip(),values)
                self.assertEqual(files['state'],old)
                self.assertNotIn('errors',files)
                self.assertIn('STATUS=verified',progress)
                self.assertIn('NETWORK=online',progress)

    def test_mode_readback_failure_rolls_back_and_never_claims_success(self):
        result,files,progress,old=self.run_case('mode_bad_readback',['set-mode','nsa'])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(files['mode-values'].strip(),'4 3')
        self.assertEqual(files['state'],old)
        self.assertIn('STATUS=failed',progress)
        self.assertIn('previous mode restored',result.stdout)

    def test_verified_bands_are_published_before_ifup_and_control_lock_is_free(self):
        result,files,progress,_=self.run_case()
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertNotIn('errors',files)
        self.assertIn('STATUS=verified',progress)
        self.assertIn('PHASE=complete',progress)
        self.assertIn('NETWORK=online',progress)
        self.assertNotIn('active',files)

    def test_wrong_mask_never_replaces_verified_state_or_claims_success(self):
        result,files,progress,old=self.run_case('bad_readback')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(files['state'],old)
        self.assertIn('STATUS=failed',progress)
        self.assertIn('PHASE=failed',progress)
        self.assertNotIn('active',files)

    def test_network_failure_retains_actual_verified_band_result(self):
        result,files,progress,_=self.run_case('network_fail')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('STATUS=verified',files['state'])
        self.assertIn('STATUS=verified',progress)
        self.assertIn('NETWORK=failed',progress)
        self.assertIn('PHASE=failed',progress)
        self.assertNotIn('active',files)

    def test_cell_verification_deadline_includes_queries_and_cooldowns(self):
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name);(root/'clock').write_text('100')
            prefix=SCRIPT.read_text().split('action="${1:-}"')[0].replace('/bin/sleep','test_sleep').replace('/usr/bin/timeout','test_timeout')
            mock=r'''
date() { cat "$TEST_DIR/clock"; }
advance() { echo $(( $(cat "$TEST_DIR/clock") + $1 )) > "$TEST_DIR/clock"; }
test_sleep() { advance "$1"; }
test_timeout() {
 advance "$1"
 echo call >> "$TEST_DIR/calls"
 echo '+ECELL: 1,11,0,0,0,0,23,100,80,0,0,0,100,0,0,640000'
}
'''
            result=subprocess.run(['sh','-c',mock+prefix+'\nuptime_seconds() { cat "$TEST_DIR/clock"; }; verify_cell 627264 23'],env=dict(os.environ,TEST_DIR=name),capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertLessEqual(int((root/'clock').read_text())-100,45)
            self.assertLessEqual(len((root/'calls').read_text().splitlines()),3)

    def test_status_collector_yields_during_control_transaction(self):
        with tempfile.TemporaryDirectory() as name:
            marker=pathlib.Path(name)/'active';marker.touch()
            source=(SCRIPT.parent/'lg6851f-modem-status').read_text().split("trap 'rm -f")[0]
            source=source.replace('. /lib/functions.sh','config_load() { :; }; config_get() { :; }').replace('/tmp/lg6851f-modem-control.active',str(marker))
            for call in ['query nw_get_rat',"at_query 'AT+ECELL'"]:
                result=subprocess.run(['sh','-c',source+'\n'+call],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,75,result.stderr)

    def test_ims_collector_preserves_cache_on_failure_and_yields_first_dial(self):
        source=(SCRIPT.parent/'lg6851f-modem-status').read_text().split("trap 'rm -f")[0]
        source=source.replace('. /lib/functions.sh','config_load() { :; }; config_get() { :; }')
        cases=[('false',0,'+CIREG: 2,1,5','old','1',False),
               ('true',7,'+CIREG: 2,1,5','old','1',True),
               ('true',0,'OK','old','1',True),
               ('true',0,'+CIREG: 2,1,5','+CIREG: 2,1,5','42',True),
               ('true',0,'+CIREG: 2,0','+CIREG: 2,0','42',True)]
        with tempfile.TemporaryDirectory() as name:
            for up,rc,output,expected,updated,called in cases:
                with self.subTest(up=up,rc=rc,output=output):
                    calls=pathlib.Path(name)/'calls';calls.unlink(missing_ok=True)
                    mock='''
at_query() { [ "$1" = 'AT+CIREG?' ] || exit 99; echo call >> "$TEST_DIR/calls"; printf '%s\\n' "$TEST_OUTPUT"; return "$TEST_RC"; }
date() { echo 42; }
IMS_CIREG=old; IMS_UPDATED=1
update_ims
printf '%s\\n%s\\n' "$IMS_CIREG" "$IMS_UPDATED"
'''
                    r=subprocess.run(['sh','-c',source+mock],env=dict(os.environ,UP=up,TEST_RC=str(rc),TEST_OUTPUT=output,TEST_DIR=name),capture_output=True,text=True,timeout=5)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(r.stdout.splitlines(),[expected,updated])
                    self.assertEqual(calls.exists(),called)


if __name__=='__main__':unittest.main()
