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

openclash=package/vendor/luci-app-openclash/root
nikki=package/vendor/nikki/files
luci_nikki=package/vendor/luci-app-nikki/files
material 0755 files/etc/init.d/openclash "$openclash/etc/init.d/openclash"
material 0755 files/etc/init.d/nikki "$nikki/etc/init.d/nikki"
for entry in lib/upgrade/keep.d/luci-app-openclash usr/share/rpcd/acl.d/luci-app-openclash.json; do
	material 0644 "files/$entry" "$openclash/$entry"
done
material 0644 files/lib/upgrade/keep.d/nikki "$nikki/lib/upgrade/keep.d/nikki"
for entry in usr/share/luci/menu.d/luci-app-nikki.json usr/share/rpcd/acl.d/luci-app-nikki.json \
             www/luci-static/resources/view/nikki/log_ui_v20261017_1.js; do
	material 0644 "files/$entry" "$luci_nikki/$entry"
done
