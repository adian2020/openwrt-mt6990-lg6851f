#!/usr/bin/env python3
"""真实 ucode/文件系统与本地假投递端；不连接模组、不向外发送消息。"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'package/vendor/luci-app-5gmodem'
UCODE=os.environ.get('UCODE') or shutil.which('ucode')


def stored(index,text,sender='10086',stamp='26/11/07,05:00:00+32',prefix=''):
    return f'+CMGL: {index},"REC UNREAD","{sender}","","{stamp}"\r\n{prefix}{text.encode("utf-16-be").hex().upper()}\r\n'


@unittest.skipUnless(UCODE,'需要原生 ucode/fs')
class ForwardTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        for name in ['tmp/sysinfo','etc/lg6851f-sms-forward','var/lock','bin']:
            (self.root/name).mkdir(parents=True,exist_ok=True)
        (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f\n')
        (self.root/'tmp/lg6851f-modem-status.state').write_text('ICCID=synthetic-sim\n')
        self.config=dict(enabled=True,webhook=True,smtp=True,sms=True,interval=60,
                         url='https://example.invalid/hook',provider='json',
                         host='smtp.example.invalid',port=465,tls='tls',username='user',password='secret',
                         revision='one',**{'from':'router@example.invalid','to':'owner@example.invalid','phone':'+8613800000000'})
        self.script=(PACKAGE/'root/usr/libexec/lg6851f-sms-forward.uc').read_text()
        self.script=self.script.replace("from 'uci'","from 'testuci'")
        for prefix in ['/tmp/','/etc/','/var/lock/']:
            self.script=self.script.replace(prefix,str(self.root/prefix.lstrip('/'))+'/')
        for binary in ['lg6851f-sms-list','modem5g-sms-send','curl']:
            self.script=self.script.replace('/usr/bin/'+binary,str(self.root/'bin'/binary))
        self.script=self.script.replace("system('/bin/sync')","0")
        self.script=self.script.replace('sleep(value.interval*1000);','break;')
        (self.root/'worker.uc').write_text(self.script)
        (self.root/'testuci.uc').write_text('export function cursor(){return {load:function(){return true;},get_all:function(){return TEST_CONFIG;}};}')
        self.executable('lg6851f-sms-list','''import pathlib,os
print(pathlib.Path(os.environ['TEST_ROOT'],'list').read_text(),end='')
''')
        self.executable('modem5g-sms-send','''import json,os,pathlib,sys
r=pathlib.Path(os.environ['TEST_ROOT'])
with (r/'deliveries').open('a') as f:f.write(json.dumps({'channel':'sms','args':sys.argv[1:]})+'\\n')
sys.exit(int(os.environ.get('SMS_RESULT','0')))
''')
        self.executable('curl','''import json,os,pathlib,sys
r=pathlib.Path(os.environ['TEST_ROOT'])
c=pathlib.Path(sys.argv[-1]).read_text()
channel='smtp' if 'mail-from' in c else 'webhook'
with (r/'deliveries').open('a') as f:f.write(json.dumps({'channel':channel,'config':c})+'\\n')
for line in c.splitlines():
 if line.startswith('output = '):pathlib.Path(json.loads(line.split(' = ',1)[1])).write_text(os.environ.get('WEB_REPLY','{}'))
sys.stdout.write(os.environ.get('HTTP_CODE','200') if channel=='webhook' else '')
sys.exit(int(os.environ.get('CURL_RESULT','0')))
''')
        self.write_list('')

    def executable(self,name,source):
        path=self.root/'bin'/name
        path.write_text('#!/usr/bin/python3\n'+source)
        path.chmod(0o700)

    def uc(self,source,**values):
        (self.root/'pure.uc').write_text("import * as f from 'lg6851f.forward'; printf('%J', "+source+');')
        result=subprocess.run(self.command(values)+[str(self.root/'pure.uc')],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def command(self,values):
        cmd=[UCODE]
        for library in [os.environ.get('UCODE_LIBRARY'),str(PACKAGE/'root/usr/share/ucode'),str(self.root)]:
            if library:cmd+=['-L',library]
        for key,value in values.items():cmd+=['-D',key+'='+json.dumps(value)]
        return cmd

    def write_list(self,records):
        (self.root/'list').write_text(records+'\r\nOK\r\n')

    def cycle(self,**env):
        result=subprocess.run(self.command({'TEST_CONFIG':self.config})+[str(self.root/'worker.uc'),'run'],
                              text=True,capture_output=True,env=dict(os.environ,TEST_ROOT=str(self.root),**env))
        self.assertEqual(result.returncode,0,result.stderr)

    def deliveries(self):
        path=self.root/'deliveries'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_unicode_and_json_template_are_not_shell_or_json_fragments(self):
        value=self.uc('f.webhook_body(f.defaults(),MESSAGE)',MESSAGE={'from':'10086','text':'中文"\\\n$(id) {from}','time':'now','device':'router'})
        self.assertEqual(value['text'],'中文"\\\n$(id) {from}')
        self.assertEqual(value['from'],'10086')

    def test_multipart_waits_for_all_parts_and_decodes_sender(self):
        sender='+8613900000000'.encode('utf-16-be').hex()
        records=stored(1,'世界',sender,prefix='050003A70202')+stored(2,'你好',sender,prefix='050003A70201')
        value=self.uc('f.parse_sms(RAW)',RAW=records+'\r\nOK\r\n')
        self.assertEqual(value['messages'][0]['text'],'你好世界')
        self.assertEqual(value['messages'][0]['from'],'+8613900000000')
        value=self.uc('f.parse_sms(RAW)',RAW=stored(1,'部分',prefix='050003A70201')+'\r\nOK\r\n')
        self.assertEqual(value,{'messages':[],'incomplete':1})

    def test_invalid_truncated_or_non_ucs2_source_is_rejected(self):
        for raw in [stored(1,'text'),'+CMGL: unknown\r\nOK\r\n',stored(1,'x').replace('0078','D800')+'\r\nOK\r\n']:
            self.assertIn('error',self.uc('f.parse_sms(RAW)',RAW=raw))

    def test_sms_parts_preserve_chinese_and_surrogate_pairs(self):
        text='中文😀'*90
        parts=self.uc('f.sms_parts(MESSAGE)',MESSAGE={'from':'10086','text':text})
        decoded=[bytes.fromhex(part).decode('utf-16-be') for part in parts]
        self.assertTrue(all(len(bytes.fromhex(part))<=140 for part in parts))
        import re
        self.assertEqual(''.join(re.sub(r'^\[\d+/\d+\] ','',part) for part in decoded),'[10086] '+text)

    def test_validation_rejects_headers_bad_protocol_and_wrong_provider_answer(self):
        for changes in [{'url':'file:///etc/shadow'},{'username':'user\r\nInjected: bad'},{'phone':'$(id)'},{'interval':1}]:
            self.assertIn('error',self.uc('f.validate(CONFIG)',CONFIG=dict(self.config,**changes)))
        self.assertFalse(self.uc('f.service_ok("wecom",RAW)',RAW='{"errcode":42}'))
        self.assertTrue(self.uc('f.service_ok("wecom",RAW)',RAW='{"errcode":0}'))

    def test_baseline_then_all_channels_once_across_process_restarts(self):
        old=stored(1,'历史短信')
        self.write_list(old);self.cycle()
        self.assertEqual(self.deliveries(),[])
        self.write_list(old+stored(2,'新增短信',stamp='26/11/07,05:01:00+32'))
        self.cycle();self.cycle()
        self.assertEqual([item['channel'] for item in self.deliveries()],['webhook','smtp','sms'])
        ledger=self.root/'etc/lg6851f-sms-forward/state.json'
        self.assertNotIn('新增短信',ledger.read_text())
        self.assertNotIn('secret',ledger.read_text())
        self.assertEqual(ledger.stat().st_mode&0o777,0o600)
        self.assertEqual(list((self.root/'tmp').glob('lg6851f-forward-send.*')),[])

    def test_self_forward_blocked_and_failed_webhook_does_not_block_email(self):
        self.config['provider']='wecom';self.cycle()
        self.write_list(stored(1,'新增',sender=self.config['phone']))
        self.cycle(WEB_REPLY='{"errcode":7}')
        self.assertEqual([item['channel'] for item in self.deliveries()],['webhook','smtp'])
        state=json.loads((self.root/'tmp/lg6851f-sms-forward-status.json').read_text())
        self.assertEqual(state['results']['webhook']['state'],'failed')
        self.assertEqual(state['results']['smtp']['state'],'sent')
        self.assertEqual(state['results']['sms']['state'],'blocked')

    def test_uncertain_sms_stops_remaining_parts_and_is_not_automatically_repeated(self):
        self.config.update(webhook=False,smtp=False)
        self.cycle();self.write_list(stored(1,'中'*130))
        self.cycle(SMS_RESULT='4');self.cycle()
        self.assertEqual(len(self.deliveries()),1)

    def test_failed_source_does_not_create_baseline(self):
        (self.root/'list').write_text('ERROR\r\n')
        self.cycle()
        self.assertFalse((self.root/'etc/lg6851f-sms-forward/state.json').exists())
        self.assertEqual(self.deliveries(),[])

    def test_interrupted_delivery_is_not_automatically_replayed(self):
        self.config.update(smtp=False,sms=False)
        self.cycle();self.write_list(stored(1,'新增短信'));self.cycle()
        ledger=self.root/'etc/lg6851f-sms-forward/state.json'
        state=json.loads(ledger.read_text())
        for job in state['jobs'].values():
            if 'webhook' in job:job['webhook'][0]['state']='inflight'
        ledger.write_text(json.dumps(state));self.cycle()
        self.assertEqual(len(self.deliveries()),1)
        state=json.loads(ledger.read_text())
        self.assertEqual(next(job for job in state['jobs'].values() if 'webhook' in job)['webhook'][0]['state'],'uncertain')

    def test_manual_retry_only_retries_failed_channel(self):
        self.config['provider']='wecom';self.cycle()
        self.write_list(stored(1,'新增短信'));self.cycle(WEB_REPLY='{"errcode":7}')
        (self.root/'tmp/lg6851f-sms-forward-retry').write_text('manual')
        self.cycle(WEB_REPLY='{"errcode":0}')
        self.assertEqual([item['channel'] for item in self.deliveries()],['webhook','smtp','sms','webhook'])

    def test_test_message_bypasses_keyword_filter(self):
        self.config['keyword']='only-this-keyword'
        (self.root/'tmp/lg6851f-sms-forward-test').write_text('test-request')
        self.cycle()
        self.assertEqual([item['channel'] for item in self.deliveries()],['webhook','smtp','sms'])

    def test_get_config_masks_password_and_status_contains_no_destinations(self):
        result=subprocess.run(self.command({'TEST_CONFIG':self.config})+[str(self.root/'worker.uc'),'get'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertTrue(data['values']['password_set'])
        self.assertEqual(data['values']['password'],'')
        self.cycle()
        self.write_list(stored(1,'新增短信'));self.cycle()
        status=(self.root/'tmp/lg6851f-sms-forward-status.json').read_text()
        for secret in ['secret','example.invalid','13800000000','新增短信']:
            self.assertNotIn(secret,status)

    def test_mu_get_form_headers_timeout_and_service_expectation(self):
        self.config.update(smtp=False,sms=False,webhook_method='GET',url='https://example.invalid/hook?text={text}',webhook_timeout=120,webhook_headers='X-Fixture: yes',webhook_expect='ok=true')
        self.cycle();self.write_list(stored(1,'a&中'));self.cycle(WEB_REPLY='{"ok":true}')
        request=self.deliveries()[0]['config']
        self.assertIn('request = "GET"',request)
        self.assertIn('max-time = 120',request)
        self.assertIn('a%26%E4%B8%AD',request)
        self.assertIn('X-Fixture: yes',request)
        self.assertNotIn('data-binary',request)
        self.assertEqual(json.loads((self.root/'tmp/lg6851f-sms-forward-status.json').read_text())['results']['webhook']['state'],'sent')

    def test_multiple_sms_destinations_keep_independent_dedup_and_self_block(self):
        self.config.update(webhook=False,smtp=False,phone='10086\n10010\n10000')
        self.cycle();self.write_list(stored(1,'new',sender='10086'));self.cycle();self.cycle()
        self.assertEqual([v['args'][1] for v in self.deliveries()],['10010','10000'])

    def test_dingtalk_signing_masks_secret_and_has_expected_response_contract(self):
        self.config.update(smtp=False,sms=False,webhook_kind='dingtalk',dingtalk_webhook='https://oapi.dingtalk.com/robot/send?access_token=fixture',dingtalk_secret='SEC-private')
        self.cycle();self.write_list(stored(1,'new'));self.cycle(WEB_REPLY='{"errcode":0}')
        request=self.deliveries()[0]['config']
        self.assertIn('&timestamp=',request);self.assertIn('&sign=',request);self.assertNotIn('SEC-private',request)
        result=subprocess.run(self.command({'TEST_CONFIG':self.config})+[str(self.root/'worker.uc'),'get'],text=True,capture_output=True,check=True)
        self.assertNotIn('SEC-private',result.stdout);self.assertTrue(json.loads(result.stdout)['values']['dingtalk_secret_set'])

    def test_clear_history_keeps_durable_ledger_and_does_not_replay(self):
        self.cycle();self.write_list(stored(1,'new'));self.cycle()
        ledger=self.root/'etc/lg6851f-sms-forward/state.json';before=ledger.read_bytes()
        result=subprocess.run(self.command({'TEST_CONFIG':self.config})+[str(self.root/'worker.uc'),'clear'],text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout)['code'],0)
        self.assertEqual(ledger.read_bytes(),before)
        self.assertEqual(json.loads((self.root/'tmp/lg6851f-sms-forward-status.json').read_text())['history'],[])
        self.cycle();self.assertEqual(len(self.deliveries()),3)

    def test_blacklist_words_and_invalid_extra_headers(self):
        for headers in ['Host: injected','X-Fixture: value\r\nInjected: yes','Content-Length: 0']:
            self.assertIn('error',self.uc('f.validate(CONFIG)',CONFIG=dict(self.config,webhook_headers=headers)))
        self.config['blacklist_keywords']='secret\n验证码'
        self.cycle();self.write_list(stored(1,'验证码 1234'));self.cycle();self.assertEqual(self.deliveries(),[])


if __name__=='__main__':unittest.main()
