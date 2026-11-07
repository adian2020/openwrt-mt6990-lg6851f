#!/bin/sh
# Apply only the dashboard RPC fix to v1.0.11; no flash/overlay reset/radio change.
set -eu
case "$(cat /tmp/sysinfo/board_name)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id)" = 81c83ea30991ced06c02f12b967eeaadb1cfd8cd ] || { echo '仅供本次v1.0.11诊断使用'; exit 95; }
ref="${1:-}"
case "$ref" in ''|*[!0-9a-f]*) echo '需要完整源码提交编号'; exit 2;; esac
[ "${#ref}" = 40 ] || exit 2
backup="$(mktemp -d /root/lg6851f-dashboard-before.XXXXXX)"
chmod 700 "$backup"
stage="$backup/stage"
mkdir -p "$stage"
paths='usr/share/rpcd/ucode/luci.modem5g
usr/share/ucode/lg6851f/dashboard-collect.uc
usr/libexec/lg6851f-dashboard-collect.uc
usr/bin/lg6851f-dashboard-collect'
for path in $paths; do
	mkdir -p "$stage/$(dirname "$path")" "$backup/original/$(dirname "$path")"
	wget -q -O "$stage/$path" "https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/$ref/package/vendor/luci-app-5gmodem/root/$path"
	[ -s "$stage/$path" ] || exit 5
	if [ -e "/$path" ]; then cp -p "/$path" "$backup/original/$path"; fi
done
/usr/bin/ucode -L "$stage/usr/share/ucode" -c -o "$backup/rpc.check" "$stage/usr/share/rpcd/ucode/luci.modem5g"
/usr/bin/ucode -L "$stage/usr/share/ucode" -c -o "$backup/collector.check" "$stage/usr/libexec/lg6851f-dashboard-collect.uc"
sh -n "$stage/usr/bin/lg6851f-dashboard-collect"
for path in $paths; do
	mkdir -p "/$(dirname "$path")"
	cp "$stage/$path" "/$path"
	chmod 644 "/$path"
done
chmod 755 /usr/bin/lg6851f-dashboard-collect
cat > "$backup/restore.sh" <<'EOF'
#!/bin/sh
set -eu
backup="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cp -p "$backup/original/usr/share/rpcd/ucode/luci.modem5g" /usr/share/rpcd/ucode/luci.modem5g
/etc/init.d/rpcd restart
echo '已恢复热修复前的RPC文件'
EOF
chmod 700 "$backup/restore.sh"
rm -f /tmp/lg6851f-dashboard-v2.json
/etc/init.d/rpcd restart
echo "网页RPC热修复已应用，备份位于：$backup"
echo "回退命令：sh $backup/restore.sh"
if ! command -v iwinfo >/dev/null 2>&1; then
	echo '当前固件没有iwinfo命令：无线细节暂缺，此补丁先验证看板及其它页面可用性；新版固件已补齐该依赖。'
fi
