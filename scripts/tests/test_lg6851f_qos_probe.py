#!/usr/bin/env python3
"""原生 ucode 测试二进制 getter 请求；仅替换 ubus/uci，不访问模组。"""
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
UCODE=os.environ.get('UCODE') or shutil.which('ucode')


@unittest.skipUnless(UCODE,'需要原生 ucode')
class QosProbeTest(unittest.TestCase):
    def run_probe(self, change=False, **replace):
        responses={
            '8': {'hex':(struct.pack('<II',1,4)+b'example.net'.ljust(32,b'\0')).hex()},
            '12': {'hex':(b'\1'+b'example.net'.ljust(150,b'\0')).hex()},
            '13': {'hex':struct.pack('<I4xQQ',8,256000000,12800000).hex()},
        }
        responses.update(replace)
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name)
            source=(ROOT/'scripts/lg6851f-collect-qos.sh').read_text().split("<<'UCODE'\n",1)[1].split('\nUCODE\n',1)[0]
            source=source.replace("from 'ubus'", "from 'mockubus'").replace("from 'uci'", "from 'mockuci'")
            (root/'probe.uc').write_text(source)
            (root/'mockuci.uc').write_text("export function cursor(){return {load:function(){return true;},get:function(){return 'example.net';}};}\n")
            (root/'mockubus.uc').write_text('''
let status_reads=0;
function bytes(hex){let out='';for(let i=0;i<length(hex);i+=2)out+=chr(+('0x'+substr(hex,i,2)));return out;}
export function error(){return 'mock error';}
export function connect(path,timeout){return {call:function(object,method,args){
 if(object=='network.interface.modem5g'&&method=='status'){
  status_reads++;return {up:true,uptime:120+status_reads,l3_device:'ccmni9',data:{cid:CHANGED&&status_reads>1?'5':'4'}};
 }
 if(object!='ql-netd'||method!='datacall'||index([8,12,13],args.id)<0)throw 'unexpected non-read request';
 if(args.len!=4||length(args.data)!=3||ord(args.data,1)!=0||ord(args.data,2)!=0)throw 'bad binary request length or zeros';
 if(ord(args.data,0)!=(args.id==8?0:4))throw 'wrong active CID';
 let fixture=RESPONSES[''+args.id];
 let data=bytes(fixture.hex);
 return {cmd:fixture.cmd??args.id,result:fixture.result??0,data_len:fixture.len??length(data),
  data:substr(data,0,length(data)-(fixture.truncated??1))};
}};}
''')
            result=subprocess.run([UCODE,'-L',name,'-D','RESPONSES='+json.dumps(responses),'-D','CHANGED='+json.dumps(change),str(root/'probe.uc')],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,254,result.stderr)
            return result.returncode,json.loads(result.stdout)

    def test_binary_zero_bytes_and_only_three_read_opcodes(self):
        rc,data=self.run_probe()
        self.assertEqual(rc,0)
        self.assertEqual(data['qos']['class_id'],8)
        self.assertEqual([row['command'] for row in data['requests']],[8,12,13])
        self.assertEqual([row['expected_request_hex'] for row in data['requests']],['00000000','04000000','04000000'])
        self.assertEqual(data['sdk_apn'],'example.net')
        self.assertTrue(data['requests'][-1]['omitted_final_byte'])
        self.assertEqual(len(data['requests'][-1]['data_hex']),46)

    def test_unknown_sdk_context_is_not_queried(self):
        rc,data=self.run_probe(**{'8':{'hex':(struct.pack('<II',1,5)+b'example.net'.ljust(32,b'\0')).hex()}})
        self.assertEqual(rc,95)
        self.assertEqual(data['status'],'ACTIVE_CID_NOT_IN_SDK_LIST')
        self.assertEqual(len(data['requests']),1)

    def test_incomplete_count_is_not_reconstructed(self):
        rc,data=self.run_probe(**{'8':{'hex':struct.pack('<I',0).hex()}})
        self.assertEqual(rc,5)
        self.assertEqual(data['status'],'SDK_LIST_READ_FAILED')
        self.assertEqual(data['requests'][0]['data_hex'],'000000')
        self.assertIsNone(data['qos'])

    def test_hardware_empty_sdk_list_does_not_query_qos(self):
        # 实机返回固定 580 字节结构：数量为零，其余为零填充。
        rc,data=self.run_probe(**{'8':{'hex':bytes(580).hex()}})
        self.assertEqual(rc,95)
        self.assertEqual(data['status'],'ACTIVE_CID_NOT_IN_SDK_LIST')
        self.assertEqual(data['call_list'],[])
        self.assertEqual([row['command'] for row in data['requests']],[8])
        self.assertEqual(data['requests'][0]['received_bytes'],579)
        self.assertIsNone(data['qos'])

    def test_ims_or_other_apn_is_not_used_for_default_connection(self):
        rc,data=self.run_probe(**{'12':{'hex':(b'\1'+b'ims'.ljust(150,b'\0')).hex()}})
        self.assertEqual(rc,95)
        self.assertEqual([row['command'] for row in data['requests']],[8,12])
        self.assertIsNone(data['qos'])

    def test_truncated_or_failed_reply_does_not_create_a_qos_class(self):
        for reply in [{'hex':'00','result':-2147090425},
                      {'hex':struct.pack('<I4xQQ',8,256000000,12800000).hex(),'truncated':2},
                      {'hex':struct.pack('<I4xQQ',8,256000000,12800000).hex(),'cmd':99}]:
            rc,data=self.run_probe(**{'13':reply})
            self.assertEqual(rc,5)
            self.assertIsNone(data['qos'])

    def test_connection_change_discards_sample(self):
        rc,data=self.run_probe(change=True)
        self.assertEqual(rc,75)
        self.assertEqual(data['status'],'DATA_CONNECTION_CHANGED_DURING_READ')
        self.assertIsNone(data['qos'])


if __name__=='__main__':unittest.main()
