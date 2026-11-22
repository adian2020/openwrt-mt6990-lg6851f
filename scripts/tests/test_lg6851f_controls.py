"""Run control RPC configuration logic with real UCI and no hardware commands."""
import json,os,pathlib,re,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
RPC=ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/rpcd/ucode/luci.modem5g'
UCODE=os.environ.get('UCODE')

class ControlTest(unittest.TestCase):
 def test_roaming_preserves_radio_settings_without_qos_rpc(self):
  self.assertTrue(UCODE,'Set UCODE to the native interpreter')
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);cfg=root/'config';cfg.mkdir()
   (cfg/'network').write_text("config interface 'modem5g'\n option auto '1'\n option radio_enabled '1'\n option dataroaming '0'\n")
   source=RPC.read_text().replace("import { cursor } from 'uci';","import { cursor as native_cursor } from 'uci';\nfunction cursor(){return native_cursor("+json.dumps(str(cfg))+",null,"+json.dumps(str(root/'delta'))+");}")
   source=re.sub(r'function board_ok\(\) \{.*?\n\}', 'function board_ok(){return true;}',source,count=1,flags=re.S)
   source=re.sub(r'function capture\(argv, seconds\) \{.*?\n\}', '''function capture(argv,seconds){
    return {code:0,output:''};
   }''',source,count=1,flags=re.S)
   rpc=root/'rpc.uc';rpc.write_text(source)
   program=root/'test.uc';program.write_text("""
let m=loadfile(%s)()['luci.modem5g'];
let roaming=m.set_data_roaming.call({args:{enabled:true}});
printf('%%J',{qos_read:m.get_fair_qos!=null,qos_write:m.set_fair_qos!=null,roaming});
"""%json.dumps(str(rpc)))
   cmd=[UCODE,'-L',os.environ['UCODE_LIBRARY'],'-L',str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/ucode'),str(program)]
   r=subprocess.run(cmd,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   value=json.loads(r.stdout)
   self.assertFalse(value['qos_read']);self.assertFalse(value['qos_write'])
   self.assertEqual(value['roaming']['code'],0)
   network=(cfg/'network').read_text()
   self.assertIn("option dataroaming '1'",network)
   self.assertIn("option auto '1'",network)
   self.assertIn("option radio_enabled '1'",network)

if __name__=='__main__':unittest.main()
