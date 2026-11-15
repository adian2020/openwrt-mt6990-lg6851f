#!/bin/sh
# Read-only, bounded LK partition collection; no boot-control writes or reboot.
set -eu
umask 077
root=$(mktemp -d /tmp/lg6851f-bootchain.XXXXXX)
report="$root/identity.txt"
{
 echo 'collector_version=1'
 uname -a
 cat /proc/cmdline /proc/sys/kernel/random/boot_id /proc/uptime
 echo '=== Fixed partition identities (metadata only) ==='
 for p in 1 25 26 38 39 46; do
  echo "--- mmcblk0p$p ---"
  for f in uevent size partition dev; do cat "/sys/class/block/mmcblk0p$p/$f" 2>/dev/null || :; done
 done
 echo '=== Existing boot-control bytes (read only) ==='
 if [ -b /dev/mmcblk0p1 ] && grep -qx 'PARTNAME=misc' /sys/class/block/mmcblk0p1/uevent && [ "$(cat /sys/class/block/mmcblk0p1/size)" = 1024 ]; then
  dd if=/dev/mmcblk0p1 bs=1 skip=2048 count=32 2>/dev/null | hexdump -C
 fi
} > "$report" 2>&1
found=0
for sys in /sys/class/block/mmcblk0p*; do
 [ -r "$sys/uevent" ] || continue
 name=$(sed -n 's/^PARTNAME=//p' "$sys/uevent")
 case "$name" in lk_a|lk_b) ;; *) continue;; esac
 devname=$(sed -n 's/^DEVNAME=//p' "$sys/uevent")
 case "$devname" in mmcblk0p[0-9]*) ;; *) echo 'Unexpected device name; refusing' >&2; exit 95;; esac
 case "${devname#mmcblk0p}" in *[!0-9]*) echo 'Invalid partition suffix' >&2; exit 95;; esac
 [ "$devname" = "${sys##*/}" ] || exit 95
 sectors=$(cat "$sys/size")
 case "$sectors" in ''|*[!0-9]*) echo 'Invalid partition size' >&2; exit 95;; esac
 [ "$sectors" -gt 0 ] && [ "$sectors" -le 16384 ] || { echo "LK超过8MiB采集上限，未读取镜像；分区信息：$report" >&2; exit 27; }
 device="/dev/$devname"
 [ -b "$device" ] || exit 95
 [ ! -e "$root/$name.img" ] || { echo 'Duplicate LK partition name' >&2; exit 95; }
 echo "=== $name $device sectors=$sectors ===" >> "$report"
 cat "$sys/uevent" >> "$report"
 # Keep each read below the budget; no whole-eMMC or rootfs hash scan.
 timeout 12 dd if="$device" of="$root/$name.img" bs=65536 count="$(((sectors * 512 + 65535) / 65536))" 2>> "$report"
 [ "$(wc -c < "$root/$name.img")" -eq "$((sectors * 512))" ] || { echo 'Incomplete LK read' >&2; exit 5; }
 found=$((found+1))
 sleep 1
done
[ "$found" -gt 0 ] || { echo "No LK partitions found; metadata: $report" >&2; exit 95; }
dmesg > "$root/kernel.log" 2>/dev/null || :
(cd "$root"; sha256sum ./*.img > SHA256SUMS)
archive="$root.tar.gz"
tar -czf "$archive" -C "$root" .
printf '只读采集完成：%s\n未切换槽位、未写misc或固件分区、未重启。\n' "$archive"
