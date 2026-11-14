#!/usr/bin/env python3
"""Execute the installed shell collector; AT is a strict argument recorder."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
class ListTest(unittest.TestCase):
 def test_exact_at_bytes_without_literal_shell_escapes(self):
  with tempfile.TemporaryDirectory() as folder:
   p=pathlib.Path(folder);at=p/'at';log=p/'calls'
   at.write_text('''#!/usr/bin/python3
import os,sys,json
with open(os.environ['AT_LOG'],'a') as f:f.write(json.dumps(sys.argv[1])+'\\n')
if sys.argv[1] not in ['AT+CMGF=1','AT+CSCS="UCS2"','AT+CMGL="ALL"']:raise SystemExit(7)
print('\\r\\nOK\\r\\n')
''');at.chmod(0o700)
   source=(ROOT/'package/vendor/lg6851f-modem-chain-only/files/usr/bin/lg6851f-sms-list').read_text().replace('/var/lock/lg6851f-sms-operation.lock',str(p/'lock')).replace('/usr/bin/modem5g-at',str(at))
   script=p/'collect';script.write_text(source)
   result=subprocess.run(['sh',str(script)],env=dict(os.environ,AT_LOG=str(log)),capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual([json.loads(v) for v in log.read_text().splitlines()],['AT+CMGF=1','AT+CSCS="UCS2"','AT+CMGL="ALL"'])
   self.assertIn('OK',result.stdout)
 def test_explicit_busy_is_bounded_but_modem_error_is_not_retried(self):
  for fail_code,expected_calls in [(75,3),(7,1)]:
   with tempfile.TemporaryDirectory() as folder:
    p=pathlib.Path(folder);at=p/'at';log=p/'calls'
    at.write_text('#!/bin/sh\necho x >> "'+str(log)+'"\nexit '+str(fail_code)+'\n');at.chmod(0o700)
    source=(ROOT/'package/vendor/lg6851f-modem-chain-only/files/usr/bin/lg6851f-sms-list').read_text().replace('/var/lock/lg6851f-sms-operation.lock',str(p/'lock')).replace('/usr/bin/modem5g-at',str(at)).replace('sleep 1',':')
    script=p/'collect';script.write_text(source)
    result=subprocess.run(['sh',str(script)],capture_output=True,text=True)
    self.assertEqual(result.returncode,fail_code);self.assertEqual(len(log.read_text().splitlines()),expected_calls)
    self.assertIn('SMS_STAGE=text_mode RC='+str(fail_code),result.stderr)

if __name__=='__main__':unittest.main()
