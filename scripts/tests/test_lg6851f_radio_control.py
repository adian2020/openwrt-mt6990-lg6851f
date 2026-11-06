#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/vendor/lg6851f-modem-chain-only/files'


class RadioControlTest(unittest.TestCase):
    def run_case(self, enabled, scenario='success'):
        with tempfile.TemporaryDirectory() as name:
            root = pathlib.Path(name)
            (root/'board').write_text('fiberhome,lg6851f')
            (root/'policy').write_text('0' if enabled else '1')
            library = (FILES/'lib/functions/lg6851f-radio.sh').read_text() + '''
lg6851f_radio_call() {
    echo "$*" >> "$TEST_DIR/calls"
    if [ "$1" = --nw_radio_state_set ]; then
        [ "$TEST_SCENARIO" != cancel ] || { kill -TERM "$$"; return 143; }
        [ "$TEST_SCENARIO" != error ] || return 74
        [ "$TEST_SCENARIO" != mismatch ] || return 0
        echo "$2" > "$TEST_DIR/hardware"
    else
        if [ -f "$TEST_DIR/hardware" ] && [ "$(cat "$TEST_DIR/hardware")" = 1 ]; then
            echo MIPC_NW_RADIO_STATE_ON
        else echo MIPC_NW_RADIO_STATE_OFF; fi
    fi
}
uci() {
    case "$2" in
    changes) [ "$TEST_SCENARIO" != dirty ] || echo network.lan.ipaddr=x ;;
    set) echo "${3##*=}" > "$TEST_DIR/pending" ;;
    commit) cp "$TEST_DIR/pending" "$TEST_DIR/policy" ;;
    esac
    return 0
}
timeout() {
    echo "$2" > "$TEST_DIR/action"
    cat "$TEST_DIR/policy" > "$TEST_DIR/action-policy"
    /usr/bin/flock -n "$TEST_DIR/control.lock" -c true || return 99
}
'''
            (root/'library').write_text(library)
            source = (FILES/'usr/bin/lg6851f-radio-control').read_text()
            for old, new in [('/tmp/sysinfo/board_name', str(root/'board')),
                             ('/lib/functions/lg6851f-radio.sh', str(root/'library')),
                             ('/var/lock/lg6851f-modem-recovery.lock', str(root/'recovery')),
                             ('/var/lock/luci-modem5g-control.lock', str(root/'control.lock'))]:
                source = source.replace(old, new)
            (root/'script').write_text(source)
            result = subprocess.run(['sh', str(root/'script'), str(int(enabled))],
                env=dict(os.environ, TEST_DIR=name, TEST_SCENARIO=scenario), capture_output=True, text=True)
            data = {p.name: p.read_text().strip() for p in root.iterdir() if p.name in ['policy','calls','action','action-policy']}
            self.assertFalse((root/'recovery').exists())
            return result.returncode, data

    def test_enable_verifies_persists_then_connects_after_unlock(self):
        rc, data = self.run_case(True)
        self.assertEqual(rc, 0)
        self.assertEqual(data['calls'].splitlines(), ['--nw_radio_state_set 1', '--nw_radio_state_get'])
        self.assertEqual((data['policy'],data['action-policy'],data['action']),('1','1','/sbin/ifup'))

    def test_disable_persists_before_stopping_data(self):
        rc, data = self.run_case(False)
        self.assertEqual(rc, 0)
        self.assertEqual((data['policy'],data['action-policy'],data['action']),('0','0','/sbin/ifdown'))

    def test_failed_or_unverified_action_never_saves_or_dials(self):
        for scenario, expected in [('error',74),('mismatch',5),('dirty',16),('cancel',143)]:
            with self.subTest(scenario=scenario):
                rc, data = self.run_case(True, scenario)
                self.assertEqual(rc, expected)
                self.assertEqual(data['policy'],'0')
                self.assertNotIn('action',data)
                if scenario=='dirty': self.assertNotIn('calls',data)


if __name__=='__main__': unittest.main()
