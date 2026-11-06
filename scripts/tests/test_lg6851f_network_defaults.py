#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT/'package/vendor/lg6851f-modem-chain-only/files/etc/uci-defaults/90-lg6851f-network'


class NetworkDefaultsTest(unittest.TestCase):
    def apply_defaults(self, config):
        with tempfile.TemporaryDirectory() as name:
            root=pathlib.Path(name)
            (root/'config').write_text(json.dumps(config))
            cli='''#!/usr/bin/env python3
import sys,os,json,pathlib
p=pathlib.Path(os.environ['TEST_CONFIG']);data=json.loads(p.read_text());args=[x for x in sys.argv[1:] if x!='-q']
if args[0]=='get':
    if args[1] not in data:sys.exit(1)
    print(data[args[1]])
elif args[0]=='set':
    key,value=args[1].split('=',1);data[key]=value;p.write_text(json.dumps(data))
'''
            (root/'uci').write_text(cli);(root/'uci').chmod(0o700)
            # Execute the complete interface-default phase; firewall migration
            # is unchanged and intentionally outside this test.
            script=BOOTSTRAP.read_text().split('# Migrate images')[0]
            subprocess.run(['sh','-c',script],env=dict(os.environ,PATH=name+':'+os.environ['PATH'],TEST_CONFIG=str(root/'config')),check=True)
            return json.loads((root/'config').read_text())

    def test_existing_apn_radio_off_and_autostart_choice_survive(self):
        before={'network.modem5g':'interface','network.modem5g.proto':'ql_datacall',
            'network.modem5g.device':'ccmni','network.modem5g.apn':'custom.apn',
            'network.modem5g.iptype':'1','network.modem5g.roamingtype':'1',
            'network.modem5g.mtu':'1300','network.modem5g.plmn':'46011',
            'network.modem5g.auto_conf':'0','network.modem5g.auto':'0','network.modem5g.radio_enabled':'0'}
        self.assertEqual(self.apply_defaults(before),before)

    def test_fresh_interface_enables_radio_and_autostart(self):
        after=self.apply_defaults({})
        self.assertEqual(after['network.modem5g.radio_enabled'],'1')
        self.assertEqual(after['network.modem5g.auto'],'1')
        self.assertEqual(after['network.modem5g.proto'],'ql_datacall')


if __name__=='__main__':unittest.main()
