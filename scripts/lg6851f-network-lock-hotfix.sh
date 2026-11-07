#!/bin/sh
# Fix the lock page and move its read-only collection outside RPC; no flashing.
set -eu
umask 077
case "$(cat /tmp/sysinfo/board_name)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id)" = 81c83ea30991ced06c02f12b967eeaadb1cfd8cd ] || { echo '仅供本次v1.0.11使用'; exit 95; }
ref="${1:-}"
case "$ref" in ''|*[!0-9a-f]*) echo '需要完整源码提交编号'; exit 2;; esac
[ "${#ref}" = 40 ] || exit 2
backup="$(mktemp -d /root/lg6851f-lock-before.XXXXXX)"
stage="$backup/stage"
cat > "$backup/paths" <<'EOF'
root/usr/share/rpcd/ucode/luci.modem5g|/usr/share/rpcd/ucode/luci.modem5g
root/usr/share/rpcd/acl.d/luci-app-5gmodem.json|/usr/share/rpcd/acl.d/luci-app-5gmodem.json
root/usr/share/luci/menu.d/luci-app-5gmodem.json|/usr/share/luci/menu.d/luci-app-5gmodem.json
root/usr/bin/lg6851f-lock-status-collect|/usr/bin/lg6851f-lock-status-collect
root/usr/libexec/lg6851f-lock-status-collect.uc|/usr/libexec/lg6851f-lock-status-collect.uc
htdocs/luci-static/resources/view/modem5g/lock_v20.js|/www/luci-static/resources/view/modem5g/lock_v20.js
EOF
while IFS='|' read -r source destination; do
	mkdir -p "$stage$(dirname "$destination")" "$backup/original$(dirname "$destination")"
	wget -T 30 -q -O "$stage$destination" "https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/$ref/package/vendor/luci-app-5gmodem/$source"
	[ -s "$stage$destination" ] || exit 5
	if [ -e "$destination" ]; then cp -p "$destination" "$backup/original$destination"; fi
done < "$backup/paths"
[ "$(sha256sum "$stage/www/luci-static/resources/view/modem5g/lock_v20.js" | cut -d ' ' -f 1)" = f6066dec819477c67832cba09d2621a72ffd286f3c317d4c7eb562d0df017a02 ] || { echo '页面指纹不匹配，未应用'; exit 5; }
/usr/bin/ucode -c -o "$backup/rpc.check" "$stage/usr/share/rpcd/ucode/luci.modem5g"
/usr/bin/ucode -c -o "$backup/worker.check" "$stage/usr/libexec/lg6851f-lock-status-collect.uc"
sh -n "$stage/usr/bin/lg6851f-lock-status-collect"
jsonfilter -i "$stage/usr/share/luci/menu.d/luci-app-5gmodem.json" -e '@' >/dev/null
jsonfilter -i "$stage/usr/share/rpcd/acl.d/luci-app-5gmodem.json" -e '@' >/dev/null
cat > "$backup/restore.sh" <<'EOF'
#!/bin/sh
set -eu
backup="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
while IFS='|' read -r source destination; do
	if [ -e "$backup/original$destination" ]; then
		cp -p "$backup/original$destination" "$destination"
	else
		rm -f "$destination"
	fi
done < "$backup/paths"
rm -f /tmp/luci-indexcache
for cache in /tmp/luci-indexcache.*; do [ ! -f "$cache" ] || rm -f "$cache"; done
/etc/init.d/rpcd restart
echo '已恢复热修复前的网络锁定页面及RPC文件，请刷新网页'
EOF
chmod 700 "$backup/restore.sh"
while IFS='|' read -r source destination; do
	mkdir -p "$(dirname "$destination")"
	cp "$stage$destination" "$destination"
	chmod 644 "$destination"
done < "$backup/paths"
chmod 755 /usr/bin/lg6851f-lock-status-collect
rm -f /tmp/luci-indexcache
for cache in /tmp/luci-indexcache.*; do [ ! -f "$cache" ] || rm -f "$cache"; done
/etc/init.d/rpcd restart
if ! timeout 25 ubus wait_for luci.modem5g || ! ubus -v list luci.modem5g | grep -q '"get_lock_cache"'; then
	echo '新RPC未就绪，自动恢复原文件'
	sh "$backup/restore.sh"
	exit 5
fi
echo "网络锁定修复已应用，请刷新网页；备份：$backup"
echo "回退命令：sh $backup/restore.sh"
