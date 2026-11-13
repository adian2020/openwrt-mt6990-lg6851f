"""Run the real QoS control script against private network-command fixtures."""
import json, os, pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
BASE=ROOT/'target/linux/mediatek/mt6990/base-files'
class FairQosTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=pathlib.Path(self.temp.name);(self.root/'bin').mkdir();(self.root/'net').mkdir();(self.root/'net/ccmni2').touch();(self.root/'board').write_text('fiberhome,lg6851f')
  self.config={'enabled':'1','network_interface':'modem5g','ifb_device':'ifb-cellular','max_hosts':'36','overhead':'44','diffserv':'diffserv4','ingress_seed':'1gbit'}
  self.save_config();(self.root/'network').write_text(json.dumps({'wan':'ccmni2','q':{},'ifb':False,'clsact':True,'filters':{'20':'foreign-device'}}))
  lib=self.root/'functions';lib.write_text('''config_load(){ :; }
config_get(){ local value; value=$(python3 -c 'import json,os,sys;print(json.load(open(os.environ["TEST_ROOT"]+"/config")).get(sys.argv[1],sys.argv[2]))' "$3" "${4:-}"); export "$1=$value"; }
config_get_bool(){ config_get "$@"; }
''')
  mock=self.root/'bin/mock';mock.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['TEST_ROOT']);n=json.loads((p/'network').read_text());cmd=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:]
with (p/'calls').open('a') as f:f.write(cmd+' '+' '.join(a)+'\\n')
if os.environ.get('FAIL_FILTER')=='1' and cmd=='tc' and a[:2]==['filter','add']:sys.exit(1)
rc=0;changed=False
if cmd=='ubus':print(json.dumps({'l3_device':n['wan']}))
elif cmd=='jsonfilter':print(json.load(sys.stdin)['l3_device'])
elif cmd=='ip':
 if a[:3]==['link','show','dev']:rc=0 if n['ifb'] else 1
 elif a[:2]==['link','add']:n['ifb']=True;changed=True
 elif a[:2]==['link','del']:n['ifb']=False;n['q'].pop(a[2],None);changed=True
elif cmd=='tc':
 dev=a[a.index('dev')+1]
 if a[:2]==['qdisc','show']:
  if dev==n['wan']:print(n['q'].get(dev,'qdisc fq_codel 0: root refcnt 2'))
  elif dev in n['q']:print(n['q'][dev])
  if dev==n['wan'] and n['clsact']:print('qdisc clsact ffff: parent ffff:fff1')
 elif a[0]=='qdisc':
  changed=True
  if 'clsact' in a:n['clsact']=a[1]!='del'
  elif a[1]=='del':n['q'].pop(dev,None)
  else:n['q'][dev]='qdisc cake '+a[a.index('handle')+1]+' root refcnt 2'
 elif a[0]=='filter':
  pref=a[a.index('pref')+1] if 'pref' in a else None
  if a[1]=='show' and 'egress' not in a:
   for k,v in n['filters'].items():
    if pref is None or pref==k:print('filter pref '+k+' mirred egress redirect to device '+v)
  elif a[1]=='add':n['filters'][pref]=a[-1];changed=True
  elif a[1]=='del':n['filters'].pop(pref,None);changed=True
