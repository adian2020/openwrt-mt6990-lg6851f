#!/usr/bin/env python3
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'package/vendor/lg6851f-modem-chain-only/files/lib/functions/lg6851f-radio.sh'

class RadioStartupTest(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as d:
            script = '''. "$1"
LG6851F_RADIO_LOCK="$2/control.lock"
statefile="$2/state"
echo OFF > "$statefile"
sleep() { :; }
logger() { :; }
# Keep the real startup retry algorithm; mock only the vendor transport.
scenario="$3"
uci() { [ "$scenario" != disabled ] && echo 1 || echo 0; }
lg6851f_radio_transaction() {
    case "$1" in
    --nw_radio_state_get) printf 'Get SW radio state:MIPC_NW_RADIO_STATE_%s\\r\\n' "$(cat "$statefile")" ;;
    --nw_radio_state_set) echo set >> "$statefile.calls"; [ "$scenario" = failure ] || echo ON > "$statefile" ;;
    esac
}
[ "$scenario" != already ] || echo ON > "$statefile"
lg6851f_ensure_radio_on
rc=$?
echo "rc=$rc"
wc -l < "$statefile.calls" 2>/dev/null || echo 0
exit 0
'''
            result = subprocess.run(['sh', '-c', script, 'test', str(HELPER), d, scenario], capture_output=True, text=True, check=True)
            return result.stdout.splitlines()

    def test_already_on_never_toggles_radio(self):
        self.assertEqual(self.run_case('already'), ['rc=0', '0'])

    def test_startup_enables_off_radio_and_verifies_it(self):
        self.assertEqual(self.run_case('startup'), ['rc=0', '1'])

    def test_explicitly_disabled_radio_is_not_enabled(self):
        self.assertEqual(self.run_case('disabled'), ['rc=2', '0'])

    def test_failure_is_bounded_and_reported(self):
        self.assertEqual(self.run_case('failure'), ['rc=1', '5'])

if __name__ == '__main__':
    unittest.main()
