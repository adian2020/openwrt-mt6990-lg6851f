"""Exercise feed compatibility preparation in a private checkout fixture."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class PrepareProxyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/mt6990-prepare-proxy.sh', self.root / 'scripts/prepare.sh')
        feeds = self.root / 'scripts/feeds'
        feeds.write_text('#!/bin/sh\n[ ! -d feeds/video/frameworks/qt6/qt6base ] || exit 99\nprintf "%s\\n" "$*" > feeds-update-called\n')
        feeds.chmod(0o755)
        for recipe in ['nikki/nikki', 'nikki/mihomo-meta', 'nikki/mihomo-alpha',
                       'video/frameworks/qt5/qt5base', 'video/frameworks/qt6/qt6base',
                       'luci/applications/luci-app-fwknopd', 'packages/sound/squeezelite',
                       'video/unrelated']:
            folder = self.root / 'feeds' / recipe
            folder.mkdir(parents=True)
            (folder / 'Makefile').write_text('DEPENDS:=+mihomo\n' if recipe == 'nikki/nikki' else 'unchanged\n')
        (self.root / 'tmp').mkdir()

    def prepare(self, config):
        (self.root / '.config').write_text(config)
        return subprocess.run(['sh', str(self.root / 'scripts/prepare.sh')],
                              capture_output=True, text=True)

    def test_unselected_qt6_is_removed_before_index_refresh(self):
        result = self.prepare('CONFIG_PACKAGE_luci-app-autoreboot=y\n# CONFIG_PACKAGE_qt6base-gui is not set\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'feeds/video/frameworks/qt6/qt6base').exists())
        self.assertEqual((self.root / 'feeds/video/unrelated/Makefile').read_text(), 'unchanged\n')
        self.assertEqual((self.root / 'feeds-update-called').read_text(), 'update -i nikki video luci packages\n')
        self.assertIn('+mihomo-meta', (self.root / 'feeds/nikki/nikki/Makefile').read_text())
        self.assertFalse((self.root / 'feeds/nikki/mihomo-alpha').exists())

    def test_explicit_qt6_selection_is_rejected_and_preserved(self):
        for package in ['qt6base-gui', 'qt6base-plugin-platforms-eglfs', 'qt6quick']:
            for value in ['y', 'm']:
                with self.subTest(package=package, value=value):
                    result = self.prepare(f'CONFIG_PACKAGE_{package}={value}\n')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Kconfig compatibility fix', result.stderr)
                    self.assertTrue((self.root / 'feeds/video/frameworks/qt6/qt6base/Makefile').is_file())
                    self.assertFalse((self.root / 'feeds-update-called').exists())


if __name__ == '__main__':
    unittest.main()
