#!/usr/bin/env python3
"""执行真实 shell 回读校验函数，仅替换厂商传输，不改模组。"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'package/vendor/lg6851f-modem-chain-only/files/usr/bin/lg6851f-modem-lock'


class BandVerifyTest(unittest.TestCase):
    def run_case(self, response, lte, nr):
        source = HELPER.read_text().split('action="${1:-}"')[0]
        script = source + '\nrun_sample() { cat >/dev/null; printf "%s\\n" "$TEST_RESPONSE"; }\nverify_bands "$1" "$2"\n'
        import os
        return subprocess.run(['sh', '-c', script, 'test', lte, nr],
                              env=dict(os.environ, TEST_RESPONSE=response), text=True, capture_output=True)

    def test_requested_band_match_checks_all_bits_including_n76(self):
        response = 'lte band info = 0000000500000000\nnr band info = 000000000000000000002000'
        self.assertEqual(self.run_case(response, '1,3', '78').returncode, 0)
        response = response.replace('00002000', '00002800')  # unwanted n76
        self.assertEqual(self.run_case(response, '1,3', '78').returncode, 5)

    def test_restore_uses_reported_capability_masks(self):
        current = 'lte band info = 880800d5000027a0\nnr band info = 080800d5000001a000003c00'
        self.assertEqual(self.run_case(current+'\n'+current, '__supported__', '__supported__').returncode, 0)
        missing76 = current.replace('00003c00', '00003400')
        self.assertEqual(self.run_case(missing76+'\n'+current, '__supported__', '__supported__').returncode, 5)

    def test_restore_fails_if_supported_mask_missing(self):
        current = 'lte band info = 880800d5000027a0\nnr band info = 080800d5000001a000003c00'
        self.assertEqual(self.run_case(current, '__supported__', '__supported__').returncode, 5)


if __name__ == '__main__':
    unittest.main()
