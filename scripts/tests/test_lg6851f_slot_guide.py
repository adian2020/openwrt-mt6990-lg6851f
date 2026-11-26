#!/usr/bin/env python3
"""Validate copied commands with isolated transports; never access a router."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'files'
SOURCE=PACKAGE/'www/luci-static/resources/modem5g/slot_guide_v1.js'
TOOL=ROOT/'target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-slotctl'


class SlotGuideTest(unittest.TestCase):
 def commands(self,current):
  script="const fs=require('fs');const G=new Function('baseclass','ui',fs.readFileSync(process.argv[1],'utf8'))({extend:x=>x},{});console.log(G.commands(process.argv[2]));"
  result=subprocess.run(['node','-e',script,str(SOURCE),current],text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr);return result.stdout
 def test_both_commands_have_valid_shell_syntax_and_pinned_payload(self):
  digest=hashlib.sha256(TOOL.read_bytes()).hexdigest()
  for current,target in [('a','b'),('b','a')]:
   text=self.commands(current);self.assertIn(digest,text);self.assertIn('select '+target+' --expect',text)
   result=subprocess.run(['sh','-n'],input=text,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr)
   self.assertNotIn('reboot',[line.strip() for line in text.splitlines() if not line.strip().startswith('#')])
 def execute(self,current,actual=None,corrupt=False):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'bin').mkdir();(root/'source').write_bytes(TOOL.read_bytes() if not corrupt else b'bad download')
   (root/'state').write_text(json.dumps(dict(code=0,current=actual or current,next=actual or current,control='1'*64)))
   scripts={
    'wget':'#!/bin/sh\nwhile [ "$1" != -O ]; do shift; done\ncp "$FIXTURE/source" "$2"\n',
    'sh':'''#!/usr/bin/env python3
import json,os,pathlib,sys
r=pathlib.Path(os.environ['FIXTURE']);data=json.loads((r/'state').read_text())
if sys.argv[2]=='select':
 assert sys.argv[3] in ['a','b'] and sys.argv[4:] == ['--expect',data['control'],'--confirm']
 (r/'selected').write_text(sys.argv[3]);data['next']=sys.argv[3];(r/'state').write_text(json.dumps(data))
print(json.dumps(data))
''',
    'jsonfilter':'''#!/usr/bin/env python3
import json,sys
print(json.load(sys.stdin)[sys.argv[2].removeprefix('@.')])
''',
    'reboot':'#!/bin/sh\necho forbidden-reboot > "$FIXTURE/reboot"\nexit 99\n'}
   for name,text in scripts.items():p=root/'bin'/name;p.write_text(text);p.chmod(0o755)
   text=self.commands(current).replace('/tmp/lg6851f-slotctl.sh',str(root/'tool'))
   result=subprocess.run(['/bin/sh','-c',text],env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],FIXTURE=str(root)),text=True,capture_output=True)
   self.assertFalse((root/'reboot').exists())
   return result,(root/'selected').read_text() if (root/'selected').exists() else None
 def test_copied_commands_select_correct_opposite_without_reboot(self):
  for current,target in [('a','b'),('b','a')]:
   result,selected=self.execute(current);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(selected,target)
 def test_wrong_current_or_bad_download_never_calls_select(self):
  result,selected=self.execute('a',actual='b');self.assertEqual(result.returncode,95,result.stderr);self.assertIsNone(selected)
  result,selected=self.execute('b',corrupt=True);self.assertEqual(result.returncode,5,result.stderr);self.assertIsNone(selected)
 def test_guide_is_available_from_the_slot_page_only(self):
  menu=json.loads((PACKAGE/'usr/share/luci/menu.d/luci-app-lg6851f-slots.json').read_text())
  self.assertNotIn('admin/system/boot_slot_guide',menu)
  slots=menu['admin/system/boot_slots']
  self.assertEqual(slots['depends'],{'acl':['luci-app-lg6851f-slots']})
  view=PACKAGE/('www/luci-static/resources/view/'+slots['action']['path']+'.js')
  self.assertIn("'require modem5g.slot_guide_v1 as G'",view.read_text())
  self.assertNotIn('rpc.declare',SOURCE.read_text())


if __name__=='__main__':unittest.main()
