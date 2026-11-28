#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Sample network state on this boot without opening or reconfiguring interfaces.
set -eu
umask 077

case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in
	fiberhome,lg6851f|fiberhome_lg6851f) ;;
	*) exit 95 ;;
esac
device=/sys/class/block/mmcblk0p46
[ "$(cat "$device/partition" 2>/dev/null)" = 46 ] &&
	[ "$(cat "$device/size" 2>/dev/null)" = 5187456 ] &&
	grep -qx 'PARTNAME=user_data' "$device/uevent" || exit 95
devno=$(cat "$device/dev")
boot_id=$(cat /proc/sys/kernel/random/boot_id)
printf '%s\n' "$boot_id" | grep -Eq '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' || exit 95
exec 9>/tmp/lg6851f-pro-network-diag.lock
flock -n 9 || exit 0

shared_mount() {
	awk -v dev="$devno" '$3==dev && $4=="/" && $6 ~ /(^|,)rw(,|$)/ {
		for (i=7;i<=NF;i++) if ($i=="-" && $(i+1)=="ext4" && $(i+3) ~ /(^|,)rw(,|$)/) {
			print $5; exit
		}
	}' /proc/self/mountinfo
}

link_state() {
	local interface="$1" dir="/sys/class/net/$1" key value
	[ -d "$dir" ] || { printf '%s missing\n' "$interface"; return; }
	printf '%s\n' "$interface"
	for key in ifindex flags operstate carrier speed duplex carrier_changes statistics/rx_packets statistics/tx_packets; do
		value=$(cat "$dir/$key" 2>/dev/null) || value=unavailable
		printf '  %s=%s\n' "$key" "$value"
	done
	if [ "$interface" = eth0 ] || [ "$interface" = eth1 ]; then
		value=$(readlink "$dir/phydev" 2>/dev/null) || value=unavailable
		printf '  phydev=%s\n' "${value##*/}"
	fi
}

rpc_state() {
	local object="$1" result rc=0 query value
	shift
	result=$(ubus -t 2 call "$object" "$1" '{}' 2>/dev/null) || rc=$?
	shift
	printf '%s rc=%s\n' "$object" "$rc"
	[ "$rc" = 0 ] || return 0
	for query in "$@"; do
		value=$(printf '%s\n' "$result" | jsonfilter -e "$query" 2>/dev/null) || value=unavailable
		printf '  %s=%s\n' "$query" "${value:-unavailable}"
	done
}

sample() {
	local interface path
	printf '\n=== sample uptime=%s ===\n' "$(cut -d' ' -f1 /proc/uptime)"
	printf 'LAN2=eth0 LAN1/WAN=eth1. MAC carrier can be fixed-link.\n'
	for interface in eth0 eth1 br-lan ra0 rai0; do link_state "$interface"; done
	for path in /sys/bus/mdio_bus/devices/*/phy_id; do
		[ -r "$path" ] || continue
		printf 'mdio %s phy_id=%s\n' "$(basename "${path%/*}")" "$(cat "$path" 2>/dev/null || echo unavailable)"
	done
	for path in /sys/class/net/br-lan/brif/* /sys/class/ieee80211/phy* /sys/class/udc/*; do
		[ -e "$path" ] && printf 'present %s\n' "$path"
	done
	[ ! -e /tmp/lg6851f-vendor618-ready ] || printf 'vendor618-ready marker present\n'
	rpc_state network.interface.lan status '@.up' '@.pending' '@.device' '@.l3_device'
	rpc_state network.wireless status '@.radio0.up' '@.radio0.pending' '@.radio1.up' '@.radio1.pending'
	rpc_state hostapd status '@.interfaces.*.running'
	printf '=== vendor618 startup stages ===\n'
	if [ -r /tmp/lg6851f-vendor618-boot.log ]; then
		awk '/^(BEGIN |STAGE |MODULES_LOADED |END |BLOCKED:|WO readiness)/ {print substr($0,1,240)}' \
			/tmp/lg6851f-vendor618-boot.log | tail -40
	else
		printf 'startup log unavailable\n'
	fi
	printf '=== selected network events ===\n'
	dmesg 2>/dev/null | awk '/mtk_soc_eth|yt8821|eth[01]:|br-lan:|MDIO|phylink|wo(cpu| firmware)|WO FW DL|netsys swdvfs/ {print substr($0,1,240)}' | tail -35
	/usr/bin/timeout -k 1 3 logread 2>/dev/null |
		awk '/lg6851f-(public|vendor618)|netifd.*(eth[01]|br-lan|radio[01]|VENDOR_)|hostapd.*(AP-ENABLED|AP-DISABLED|failed)/ {print substr($0,1,240)}' | tail -35
}

# Wait for the normal storage service. Never mount or repair a filesystem here.
mountpoint=''
for attempt in $(seq 1 60); do
	mountpoint=$(shared_mount)
	[ -z "$mountpoint" ] || break
	sleep 1
done
[ -n "$mountpoint" ] || exit 75
shared=$(printf '%b' "$mountpoint")
root="$shared/lg6851f-pro-network-diag"
[ ! -L "$root" ] || exit 22
available=$(df -Pk "$shared" | awk 'NR==2 {print $4}')
[ "${available:-0}" -ge 16384 ] || exit 28
mkdir -p "$root"
chmod 700 "$root"
report="$root/boot-$boot_id.txt"
[ ! -L "$report" ] || exit 22
[ ! -e "$report" ] || exit 0
tmp=''
trap '[ -z "$tmp" ] || rm -f "$tmp"' EXIT
trap 'exit 0' INT TERM

# Five snapshots over two minutes, including the original ADB start window.
for delay in 0 15 30 30 45; do
	[ "$delay" = 0 ] || sleep "$delay"
	[ "$(shared_mount)" = "$mountpoint" ] && [ ! -L "$root" ] && [ ! -L "$report" ] || exit 75
	tmp=$(mktemp "$root/.boot-$boot_id.XXXXXX")
	if [ -f "$report" ]; then
		head -c 131072 "$report" > "$tmp"
	else
		{
			printf 'diagnostic_version=1\nboot_id=%s\n' "$boot_id"
			printf 'firmware_id=%s\n' "$(cat /etc/mt6990-firmware-id 2>/dev/null || echo unavailable)"
			tr ' ' '\n' </proc/cmdline | grep -E '^(bootslot|root)=' || true
		} > "$tmp"
	fi
	sample >> "$tmp"
	[ "$(wc -c < "$tmp")" -le 131072 ] || exit 28
	[ "$(shared_mount)" = "$mountpoint" ] || exit 75
	mv -f "$tmp" "$report"
	tmp=''
	if [ "$delay" = 0 ]; then
		{ printf '%s\n' "$report"; ls -1t "$root"/boot-*.txt | awk -v current="$report" '$0 != current'; } |
			awk 'NR>8' | while IFS= read -r old; do rm -f "$old"; done
	fi
	sync -f "$root" 2>/dev/null || sync
done
