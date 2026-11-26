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
root = args.rootfs or repo/'files'
assets = root/'www/luci-static/resources'
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


menu_files = [
    'luci-app-5gmodem.json',
    'luci-app-fiberhome.json',
    'luci-app-lg6851f-slots.json',
]
menus = {}
for name in menu_files:
    path = root/'usr/share/luci/menu.d'/name
    if required(path):
        menus.update(json.loads(path.read_text()))
expected_views = {
    'admin/modem5g/overview': 'modem5g/status_cells_ca_v20261021_27',
    'admin/modem5g/sms': 'modem5g/sms_v20261015_3',
    'admin/modem5g/traffic': 'modem5g/traffic_v20261016_1',
    'admin/modem5g/network': 'modem5g/network_v20261026_71',
    'admin/modem5g/terminal': 'modem5g/terminal_v20261016_1',
    'admin/home': 'fiberhome/home_stable_v20261026_71',
    'admin/system/boot_slots': 'system/lg6851f-slots',
}
acl_files = [
    'luci-app-5gmodem.json', 'luci-app-fiberhome.json',
    'luci-app-lg6851f-cellular.json', 'luci-lg6851f-wireless-shared.json',
    'luci-app-lg6851f-slots.json',
]
acls = {}
for name in acl_files:
    path = root/'usr/share/rpcd/acl.d'/name
    if required(path):
        acls.update(json.loads(path.read_text()))

slot_acl = acls.get('luci-app-lg6851f-slots', {})
if slot_acl.get('read') != {'ubus': {'luci.lg6851fslots': ['get_boot_slots']}} or slot_acl.get('write') != {
        'ubus': {'luci.lg6851fslots': ['select_boot_slot'], 'system': ['reboot']}}:
    errors.append('启动槽位读写权限范围不符')
objects = {}
for acl in acls.values():
    for rule in ('read', 'write'):
        for name, methods in acl.get(rule, {}).get('ubus', {}).items():
            if name not in {'uci', 'system', 'network.interface', 'iwinfo'}:
                objects.setdefault(name, set()).update(methods)
for name, methods in objects.items():
    path = root/'usr/share/rpcd/ucode'/name
    if required(path):
        program = path.read_text()
        for method in methods - {'*'}:
            if not re.search(r'\b' + re.escape(method) + r'\s*:', program):
                errors.append(f'ACL 引用了缺失的 RPC：{name}.{method}')

checked = set()
def check_js(asset):
    if asset in checked:
        return
    checked.add(asset)
    path = assets/asset
    if not required(path):
        return
    source = path.read_text()
    namespaces = ('lg6851f.', 'modem5g.', 'fiberhome.', 'pwmfan.')
    for module in re.findall(r"['\"]require ([\w.-]+)(?: as \w+)?['\"]", source):
        if module.startswith(namespaces):
            check_js(module.replace('.', '/')+'.js')
    for name in re.findall(r"['\"](lg6851f/[^'\"]+\.css)(?:\?[^'\"]*)?['\"]", source):
        required(assets/name)

for route, view in expected_views.items():
    entry = menus.get(route, {})
    if entry.get('action') != {'type': 'view', 'path': view}:
        errors.append(f'页面路由缺失或错误：{route}')
    for name in entry.get('depends', {}).get('acl', []):
        if name not in acls:
            errors.append(f'页面权限缺失：{route} → {name}')
    check_js('view/'+view+'.js')
for name in ('network_v20261026_71', 'status_cells_ca_v20261021_27'):
    required(assets/f'view/modem5g/{name}.js')
for name in ('menu-aurora.js', 'router-aurora.js', 'translations/zh-cn_v20261026_72.js'):
    required(assets/name)
for name in ('header.ut', 'footer.ut', 'sysauth.ut'):
    required(root/'usr/share/ucode/luci/template/themes/aurora'/name)
for name in ('main.css', 'login.css', 'images/logo.svg', 'fonts/lato-v24-latin-regular.woff2'):
    required(root/'www/luci-static/aurora'/name)
