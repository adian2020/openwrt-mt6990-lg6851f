#!/bin/sh
# Hotfix only the v1.0.19 slot view; never invokes slotctl, services or reboot.
set -eu
umask 077
[ "$(id -u)" = 0 ] || { echo '请使用root执行'; exit 1; }
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配，未修改'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id 2>/dev/null)" = b7dcaa16ce3d8fced5c314ee48fe3c017a291815 ] || { echo '此补丁仅适用于v1.0.19，未修改'; exit 95; }
prefix="${1:-}"
case "$#:$prefix" in 0:|1:https://v6.gh-proxy.org/) ;; *) echo '可选参数仅支持https://v6.gh-proxy.org/'; exit 22;; esac
destination=/www/luci-static/resources/view/system/lg6851f-slots.js
old=7c184590f0e96aaec0774888bfa915a9502fb9869e033c33b4948ef86ad4047a
first=5ac75940b6ecd11b0ae24895b5bce9970f2499ef5b9d54ce520478fcf3f210eb
new=53a9990b7626e30ae788e30bd6a7f66180d2f55008b41bee1f5f026ae6b1417c
[ -f "$destination" ] && [ ! -L "$destination" ] || { echo '未找到预期页面，未修改'; exit 95; }
fingerprint() { sha256sum "$1" | cut -d ' ' -f 1; }
current=$(fingerprint "$destination")
if [ "$current" = "$new" ]; then echo '切槽页面已是修复版，请使用无痕窗口重新打开页面'; exit 0; fi
case "$current" in "$old"|"$first") before="$current";; *) echo "页面指纹不是预期原版或第一版补丁，未修改：$current"; exit 95;; esac
lock=/tmp/lg6851f-slots-ui-hotfix.lock
mkdir "$lock" 2>/dev/null || { echo '已有页面补丁正在执行，未修改'; exit 75; }
work=
pending=
cleanup() { [ -z "$pending" ] || rm -f "$pending"; [ -z "$work" ] || rm -rf "$work"; rmdir "$lock" 2>/dev/null || :; }
trap cleanup EXIT
trap 'exit 143' TERM INT HUP
work=$(mktemp -d /tmp/lg6851f-slots-ui.XXXXXX)
url="${prefix}https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/dff868438f2a502030b9d87b8e8bf6dd2e88a28c/package/vendor/luci-app-5gmodem/htdocs/luci-static/resources/view/system/lg6851f-slots.js"
wget -T 30 -O "$work/new.js" "$url"
[ "$(fingerprint "$work/new.js")" = "$new" ] || { echo '下载的页面校验失败，未应用'; exit 5; }
[ "$(fingerprint "$destination")" = "$before" ] || { echo '下载期间页面已变化，未应用'; exit 75; }
backup=$(mktemp -d /root/lg6851f-slots-ui-before.XXXXXX)
cp -p "$destination" "$backup/original.js"
[ "$(fingerprint "$backup/original.js")" = "$before" ] || { echo "备份核对失败，未应用：$backup"; exit 5; }
printf '%s\n' "$before" > "$backup/original.sha256"
cat > "$backup/restore.sh" <<'EOF'
#!/bin/sh
set -eu
umask 077
[ "$(id -u)" = 0 ] || exit 1
[ "$(cat /rom/etc/mt6990-firmware-id 2>/dev/null)" = b7dcaa16ce3d8fced5c314ee48fe3c017a291815 ] || { echo '固件已变化，不自动回退旧页面'; exit 95; }
backup=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destination=/www/luci-static/resources/view/system/lg6851f-slots.js
[ -f "$destination" ] && [ ! -L "$destination" ] || exit 95
current=$(sha256sum "$destination" | cut -d ' ' -f 1)
original=$(cat "$backup/original.sha256")
case "$original" in 7c184590f0e96aaec0774888bfa915a9502fb9869e033c33b4948ef86ad4047a|5ac75940b6ecd11b0ae24895b5bce9970f2499ef5b9d54ce520478fcf3f210eb) ;; *) echo '不支持的原始备份'; exit 95;; esac
[ "$current" != "$original" ] || { echo '已是备份页面'; exit 0; }
[ "$current" = 53a9990b7626e30ae788e30bd6a7f66180d2f55008b41bee1f5f026ae6b1417c ] || { echo '页面已被其他修改，不自动覆盖'; exit 95; }
[ "$(sha256sum "$backup/original.js" | cut -d ' ' -f 1)" = "$original" ] || { echo '原始备份校验失败'; exit 5; }
pending=$(mktemp "$destination.XXXXXX")
trap 'rm -f "$pending"' EXIT
cp -p "$backup/original.js" "$pending"
mv -f "$pending" "$destination"
echo '已恢复原切槽页面，请用无痕窗口重新打开'
EOF
chmod 700 "$backup/restore.sh"
echo "页面备份：$backup"
echo "回退命令：sh $backup/restore.sh"
pending=$(mktemp "$destination.XXXXXX")
cp "$work/new.js" "$pending"
chmod 644 "$pending"
[ "$(fingerprint "$destination")" = "$before" ] || { echo '安装前页面已变化，未覆盖'; exit 75; }
mv -f "$pending" "$destination"
pending=
[ "$(fingerprint "$destination")" = "$new" ] || { echo "页面读回校验失败，请使用上述回退命令：$backup"; exit 5; }
echo '切槽页面第二版热修复完成；未切槽、未重启、未重启任何服务。'
echo '请用无痕窗口重新登录，打开系统→启动槽位，先点击刷新状态，再测试切换按钮。'
