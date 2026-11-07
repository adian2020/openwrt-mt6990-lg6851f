#!/usr/bin/env python3
"""Dedicated feed setup must retain its pinned key and optional Nikki feed."""
import hashlib
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / 'target/linux/mediatek/mt6990/base-files'
KEY = BASE / 'etc/apk/keys/mt6990-760d829.pem'
DEFAULTS = BASE / 'etc/uci-defaults/98-lg6851f-apk-compatible-feeds'
FINGERPRINT = 'fee65298978c37b71198b8472673e6a73c5f7c0c99be6a85d030c4dc4a879d84'
FEED = 'https://cdn.jsdelivr.net/gh/13179415360/openwrt-mt6990-lg6851f@760d829021769a0aff5d713e7316c7d36ff40c71'


class ApkFeedTest(unittest.TestCase):
    def test_bundled_key_matches_immutable_manifest(self):
        self.assertEqual(hashlib.sha256(KEY.read_bytes()).hexdigest(), FINGERPRINT)

    def apply(self, key):
        with tempfile.TemporaryDirectory() as name:
            apk = pathlib.Path(name) / 'apk'
            (apk / 'keys').mkdir(parents=True)
            (apk / 'repositories.d').mkdir()
            if key is not None:
                (apk / 'keys/mt6990-760d829.pem').write_bytes(key)
            (apk / 'keys/public-key.pem').write_text('current build key')
            (apk / 'arch').write_text('aarch64_cortex-a53\n')
            (apk / 'repositories.d/distfeeds.list').write_text('original feed\n')
            (apk / 'repositories.d/nikki.list').write_text('firmware matched Nikki\n')
            (apk / 'repositories.d/customfeeds.list').write_text('old custom feed\n')
            script = DEFAULTS.read_text().replace('/etc/apk', str(apk))
            result = subprocess.run(['sh', '-c', script], capture_output=True, text=True)
            files = {str(p.relative_to(apk)): p.read_bytes() for p in apk.rglob('*') if p.is_file()}
            return result.returncode, files

    def test_configured_feeds_have_key_and_preserve_nikki_and_build_key(self):
        code, files = self.apply(KEY.read_bytes())
        self.assertEqual(code, 0)
        feeds = files['repositories.d/distfeeds.list'].decode().splitlines()
        self.assertEqual([line for line in feeds if not line.startswith('#')],
                         [FEED + '/' + feed + '/packages.adb' for feed in ['target', 'base', 'luci', 'packages']])
        self.assertEqual(files['keys/public-key.pem'], b'current build key')
        self.assertEqual(files['repositories.d/nikki.list'], b'firmware matched Nikki\n')
        self.assertEqual(files['customfeeds.disabled-by-mt6990-safety'], b'old custom feed\n')
        self.assertEqual(files['arch'], b'aarch64_cortex-a55_neon-vfpv4\n')

    def test_missing_or_wrong_key_refuses_feed_changes(self):
        for key in [None, b'wrong key\n']:
            with self.subTest(key=key):
                code, files = self.apply(key)
                self.assertNotEqual(code, 0)
                self.assertEqual(files['repositories.d/distfeeds.list'], b'original feed\n')
                self.assertEqual(files['repositories.d/customfeeds.list'], b'old custom feed\n')
                self.assertEqual(files['arch'], b'aarch64_cortex-a53\n')


if __name__ == '__main__':
    unittest.main()
