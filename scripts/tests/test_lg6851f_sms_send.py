#!/usr/bin/env python3
"""编译真实发送客户端，替换厂商函数；检查 ABI、UCS2 字符串及确认语义。"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('cc'),'需要本机C编译器')
class SmsSendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root=pathlib.Path(cls.temp.name)
        source=(ROOT/'package/vendor/lg6851f-modem-chain-only/src/modem5g-sms-send.c').read_text()
        source=source.replace('/var/lock/lg6851f-sms-operation.lock',str(cls.root/'lock'))
        (cls.root/'client.c').write_text(source)
        (cls.root/'vendor.c').write_text('''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
struct sms {int32_t format;char number[256];int32_t length;unsigned char content[1440];};
int ql_sms_init(int sim){return sim==0?0:1;}
int ql_sms_release(void){return getenv("RELEASE_FAIL")?1:0;}
int ql_sms_send_msg(struct sms *m){
 if(getenv("SEND_FAIL"))return 1;
 if(m->format!=atoi(getenv("FORMAT")))return 2;
 if(m->length!=(int)strlen(getenv("BODY")))return 3;
 if(memcmp(m->content,getenv("BODY"),m->length))return 4;
 if(strcmp(m->number,"+8613800000000"))return 5;
 return 0;
}
''')
        subprocess.run(['cc','-Wall','-Wextra','-Werror','-o',str(cls.root/'send'),str(cls.root/'client.c'),str(cls.root/'vendor.c')],check=True)

    def send(self,*args,**extra):
        return subprocess.run([str(self.root/'send'),*args],env=dict(os.environ,FORMAT='2',BODY='4E2D6587',**extra),text=True,capture_output=True)

    def test_ucs2_uses_actual_vendor_format_two_and_hex_string(self):
        result=self.send('--ucs2','+8613800000000','4E2D6587')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('official qlril API',result.stdout)

    def test_invalid_numbers_hex_and_oversize_are_rejected(self):
        for number,body in [('+86"bad','4E2D6587'),('+12','4E2D6587'),('+8613800000000','00xx'),('+8613800000000','4E2D'*71)]:
            self.assertEqual(self.send('--ucs2',number,body).returncode,2)

    def test_release_failure_does_not_turn_confirmed_submission_into_failure(self):
        result=self.send('--ucs2','+8613800000000','4E2D6587',RELEASE_FAIL='1')
        self.assertEqual(result.returncode,0)
        self.assertIn('ql_sms_release failed',result.stderr)
        self.assertIn('official qlril API',result.stdout)

    def test_failed_submission_is_never_reported_successful(self):
        result=self.send('--ucs2','+8613800000000','4E2D6587',SEND_FAIL='1')
        self.assertEqual(result.returncode,4)
        self.assertNotIn('official qlril API',result.stdout)


if __name__=='__main__':unittest.main()
