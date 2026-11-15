#!/usr/bin/env python3
"""Compile patched pinned procd ubus code with simulated transport, not PID 1."""
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'package/system/procd'
FIXTURE = ROOT/'scripts/tests/fixtures/procd-60fdbf00'

STUB = r'''
#include <stdbool.h>
struct blob_attr;
struct udebug_ubus { int unused; };
struct uloop_timeout { void (*cb)(struct uloop_timeout *); };
struct ubus_context { void (*connection_lost)(struct ubus_context *); unsigned local_id; };
#define DEBUG(...) ((void)0)
void procd_udebug_set_enabled(bool value);
void udebug_ubus_init(struct udebug_ubus *, struct ubus_context *, const char *, void (*)(struct udebug_ubus *, struct blob_attr *, bool));
void uloop_timeout_set(struct uloop_timeout *, int);
int ubus_reconnect(struct ubus_context *, const char *);
struct ubus_context *ubus_connect(const char *);
void ubus_add_uloop(struct ubus_context *);
void ubus_init_hotplug(struct ubus_context *);
void ubus_init_service(struct ubus_context *);
void ubus_init_system(struct ubus_context *);
void watch_ubus(struct ubus_context *);
void procd_state_ubus_connect(void);
'''
HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <string.h>
#include "ubus.c"
static int remaining = 5, delay, entered;
static struct ubus_context fake;
static char calls[128];
static void called(const char *s) { strcat(calls, s); }
void procd_udebug_set_enabled(bool value) {}
void udebug_ubus_init(struct udebug_ubus *a, struct ubus_context *b, const char *c, void (*d)(struct udebug_ubus *, struct blob_attr *, bool)) { called("d"); }
void uloop_timeout_set(struct uloop_timeout *t, int ms) { delay = ms; }
int ubus_reconnect(struct ubus_context *c, const char *s) { return 0; }
struct ubus_context *ubus_connect(const char *s) {
 called("c");
 if (remaining-- > 0) { errno = ENOENT; return NULL; }
 return &fake;
}
void ubus_add_uloop(struct ubus_context *c) { called("a"); }
void ubus_init_hotplug(struct ubus_context *c) { called("h"); }
void ubus_init_service(struct ubus_context *c) { called("s"); }
void ubus_init_system(struct ubus_context *c) { called("y"); }
void watch_ubus(struct ubus_context *c) { called("w"); }
void procd_state_ubus_connect(void) { called("n"); entered++; }
int main(void) {
 const int delays[] = {100, 200, 400, 800, 1000};
 procd_connect_ubus();
 assert(delay == 50 && !entered);
 for (unsigned i = 0; i < 5; i++) {
  ubus_timer.cb(&ubus_timer);
  assert(delay == delays[i] && !entered && errno == ENOENT);
 }
 ubus_timer.cb(&ubus_timer);
 assert(entered == 1 && timeout == 50 && fake.connection_lost != NULL);
 assert(!strcmp(calls, "ccccccdhsywan"));
 /* Runtime reconnection retains original callbacks and does not enter init. */
 fake.connection_lost(&fake);
 assert(delay == 50);
 ubus_timer.cb(&ubus_timer);
 assert(entered == 1 && !strcmp(calls, "ccccccdhsywana"));
 return 0;
}
'''

class ProcdTraceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = pathlib.Path(self.temp.name)
        shutil.copytree(FIXTURE, self.work/'source')
        self.source = self.work/'source'
        shutil.copy(PACKAGE/'src/lg6851f-boot-trace.h', self.source)
        subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(PACKAGE/'patches/901-mt6990-measure-boot-ubus-stages.patch')],cwd=self.source,check=True,capture_output=True)
        self.trace = self.work/'trace.log'
        self.trace.write_text('LG6851F_BOOT_ID=fixture\n')
        self.trace.chmod(0o600)
        self.ready = self.work/'ready'
        self.boot_id = self.work/'boot-id'
        self.boot_id.write_text('12345678-1234-1234-1234-000000000001\n')
    def compile(self, source, enabled=True):
        p=self.source/'harness.c';p.write_text(source)
        exe=self.work/'harness'
        cmd=[os.environ.get('CC','cc'),'-D_GNU_SOURCE','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I',str(self.source),str(p),'-o',str(exe)]
        if enabled:cmd += ['-DLG6851F_BOOT_TRACE', '-DLG6851F_TRACE_PATH="'+str(self.trace)+'"','-DLG6851F_KMSG_PATH="'+str(self.work/'no-kmsg')+'"', '-DLG6851F_READY_PATH="'+str(self.ready)+'"', '-DLG6851F_BOOT_ID_PATH="'+str(self.boot_id)+'"']
        subprocess.run(cmd,check=True,capture_output=True,text=True)
        subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=5)
    def test_pinned_fixture_identity_and_patch_inputs(self):
        expected={'state.c':'8464ba9cc83e8e313ef9e7185693b131d10cdda4','ubus.c':'23f640ab74bfca859f4214a078cfbb2b04a06c73','initd/preinit.c':'46411aa413a2a65614cfc765d3d6a42dee200532'}
        for name, wanted in expected.items():
            data=(FIXTURE/name).read_bytes()
            actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            self.assertEqual(actual,wanted)
        self.assertIn('PKG_SOURCE_VERSION:=60fdbf00e924fff0a510c4ec31c520d35e69bfe1',(PACKAGE/'Makefile').read_text())
    def test_real_ubus_code_keeps_backoff_and_registration_order(self):
        (self.source/'procd.h').write_text(STUB)
        self.compile(HARNESS)
        text=self.trace.read_text()
        self.assertIn('phase=ubus-connect-begin attempt=6',text)
        self.assertIn('phase=ubus-connect-end attempt=6 success=1',text)
        self.assertIn('phase=ubus-initial-ready attempts=6',text)
        self.assertEqual(text.count('phase=ubus-register-begin'),5)
        self.assertEqual(text.count('phase=ubus-register-end'),5)
        self.assertEqual(text.count('phase=ubus-connect-begin'),6)
    def test_failed_trace_io_does_not_block_ubus_boot(self):
        self.trace.unlink();self.trace.mkdir()
        (self.source/'procd.h').write_text(STUB)
        self.compile(HARNESS)
        self.assertTrue(self.trace.is_dir())
    def test_other_targets_compile_out_trace_arguments_and_files(self):
        original=self.trace.read_bytes()
        self.compile(r'''
