#!/usr/bin/env python3
"""发布前核验蜂窝菜单、资源、RPC/ACL 和可执行控制脚本。不会运行模组命令。"""
import argparse
import hashlib
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

feed_root = args.rootfs or repo/'target/linux/mediatek/mt6990/base-files'
feed_key = feed_root/'etc/apk/keys/mt6990-760d829.pem'
if not feed_key.is_file() or hashlib.sha256(feed_key.read_bytes()).hexdigest() != 'fee65298978c37b71198b8472673e6a73c5f7c0c99be6a85d030c4dc4a879d84':
    errors.append('MT6990专用软件源公钥缺失或指纹不匹配')


def required(path, executable=False):
    target=path
    if args.rootfs:
        for _ in range(16):
            if not target.is_symlink():
                break
            link=target.readlink()
            target=pathlib.Path(os.path.normpath(str(root/link.relative_to('/') if link.is_absolute() else target.parent/link)))
    if not target.is_file() or not target.stat().st_size:
        errors.append(f'缺少文件：{path}')
        return False
    if executable and not os.access(target, os.X_OK):
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
for removed in ['admin/modem5g/cpu','admin/modem5g/sim']:
    if removed in menu: errors.append('已移除的页面重新出现在菜单：'+removed)
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
for module in re.findall(r"from '(lg6851f\.[\w-]+)'", rpc_source):
    required(root/('usr/share/ucode/'+module.replace('.', '/')+'.uc'))
for name in ['usr/share/ucode/lg6851f/forward.uc','etc/config/lg6851f_sms_forward',
             'lib/upgrade/keep.d/lg6851f-sms-forward','usr/libexec/lg6851f-sms-forward.uc']:
    required(root/name)
required(root/'etc/init.d/lg6851f-sms-forward',executable=True)
required(root/'usr/bin/lg6851f-dashboard-collect',executable=True)
required(root/'usr/bin/lg6851f-lock-status-collect',executable=True)
required(root/'usr/libexec/lg6851f-lock-status-collect.uc')
required(root/'usr/libexec/lg6851f-dashboard-collect.uc')
required(root/'usr/share/ucode/lg6851f/dashboard-collect.uc')
for name in ['usr/libexec/lg6851f-traffic.uc','usr/libexec/lg6851f-apn-resolve.uc',
             'usr/share/ucode/lg6851f/traffic-core.uc','usr/share/ucode/lg6851f/apn.uc',
             'etc/config/lg6851f_apn','lib/upgrade/keep.d/lg6851f-traffic-apn',
             'usr/libexec/lg6851f-radio-collect.uc','usr/share/licenses/luci-app-5gmodem/MU300-NOTICE']:
    required(root/name)
required(root/'etc/init.d/lg6851f-traffic',executable=True)
required(root/'etc/init.d/lg6851f-cellular-refresh',executable=True)
required(root/'usr/bin/lg6851f-cellular-refresh',executable=True)
required(chain/'usr/bin/lg6851f-modem-restart',executable=True)
required(root/'usr/bin/lg6851f-radio-collect',executable=True)
if not args.rootfs:
    required(root/'etc/uci-defaults/99-lg6851f-sms-forward',executable=True)
for name in ['usr/bin/lg6851f-radio-control','usr/bin/lg6851f-modem-details',
             'usr/bin/lg6851f-modem-lock','usr/bin/lg6851f-modem-status',
             'usr/sbin/lg6851f-data-watchdog','usr/bin/lg6851f-sms-list']:
    required(chain/name, executable=True)
for name in ['lib/functions/lg6851f-radio.sh','lib/netifd/proto/ql_datacall.sh']:
    required(chain/name)
if args.rootfs:
    required(root/'usr/bin/iwinfo',executable=True)
    required(root/'usr/bin/curl',executable=True)
    required(root/'usr/bin/sha256sum',executable=True)
    for module in ['fs','uci','ubus','uloop']:
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