for name in [
    'usr/libexec/lg6851f-cellular', 'usr/libexec/lg6851f-dashboard.ucb',
    'usr/share/ucode/lg6851f/cellular-ca.uc', 'usr/share/ucode/lg6851f/cellular-engine.uc',
    'usr/share/ucode/lg6851f/cellular-core.uc', 'usr/share/ucode/lg6851f/wireless-shared.uc',
    'usr/sbin/lg6851f-dashboard-sampler', 'usr/bin/lg6851f-ca-read',
    'etc/init.d/fiberhomedash', 'etc/init.d/lg6851f-cellular-traffic',
    'etc/init.d/lg6851f-modem-boot-lock', 'usr/bin/lg6851f-modem-lock',
    'usr/bin/lg6851f-modem-ui-job', 'usr/bin/lg6851f-modem-status',
    'lib/netifd/proto/ql_datacall.sh', 'lib/netifd/proto/ql_mipc.sh',
]:
    required(root/name)
for name in ('mipc_wan_cli', 'sample_nw', 'lg6851f-network-led'):
    required(chain/'usr/bin'/name, executable=True)
if args.rootfs:
    for name in ('modem5g-at', 'modem5g-sms-send', 'lg6851f-ipv6-prefix'):
        required(root/'usr/bin'/name, executable=True)
required(feed_root/'usr/bin/lg6851f-archive-ab-report',executable=True)
required(feed_root/'usr/bin/lg6851f-collect-ab-failure',executable=True)
required(feed_root/'usr/sbin/lg6851f-slotctl',executable=True)
required(feed_root/'usr/sbin/lg6851f-confirm-boot',executable=True)
required(feed_root/'etc/init.d/lg6851f-boot-confirm',executable=True)
required(feed_root/'etc/init.d/lg6851f-ab-report',executable=True)
required(feed_root/'usr/bin/lg6851f-setup-apk-library',executable=True)
required(feed_root/'usr/sbin/lg6851f-boot-observer',executable=True)
required(feed_root/'etc/init.d/lg6851f-boot-observer',executable=True)
for item in ['lib/functions/lg6851f-boot-trace.sh','lib/preinit/05_lg6851f_boot_trace','lib/preinit/99_lg6851f_boot_trace','etc/hotplug.d/ieee80211/00-lg6851f-boot-trace']:
    required(feed_root/item)
if args.rootfs:
    procd_binary=root/'sbin/procd'
    if required(procd_binary,executable=True) and any(marker not in procd_binary.read_bytes() for marker in (b'/tmp/lg6851f-init-complete', b'/tmp/lg6851f-init-complete.shutdown')):
        errors.append('procd缺少本机初始化/正常关机凭据，拒绝发布无法确认启动的固件')
    # Every normal cloud image must carry its own library identity and ROM key.
    library=root/'usr/share/mt6990-apk'
    for filename in ['build.json','selection.json','repositories.list','public-key.pem']:
        required(library/filename)
    if (library/'build.json').is_file():
        identity=json.loads((library/'build.json').read_text())
        if identity.get('source_sha')!=(root/'etc/mt6990-firmware-id').read_text().strip():
            errors.append('固件源码编号与软件库不匹配')
        expected=f'https://raw.githubusercontent.com/{identity["repository"]}/apk-lib-{identity["snapshot"]}/{identity["snapshot"]}/packages.adb\n'
        if (library/'repositories.list').read_text()!=expected:errors.append('固件软件库URL与构建快照不匹配')
        if (library/'public-key.pem').read_bytes()!=(root/'etc/apk/keys/public-key.pem').read_bytes():errors.append('固件ROM软件库公钥与本次APK签名公钥不匹配')
    required(root/'usr/bin/iwinfo',executable=True)
    required(root/'usr/sbin/miniupnpd',executable=True)
    required(assets/'view/upnp/upnp.js')
    required(root/'etc/openclash/core/clash_meta')
    required(root/'usr/bin/curl',executable=True)
    required(root/'usr/bin/sha256sum',executable=True)
    for module in ['fs','uci','ubus','uloop','digest','nl80211']:
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
print(f'通过：{len(expected_views)} 个页面入口、{len(checked)} 个页面和模块、RPC/ACL、Aurora 与 A/B 检查')