# Pipeline readers run concurrently; queries must never truncate shared state.
if changed:(p/'network').write_text(json.dumps(n))
sys.exit(rc)
''');mock.chmod(0o755)
  for cmd in ['tc','ip','ubus','jsonfilter','modprobe','logger']:(self.root/'bin'/cmd).symlink_to(mock)
  source=(BASE/'usr/sbin/lg6851f-fair-qos').read_text().replace('/lib/functions.sh',str(lib)).replace('/tmp/sysinfo/board_name',str(self.root/'board')).replace('/sys/class/net/',str(self.root/'net')+'/').replace('/var/run/lg6851f-fair-qos',str(self.root/'qos')).replace('/var/lock/lg6851f-fair-qos.lock',str(self.root/'lock'))
  self.script=self.root/'script';self.script.write_text(source)
 def save_config(self):(self.root/'config').write_text(json.dumps(self.config))
 def run_qos(self,action='start',fail=False):
  return subprocess.run(['sh',str(self.script),action],env=dict(os.environ,TEST_ROOT=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH'],FAIL_FILTER='1' if fail else '0'),capture_output=True,text=True)
 def state(self):return json.loads((self.root/'network').read_text())
 def test_readonly_commands_do_not_rewrite_fixture_state(self):
  state_file=self.root/'network';before=json.dumps(self.state(),indent=2)+'\n';state_file.write_text(before)
  env=dict(os.environ,TEST_ROOT=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH'])
  result=subprocess.run(['sh','-c','ubus -S call network.interface.modem5g status | jsonfilter -e @.l3_device; tc qdisc show dev ccmni2; ip link show dev ifb-cellular'],env=env,capture_output=True,text=True)
  self.assertIn('ccmni2',result.stdout)
  self.assertEqual(state_file.read_text(),before)
 def test_default_disabled_does_not_touch_network(self):
  self.config['enabled']='0';self.save_config();self.assertEqual(self.run_qos().returncode,0)
  self.assertFalse((self.root/'calls').exists());self.assertFalse(self.state()['ifb'])
 def test_enable_and_stop_preserve_foreign_filters(self):
  self.assertEqual(self.run_qos().returncode,0);self.assertTrue(self.state()['ifb'])
  self.assertEqual(self.run_qos('stop').returncode,0);n=self.state();self.assertFalse(n['ifb']);self.assertEqual(n['q'],{});self.assertEqual(n['filters'],{'20':'foreign-device'});self.assertTrue(n['clsact'])
 def test_disabled_redial_and_manual_stop_marker_do_not_restore(self):
  self.assertEqual(self.run_qos().returncode,0);self.config['enabled']='0';self.save_config();self.assertEqual(self.run_qos().returncode,0);self.assertFalse(self.state()['ifb'])
  self.config['enabled']='1';self.save_config();(self.root/'qos.stopped').touch();self.assertEqual(self.run_qos().returncode,0);self.assertFalse(self.state()['ifb'])
 def test_invalid_settings_do_not_block_stop(self):
  self.assertEqual(self.run_qos().returncode,0);self.config['max_hosts']='bad';self.save_config();self.assertEqual(self.run_qos('stop').returncode,0);self.assertFalse(self.state()['ifb'])
 def test_partial_setup_failure_rolls_back(self):
  self.assertNotEqual(self.run_qos(fail=True).returncode,0);self.assertFalse(self.state()['ifb']);self.assertEqual(self.state()['q'],{});self.assertEqual(self.state()['filters'],{'20':'foreign-device'})
 def test_duplicate_event_does_not_replace_queues(self):
  self.assertEqual(self.run_qos().returncode,0);(self.root/'calls').write_text('');self.assertEqual(self.run_qos().returncode,0);self.assertNotIn('qdisc replace',(self.root/'calls').read_text())
 def test_redial_cleans_old_device_then_follows_new_device(self):
  self.assertEqual(self.run_qos().returncode,0)
  n=self.state();n['wan']='ccmni3';(self.root/'network').write_text(json.dumps(n));(self.root/'net/ccmni3').touch()
  self.assertEqual(self.run_qos().returncode,0)
  self.assertEqual((self.root/'qos.state').read_text().splitlines()[0],'ccmni3')
  self.assertNotIn('ccmni2',self.state()['q'])
 def test_foreign_root_queue_is_not_overwritten(self):
  n=self.state();n['q']['ccmni2']='qdisc htb 1234: root refcnt 2';(self.root/'network').write_text(json.dumps(n))
  self.assertNotEqual(self.run_qos().returncode,0);self.assertFalse(self.state()['ifb']);self.assertIn('htb',self.state()['q']['ccmni2'])
 def test_migration_disables_old_config_once_but_keeps_later_opt_in(self):
  source=(BASE/'etc/uci-defaults/99-lg6851f-fair-qos-enable').read_text().replace('/etc/init.d/lg6851f_fair_qos',str(self.root/'service')).replace('/tmp/sysinfo/board_name',str(self.root/'board'))
  service=self.root/'service';service.write_text('#!/bin/sh\necho "$*" >> "$TEST_ROOT/service-calls"\n');service.chmod(0o755)
  uci=self.root/'bin/uci';uci.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['TEST_ROOT'])/'config';c=json.loads(p.read_text());a=[x for x in sys.argv[1:] if x!='-q'];k=a[1].split('.')[-1] if len(a)>1 else ''
if a[0]=='get':
 if k=='main':print('main')
 elif k in c:print(c[k])
 else:sys.exit(1)
elif a[0]=='set':k,v=a[1].split('=',1);c[k.split('.')[-1]]=v;p.write_text(json.dumps(c))
''');uci.chmod(0o755)
  env=dict(os.environ,TEST_ROOT=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH'])
  self.assertEqual(subprocess.run(['sh','-c',source],env=env).returncode,0)
  self.assertEqual(json.loads((self.root/'config').read_text())['enabled'],'0')
  c=json.loads((self.root/'config').read_text());c['enabled']='1';(self.root/'config').write_text(json.dumps(c))
  self.assertEqual(subprocess.run(['sh','-c',source],env=env).returncode,0)
  self.assertEqual(json.loads((self.root/'config').read_text())['enabled'],'1')
  self.assertEqual((self.root/'service-calls').read_text().splitlines().count('stop'),1)
 def test_hotplug_does_not_reenable_disabled_or_stopped_qos(self):
  self.script.chmod(0o755)
  uci=self.root/'bin/uci';uci.write_text('#!/bin/sh\necho modem5g\n');uci.chmod(0o755)
  service=self.root/'service';service.write_text('#!/bin/sh\nexit 0\n');service.chmod(0o755)
  hook=(BASE/'etc/hotplug.d/iface/95-lg6851f-fair-qos').read_text().replace('/var/run/lg6851f-fair-qos.stopped',str(self.root/'qos.stopped')).replace('/etc/init.d/lg6851f_fair_qos',str(service)).replace('/usr/sbin/lg6851f-fair-qos',str(self.script))
  env=dict(os.environ,TEST_ROOT=str(self.root),PATH=str(self.root/'bin')+':'+os.environ['PATH'],INTERFACE='modem5g',ACTION='ifup')
  self.config['enabled']='0';self.save_config()
  for action in ['ifup','ifupdate','ifdown']:
   self.assertEqual(subprocess.run(['sh','-c',hook],env=dict(env,ACTION=action)).returncode,0)
   self.assertFalse(self.state()['ifb'])
  self.config['enabled']='1';self.save_config();(self.root/'qos.stopped').touch()
  self.assertEqual(subprocess.run(['sh','-c',hook],env=env).returncode,0);self.assertFalse(self.state()['ifb'])
if __name__=='__main__':unittest.main()
