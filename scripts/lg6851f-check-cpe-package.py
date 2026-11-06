#!/usr/bin/env python3
"""发布前核验蜂窝菜单、资源、RPC/ACL 和可执行控制脚本。不会运行模组命令。"""
import argparse
import json
import os
import pathlib
import re
import subprocess

repo = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--rootfs', type=pathlib.Path, help='核验已经组装的固件根目录；省略则检查源码')
args = parser.parse_args()
package = repo/'package/vendor/luci-app-5gmodem'
root = args.rootfs or package/'root'
assets = root/'www/luci-static/resources' if args.rootfs else package/'htdocs/luci-static/resources'
chain = args.rootfs or repo/'package/vendor/lg6851f-modem-chain-only/files'
errors = []


def required(path, executable=False):
    if not path.is_file() or not path.stat().st_size:
        errors.append(f'缺少文件：{path}')
        return False
    if executable and not os.access(path, os.X_OK):
        errors.append(f'文件不可执行：{path}')
    return True


menu_path = root/'usr/share/luci/menu.d/luci-app-5gmodem.json'
acl_path = root/'usr/share/rpcd/acl.d/luci-app-5gmodem.json'
rpc_path = root/'usr/share/rpcd/ucode/luci.modem5g'
for path in [menu_path, acl_path, rpc_path]:
    required(path)
if errors:
    raise SystemExit('\n'.join(errors))
menu = json.loads(menu_path.read_text())
acl = json.loads(acl_path.read_text())['luci-app-5gmodem']
rpc_source = rpc_path.read_text()
methods = set(re.findall(r'^\t(\w+):\s*\{\s*(?:call|args):', rpc_source, re.M))
permitted = set(acl['read']['ubus']['luci.modem5g'] + acl['write']['ubus']['luci.modem5g'])
for name, entry in menu.items():
    action = entry.get('action', {})
    if action.get('type') == 'view':
        required(assets/'view'/(action['path']+'.js'))
for path in assets.glob('**/*.js'):
    source = path.read_text()
    for module in re.findall(r"['\"]require (modem5g\.[\w]+)(?: as \w+)?['\"]", source):
        required(assets/(module.replace('.', '/')+'.js'))
    for method in re.findall(r"rpc\.declare\(\{[^}]*object:\s*['\"]luci\.modem5g['\"][^}]*method:\s*['\"](\w+)['\"]", source):
        if method not in methods or method not in permitted:
            errors.append(f'RPC 或权限未接入：{path.name} → {method}')
for module in re.findall(r"from '(lg6851f\.\w+)'", rpc_source):
    required(root/('usr/share/ucode/'+module.replace('.', '/')+'.uc'))
for name in ['usr/bin/lg6851f-radio-control','usr/bin/lg6851f-modem-details',
             'usr/bin/lg6851f-modem-lock','usr/bin/lg6851f-modem-status',
             'usr/sbin/lg6851f-data-watchdog']:
    required(chain/name, executable=True)
for name in ['lib/functions/lg6851f-radio.sh','lib/netifd/proto/ql_datacall.sh']:
    required(chain/name)
if args.rootfs:
    for module in ['fs','uci']:
        required(root/('usr/lib/ucode/'+module+'.so'))
    # The SDK also ships an old unversioned /usr/lib/libuci.so for its own
    # processes. Native ucode must bind to the modern versioned system ABI.
    uci_module=root/'usr/lib/ucode/uci.so'
    if uci_module.is_file():
        dynamic=subprocess.run(['readelf','-d',str(uci_module)],text=True,capture_output=True,check=True).stdout
        libraries=re.findall(r'\[([^\]]+)\]',dynamic)
        uci_libraries=[name for name in libraries if name.startswith('libuci.so')]
        if not uci_libraries or any(name=='libuci.so' for name in uci_libraries):
            errors.append('ucode UCI 模块未绑定系统的版本化 libuci ABI')
        for name in uci_libraries:
            if not (root/'lib'/name).is_file() and not (root/'usr/lib'/name).is_file():
                errors.append('缺少系统 UCI 运行库：'+name)
if errors:
    raise SystemExit('\n'.join(errors))
views = sum(entry.get('action', {}).get('type')=='view' for entry in menu.values())
print(f'通过：{views} 个页面入口、共享资源、RPC/ACL 及射频/拨号脚本均完整（'+('固件根目录' if args.rootfs else '源码')+'）')
