#!/usr/bin/env python3
"""Real APK v3 signing/index/resolver checks, with synthetic payloads only."""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('library',ROOT/'scripts/mt6990-apk-library.py');lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
APK=os.environ.get('APK')

class NativeLibraryTest(unittest.TestCase):
 def setUp(self):
  self.assertTrue(APK and pathlib.Path(APK).is_file(),'Set APK to the native build-pinned apk-tools executable')
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  for d in ['files/'+lib.META,'rootfs/'+lib.META,'rootfs/etc/apk/keys','bin/packages/'+lib.ARCH+'/base','payload']:(self.root/d).mkdir(parents=True)
  self.run_command(['openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',self.root/'private-key.pem'])
  self.run_command(['openssl','pkey','-in',self.root/'private-key.pem','-pubout','-out',self.root/'public-key.pem'])
  flags={'TARGET_mediatek_mt6990':'y','TARGET_mediatek_mt6990_DEVICE_fiberhome_lg6851f':'y','USE_APK':'y','SIGNED_PACKAGES':'y','SIGN_EACH_PACKAGE':'y','SIGNATURE_CHECK':'y','TARGET_ARCH_PACKAGES':'"'+lib.ARCH+'"','PACKAGE_fixture-app':'m'}
  (self.root/'.config').write_text(''.join('CONFIG_'+k+'='+v+'\n' for k,v in flags.items()))
  meta={'version':1,'board':'fiberhome,lg6851f','target':'mediatek/mt6990','repository':'adian2020/example','snapshot':'12345-1','source_sha':'a'*40,'architecture':lib.ARCH,'repository_url':'https://raw.githubusercontent.com/adian2020/example/apk-lib-12345-1/12345-1/packages.adb'}
  lib.writejson(self.root/'files'/lib.META/'build.json',meta);lib.writejson(self.root/'files'/lib.META/'selection.json',{'fixture-app':'m'});(self.root/'files'/lib.META/'repositories.list').write_text(meta['repository_url']+'\n')
  for n in ['build.json','selection.json','repositories.list']:shutil.copy(self.root/'files'/lib.META/n,self.root/'rootfs'/lib.META/n)
  for dst in [self.root/'rootfs/etc/apk/keys/public-key.pem',self.root/'rootfs'/lib.META/'public-key.pem']:shutil.copy(self.root/'public-key.pem',dst)
  (self.root/'files/etc').mkdir(exist_ok=True);(self.root/'files/etc/mt6990-plugin-versions.json').write_text('[]')
  (self.root/'rootfs/etc/apk/world').write_text('kernel=6.18.44-r1\n')
  for name,version,dep in [('kernel','6.18.44-r1',''),('fixture-lib','1-r0',''),('fixture-app','1-r0','fixture-lib'),('nikki','1-r0',''),('luci-app-nikki','1-r0',''),('luci-i18n-nikki-zh-cn','1-r0',''),('mihomo-meta','1-r0','')]:self.make_package(name,version,dep)
 def run_command(self,args):return subprocess.run([str(a) for a in args],check=True,capture_output=True,text=True)
 def make_package(self,name,version='1-r0',dep='',key=None,provides=''):
  path=self.root/'bin/packages'/lib.ARCH/'base'/f'{name}-{version}.apk'
  self.run_command([APK,'mkpkg','--info','name:'+name,'--info','version:'+version,'--info','arch:'+lib.ARCH,'--info','depends:'+dep,'--info','provides:'+provides,'--files',self.root/'payload','--sign',key or self.root/'private-key.pem','--output',path]);return path
 def bundle(self):lib.bundle(self.root,self.root/'bin/output',self.root/'rootfs',pathlib.Path(APK))
 def test_real_signed_packages_index_and_transitive_dependency_simulation(self):
  self.bundle();folder=self.root/'bin/output';manifest=lib.readjson(folder/'repository.manifest.json')
  self.assertEqual(manifest['package_count'],7);self.assertEqual(manifest['packages']['fixture-lib'],'1-r0')
  self.assertFalse((folder/'private-key.pem').exists());self.assertEqual(manifest['public_key_sha256'],lib.sha(self.root/'public-key.pem'))
  self.assertFalse((self.root/'rootfs/usr/bin/fixture-app').exists())
  self.assertEqual(manifest['firmware_world'],['kernel=6.18.44-r1'])
  self.assertEqual((folder/'firmware.world').read_bytes(),(self.root/'rootfs/etc/apk/world').read_bytes())
  self.assertEqual(lib.readjson(self.root/'bin/mt6990-apk-validation/validation.json')['status'],'passed')
 def test_missing_dependency_stops_before_publication(self):
  (self.root/'bin/packages'/lib.ARCH/'base/fixture-lib-1-r0.apk').unlink()
  with self.assertRaisesRegex(RuntimeError,"fixture-app"):self.bundle()
  self.assertFalse((self.root/'bin/output').exists())
 def test_unversioned_virtual_provider_uses_the_firmware_world(self):
  self.make_package('ca-bundle',provides='ca-certs')
  self.make_package('fixture-tls',dep='ca-certs')
  # The old empty-world request fails even though the provider is in the index.
  with self.assertRaisesRegex(RuntimeError,'ca-certs'):self.bundle()
  diagnostics=self.root/'bin/mt6990-apk-validation'
  self.assertEqual(lib.readjson(diagnostics/'validation.json')['status'],'failed')
  self.assertTrue((diagnostics/'packages.adb').is_file())
  self.assertFalse((diagnostics/'private-key.pem').exists())
  world=self.root/'rootfs/etc/apk/world';world.write_text(world.read_text()+'ca-bundle=1-r0\n')
  before=world.read_bytes();self.bundle();self.assertEqual(world.read_bytes(),before)
  self.assertEqual(lib.readjson(self.root/'bin/output/repository.manifest.json')['package_count'],9)
 def test_world_parser_reads_the_real_apk_generated_format(self):
  self.make_package('ca-bundle',provides='ca-certs')
  world=self.root/'rootfs/etc/apk/world';world.write_text(world.read_text()+'ca-bundle=1-r0\n')
  self.bundle()
  image=self.root/'actual-image';image.mkdir()
  self.run_command([APK,'--root',image,'--arch',lib.ARCH,'--keys-dir',self.root/'rootfs/etc/apk/keys','--no-network','--no-scripts','--repositories-file','/dev/null','--repository',self.root/'bin/output/packages.adb','add','--initdb','--usermode','kernel=6.18.44-r1','ca-bundle=1-r0'])
  versions={'kernel':'6.18.44-r1','ca-bundle':'1-r0'}
  self.assertEqual(set(lib.firmware_world(image,versions)),{'kernel=6.18.44-r1','ca-bundle=1-r0'})
 def test_missing_world_or_mismatched_base_constraints_stop_publication(self):
  world=self.root/'rootfs/etc/apk/world';world.unlink()
  with self.assertRaisesRegex(ValueError,'world'):self.bundle()
  for text in ['', '--allow-untrusted\n', 'missing-base\n', 'kernel=other-version\n']:
   world.write_text(text)
   with self.assertRaises(ValueError):self.bundle()
  self.assertFalse((self.root/'bin/output').exists())
 def test_foreign_signature_is_rejected(self):
  other=self.root/'other.pem';self.run_command(['openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',other]);self.make_package('foreign',key=other)
  with self.assertRaises(subprocess.CalledProcessError):self.bundle()
  self.assertFalse((self.root/'bin/output').exists())
 def test_image_key_and_identity_must_match(self):
  (self.root/'rootfs'/lib.META/'public-key.pem').write_text('wrong')
  with self.assertRaises(ValueError):self.bundle()
  shutil.copy(self.root/'public-key.pem',self.root/'rootfs'/lib.META/'public-key.pem')
  (self.root/'rootfs'/lib.META/'build.json').write_text('{}')
  with self.assertRaises(ValueError):self.bundle()
if __name__=='__main__':unittest.main()
