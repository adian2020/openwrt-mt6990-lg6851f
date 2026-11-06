#!/usr/bin/env python3
"""执行实际 ql_datacall setup 的前半段，验证射频早于 SIM/APN，失败不永久阻断。"""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
PROTO=ROOT/'package/vendor/lg6851f-modem-chain-only/files/lib/netifd/proto/ql_datacall.sh'


class RadioSetupOrderTest(unittest.TestCase):
    def run_case(self, enabled=1, radio_rc=0):
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name)
            (root/'radio').write_text('lg6851f_ensure_radio_on() { echo radio >> "$TEST_DIR/order"; return "$TEST_RC"; }\n')
            (root/'proto').write_text(PROTO.read_text().replace('/lib/functions/lg6851f-radio.sh',str(root/'radio')))
            script='''INCLUDE_ONLY=1
. "$TEST_DIR/proto"
hexdump() { echo '0 0 0 0 0 0000'; }
cat() { [ "$1" != /sys/kernel/ccci/boot ] || { echo md1:4; return; }; command cat "$@"; }
uci() { case "$*" in *network.modem5g.radio_enabled*) echo "$TEST_ENABLED" ;; esac; }
json_get_vars() { apn=test.apn;auto_conf=1;vlan=0;mode=1; }
wait_modem_stack_ready() { return 0; }
proto_notify_error() { echo "$2" > "$TEST_DIR/error"; }
proto_block_restart() { echo blocked > "$TEST_DIR/blocked"; }
check_auto_apn_prov() { echo apn >> "$TEST_DIR/order"; exit 0; }
proto_ql_datacall_setup modem5g
exit 0
'''
            subprocess.run(['sh','-c',script],env=dict(os.environ,TEST_DIR=name,TEST_RC=str(radio_rc),TEST_ENABLED=str(enabled)),capture_output=True,text=True,check=True)
            return {p.name:p.read_text().strip() for p in root.iterdir() if p.name in ['order','error','blocked']}

    def test_radio_ready_precedes_apn(self):
        self.assertEqual(self.run_case(),{'order':'radio\napn'})

    def test_transient_failure_does_not_enter_apn_or_block_restart(self):
        data=self.run_case(radio_rc=1)
        self.assertEqual(data,{'order':'radio','error':'RADIO_START_PENDING'})

    def test_explicit_off_blocks_automatic_restart(self):
        self.assertEqual(self.run_case(enabled=0),{'error':'RADIO_DISABLED_BY_USER','blocked':'blocked'})


if __name__=='__main__':unittest.main()
