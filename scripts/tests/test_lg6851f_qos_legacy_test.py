#!/usr/bin/env python3
"""Exercise temporary legacy-controller lifecycle with isolated command adapters.

The historic payload stays byte-identical; its network execution is mocked.
No real tc, UCI, procd, modem or router operation is performed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'target/linux/mediatek/mt6990/base-files'
LEGACY = ROOT/'scripts/tests/fixtures/lg6851f-fair-qos-legacy.sh'
PAYLOAD_HASH = '3f8c535dbc2a28909955181232c3c06041959b5b7e69718660856e937a8c5496'


class LegacyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['tmp/sysinfo','var/run','var/lock','root','etc/config','etc/init.d',
                     'etc/hotplug.d/iface','usr/sbin','sys/class/net/ccmni2','bin','proc/sys/kernel/random']:
            (self.root/name).mkdir(parents=True, exist_ok=True)
        self.program = self.root/'usr/sbin/lg6851f-fair-qos'
        self.service = self.root/'etc/init.d/lg6851f_fair_qos'
        self.hook = self.root/'etc/hotplug.d/iface/95-lg6851f-fair-qos'
        for path in [self.program, self.service, self.hook]:
            path.write_bytes((BASE/path.relative_to(self.root)).read_bytes())
        self.config = self.root/'etc/config/lg6851f_fair_qos'
        self.config.write_text(json.dumps(dict(enabled='0',network_interface='modem5g',ifb_device='ifb-cellular')))
        (self.root/'tmp/sysinfo/board_name').write_text('fiberhome,lg6851f\n')
        (self.root/'proc/sys/kernel/random/boot_id').write_text('boot-fixture\n')
        self.net = self.root/'net.json'; self.net.write_text(json.dumps(dict(ifb=False,root='fq_codel',foreign=False)))
        source = (ROOT/'scripts/lg6851f-qos-legacy-test.sh').read_text()
        # Rewrite only absolute execution paths, not the pinned GitHub URL.
        source = re.sub(r'(?<![\w:])/(tmp|var|etc|usr|sys|root|proc)/',
                        lambda m:str(self.root/m[1])+'/',source)
        self.script = self.root/'controller.sh'; self.script.write_text(source)
        rc = self.root/'etc/rc.common'
        rc.write_text('''#!/bin/sh
echo "$*" >> "$FIXTURE/services"
if [ "$1" = "$FIXTURE/etc/init.d/lg6851f_fair_qos" ]; then
 case "$2" in
 stop) touch "$FIXTURE/var/run/lg6851f-fair-qos.stopped";;
 start) rm -f "$FIXTURE/var/run/lg6851f-fair-qos.stopped";;
 esac
fi
''')
        self.assertEqual(hashlib.sha256(LEGACY.read_bytes()).hexdigest(), PAYLOAD_HASH)
        (self.root/'download').write_bytes(LEGACY.read_bytes())
        mock = self.root/'bin/mock'
        mock.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys,shutil
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:];cmd=pathlib.Path(sys.argv[0]).name
net=json.loads((r/'net.json').read_text())
with (r/'calls').open('a') as f:f.write(cmd+' '+' '.join(a)+'\\n')
if cmd=='id': print(0)
elif cmd=='uname': print('6.18.44')
elif cmd=='wget':
 if os.environ.get('BAD_DOWNLOAD')=='1':sys.exit(4)
 shutil.copyfile(r/'download',a[a.index('-O')+1])
elif cmd=='uci':
 folder=r/'etc/config'
 if '-c' in a:idx=a.index('-c');folder=pathlib.Path(a[idx+1]);a=a[:idx]+a[idx+2:]
 if '-t' in a:idx=a.index('-t');a=a[:idx]+a[idx+2:]
 a=[v for v in a if v!='-q'];p=folder/'lg6851f_fair_qos';cfg=json.loads(p.read_text())
 if a[0]=='get': print(cfg[a[1].split('.')[-1]])
 elif a[0]=='set':key,value=a[1].split('=',1);cfg[key.split('.')[-1]]=value;p.write_text(json.dumps(cfg))
 elif a[0] in ['commit','changes']:pass
 else:raise AssertionError(a)
elif cmd=='ubus': print(json.dumps({'l3_device':'ccmni2'}))
elif cmd=='jsonfilter': print(json.load(sys.stdin)['l3_device'])
elif cmd=='ip': sys.exit(0 if net['ifb'] else 1)
elif cmd=='tc':
 if '-s' in a:a.remove('-s')
 if a[:2]==['qdisc','show']:
  d=a[a.index('dev')+1]
  if d=='ifb-cellular':print('qdisc cake 8002: root refcnt 2')
  else:print('qdisc '+net['root']+' 8001: root refcnt 2')
 elif a[:2]==['filter','show'] and 'egress' not in a:
  if net['foreign']:print('filter pref 20 mirred egress redirect to device foreign-ifb')
  elif net['ifb']:print('filter pref 10 mirred egress redirect to device ifb-cellular')
 else:pass
elif cmd=='sh':
 if len(a)>1 and a[0].endswith('/legacy.sh'):
  assert os.environ.get('UCI_CONFIG_DIR')==str(r/'tmp/lg6851f-qos-legacy-test/config')
  cfg=json.loads((pathlib.Path(os.environ['UCI_CONFIG_DIR'])/'lg6851f_fair_qos').read_text())
  assert cfg['enabled']=='1'
  state=r/'var/run/lg6851f-fair-qos.state'
  if a[1]=='start':
   net.update(ifb=True,root='cake');state.write_text('ccmni2\\n')
  elif a[1]=='stop':
   net.update(ifb=False,root='fq_codel');state.unlink(missing_ok=True)
  (r/'net.json').write_text(json.dumps(net))
 else:os.execv('/bin/sh',['sh',*a])
else:raise AssertionError(cmd)
''')
        mock.chmod(0o755)
        for cmd in ['id','uname','wget','uci','ubus','jsonfilter','tc','ip','sh']:
            (self.root/'bin'/cmd).symlink_to(mock)
        self.before = {p:p.read_bytes() for p in [self.program,self.service,self.hook,self.config]}

    def run_control(self, action, **extra):
        return subprocess.run(['/bin/sh',str(self.script),action],capture_output=True,text=True,
                              env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],FIXTURE=str(self.root),**extra))

    def assert_persistent_unchanged(self):
        for p, data in self.before.items(): self.assertEqual(p.read_bytes(),data,str(p))

    def test_private_config_exact_payload_backup_and_on_off_restore(self):
        for action in ['on','on','status','off','on','restore']:
            result=self.run_control(action);self.assertEqual(result.returncode,0,(action,result.stdout,result.stderr))
            self.assert_persistent_unchanged()
            if action=='on':
                work=self.root/'tmp/lg6851f-qos-legacy-test'
                self.assertEqual((work/'legacy.sh').read_bytes(),LEGACY.read_bytes())
                self.assertEqual(json.loads((work/'config/lg6851f_fair_qos').read_text())['enabled'],'1')
        self.assertFalse((self.root/'tmp/lg6851f-qos-legacy-test').exists())
        self.assertFalse(json.loads(self.net.read_text())['ifb'])
        backups=list((self.root/'root').glob('lg6851f-qos-before-test.*'));self.assertEqual(len(backups),1)
        for key,p in [('program',self.program),('service',self.service),('hotplug',self.hook),('config',self.config)]:
            self.assertEqual((backups[0]/key/p.name).read_bytes(),self.before[p])

    def test_bad_download_or_corrupt_payload_never_stops_current_service(self):
        for failure in ['network','corrupt']:
            with self.subTest(failure=failure):
                if failure=='corrupt':(self.root/'download').write_text('corrupt payload')
                result=self.run_control('on',BAD_DOWNLOAD='1' if failure=='network' else '0')
                self.assertNotEqual(result.returncode,0)
                self.assertFalse((self.root/'services').exists());self.assert_persistent_unchanged()
                shutil.rmtree(self.root/'tmp/lg6851f-qos-legacy-test',ignore_errors=True)

    def test_enabled_current_qos_and_modified_program_are_rejected(self):
        cfg=json.loads(self.config.read_text());cfg['enabled']='1';self.config.write_text(json.dumps(cfg))
        self.assertNotEqual(self.run_control('on').returncode,0)
        self.config.write_bytes(self.before[self.config]);self.program.write_text('modified')
        self.assertNotEqual(self.run_control('on').returncode,0)
        self.assertFalse((self.root/'services').exists())

    def test_foreign_queues_and_filters_are_not_overwritten(self):
        for net in [dict(ifb=False,root='htb',foreign=False),dict(ifb=False,root='fq_codel',foreign=True)]:
            self.net.write_text(json.dumps(net));result=self.run_control('on')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(json.loads(self.net.read_text()),net)
            self.assert_persistent_unchanged()

    def test_periodic_tick_does_not_revive_after_an_external_stop(self):
        self.assertEqual(self.run_control('on').returncode,0)
        self.assertEqual(self.run_control('_tick').returncode,0)
        (self.root/'var/run/lg6851f-fair-qos.state').unlink()
        self.net.write_text(json.dumps(dict(ifb=False,root='fq_codel',foreign=False)))
        self.assertEqual(self.run_control('_tick').returncode,76)
        self.assertFalse(json.loads(self.net.read_text())['ifb'])

    def test_modern_ownership_cannot_be_removed_or_replaced(self):
        self.assertEqual(self.run_control('on').returncode,0)
        state=self.root/'var/run/lg6851f-fair-qos.state';state.write_text('ccmni2\nifb-cellular\n1\n')
        self.assertEqual(self.run_control('_tick').returncode,76)
        self.assertNotEqual(self.run_control('off').returncode,0)
        self.assertEqual(state.read_text(),'ccmni2\nifb-cellular\n1\n')

    def test_upgrade_marker_and_wrong_boot_identity_block_changes(self):
        marker=self.root/'tmp/sysupgrade';marker.touch()
        self.assertNotEqual(self.run_control('on').returncode,0);marker.unlink()
        self.assertEqual(self.run_control('on').returncode,0)
        (self.root/'proc/sys/kernel/random/boot_id').write_text('new-boot')
        self.assertNotEqual(self.run_control('_tick').returncode,0)
        self.assert_persistent_unchanged()


if __name__=='__main__':unittest.main()
