"""一次性探针：模拟模组传输，验证菜单收尾及SDK只读请求，不连接实机。"""
import json,os,pathlib,re,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
PROBE=ROOT/'scripts/lg6851f-probe-bler-phone.sh'
class BlerProbeTest(unittest.TestCase):
 def run_bler(self,fail=False):
  with tempfile.TemporaryDirectory() as name:
   p=pathlib.Path(name);(p/'board').write_text('fiberhome,lg6851f')
   sample=p/'sample';sample.write_text('''#!/usr/bin/env python3
import sys,os,pathlib
lines=[]
marker=pathlib.Path(os.environ['PROBE_AUDIT']+'.failed')
fail=os.environ.get('PROBE_FAIL')=='1' and not marker.exists()
for line in sys.stdin:
 lines.append(line.strip())
 if line.strip()=='-1' or (fail and len(lines)==3):break
with open(os.environ['PROBE_AUDIT'],'a') as f:f.write(' '.join(lines)+'\\n')
if fail:marker.touch();sys.exit(124)
print('synthetic callback: NR Downlink BLER = 0')
''');sample.chmod(0o755)
   for command,text in [('ubus','echo \'{"up":true}\''),('jsonfilter','echo true'),('sleep','/bin/sleep 0.02')]:
    f=p/command;f.write_text('#!/bin/sh\n'+text+'\n');f.chmod(0o755)
   source=PROBE.read_text().replace('/tmp/sysinfo/board_name',str(p/'board')).replace('/var/lock/luci-modem5g-control.lock',str(p/'lock')).replace('/usr/bin/sample_nw',str(sample))
   script=p/'probe';script.write_text(source)
   r=subprocess.run(['sh',str(script),'bler'],env=dict(os.environ,PATH=name+':'+os.environ['PATH'],PROBE_AUDIT=str(p/'audit'),PROBE_FAIL='1' if fail else '0'),capture_output=True,text=True,timeout=10)
   self.assertEqual(subprocess.run(['flock','-n',str(p/'lock'),'-c','true']).returncode,0)
   return r,(p/'audit').read_text().splitlines()
 def test_registration_is_followed_by_unregister_release_and_exit(self):
  r,lines=self.run_bler()
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual(lines,['0 45 1 45 0 1 -1'])
 def test_failed_probe_sends_unregister_in_a_cleanup_session(self):
  r,lines=self.run_bler(fail=True)
  self.assertEqual(r.returncode,124,r.stderr)
  self.assertEqual(lines,['0 45 1','0 45 0 1 -1'])

@unittest.skipUnless(os.environ.get('UCODE') or shutil.which('ucode'),'需要原生ucode')
class PhoneProbeTest(unittest.TestCase):
 def query(self,response):
  with tempfile.TemporaryDirectory() as name:
   p=pathlib.Path(name)
   source=re.search(r"<<'UCODE'\n(.*?)\nUCODE",PROBE.read_text(),re.S)[1].replace("from 'ubus'","from 'probeubus'")
   (p/'probe.uc').write_text(source)
   (p/'probeubus.uc').write_text('''export function error(){return 'mock error';}
export function connect(){return {call:function(object,method,args){
 if(object!='ril'||method!='ril_request'||args.id!=0xb02||args.data_len!=4||length(args.data)!=3||ord(args.data,0)!=1||ord(args.data,1)!=11||ord(args.data,2)!=0)die('unexpected request');
 return RESPONSE;
}};}
''')
   args=[os.environ.get('UCODE') or shutil.which('ucode'),'-L',name,'-L',os.environ.get('UCODE_LIBRARY',name),'-D','RESPONSE='+json.dumps(response),str(p/'probe.uc')]
   r=subprocess.run(args,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   return json.loads(r.stdout)
 def test_actual_number_is_returned_from_expected_sdk_response(self):
  r=self.query(dict(id=0xb02,result=0,data_len=83,data='123456789'+chr(0)*73))
  self.assertEqual(r['status'],'NUMBER_RETURNED');self.assertEqual(r['phone'],'123456789')
 def test_empty_number_is_not_invented(self):
  self.assertEqual(self.query(dict(id=0xb02,result=0,data_len=83,data=chr(0)*82))['status'],'NUMBER_NOT_PROVIDED')
 def test_wrong_id_failure_or_truncated_reply_is_rejected(self):
  for row in [dict(id=0xb03,result=0,data_len=83,data='123456789'+chr(0)*73),dict(id=0xb02,result=1,data_len=83,data=chr(0)*82),dict(id=0xb02,result=0,data_len=83,data='123456789')]:
   with self.subTest(row=row):self.assertEqual(self.query(row)['status'],'SDK_RESPONSE_NOT_CONFIRMED')
 def test_missing_service_is_reported(self):self.assertEqual(self.query(None)['status'],'SDK_REQUEST_FAILED')
 def test_device_82_byte_reply_is_preserved_without_inventing_layout(self):
  raw=chr(0)*81
  r=self.query(dict(id=0xb02,result=0,data_len=82,data=raw))
  self.assertEqual(r['received_bytes'],81)
  self.assertEqual(r['data_hex'],'00'*81)
  self.assertEqual(r['status'],'SDK_RESPONSE_NOT_CONFIRMED')
  self.assertNotIn('phone',r)
if __name__=='__main__':unittest.main()
