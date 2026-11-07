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
    def run_case(self,scenario='success'):
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
wait_cli_idle() { return 0; }
wait_network_up() { [ "$TEST_SCENARIO" != network_fail ]; }
run_sample() {
 input="$(cat)"
 case "$input" in *19*)
  if [ "$TEST_SCENARIO" = bad_readback ]; then echo 'lte band info = 0000004000000000'; else echo 'lte band info = 0000000500000000'; fi
  echo 'nr band info = 000000000000000000002000' ;;
 *) printf 'set or restore band success!\nset or restore band success!\n' ;;
 esac
}
'''
            result=subprocess.run(['sh','-c',prefix+mocks+'\naction="${1:-}"'+main,'test','--request-id','lg6851f-lock-job.test','apply-bands','1,3','78'],env=dict(os.environ,TEST_DIR=name,TEST_SCENARIO=scenario),capture_output=True,text=True,timeout=10)
            return result,{p.name:p.read_text() for p in root.iterdir() if p.is_file()},(job/'state').read_text(),old_state

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


if __name__=='__main__':unittest.main()
