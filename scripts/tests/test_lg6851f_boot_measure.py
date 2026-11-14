#!/usr/bin/env python3
"""Execute boot measurement helpers with local fixtures, never a real device."""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT/'target/linux/mediatek/mt6990/base-files'
spec = importlib.util.spec_from_file_location('boot_analyzer', ROOT/'scripts/lg6851f-analyze-boot.py')
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)

class BootMeasureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root/'bin').mkdir()
        (self.root/'uptime').write_text('12.50 30.00\n')
        (self.root/'boot_id').write_text('fixture-boot\n')
        self.trace = self.root/'stages.log'
        helper = (BASE/'lib/functions/lg6851f-boot-trace.sh').read_text()
        for old, new in [('/tmp/lg6851f-boot-stages.log',str(self.trace)),('/proc/uptime',str(self.root/'uptime')),('/proc/sys/kernel/random/boot_id',str(self.root/'boot_id')),('/dev/kmsg',str(self.root/'not-a-device'))]:
            helper = helper.replace(old, new)
        self.helper = self.root/'helper.sh'
        self.helper.write_text(helper)
        self.env = dict(os.environ, TEST_DIR=str(self.root), PATH=str(self.root/'bin')+':'+os.environ['PATH'])
    def run_shell(self, text):
        return subprocess.run(['sh','-c',text],env=self.env,capture_output=True,text=True,timeout=15)
    def binary(self, name, text):
        p = self.root/'bin'/name
        p.write_text('#!/bin/sh\n'+text+'\n')
        p.chmod(0o755)
    def test_marker_has_boot_identity_monotonic_clock_and_private_mode(self):
        p = self.run_shell(f'. "{self.helper}"; lg6851f_bootmark kmodloader-begin; lg6851f_bootmark kmodloader-end rc=0')
        self.assertEqual(p.returncode,0,p.stderr)
        text = self.trace.read_text()
        self.assertIn('LG6851F_BOOT_ID=fixture-boot',text)
        self.assertEqual(text.count('LG6851F_BOOT_ID='),1)
        self.assertIn('uptime=12.50 phase=kmodloader-end rc=0',text)
        self.assertEqual(self.trace.stat().st_mode & 0o777,0o600)
    def test_marker_ignores_symlinks_and_cannot_change_caller_success(self):
        target = self.root/'target';target.write_text('untouched')
        self.trace.symlink_to(target)
        p = self.run_shell(f'. "{self.helper}"; lg6851f_bootmark anything')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(target.read_text(),'untouched')
        self.trace.unlink();self.trace.mkdir()
        self.assertEqual(self.run_shell(f'. "{self.helper}"; lg6851f_bootmark anything').returncode,0)
    def test_boot_defaults_keep_failures_retryable_and_original_final_return(self):
        defaults = self.root/'defaults';defaults.mkdir()
        (defaults/'10-success').write_text('echo first >> "$TEST_DIR/calls"; exit 0\n')
        (defaults/'20-failure').write_text('echo second >> "$TEST_DIR/calls"; exit 7\n')
        (self.root/'board.json').write_text('{}')
        self.binary('wifi','echo "wifi $*" >> "$TEST_DIR/calls"')
        self.binary('kmodloader','echo modules >> "$TEST_DIR/calls"; exit 9')
        self.binary('reload_config','echo reload >> "$TEST_DIR/calls"; exit 13')
        self.binary('uci','echo "uci $*" >> "$TEST_DIR/calls"')
        self.binary('sync',':')
        empty = self.root/'system.sh';empty.write_text('')
        source = (ROOT/'package/base-files/files/etc/init.d/boot').read_text()
        replacements = [('/lib/functions/lg6851f-boot-trace.sh',str(self.helper)),('/lib/functions/system.sh',str(empty)),('/etc/uci-defaults',str(defaults)),('/etc/board.json',str(self.root/'board.json'))]
        for name in ['wifi','kmodloader','reload_config']:
            replacements.append(('/sbin/'+name,str(self.root/'bin'/name)))
        # Redirect every writable absolute path; mount is mocked, no host mounts.
        for name in ['/var','/run','/tmp']:
            replacements.append((name,str(self.root/'sandbox'/name.lstrip('/'))))
        # Apply writable-path redirects before fixture paths are inserted.
        for old,new in reversed(replacements):
            if old in ['/var','/run','/tmp']:source=source.replace(old,new)
        for old,new in replacements:
            if old not in ['/var','/run','/tmp']:source=source.replace(old,new)
        self.binary('mount',':')
        script = self.root/'boot.sh';script.write_text(source+'\nboot\n')
        p = subprocess.run(['sh',str(script)],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,13,p.stderr)
        self.assertFalse((defaults/'10-success').exists())
        self.assertTrue((defaults/'20-failure').exists())
        self.assertEqual((self.root/'calls').read_text().splitlines(),['wifi config','modules','first','second','uci commit','reload'])
        text = self.trace.read_text()
        self.assertIn('phase=kmodloader-end rc=9',text)
        self.assertIn('phase=defaults-script-end 20-failure rc=7',text)
        self.assertIn('phase=s10-boot-end rc=13',text)
    def test_preinit_hooks_preserve_nested_order_once_flags_and_failure_handling(self):
        library=ROOT/'package/base-files/files/lib/functions/preinit.sh'
        program=f'. "{library}"\n'+r'''
boot_hook_trace() { printf "%s\n" "$*" >> "$TEST_DIR/hook-trace"; }
boot_hook_init preinit_main
boot_hook_init nested
one() { echo "one:$1:$2" >> "$TEST_DIR/calls"; boot_run_hook nested inner; return 7; }
two() { echo "two:$1:$2" >> "$TEST_DIR/calls"; }
boot_hook_add preinit_main one
boot_hook_add preinit_main two
boot_hook_add nested two
boot_run_hook preinit_main outer
first_rc=$?
boot_run_hook preinit_main outer
[ "$first_rc" = 0 ] && [ "$PI_RAN_one" = 1 ] && [ "$PI_RAN_two" = 1 ]
'''
        result=subprocess.run(['bash','-c',program],env=self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.root/'calls').read_text().splitlines(),['one:preinit_main:outer','two:nested:inner'])
        self.assertEqual((self.root/'hook-trace').read_text().splitlines(),[
            'preinit-hook-begin preinit_main one','preinit-hook-begin nested two',
            'preinit-hook-end nested two rc=0','preinit-hook-end preinit_main one rc=7'])
    def test_mount_root_observation_preserves_original_no_restore_return(self):
        source=(ROOT/'package/base-files/files/lib/preinit/80_mount_root').read_text()
        for old,new in [('/sysupgrade.tgz',str(self.root/'no-backup.tgz')),('/tmp/sysupgrade.tar',str(self.root/'no-backup.tar'))]:
            source=source.replace(old,new)
        program=r'''
boot_hook_add() { :; }
boot_hook_trace() { echo "$*" >> "$TEST_DIR/mount-trace"; }
mount_root() { echo mount >> "$TEST_DIR/calls"; return 9; }
boot_run_hook() { echo "$*" >> "$TEST_DIR/calls"; }
'''+source+'\ndo_mount_root\n'
        result=self.run_shell(program)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual((self.root/'calls').read_text().splitlines(),['mount','preinit_mount_root'])
        self.assertIn('mount-root-command-end rc=9',(self.root/'mount-trace').read_text())
    def observer(self, disabled=False):
        (self.root/'phys').mkdir()
        (self.root/'board').write_text('fiberhome,lg6851f')
        self.binary('sleep',"awk -v step=\"$TEST_STEP\" '{print $1+step, $2}' \"$TEST_DIR/uptime\" > \"$TEST_DIR/uptime.next\"; mv \"$TEST_DIR/uptime.next\" \"$TEST_DIR/uptime\"")
        self.binary('ubus', '''echo "$*" >> "$TEST_DIR/queries"
mkdir -p "$TEST_DIR/phys/phy0"
if [ -f "$TEST_DIR/queried" ] && [ "$TEST_DISABLED" != 1 ]; then
 echo '{"interfaces":{"ap0":{"running":true,"wiphy":"phy0"}}}'
else
 touch "$TEST_DIR/queried"
 echo '{"interfaces":{"ap0":{"running":false,"wiphy":"phy0"}}}'
fi''')
        jf = self.root/'bin/jsonfilter'
        jf.write_text('''#!/usr/bin/env python3
import sys,json
arg=sys.argv; data=json.loads(arg[arg.index('-s')+1]); expression=arg[arg.index('-e')+1]
if expression=='@.interfaces': print(json.dumps(data['interfaces']))
else:
 for row in data['interfaces'].values():print(str(row['running']).lower())
''');jf.chmod(0o755)
        source = (BASE/'usr/sbin/lg6851f-boot-observer').read_text()
        for old,new in [('/lib/functions/lg6851f-boot-trace.sh',str(self.helper)),('/tmp/sysinfo/board_name',str(self.root/'board')),('/proc/uptime',str(self.root/'uptime')),('/sys/class/ieee80211',str(self.root/'phys')),('/tmp/lg6851f-boot-observer.',str(self.root/'observer.')),('/tmp/lg6851f-boot-first-ap.json',str(self.root/'first-ap.json'))]:
            source=source.replace(old,new)
        script=self.root/'observer.sh';script.write_text(source)
        env=dict(self.env,TEST_DISABLED='1' if disabled else '0',TEST_STEP='30' if disabled else '1')
        p=subprocess.run(['sh',str(script)],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        return self.trace.read_text()
    def test_observer_waits_for_actual_running_state_and_only_queries_hostapd(self):
        text=self.observer()
        self.assertIn('phase=phy-observed phy0 previous_scan=12.50',text)
        self.assertIn('phase=ap-running-observed last_not_running=12.50',text)
        self.assertIn('phase=observer-end reason=first-ap-running',text)
        self.assertEqual((self.root/'queries').read_text().splitlines(),['-t 1 call hostapd status {}']*2)
        # Cross-check the real hostapd recipe's exported RPC method, not just mocks.
        hostapd=(ROOT/'package/network/services/hostapd/files/hostapd.uc').read_text()
        methods=set(re.findall(r'^\t(\w+):\s*\{\n\t\targs:',hostapd,re.M))
        self.assertIn('status',methods)
        self.assertTrue((self.root/'first-ap.json').is_file())
        self.assertEqual(list(self.root.glob('observer.*')), [self.root/'observer.sh'])
    def test_disabled_ap_times_out_without_enabling_anything(self):
        text=self.observer(disabled=True)
        self.assertIn('phase=observer-end reason=timeout',text)
        self.assertNotIn('phase=ap-running-observed',text)
        self.assertFalse((self.root/'first-ap.json').exists())
    def test_analyzer_does_not_mix_old_persistent_boots(self):
        text='''=== 本次启动阶段（内核运行秒数，不代表上电总耗时） ===
LG6851F_BOOT_ID=current
LG6851F_BOOT_STAGE uptime=20.00 phase=kmodloader-begin
LG6851F_BOOT_STAGE uptime=35.25 phase=kmodloader-end rc=0
LG6851F_BOOT_STAGE uptime=21.00 phase=phy-observed phy0 previous_scan=20.00
LG6851F_BOOT_STAGE uptime=45.00 phase=ap-running-observed last_not_running=44.00
=== 持久日志 ===
LG6851F_BOOT_ID=old
LG6851F_BOOT_STAGE uptime=100.00 phase=kmodloader-end rc=0
'''
        result='\n'.join(analyzer.analyze(text))
        self.assertIn('耗时 15.25 秒',result)
        self.assertIn('不晚于 45.00 秒',result)
        self.assertNotIn('100.00',result)
        self.assertIn('采样点差',result)
        detailed='''LG6851F_BOOT_STAGE uptime=4 phase=preinit-hook-begin preinit_main failsafe_wait
LG6851F_BOOT_STAGE uptime=8 phase=preinit-hook-end preinit_main failsafe_wait rc=1
LG6851F_BOOT_STAGE uptime=10 phase=ubus-register-begin service
LG6851F_BOOT_STAGE uptime=12 phase=ubus-register-end service
LG6851F_BOOT_STAGE uptime=9 phase=ubus-connect-begin attempt=1
LG6851F_BOOT_STAGE uptime=9.1 phase=ubus-connect-end attempt=1 success=1
'''
        summary='\n'.join(analyzer.analyze(detailed))
        self.assertIn('4.000 秒  preinit_main failsafe_wait rc=1',summary)
        self.assertIn('2.000 秒  service',summary)
        self.assertIn('0.100 秒  attempt=1 success=1',summary)
    def test_analyzer_never_uses_wifi_up_as_ap_enabled_and_rejects_mixed_boots(self):
        result='\n'.join(analyzer.analyze('LG6851F_BOOT_STAGE uptime=10 phase=wifi-up-request-end rc=0'))
        self.assertIn('首个热点运行确认：没有记录',result)
        with self.assertRaises(ValueError):analyzer.analyze('LG6851F_BOOT_ID=one\nLG6851F_BOOT_ID=two')
        self.assertIn('不能追溯',analyzer.analyze('log truncated')[0])

if __name__=='__main__':unittest.main()
