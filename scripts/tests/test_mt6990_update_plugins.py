"""Check update conflict and local adaptation handling without network access."""
import importlib.util
import pathlib
import unittest
import tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('updater',ROOT/'scripts/mt6990-update-plugins.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class PluginUpdateTest(unittest.TestCase):
    def test_independent_local_and_upstream_changes_merge(self):
        base=b'version=1\na\nb\nc\nd\nboot=unprotected\n'
        local=base.replace(b'boot=unprotected',b'boot=mt6990-protected')
        upstream=base.replace(b'version=1',b'version=2')
        self.assertEqual(u.merge_file(local,base,upstream),upstream.replace(b'boot=unprotected',b'boot=mt6990-protected'))
    def test_conflict_stops_instead_of_overwriting_local_protection(self):
        with self.assertRaises(RuntimeError):u.merge_file(b'boot=protected\n',b'boot=old\n',b'boot=changed\n')
    def test_native_uu_helpers_are_executable_before_image_install(self):
        with tempfile.TemporaryDirectory() as folder:
            package=pathlib.Path(folder)
            for name in ['root/etc/init.d/uuplugin','root/usr/libexec/uuplugin/uu-view','root/usr/libexec/uuplugin/uu-sync.d/openclash.sh']:
                path=package/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#!/bin/sh\n');path.chmod(0o644)
            u.adapt_uu_helpers(package)
            for path in package.rglob('*'):
                if path.is_file():self.assertEqual(path.stat().st_mode&0o777,0o755)

    def test_add_delete_binary_and_unchanged_paths(self):
        self.assertEqual(u.merge_file(None,None,b'added'),b'added')
        self.assertIsNone(u.merge_file(b'old',b'old',None))
        self.assertEqual(u.merge_file(b'local',b'base',b'base'),b'local')
        with self.assertRaises(RuntimeError):u.merge_file(b'local',b'base',None)
        with self.assertRaises(RuntimeError):u.merge_file(b'\0local',b'\0base',b'\0new')

if __name__=='__main__':unittest.main()
