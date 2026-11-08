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



class AutoAPNContinueTest(unittest.TestCase):
    def run_apn(self, configured='46002', valid='0'):
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name)
            (root/'proto').write_text(PROTO.read_text())
            script='''
INCLUDE_ONLY=1
. "$TEST_DIR/proto"
mipc_wan_cli() { echo '{}'; }
json_load() { return "$TEST_JSON_STATUS"; }
json_get_var() {
 case "$2" in
 apn|iaapn) value=ctnet;; plmn) value=460011;; protocol|roaming_protocol|iaprotocol|iaroaming_protocol) value=3;; auth_type) value=0;; *) value='';;
 esac
 export "$1=$value"
}
uci() { printf '%s\\n' "$*" >> "$TEST_DIR/uci-calls"; }
proto_notify_error() { echo "unexpected APN restart" >&2; exit 91; }
apn=custom.apn; plmn="$TEST_CONFIGURED"; iptype=1; roamingtype=1; iaroamingtype=1; dataroaming=0
check_auto_apn_prov "$plmn" modem5g
rc=$?
printf '%s\\n' "$rc" "$apn" "$plmn" "$iptype" "$iaapn" "$dataroaming" > "$TEST_DIR/state"
'''
            result=subprocess.run(['sh','-c',script],env=dict(os.environ,TEST_DIR=name,TEST_CONFIGURED=configured,TEST_JSON_STATUS=valid),text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=(root/'uci-calls').read_text() if (root/'uci-calls').exists() else ''
            return (root/'state').read_text().splitlines(),calls

    def test_changed_sim_continues_same_setup_with_detected_apn(self):
        state,calls=self.run_apn()
        self.assertEqual(state,['0','ctnet','460011','3','ctnet','0'])
        self.assertIn('set network.modem5g.plmn=460011',calls)
        self.assertNotIn('dataroaming=',calls)

    def test_same_sim_normalized_does_not_overwrite_manual_apn(self):
        state,calls=self.run_apn(configured='46011')
        self.assertEqual(state[1],'custom.apn')
        self.assertEqual(calls,'')

    def test_invalid_vendor_reply_does_not_change_configuration(self):
        state,calls=self.run_apn(valid='1')
        self.assertEqual(state[0:2],['1','custom.apn'])
        self.assertEqual(calls,'')

if __name__=='__main__':unittest.main()
