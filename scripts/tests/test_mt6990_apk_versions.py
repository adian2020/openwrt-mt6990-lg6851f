#!/usr/bin/env python3
"""Use real apk-tools to validate Smart versions before the full firmware build."""
import importlib.util
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('updater',ROOT/'scripts/mt6990-update-plugins.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
APK=os.environ.get('APK')

class ApkVersionTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(APK and pathlib.Path(APK).is_file(),'Set APK to the staged native apk-tools executable')
    def version(self,stamp):
        release={'tag_name':'Prerelease-Alpha','assets':[{'name':'mihomo-linux-arm64-alpha-smart-c4df732.gz','digest':'sha256:'+'a'*64,'updated_at':stamp}]}
        return u.smart_asset(release)[1]
    def check(self,version):
        return subprocess.run([APK,'version','--check',version],capture_output=True,text=True)
    def test_recipe_and_generated_versions_are_valid_and_can_be_packaged(self):
        recipe=(ROOT/'package/vendor/mihomo-openclash-core/Makefile').read_text()
        version=re.search(r'^PKG_VERSION:=(.+)$',recipe,re.M)[1]
        revision=re.search(r'^PKG_RELEASE:=(.+)$',recipe,re.M)[1]
        versions=[version+'-r'+revision,self.version('2026-11-14T00:00:01Z')+'-r'+revision,self.version('2026-11-14T23:59:59Z')+'-r'+revision]
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);(root/'payload').mkdir()
            for index,value in enumerate(versions):
                result=self.check(value);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                subprocess.run([APK,'mkpkg','--info','name:smart-version-regression','--info','version:'+value,'--info','arch:all','--files',str(root/'payload'),'--output',str(root/f'{index}.apk')],check=True,capture_output=True,text=True)
    def test_legacy_invalid_version_is_rejected(self):
        self.assertNotEqual(self.check('20261114~alpha.smart.c4df732-r3').returncode,0)
    def test_same_day_and_next_day_updates_sort_forward(self):
        versions=[self.version(t) for t in ['2026-11-14T00:00:01Z','2026-11-14T12:00:00Z','2026-11-14T23:59:59Z','2026-11-15T00:00:00Z']]
        for old,new in zip(versions,versions[1:]):
            result=subprocess.run([APK,'version','--test',old,new],capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),'<')

if __name__=='__main__':unittest.main()
