"""Run control RPC configuration logic with real UCI and no hardware commands."""
import json,os,pathlib,re,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
RPC=ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/rpcd/ucode/luci.modem5g'
UCODE=os.environ.get('UCODE')

class ControlTest(unittest.TestCase):
 def test_qos_opt_in_failure_cleanup_and_roaming_use_real_configuration(self):
  self.assertTrue(UCODE,'Set UCODE to the native interpreter')
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);cfg=root/'config';cfg.mkdir()
   (cfg/'lg6851f_fair_qos').write_text("config main 'main'\n option enabled '0'\n")
   (cfg/'network').write_text("config interface 'modem5g'\n option auto '1'\n option radio_enabled '1'\n option dataroaming '0'\n")
   source=RPC.read_text().replace("import { cursor } from 'uci';","import { cursor as native_cursor } from 'uci';\nfunction cursor(){return native_cursor("+json.dumps(str(cfg))+",null,"+json.dumps(str(root/'delta'))+");}")
   source=re.sub(r'function board_ok\(\) \{.*?\n\}', 'function board_ok(){return true;}',source,count=1,flags=re.S)
   source=re.sub(r'function capture\(argv, seconds\) \{.*?\n\}', '''function capture(argv,seconds){
    if(argv[0]=='/etc/init.d/lg6851f_fair_qos' && argv[1]=='restart' && getenv('FAIL_ENABLE')=='1')return {code:5,output:'simulated install failure'};
    return {code:0,output:''};
   }''',source,count=1,flags=re.S)
   rpc=root/'rpc.uc';rpc.write_text(source)
   program=root/'test.uc';program.write_text("""
let m=loadfile(%s)()['luci.modem5g'];
let initial=m.get_fair_qos.call();
let invalid=m.set_fair_qos.call({args:{enabled:'true'}});
let on=m.set_fair_qos.call({args:{enabled:true}});
let off=m.set_fair_qos.call({args:{enabled:false}});
let roaming=m.set_data_roaming.call({args:{enabled:true}});
printf('%%J',{initial,invalid,on,off,roaming});
"""%json.dumps(str(rpc)))
   cmd=[UCODE,'-L',os.environ['UCODE_LIBRARY'],'-L',str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/ucode'),str(program)]
   for fail in ['0','1']:
    r=subprocess.run(cmd,env=dict(os.environ,FAIL_ENABLE=fail),capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
    value=json.loads(r.stdout)
    self.assertFalse(value['initial']['enabled']);self.assertEqual(value['invalid']['code'],22)
    self.assertEqual(value['on']['enabled'],fail=='0');self.assertEqual(value['on']['code'],0 if fail=='0' else 5)
    self.assertFalse(value['off']['enabled']);self.assertEqual(value['roaming']['code'],0)
   network=(cfg/'network').read_text()
   self.assertIn("option dataroaming '1'",network)
   self.assertIn("option auto '1'",network)
   self.assertIn("option radio_enabled '1'",network)

if __name__=='__main__':unittest.main()
