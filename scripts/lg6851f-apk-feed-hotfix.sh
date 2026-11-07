#!/bin/sh
# Restore trust for the already configured, immutable dedicated feed only.
set -eu
case "$(cat /tmp/sysinfo/board_name)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '设备不匹配'; exit 95;; esac
[ "$(cat /rom/etc/mt6990-firmware-id)" = 81c83ea30991ced06c02f12b967eeaadb1cfd8cd ] || { echo '仅供本次v1.0.11使用'; exit 95; }
ref="${1:-}"
case "$ref" in ''|*[!0-9a-f]*) echo '需要完整源码提交编号'; exit 2;; esac
[ "${#ref}" = 40 ] || exit 2
feed_root=https://cdn.jsdelivr.net/gh/13179415360/openwrt-mt6990-lg6851f@760d829021769a0aff5d713e7316c7d36ff40c71
expected=fee65298978c37b71198b8472673e6a73c5f7c0c99be6a85d030c4dc4a879d84
key=/etc/apk/keys/mt6990-760d829.pem
for feed in target base luci packages; do
	grep -qxF "$feed_root/$feed/packages.adb" /etc/apk/repositories.d/distfeeds.list || {
		echo '现有基础源不匹配，未修改公钥或软件源'; exit 95;
	}
done
if [ -e "$key" ] && [ "$(sha256sum "$key" | cut -d ' ' -f 1)" != "$expected" ]; then
	echo '同名公钥内容不同，未覆盖'; exit 95
fi
work="$(mktemp -d /tmp/lg6851f-apk-feed.XXXXXX)"
key_tmp=''
trap 'rm -rf "$work"; [ -z "$key_tmp" ] || rm -f "$key_tmp"' EXIT
chmod 700 "$work"
mkdir "$work/keys"
wget -T 30 -q -O "$work/keys/mt6990-760d829.pem" "https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/$ref/target/linux/mediatek/mt6990/base-files/etc/apk/keys/mt6990-760d829.pem"
[ "$(sha256sum "$work/keys/mt6990-760d829.pem" | cut -d ' ' -f 1)" = "$expected" ] || { echo '公钥指纹不匹配，未安装'; exit 5; }
for feed in target base luci packages; do
	wget -T 30 -q -O "$work/$feed.adb" "$feed_root/$feed/packages.adb"
	apk --keys-dir "$work/keys" verify "$work/$feed.adb" || { echo "${feed}源签名验证失败，未安装公钥"; exit 5; }
done
key_tmp="$(mktemp /etc/apk/keys/.mt6990-feed.XXXXXX)"
cp "$work/keys/mt6990-760d829.pem" "$key_tmp"
chmod 644 "$key_tmp"
mv -f "$key_tmp" "$key"
key_tmp=''
echo '四个基础源签名验证通过，已补齐专用公钥；开始更新索引。'
apk update
