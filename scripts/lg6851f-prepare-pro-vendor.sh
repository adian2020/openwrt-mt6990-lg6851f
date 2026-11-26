#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

top="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$top"

material() (
	mode="$1" source="$2" target="$3"
	if [ ! -f "$source" ]; then
		printf 'LG6851F Pro package input is missing: %s\n' "$source" >&2
		exit 1
	fi
	if [ -f "$target" ] && [ ! -L "$target" ] && cmp -s "$source" "$target"; then
		exit 0
	fi
	mkdir -p "$(dirname -- "$target")"
	temporary="$(mktemp "${target}.XXXXXX")"
	trap 'rm -f -- "$temporary"' EXIT
	install -m "$mode" "$source" "$temporary"
	mv -fT "$temporary" "$target"
)

dash=package/vendor/luci-app-fiberhomedash/files
for entry in usr/share/luci/menu.d/luci-app-fiberhome.json usr/share/rpcd/acl.d/luci-app-fiberhome.json; do
	material 0644 "files/$entry" "$dash/$entry"
done
material 0755 files/etc/init.d/fiberhomedash "$dash/etc/init.d/fiberhomedash"
material 0755 package/lg6851f/pro-material/mt6990-adb-usb.init \
	package/vendor/mt6990-adb-usb/files/etc/init.d/mt6990-adb-usb
material 0755 files/etc/init.d/openclash package/vendor/luci-app-openclash/root/etc/init.d/openclash
