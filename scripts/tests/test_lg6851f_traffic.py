import os, pathlib, subprocess, unittest, shutil, tempfile, json
ROOT=pathlib.Path(__file__).resolve().parents[2]
UCODE=os.environ.get('UCODE') or shutil.which('ucode')
@unittest.skipUnless(UCODE,'需要固定版本 ucode')
class TrafficAccountingTest(unittest.TestCase):
 def run_fixture(self,name):
  args=[UCODE]
  for library in [os.environ.get('UCODE_LIBRARY'),str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/ucode')]:
   if library:args+=['-L',library]
  args+=[str(ROOT/('scripts/tests/fixtures/'+name+'.uc'))]
  r=subprocess.run(args,env=dict(os.environ,TZ='UTC0'),capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
  return r.stdout
 def test_boundaries_reboot_calibration_and_lifetime(self):
  self.assertIn('累计流量扩展',self.run_fixture('lg6851f-traffic-core'))
 @unittest.skipUnless(os.path.exists(os.path.join(os.environ.get('UCODE_LIBRARY',''),'uci.so')),'需要原生 UCI 模块')
 def test_apn_profiles_actual_uci_and_platform_mapping(self):
  self.assertIn('MT6990 APN',self.run_fixture('lg6851f-apn'))
 @unittest.skipUnless(os.path.exists(os.path.join(os.environ.get('UCODE_LIBRARY',''),'uci.so')),'需要原生 UCI 模块')
 def test_resolver_failure_is_nonzero_before_netifd_applies(self):
  with tempfile.TemporaryDirectory() as name:
   folder=pathlib.Path(name)
   (folder/'network').write_text("config interface 'modem5g'\n option proto 'ql_datacall'\n option apn 'global.test'\n option iptype '3'\n")
   source=(ROOT/'package/vendor/luci-app-5gmodem/root/usr/libexec/lg6851f-apn-resolve.uc').read_text().replace('let c=cursor(),','let c=cursor(TEST_CONFIG_DIR),')
   script=folder/'resolve.uc';script.write_text(source)
   env=dict(os.environ,LG6851F_APN_ICCID='89860012345678901234',LG6851F_APN_IMSI='460001234567890')
   args=[UCODE,'-L',os.environ['UCODE_LIBRARY'],'-L',str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/ucode'),'-D','TEST_CONFIG_DIR='+json.dumps(name),str(script)]
   binding="config selection 'card'\n option iccid '89860012345678901234'\n option mode 'manual'\n option profile 'missing'\n"
   (folder/'lg6851f_apn').write_text(binding)
   r=subprocess.run(args,env=env,capture_output=True,text=True)
   self.assertNotEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['error'],'apn_missing')
   (folder/'lg6851f_apn').write_text(binding+"config profile 'missing'\n option name '专网'\n option apn 'private.test'\n option pdptype 'IP'\n option auth 'chap'\n option password 'test-secret'\n")
   r=subprocess.run(args,env=env,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);value=json.loads(r.stdout)
   self.assertEqual(value['settings']['apn'],'private.test');self.assertEqual(value['settings']['iptype'],1);self.assertEqual(value['settings']['auth'],2)
if __name__=='__main__':unittest.main()
