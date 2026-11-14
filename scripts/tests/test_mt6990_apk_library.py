#!/usr/bin/env python3
"""Library selection, on-device setup and immutable publishing; local fixtures only."""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
lib=module('library',ROOT/'scripts/mt6990-apk-library.py')
pub=module('publisher',ROOT/'scripts/mt6990-publish-apk-library.py')

def git(root,*args):return subprocess.check_output(['git','-C',str(root),*map(str,args)],text=True,stderr=subprocess.DEVNULL).strip()
def source_repo(root):
 root.mkdir(parents=True,exist_ok=True);git(root,'init','--quiet');git(root,'config','user.email','fixture@example.invalid');git(root,'config','user.name','Fixture')
 (root/'source-marker').write_text('source unchanged');git(root,'add','.');git(root,'commit','-qm','Fixture source');return git(root,'rev-parse','HEAD')

class SelectionTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);self.source=source_repo(self.root)
  self.config=self.root/'.config';self.config.write_text('CONFIG_TARGET_mediatek_mt6990=y\nCONFIG_TARGET_mediatek_mt6990_DEVICE_fiberhome_lg6851f=y\nCONFIG_USE_APK=y\nCONFIG_SIGNED_PACKAGES=y\nCONFIG_SIGN_EACH_PACKAGE=y\nCONFIG_SIGNATURE_CHECK=y\nCONFIG_TARGET_ARCH_PACKAGES="'+lib.ARCH+'"\nCONFIG_PACKAGE_bash=y\n# CONFIG_PACKAGE_luci-app-wol is not set\nCONFIG_PACKAGE_luci-app-5gmodem=y\n')
  self.profile=self.root/'profile.json';lib.writejson(self.profile,{'version':1,'applications':['luci-app-wol'],'utilities':['bash','jq']})
 def test_apps_and_translations_are_optional_and_builtins_are_preserved(self):
  selection=lib.select(self.root,self.config,self.profile)
  self.assertEqual(selection,{'bash':'y','jq':'m','luci-app-wol':'m','luci-i18n-wol-zh-cn':'m'})
  self.assertEqual(lib.flags(self.config)['PACKAGE_luci-app-5gmodem'],'y')
  self.assertEqual(lib.verify_selection(self.root,self.config),selection)
  lib.select(self.root,self.config,self.profile);self.assertEqual(self.config.read_text().count('CONFIG_PACKAGE_jq='),1)
 def test_missing_or_promoted_packages_and_disabled_signatures_fail(self):
  lib.select(self.root,self.config,self.profile);original=self.config.read_text()
  for bad in [original.replace('CONFIG_PACKAGE_jq=m','CONFIG_PACKAGE_jq=y'),original.replace('CONFIG_PACKAGE_jq=m',''),original.replace('CONFIG_SIGNATURE_CHECK=y','CONFIG_SIGNATURE_CHECK=n')]:
   self.config.write_text(bad)
   with self.assertRaises(ValueError):lib.verify_selection(self.root,self.config)
 def test_snapshot_preparation_checks_source_and_rerun_identity(self):
  with self.assertRaises(ValueError):lib.prepare(self.root,'adian2020/example','123-1','f'*40)
  lib.prepare(self.root,'adian2020/example','123-2',self.source)
  meta=lib.readjson(self.root/'files'/lib.META/'build.json');self.assertEqual(meta['snapshot'],'123-2')
  self.assertIn('/apk-lib-123-2/123-2/packages.adb',(self.root/'files'/lib.META/'repositories.list').read_text())
  with self.assertRaises(ValueError):lib.prepare(self.root,'adian2020/example','latest',self.source)
 def test_collect_refuses_conflicting_files_and_escaping_links(self):
  a=self.root/'bin/targets/mediatek/mt6990/packages';b=self.root/'bin/packages'/lib.ARCH/'base';a.mkdir(parents=True);b.mkdir(parents=True)
  (a/'x.apk').write_bytes(b'one');(b/'x.apk').write_bytes(b'two')
  with self.assertRaises(ValueError):lib.collect_packages(self.root)
  (b/'x.apk').unlink();(b/'outside.apk').symlink_to(self.root/'source-marker')
  with self.assertRaises(ValueError):lib.collect_packages(self.root)

class RuntimeSetupTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  self.meta=self.root/'meta';self.apk=self.root/'apk';self.meta.mkdir();(self.apk/'repositories.d').mkdir(parents=True);(self.apk/'keys').mkdir()
  self.identity={'version':1,'snapshot':'123-2','source_sha':'a'*40,'repository':'adian2020/example','architecture':lib.ARCH}
  lib.writejson(self.meta/'build.json',self.identity);self.url='https://raw.githubusercontent.com/adian2020/example/apk-lib-123-2/123-2/packages.adb\n';(self.meta/'repositories.list').write_text(self.url);(self.meta/'public-key.pem').write_text('ROM public key')
  (self.root/'board_name').write_text('fiberhome,lg6851f')
  self.idfile=self.root/'firmware-id';self.idfile.write_text('a'*40)
  (self.apk/'keys/public-key.pem').write_text('preserved old key');(self.apk/'arch').write_text('aarch64_cortex-a53\n')
  self.old='https://cdn.jsdelivr.net/gh/13179415360/openwrt-mt6990-lg6851f@760d829021769a0aff5d713e7316c7d36ff40c71/base/packages.adb\n'
  (self.apk/'repositories.d/distfeeds.list').write_text(self.old+'https://custom.invalid/packages.adb\n')
  (self.apk/'repositories.d/nikki.list').write_text('https://raw.githubusercontent.com/adian2020/example/nikki-apk/old/packages.adb\n')
  (self.apk/'repositories.d/customfeeds.list').write_text('custom retained')
  binary=self.root/'bin';binary.mkdir();jf=binary/'jsonfilter';jf.write_text('#!/usr/bin/python3\nimport sys,json\na=sys.argv\nv=json.load(open(a[a.index("-i")+1]));print(v[a[a.index("-e")+1][2:]])\n');jf.chmod(0o700)
  source=(ROOT/'target/linux/mediatek/mt6990/base-files/usr/bin/lg6851f-setup-apk-library').read_text().replace('/usr/share/mt6990-apk',str(self.meta)).replace('/etc/apk',str(self.apk)).replace('/etc/mt6990-firmware-id',str(self.idfile)).replace('/tmp/sysinfo/board_name',str(self.root/'board_name'))
  self.script=self.root/'setup';self.script.write_text(source);self.env=dict(os.environ,PATH=str(binary)+':'+os.environ['PATH'])
 def apply(self):return subprocess.run(['sh',str(self.script)],env=self.env,capture_output=True,text=True)
 def test_new_rom_key_wins_over_restored_key_and_only_known_old_endpoints_are_disabled(self):
  result=self.apply();self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual((self.apk/'keys/lg6851f-build-123-2.pem').read_text(),'ROM public key')
  self.assertEqual((self.apk/'keys/public-key.pem').read_text(),'preserved old key')
  self.assertEqual((self.apk/'repositories.d/firmware.list').read_text(),self.url)
  self.assertEqual((self.apk/'repositories.d/distfeeds.list').read_text(),'https://custom.invalid/packages.adb\n')
  self.assertEqual((self.apk/'repositories.d/customfeeds.list').read_text(),'custom retained')
  self.assertNotIn('/nikki-apk/',(self.apk/'repositories.d/nikki.list').read_text())
  backup=(self.apk/'library-backups/123-2/distfeeds.list').read_text();self.assertIn(self.old,backup)
  self.assertEqual(self.apply().returncode,0);self.assertEqual((self.apk/'library-backups/123-2/distfeeds.list').read_text(),backup)
 def test_invalid_identity_url_or_missing_rom_key_refuses_changes(self):
  original=(self.apk/'repositories.d/distfeeds.list').read_bytes()
  self.idfile.write_text('b'*40);self.assertNotEqual(self.apply().returncode,0)
  self.idfile.write_text('a'*40);(self.meta/'repositories.list').write_text('https://unexpected.invalid/packages.adb\n');self.assertNotEqual(self.apply().returncode,0)
  (self.meta/'repositories.list').write_text(self.url);(self.meta/'public-key.pem').unlink();self.assertNotEqual(self.apply().returncode,0)
  self.assertEqual((self.apk/'repositories.d/distfeeds.list').read_bytes(),original)
  self.assertFalse((self.apk/'repositories.d/firmware.list').exists())

class PublisherTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);self.source=source_repo(self.root/'source');self.repo=self.root/'source'
  self.origin=self.root/'remote.git';git(self.root,'init','--bare','--quiet',self.origin);git(self.repo,'remote','add','origin',self.origin)
  self.library=self.root/'library';self.library.mkdir()
 def library_files(self,snapshot,body='apk data'):
  (self.library/'fixture.apk').write_text(body)
  lib.writejson(self.library/'repository.manifest.json',{'repository':'adian2020/example','snapshot':snapshot,'source_sha':self.source})
  (self.library/'SHA256SUMS').write_text(''.join(lib.sha(p)+'  '+p.name+'\n' for p in sorted(self.library.iterdir()) if p.name!='SHA256SUMS'))
 def test_append_idempotence_and_refuse_overwrite_without_touching_source(self):
  self.library_files('123-1');pub.publish(self.repo,self.library);first=git(self.origin,'rev-parse','refs/heads/firmware-apk')
  self.assertEqual(git(self.origin,'rev-parse','refs/tags/apk-lib-123-1'),first)
  pub.publish(self.repo,self.library);self.assertEqual(git(self.origin,'rev-parse','refs/heads/firmware-apk'),first)
  self.library_files('123-1','different')
  with self.assertRaises(ValueError):pub.publish(self.repo,self.library)
  self.assertEqual(git(self.origin,'rev-parse','refs/heads/firmware-apk'),first)
  self.library_files('123-2');pub.publish(self.repo,self.library)
  names=git(self.origin,'ls-tree','--name-only','refs/heads/firmware-apk').splitlines();self.assertIn('123-1',names);self.assertIn('123-2',names)
  self.assertEqual(git(self.origin,'rev-parse','refs/tags/apk-lib-123-1'),first)
  self.assertEqual(git(self.origin,'rev-parse','refs/tags/apk-lib-123-2'),git(self.origin,'rev-parse','refs/heads/firmware-apk'))
  self.assertEqual(git(self.repo,'rev-parse','HEAD'),self.source);self.assertEqual((self.repo/'source-marker').read_text(),'source unchanged');self.assertEqual(git(self.repo,'status','--porcelain'),'')
 def test_existing_tag_with_different_tree_is_rejected(self):
  self.library_files('123-1');pub.publish(self.repo,self.library)
  self.library_files('123-2');pub.publish(self.repo,self.library)
  # Corrupt only the local fixture remote, never a real published snapshot.
  wrong=git(self.origin,'rev-parse','refs/tags/apk-lib-123-1')
  git(self.origin,'update-ref','refs/tags/apk-lib-123-2',wrong)
  with self.assertRaises((ValueError,subprocess.CalledProcessError)):pub.publish(self.repo,self.library)
  self.assertEqual(git(self.origin,'rev-parse','refs/tags/apk-lib-123-2'),wrong)
 def test_bad_hashes_and_source_drift_are_rejected_before_publish(self):
  self.library_files('123-1');(self.library/'fixture.apk').write_text('tampered')
  with self.assertRaises(ValueError):pub.publish(self.repo,self.library)
  self.library_files('123-1');v=lib.readjson(self.library/'repository.manifest.json');v['source_sha']='b'*40;lib.writejson(self.library/'repository.manifest.json',v)
  with self.assertRaises(ValueError):pub.publish(self.repo,self.library)

if __name__=='__main__':unittest.main()
