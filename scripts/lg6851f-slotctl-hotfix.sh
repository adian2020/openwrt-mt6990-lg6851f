#!/bin/sh
# Replace only the v1.0.19 selector file; never executes a slot operation.
set -eu
umask 077
[ "$(id -u)" = 0 ] || { echo '请使用root执行'; exit 1; }
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配，未修改'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id 2>/dev/null)" = b7dcaa16ce3d8fced5c314ee48fe3c017a291815 ] || { echo '此补丁仅适用于v1.0.19，未修改'; exit 95; }
prefix="${1:-}"
case "$#:$prefix" in 0:|1:https://v6.gh-proxy.org/) ;; *) echo '可选参数仅支持https://v6.gh-proxy.org/'; exit 22;; esac
destination=/usr/sbin/lg6851f-slotctl
old=3817de348e379c047a507c32cc2c6c42af2d4501af5a9b685f43b665ba8ddff9
new=6f924a63b88564bb811e54f77da872ac85b9dca90bee1d7971020d8ef26c99cc
[ -f "$destination" ] && [ ! -L "$destination" ] || { echo '未找到预期切槽工具，未修改'; exit 95; }
fingerprint() { sha256sum "$1" | cut -d ' ' -f 1; }
current=$(fingerprint "$destination")
if [ "$current" = "$new" ]; then echo '切槽工具已是修复版，不必重复安装'; exit 0; fi
[ "$current" = "$old" ] || { echo "工具指纹不是预期旧版，未修改：$current"; exit 95; }
lock=/tmp/lg6851f-slotctl-hotfix.lock
mkdir "$lock" 2>/dev/null || { echo '已有工具补丁正在执行，未修改'; exit 75; }
work=
pending=
cleanup() { [ -z "$pending" ] || rm -f "$pending"; [ -z "$work" ] || rm -rf "$work"; rmdir "$lock" 2>/dev/null || :; }
trap cleanup EXIT
trap 'exit 143' TERM INT HUP
[ ! -e /tmp/sysupgrade ] && [ ! -e /tmp/lg6851f-bootctrl.lock ] || { echo '存在升级标记或启动控制锁，请先核查，未修改'; exit 75; }
work=$(mktemp -d /tmp/lg6851f-slotctl-fix.XXXXXX)
url="${prefix}https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/1292a359d4a4f7312a5ab9cc9775d6d89cf46746/target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-slotctl"
wget -T 30 -O "$work/new.sh" "$url"
[ "$(fingerprint "$work/new.sh")" = "$new" ] || { echo '下载的工具校验失败，未应用'; exit 5; }
[ "$(fingerprint "$destination")" = "$old" ] || { echo '下载期间工具已变化，未应用'; exit 75; }
sh -n "$work/new.sh"
backup=$(mktemp -d /root/lg6851f-slotctl-before.XXXXXX)
cp -p "$destination" "$backup/original.sh"
[ "$(fingerprint "$backup/original.sh")" = "$old" ] || { echo "备份核对失败，未应用：$backup"; exit 5; }
cat > "$backup/restore.sh" <<'EOF'
#!/bin/sh
set -eu
umask 077
[ "$(id -u)" = 0 ] || exit 1
[ "$(cat /rom/etc/mt6990-firmware-id 2>/dev/null)" = b7dcaa16ce3d8fced5c314ee48fe3c017a291815 ] || { echo '固件已变化，不自动回退旧工具'; exit 95; }
backup=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destination=/usr/sbin/lg6851f-slotctl
[ -f "$destination" ] && [ ! -L "$destination" ] || exit 95
current=$(sha256sum "$destination" | cut -d ' ' -f 1)
[ "$current" != 3817de348e379c047a507c32cc2c6c42af2d4501af5a9b685f43b665ba8ddff9 ] || { echo '已是原工具'; exit 0; }
[ "$current" = 6f924a63b88564bb811e54f77da872ac85b9dca90bee1d7971020d8ef26c99cc ] || { echo '工具已被其他修改，不自动覆盖'; exit 95; }
[ "$(sha256sum "$backup/original.sh" | cut -d ' ' -f 1)" = 3817de348e379c047a507c32cc2c6c42af2d4501af5a9b685f43b665ba8ddff9 ] || { echo '原始备份校验失败'; exit 5; }
pending=$(mktemp "$destination.XXXXXX")
trap 'rm -f "$pending"' EXIT
cp -p "$backup/original.sh" "$pending"
mv -f "$pending" "$destination"
echo '已恢复原切槽工具'
EOF
chmod 700 "$backup/restore.sh"
echo "工具备份：$backup"
echo "回退命令：sh $backup/restore.sh"
pending=$(mktemp "$destination.XXXXXX")
cp "$work/new.sh" "$pending"
chmod 755 "$pending"
[ "$(fingerprint "$destination")" = "$old" ] || { echo '安装前工具已变化，未覆盖'; exit 75; }
mv -f "$pending" "$destination"
pending=
[ "$(fingerprint "$destination")" = "$new" ] || { echo "工具读回校验失败，请使用上述回退命令：$backup"; exit 5; }
echo '切槽工具误判修复完成；未执行切槽，未重启设备或任何服务。'
echo '请先仅设置并读回当前槽位及下次偏好，确认后再决定是否重启。'
