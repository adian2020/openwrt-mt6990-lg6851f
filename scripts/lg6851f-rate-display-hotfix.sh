#!/bin/sh
# Apply the numeric rate display to the current v1.0.11 without restarting RPC.
set -eu
umask 077
case "$(cat /tmp/sysinfo/board_name)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id)" = 81c83ea30991ced06c02f12b967eeaadb1cfd8cd ] || { echo '仅供本次v1.0.11使用'; exit 95; }
ref="${1:-}"
case "$ref" in ''|*[!0-9a-f]*) echo '需要完整源码提交编号'; exit 2;; esac
[ "${#ref}" = 40 ] || exit 2
destination=/www/luci-static/resources/view/modem5g/dashboard_v1.js
[ -f "$destination" ] && [ ! -L "$destination" ] || { echo '未找到预期的看板文件'; exit 95; }
backup="$(mktemp -d /root/lg6851f-rates-before.XXXXXX)"
wget -T 30 -q -O "$backup/new.js" "https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/$ref/package/vendor/luci-app-5gmodem/htdocs/luci-static/resources/view/modem5g/dashboard_v1.js"
[ "$(sha256sum "$backup/new.js" | cut -d ' ' -f 1)" = 23f5e1208be1c86665f9ebba0c24aaa69d2186517ebc15209f396bf46728ad41 ] || { echo '页面文件指纹不匹配，未应用'; exit 5; }
cp -p "$destination" "$backup/original.js"
cat > "$backup/restore.sh" <<'EOF'
#!/bin/sh
set -eu
backup="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cp -p "$backup/original.js" /www/luci-static/resources/view/modem5g/dashboard_v1.js
echo '已恢复原看板页面，请刷新网页'
EOF
chmod 700 "$backup/restore.sh"
pending="$(mktemp "$destination.XXXXXX")"
trap 'rm -f "$pending"' EXIT
cp "$backup/new.js" "$pending"
chmod 644 "$pending"
mv -f "$pending" "$destination"
echo "速率显示已更新，请刷新网页；原文件备份：$backup"
echo "回退命令：sh $backup/restore.sh"