#include <assert.h>
#include "lg6851f-boot-trace.h"
int main(void) { int n=0; lg6851f_boot_trace("ignored", "%d", ++n); lg6851f_boot_ready(++n); assert(n==0); return 0; }
''',enabled=False)
        self.assertEqual(self.trace.read_bytes(),original)
    def test_header_preserves_errno_and_rejects_symlink_or_writable_file(self):
        program=r'''
#include <assert.h>
#include <errno.h>
#include "lg6851f-boot-trace.h"
int main(void) { errno=E2BIG; lg6851f_boot_trace("native-probe", "value=%d", 2); assert(errno==E2BIG); return 0; }
'''
        self.compile(program)
        self.assertIn('phase=native-probe value=2',self.trace.read_text())
        victim=self.work/'victim';victim.write_text('untouched')
        self.trace.unlink();self.trace.symlink_to(victim)
        self.compile(program);self.assertEqual(victim.read_text(),'untouched')
        self.trace.unlink();self.trace.write_text('writable');self.trace.chmod(0o666)
        self.compile(program);self.assertEqual(self.trace.read_text(),'writable')
    def test_pid1_receipt_is_independent_of_trace_and_preserves_errno(self):
        self.trace.unlink()
        self.compile(r'''
#include <assert.h>
#include <errno.h>
#include <unistd.h>
#define getpid() 1
#include "lg6851f-boot-trace.h"
int main(void) { errno=E2BIG; lg6851f_boot_ready(1); assert(errno==E2BIG); return 0; }
''')
        fields=self.ready.read_text().split()
        self.assertEqual(fields[0],self.boot_id.read_text().strip())
        self.assertGreaterEqual(int(fields[1]),0)
        self.assertEqual(self.ready.stat().st_mode & 0o777,0o600)
        state=(self.source/'state.c').read_text()
        self.assertIn('case STATE_RUNNING:\n\t\tlg6851f_boot_trace("procd-running", "");\n\t\tlg6851f_boot_ready(1);',state)
        self.assertIn('case STATE_SHUTDOWN:\n\t\tlg6851f_boot_ready(0);',state)
        self.compile(r'''
#include <assert.h>
#include <errno.h>
#include <unistd.h>
#define getpid() 1
#include "lg6851f-boot-trace.h"
int main(void) { errno=E2BIG; lg6851f_boot_ready(0); assert(errno==E2BIG); assert(access(LG6851F_READY_PATH,F_OK)<0); return 0; }
''')
        self.assertEqual(pathlib.Path(str(self.ready)+'.shutdown').read_text().split(),fields)
    def test_early_shutdown_does_not_create_a_completed_init_receipt(self):
        self.compile(r'''
#include <unistd.h>
#define getpid() 1
#include "lg6851f-boot-trace.h"
int main(void) { lg6851f_boot_ready(0); return 0; }
''')
        self.assertFalse(self.ready.exists());self.assertFalse(pathlib.Path(str(self.ready)+'.shutdown').exists())
    def test_receipt_refuses_non_pid1_bad_uuid_existing_file_or_link(self):
        program=r'''
#include <unistd.h>
#define getpid() 1
#include "lg6851f-boot-trace.h"
int main(void) { lg6851f_boot_ready(1); return 0; }
'''
        self.compile(program.replace('#define getpid() 1',''))
        self.assertFalse(self.ready.exists())
        self.boot_id.write_text('invalid\n');self.compile(program);self.assertFalse(self.ready.exists())
        self.boot_id.write_text('12345678-1234-1234-1234-000000000001\n')
        self.ready.write_text('existing');self.compile(program);self.assertEqual(self.ready.read_text(),'existing')
        self.ready.unlink();self.ready.symlink_to(self.boot_id)
        self.compile(program);self.assertEqual(self.boot_id.read_text(),'12345678-1234-1234-1234-000000000001\n')

if __name__=='__main__':unittest.main()
