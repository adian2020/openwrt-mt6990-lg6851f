#!/bin/sh
# Called before mount_root; the caller validates and mounts the P46 partition.
lg6851f_adopt_legacy_reset_overlay() {
	local mnt="$1" slot="$2" pending="$1/openwrt-sysupgrade/overlay-policy"
	# Only the board-validated, explicitly requested reset for this boot slot
	# can adopt an old extroot. Never infer authorization merely from upper/.
	case "$slot" in a|b) ;; *) return 1 ;; esac
	[ ! -e "$mnt/.mt6990-extroot-managed" ] || return 1
	[ -f "$pending" ] && [ ! -L "$pending" ] || return 1
	grep -qx 'mode=reset' "$pending" || return 1
	grep -qx "slot=$slot" "$pending" || return 1
	[ -d "$mnt/upper" ] && [ -d "$mnt/work" ] || return 1
	[ ! -L "$mnt/upper" ] && [ ! -L "$mnt/work" ] || return 1
	printf '%s\n' legacy-explicit-reset > "$mnt/.mt6990-extroot-managed" || return 1
	echo 'LG6851F: adopted legacy overlay with explicit reset policy for current slot'
}

lg6851f_fresh_upgrade_upper() {
	local mnt="$1" rootuuid="$2" policy="$3" archive led_config
	case "$rootuuid" in ''|*[!a-zA-Z0-9-]*) return 1 ;; esac
	case "$policy" in keep|reset) ;; *) return 1 ;; esac
	[ -f "$mnt/.mt6990-extroot-managed" ] || return 1
	[ -d "$mnt/upper" ] && [ -d "$mnt/work" ] || return 1
	[ ! -L "$mnt/upper" ] && [ ! -L "$mnt/work" ] || return 1

	archive="$mnt/openwrt-extroot-backups/upgrade-$rootuuid"
	# Preserve an earlier archive when the same image is flashed again.
	while [ -e "$archive" ]; do archive="$archive-next"; done
	mkdir -p "$archive" || return 1
	mv "$mnt/upper" "$archive/upper" || return 1
	mv "$mnt/work" "$archive/work" || {
		mv "$archive/upper" "$mnt/upper"
		return 1
	}
	mkdir -p "$mnt/upper/etc/config" "$mnt/work" || return 1
	led_config="$archive/upper/etc/config/lg6851f_network_led"
	if [ -f "$led_config" ] && [ ! -L "$led_config" ]; then
		cp -p "$led_config" "$mnt/upper/etc/config/lg6851f_network_led" || return 1
	fi
	# Preserve only LED sections, never the rest of /etc/config/system.
	if [ -f "$archive/upper/etc/config/system" ]; then
		uci -c "$archive/upper/etc/config" export system 2>/dev/null |
			awk '/^package / { print; next } /^config / { keep=($2 == "led") } keep { print }' \
			> "$mnt/upper/etc/lg6851f-system-leds.pending"
		grep -q '^config led ' "$mnt/upper/etc/lg6851f-system-leds.pending" ||
			rm -f "$mnt/upper/etc/lg6851f-system-leds.pending"
	fi
	if [ "$policy" = reset ]; then
		rm -f "$mnt/openwrt-sysupgrade/sysupgrade.tgz"
	fi
	echo "LG6851F: fresh upgrade overlay policy=$policy; LED settings retained; old software archived"
}
