#!/usr/bin/env python3
"""Exercise the helper with separate host and hostpkg include trees."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

class HostDigestLayoutTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        for directory in ['scripts','build_dir/hostpkg/ucode-fixture/lib','staging_dir/host/include/json-c','staging_dir/hostpkg/include/ucode','modules','lib']:
            (self.root/directory).mkdir(parents=True)
        shutil.copy(ROOT/'scripts/lg6851f-build-host-digest.sh',self.root/'scripts/helper.sh')
        (self.root/'staging_dir/host/include/json-c/json.h').write_text('#define JSON_HOST_MARKER 41\n')
        (self.root/'staging_dir/hostpkg/include/ucode/fixture.h').write_text('#define UCODE_HOSTPKG_MARKER 1\n')
        (self.root/'build_dir/hostpkg/ucode-fixture/lib/digest.c').write_text('#include <json-c/json.h>\n#include <ucode/fixture.h>\nint staged_layout(void){return JSON_HOST_MARKER+UCODE_HOSTPKG_MARKER;}\n')
        # A local empty archive satisfies -lmd for this include-layout fixture;
        # the production SHA256 self-test is separately run with real digest.c.
        subprocess.run(['ar','rcs',str(self.root/'lib/libmd.a')],check=True)
        fake=self.root/'interpreter';fake.write_text('#!/usr/bin/env python3\nimport ctypes,os\np=ctypes.CDLL(os.environ["UCODE_LIBRARY"]+"/digest.so")\nassert p.staged_layout()==42\n');fake.chmod(0o700)
        self.env=dict(os.environ,UCODE=str(fake),UCODE_LIBRARY=str(self.root/'modules'),LIBRARY_PATH=str(self.root/'lib'))
        for key in ['C_INCLUDE_PATH','CPATH','CPLUS_INCLUDE_PATH']:
            self.env.pop(key,None)

    def run_helper(self):
        return subprocess.run(['sh',str(self.root/'scripts/helper.sh')],env=self.env,text=True,capture_output=True)

    def test_separate_staging_prefixes_compile_without_system_json_headers(self):
        result=self.run_helper();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.root/'modules/digest.so').is_file())
        self.assertFalse((self.root/'staging_dir/hostpkg/include/json-c').exists())

    def test_missing_staged_json_headers_fail_explicitly(self):
        (self.root/'staging_dir/host/include/json-c/json.h').unlink()
        result=self.run_helper();self.assertNotEqual(result.returncode,0)
        self.assertIn('staged host json-c headers are missing',result.stderr)
        self.assertFalse((self.root/'modules/digest.so').exists())

if __name__=='__main__':unittest.main()
