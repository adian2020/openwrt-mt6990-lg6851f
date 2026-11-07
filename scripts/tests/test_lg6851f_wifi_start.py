"""执行实际 Wi-Fi 启动脚本，验证不等待拨号、不重载已有 AP、尊重手动关闭。"""
import io,tarfile,json,os,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'package/vendor/lg6851f-modem-chain-only/files/usr/sbin/lg6851f-wifi-after-modem'
class WiFiStartupTest(unittest.TestCase):
 def run_case(self,enabled=False,provisioned=False,fail=False,phy=True,preserved=False):
  with tempfile.TemporaryDirectory() as name:
   root=pathlib.Path(name);(root/'bin').mkdir();(root/'state.json').write_text(json.dumps({'disabled':'0' if enabled else '1','country':'CN'}))
   if phy:(root/'phy0').mkdir()
   if provisioned:(root/'provisioned').touch()
   if preserved:
    with tarfile.open(root/'preserved.tgz','w:gz') as tar:
     info=tarfile.TarInfo('etc/config/wireless');info.size=4;tar.addfile(info,io.BytesIO(b'test'))
   uci=root/'bin/uci';uci.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['TEST_DIR']);s=json.loads((p/'state.json').read_text());a=sys.argv[1:];a=[v for v in a if v!='-q']
if a[0]=='show':print('wireless.radio0=wifi-device\\nwireless.default_radio0=wifi-iface')
elif a[0]=='get':
 key=a[1].split('.')[-1]
 print({'mode':'ap','device':'radio0','disabled':s['disabled']}.get(key,''))
elif a[0]=='set':
 key,value=a[1].split('=',1);s[key.split('.')[-1]]=value;(p/'state.json').write_text(json.dumps(s))
elif a[0]=='commit':sys.exit(int(os.environ['TEST_FAIL']))
''');uci.chmod(0o755)
   for cmd,body in [('wifi','echo "wifi $*" >> "$TEST_DIR/calls"'),('logger',':'),('sleep','echo sleep >> "$TEST_DIR/calls"'),('ubus','echo UNEXPECTED_MODEM_QUERY >> "$TEST_DIR/calls"; exit 99')]:
    p=root/'bin'/cmd;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
   source=SCRIPT.read_text().replace('/sys/class/ieee80211/phy0',str(root/'phy0')).replace('/etc/lg6851f-wifi-provisioned',str(root/'provisioned')).replace('/tmp/lg6851f-sysupgrade.tgz',str(root/'preserved.tgz'))
   script=root/'script';script.write_text(source)
   result=subprocess.run(['sh',str(script)],env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],TEST_DIR=name,TEST_FAIL=str(int(fail))),capture_output=True,text=True)
   return result.returncode,(root/'calls').read_text().splitlines() if (root/'calls').exists() else [],(root/'provisioned').exists()
 def test_first_boot_enables_once_without_cellular_wait(self):self.assertEqual(self.run_case(),(0,['wifi up'],True))
 def test_enabled_preserved_configuration_is_owned_by_netifd(self):self.assertEqual(self.run_case(enabled=True),(0,[],True))
 def test_manually_disabled_wifi_is_not_reenabled(self):self.assertEqual(self.run_case(provisioned=True),(0,[],True))
 def test_preserved_legacy_disabled_configuration_is_not_reenabled(self):self.assertEqual(self.run_case(preserved=True),(0,[],True))
 def test_failed_commit_does_not_mark_provisioned_or_start(self):self.assertEqual(self.run_case(fail=True),(1,[],False))
 def test_missing_phy_never_enables_wifi(self):
  rc,calls,marker=self.run_case(phy=False);self.assertEqual(rc,1);self.assertFalse(marker);self.assertEqual(calls,['sleep']*90)
if __name__=='__main__':unittest.main()
