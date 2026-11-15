#!/usr/bin/env python3
"""Exercise the actual UI-only hotfix and rollback in ordinary directories."""
import os
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATCH_VIEW=ROOT/'scripts/tests/fixtures/lg6851f-slots-hotfix2.js'


class SlotsHotfixTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.destination=self.root/'www/luci-static/resources/view/system/lg6851f-slots.js'
  self.destination.parent.mkdir(parents=True)
  # Exact v1.0.19 production view, retained so shallow CI clones work offline.
  self.original=(ROOT/'scripts/tests/fixtures/lg6851f-slots-v1.0.19.js').read_bytes()
  self.assertEqual(hashlib.sha256(self.original).hexdigest(),'7c184590f0e96aaec0774888bfa915a9502fb9869e033c33b4948ef86ad4047a')
  self.destination.write_bytes(self.original)
  for name in ['tmp/sysinfo','root','rom/etc','bin']:(self.root/name).mkdir(parents=True,exist_ok=True)
  (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f\n')
  self.firmware=self.root/'rom/etc/mt6990-firmware-id';self.firmware.write_text('b7dcaa16ce3d8fced5c314ee48fe3c017a291815\n')
  self.assertEqual(hashlib.sha256(PATCH_VIEW.read_bytes()).hexdigest(),'53a9990b7626e30ae788e30bd6a7f66180d2f55008b41bee1f5f026ae6b1417c')
  (self.root/'download').write_bytes(PATCH_VIEW.read_bytes())
  for name,text in [('id','#!/bin/sh\necho 0\n'),('wget','#!/bin/sh\n[ "${FAIL_DOWNLOAD:-0}" = 0 ] || exit 4\nwhile [ "$1" != -O ]; do shift; done\ncp "$FIXTURE/download" "$2"\n')]:
   p=self.root/'bin'/name;p.write_text(text);p.chmod(0o755)
  source=(ROOT/'scripts/lg6851f-slots-ui-hotfix.sh').read_text()
  source=re.sub(r'/(?:tmp|root|rom|www)/',lambda m:str(self.root/m[0].strip('/'))+'/',source)
  self.script=self.root/'hotfix.sh';self.script.write_text(source)
 def run_script(self,script=None,args=(),**extra):
  return subprocess.run(['sh',str(script or self.script),*args],env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root),**extra),capture_output=True,text=True)
 def test_install_repeat_and_restore_preserve_exact_original(self):
  r=self.run_script();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.destination.read_bytes(),PATCH_VIEW.read_bytes())
  folders=list((self.root/'root').glob('lg6851f-slots-ui-before.*'));self.assertEqual(len(folders),1)
  self.assertEqual((folders[0]/'original.js').read_bytes(),self.original);self.assertEqual(self.destination.stat().st_mode&0o777,0o644)
  self.assertEqual(self.run_script().returncode,0);self.assertEqual(len(list((self.root/'root').iterdir())),1)
  r=self.run_script(folders[0]/'restore.sh');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.destination.read_bytes(),self.original)
 def test_download_error_or_corruption_leaves_installed_page_untouched(self):
  self.assertEqual(self.run_script(FAIL_DOWNLOAD='1').returncode,4);self.assertEqual(self.destination.read_bytes(),self.original)
  (self.root/'download').write_text('<html>bad download</html>')
  self.assertEqual(self.run_script().returncode,5);self.assertEqual(self.destination.read_bytes(),self.original);self.assertEqual(list((self.root/'root').iterdir()),[])
 def test_other_firmware_or_modified_page_is_rejected(self):
  self.firmware.write_text('a'*40);self.assertEqual(self.run_script().returncode,95)
  self.firmware.write_text('b7dcaa16ce3d8fced5c314ee48fe3c017a291815');self.destination.write_text('custom page')
  self.assertEqual(self.run_script().returncode,95);self.assertEqual(self.destination.read_text(),'custom page')
 def test_restore_cannot_overwrite_later_edits_or_a_new_firmware(self):
  self.assertEqual(self.run_script().returncode,0);restore=next((self.root/'root').glob('*/restore.sh'))
  new=self.destination.read_bytes();self.destination.write_text('later edit');self.assertEqual(self.run_script(restore).returncode,95);self.assertEqual(self.destination.read_text(),'later edit')
  self.destination.write_bytes(new);self.firmware.write_text('a'*40);self.assertEqual(self.run_script(restore).returncode,95);self.assertEqual(self.destination.read_bytes(),new)
 def test_previously_used_proxy_is_allowed_but_other_arguments_are_rejected(self):
  self.assertEqual(self.run_script(args=['https://example.invalid/']).returncode,22);self.assertEqual(self.destination.read_bytes(),self.original)
  result=self.run_script(args=['https://v6.gh-proxy.org/']);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.destination.read_bytes(),PATCH_VIEW.read_bytes())
 def test_upgrade_from_first_hotfix_restores_the_immediately_previous_view(self):
  previous=(ROOT/'scripts/tests/fixtures/lg6851f-slots-hotfix1.js').read_bytes()
  self.assertEqual(hashlib.sha256(previous).hexdigest(),'5ac75940b6ecd11b0ae24895b5bce9970f2499ef5b9d54ce520478fcf3f210eb')
  self.destination.write_bytes(previous);result=self.run_script();self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.destination.read_bytes(),PATCH_VIEW.read_bytes());restore=next((self.root/'root').glob('*/restore.sh'))
  self.assertEqual(self.run_script(restore).returncode,0);self.assertEqual(self.destination.read_bytes(),previous)


if __name__=='__main__':unittest.main()
