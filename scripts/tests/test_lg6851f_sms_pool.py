#!/usr/bin/env python3
"""Pinned native ucode; mocked modem/sender only. Never sends a real SMS."""
import hashlib
import hmac
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

class SmsPoolTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(UCODE,'native ucode is required')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        for name in ['tmp/sysinfo','etc/lg6851f-sms','var/lock','bin','lib/lg6851f','proc/sys/kernel/random']:
            (self.root/name).mkdir(parents=True,exist_ok=True)
        (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f\n')
        (self.root/'tmp/lg6851f-modem-status.state').write_text('ICCID=fixture-sim\n')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('fixture-boot')
        (self.root/'proc/sys/kernel/random/uuid').write_text('12345678-1234-1234-1234-123456789abc')
        for src in (PACKAGE/'root/usr/share/ucode/lg6851f').glob('*.uc'):
            (self.root/'lib/lg6851f'/src.name).write_text(self.remap(src.read_text()))
        source=(PACKAGE/'root/usr/libexec/lg6851f-sms-pool.uc').read_text()
        source=source.replace("error:'短信处理被中断，请核对结果；未自动重复操作'","error:'fixture: '+e")
        source=source.replace("if(cmd=='sync'){", "if(cmd=='sync-now')return sync_pool();\n if(cmd=='sync'){")
        (self.root/'worker.uc').write_text(self.remap(source))
        self.binary('ubus',"print('{\"up\":true,\"uptime\":90}')")
        self.binary('start-stop-daemon','pass')
        self.binary('lg6851f-sms-list',"print(pathlib.Path(os.environ['TEST_ROOT'],'list').read_text(),end='')")
        self.binary('modem5g-sms-send',"""r=pathlib.Path(os.environ['TEST_ROOT'])
with (r/'submissions').open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
print('SMS submitted through official qlril API')
sys.exit(int(os.environ.get('SEND_CODE','0')))
""")
        self.binary('modem5g-at',"""r=pathlib.Path(os.environ['TEST_ROOT'])
with (r/'at-calls').open('a') as f:f.write(sys.argv[1]+'\\n')
print((r/'list').read_text() if sys.argv[1]=='AT+CMGL=\"ALL\"' else '\\r\\nOK\\r\\n',end='')
""")
        self.raw('hello')

    def remap(self,source):
        for prefix in ['/tmp/','/etc/','/var/lock/','/proc/']:
            source=source.replace(prefix,str(self.root/prefix.lstrip('/'))+'/')
        for name in ['modem5g-sms-send','modem5g-at','lg6851f-sms-list']:
            source=source.replace('/usr/bin/'+name,str(self.root/'bin'/name))
        for path in ['/bin/ubus','/sbin/start-stop-daemon']:
            source=source.replace(path,str(self.root/'bin'/path.rsplit('/',1)[1]))
        return source.replace("system('/bin/sync')","0")

    def binary(self,name,text):
        path=self.root/'bin'/name
        path.write_text('#!/usr/bin/python3\nimport pathlib,os,sys,json\n'+text+'\n');path.chmod(0o700)

    def run_uc(self,source,**data):
        path=self.root/'test.uc';path.write_text("import * as s from 'lg6851f.sms'; import * as p from 'lg6851f.sms-store'; import * as f from 'lg6851f.forward'; printf('%J',"+source+');')
        return self.execute([str(path)],data)

    def execute(self,args,data=None,env=None):
        cmd=[UCODE,'-L',os.environ.get('UCODE_LIBRARY','/usr/lib/ucode'),'-L',str(self.root/'lib')]
        for k,v in (data or {}).items():cmd+=['-D',k+'='+json.dumps(v)]
        result=subprocess.run(cmd+args,capture_output=True,text=True,env=dict(os.environ,TEST_ROOT=str(self.root),**(env or {})),timeout=10)
        self.assertIn(result.returncode,[0,5],result.stderr)
        return json.loads(result.stdout)

    def command(self,name,values=None,env=None):
        args=[str(self.root/'worker.uc'),name]
        if values is not None:
            path=self.root/'input.json';path.write_text(json.dumps(values));args.append(str(path))
        return self.execute(args,env=env)

    def raw(self,text,index=1):
        raw=f'+CMGL: {index},"REC UNREAD","10086","","26/11/13,10:20:30+32"\r\n{text.encode("utf-16-be").hex()}\r\n\r\nOK\r\n'
        (self.root/'list').write_text(raw);return raw

    def sync(self):
        result=self.command('sync-now');self.assertTrue(result['ok'],result)
        return self.run_uc('p.list(1)')['msgs'][0]['id']

    def work(self):
        path=self.root/'tmp/lg6851f-sms-current-job.json';j=json.loads(path.read_text())
        return self.execute([str(self.root/'worker.uc'),'work',j['id']])

    def test_hmac_and_url_encoding_use_standard_known_values(self):
        result=self.run_uc('b64enc(s.hmac256(KEY,TEXT))',KEY='SEC-secret',TEXT='1790000000000\nSEC-secret')
        import base64
        self.assertEqual(result,base64.b64encode(hmac.new(b'SEC-secret',b'1790000000000\nSEC-secret',hashlib.sha256).digest()).decode())
        self.assertEqual(self.run_uc('s.urlencode(TEXT)',TEXT='中文 +&\n'),'%'+'E4%B8%AD%E6%96%87%20%2B%26%0A')

    def test_unicode_parts_preserve_surrogate_pairs_and_bounds(self):
        text='中文😀'*80
        result=self.run_uc('s.outgoing(TEXT)',TEXT=text)
        import re
        self.assertGreater(len(result['parts']),1)
        self.assertTrue(all(len(p)<=280 for p in result['parts']))
        self.assertEqual(''.join(re.sub(r'^\[\d+/\d+\] ','',bytes.fromhex(p).decode('utf-16-be')) for p in result['parts']),text)
        for invalid in ['', 'x'*20000, '\x00']:
            self.assertIn('error',self.run_uc('s.outgoing(TEXT)',TEXT=invalid))

    def test_archive_reads_do_not_query_modem_and_deleted_sms_stays_hidden(self):
        ident=self.sync();before=(self.root/'tmp/lg6851f-sms-snapshot.json').read_bytes()
        first=self.run_uc('p.show(ID)',ID=ident);self.assertIn('hello',first['text'])
        self.assertEqual(self.run_uc('p.list(1)')['unread'],0)
        self.assertTrue(self.run_uc('p.remove(ID)',ID=ident)['ok'])
        self.command('sync-now');self.assertEqual(self.run_uc('p.list(1)')['total'],0)
        self.assertEqual(json.loads(before)['raw'],json.loads((self.root/'tmp/lg6851f-sms-snapshot.json').read_text())['raw'])
        self.assertEqual((self.root/'at-calls').read_text().splitlines(),['AT+CPMS?','AT+CPMS?'])
        self.assertEqual((self.root/'etc/lg6851f-sms/pool.json').stat().st_mode&0o777,0o600)

    def test_corrupt_archive_is_preserved(self):
        path=self.root/'etc/lg6851f-sms/pool.json';path.write_text('{broken')
        result=self.command('list',{'page':1});self.assertFalse(result['ok']);self.assertEqual(path.read_text(),'{broken')

    def test_boot_pending_does_not_touch_modem(self):
        self.binary('ubus',"print('{\"up\":false,\"pending\":true}')")
        self.assertFalse(self.command('sync-now')['ok']);self.assertFalse((self.root/'tmp/lg6851f-sms-snapshot.json').exists())

    def test_offline_registered_radio_can_sync_without_enabling_data(self):
        import time
        self.binary('ubus',"print('{\"up\":false,\"pending\":false}')")
        (self.root/'proc/uptime').write_text('300.0 10.0')
        (self.root/'tmp/lg6851f-modem-status.state').write_text(f'ICCID=fixture-sim\nREGISTERED=YES\nRADIO=MIPC_NW_RADIO_STATE_ON\nUPDATED={int(time.time())}\n')
        self.assertTrue(self.command('sync-now')['ok'])
        self.assertEqual(self.run_uc('p.list(1)')['total'],1)
        (self.root/'tmp/lg6851f-modem-control.active').write_text('user control')
        self.assertFalse(self.command('sync-now')['ok'])

    def test_capacity_is_real_temporary_data_and_does_not_rewrite_archive(self):
        self.binary('modem5g-at',"print('\\r\\n+CPMS: \"SM\",3,255,\"SM\",3,255,\"SM\",3,255\\r\\nOK\\r\\n')")
        self.sync();before=(self.root/'etc/lg6851f-sms/pool.json').read_bytes()
        value=self.run_uc('p.list(1)');self.assertEqual(value['sim_used'],3);self.assertEqual(value['sim_total'],255)
        self.command('sync-now');self.assertEqual((self.root/'etc/lg6851f-sms/pool.json').read_bytes(),before)

    def test_fingerprint_prevents_deleting_reused_sim_index(self):
        ident=self.sync();self.raw('different content')
        self.assertTrue(self.command('delete',{'id':ident,'sim':True})['ok']);result=self.work()
        self.assertFalse(result['ok']);self.assertNotIn('AT+CMGD=',(self.root/'at-calls').read_text())
        self.assertEqual(self.run_uc('p.list(1)')['total'],1)

    def test_verified_sim_delete_also_hides_local_record(self):
        ident=self.sync();self.command('delete',{'id':ident,'sim':True});self.assertTrue(self.work()['ok'])
        self.assertIn('AT+CMGD=1',(self.root/'at-calls').read_text());self.assertEqual(self.run_uc('p.list(1)')['total'],0)

    def test_async_send_reservation_then_archive_and_no_duplicate_work(self):
        queued=self.command('send',{'number':'+8613800000000','text':'中文😀'})
        self.assertTrue(queued['ok']);self.assertTrue(self.command('job')['running']);self.assertFalse(self.command('send',{'number':'10086','text':'x'})['ok'])
        r=self.work();self.assertTrue(r['ok'],r);self.assertFalse(self.work()['ok'])
        calls=(self.root/'submissions').read_text().splitlines();self.assertEqual(len(calls),1)
        self.assertEqual(json.loads(calls[0])[0],'--ucs2');self.assertEqual(self.run_uc('p.list(1)')['msgs'][0]['dir'],'mo')
        self.assertFalse(self.command('job')['running'])

    def test_uncertain_submission_is_not_retried(self):
        self.command('send',{'number':'10086','text':'a'*200})
        j=json.loads((self.root/'tmp/lg6851f-sms-current-job.json').read_text())
        r=self.execute([str(self.root/'worker.uc'),'work',j['id']],env={'SEND_CODE':'124'})
        self.assertFalse(r['ok']);self.assertEqual(self.run_uc('p.list(1)')['total'],0)
        self.assertFalse(self.work()['ok']);self.assertEqual(len((self.root/'submissions').read_text().splitlines()),1)
        state=json.loads((self.root/'etc/lg6851f-sms/pool.json').read_text());self.assertEqual(state['outbox'][j['id']]['state'],'uncertain')

    def test_sim_change_refuses_delete(self):
        ident=self.sync();self.command('delete',{'id':ident,'sim':True})
        (self.root/'tmp/lg6851f-modem-status.state').write_text('ICCID=new-sim')
        self.assertFalse(self.work()['ok']);self.assertNotIn('AT+CMGD=',(self.root/'at-calls').read_text())

    def test_job_timeout_uses_monotonic_time(self):
        self.command('send',{'number':'10086','text':'fixture'})
        path=self.root/'tmp/lg6851f-sms-current-job.json';job=json.loads(path.read_text());job.update(started=1,started_mono=100);path.write_text(json.dumps(job))
        (self.root/'proc/uptime').write_text('120.0 5.0')
        self.assertTrue(self.command('job')['running'])
        (self.root/'proc/uptime').write_text('1000.0 5.0')
        result=self.command('job');self.assertFalse(result['running']);self.assertFalse(result['ok']);self.assertIn('中断',result['error'])

    def test_sent_header_without_timestamp_does_not_break_inbox(self):
        raw='+CMGL: 2,"STO SENT","10010",""\r\n0078\r\n'+self.raw('hello')
        result=self.run_uc('f.parse_sms(RAW)',RAW=raw);self.assertNotIn('error',result);self.assertEqual(len(result['messages']),1)

    def test_custom_templates_filters_and_response_matching(self):
        c={'enabled':True,'webhook':True,'url':'https://example.invalid','webhook_content_type':'application/x-www-form-urlencoded','body':'text={text}','blacklist_keywords':'secret\n验证码','webhook_expect':'ok=true'}
        checked=self.run_uc('f.validate(CONFIG)',CONFIG=c);self.assertNotIn('error',checked)
        self.assertEqual(self.run_uc('f.template(CONFIG,MESSAGE,s.urlencode)',CONFIG=checked['values'],MESSAGE={'text':'a&中','from':'10086'}),'text=a%26%E4%B8%AD')
        self.assertFalse(self.run_uc('f.eligible(CONFIG,MESSAGE)',CONFIG=checked['values'],MESSAGE={'from':'10086','text':'验证码1234'}))
        self.assertTrue(self.run_uc('f.expected(CONFIG,RAW)',CONFIG=checked['values'],RAW='{"ok":true}'))
        self.assertFalse(self.run_uc('f.expected(CONFIG,RAW)',CONFIG=checked['values'],RAW='{"ok":false}'))

if __name__=='__main__':unittest.main()
