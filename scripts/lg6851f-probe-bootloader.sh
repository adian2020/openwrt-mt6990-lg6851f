#!/bin/sh
# Read-only, bounded LK collection. Archive diagnostics even on guarded failure.
set -eu
umask 077
root=$(mktemp -d /tmp/lg6851f-bootchain.XXXXXX)
report="$root/identity.txt"
exec 3>&1 4>&2
stage=identity
found=0
reading=
finish() {
 local rc="$1" archive="$root.tar.gz" archive_rc
 trap - EXIT INT TERM HUP
 set +e
 if [ "$rc" -ne 0 ] && [ -n "$reading" ] && [ -f "$reading" ]; then
  mv "$reading" "$reading.partial"
 fi
 {
  printf 'collector_version=2\nexit_code=%s\nstage=%s\ncompleted_lk_images=%s\n' "$rc" "$stage" "$found"
  [ "$rc" -ne 0 ] || echo 'status=complete'
  [ "$rc" -eq 0 ] || echo 'status=incomplete; partial images are not complete firmware dumps'
 } > "$root/status.txt"
 [ -f "$root/kernel.log" ] || dmesg > "$root/kernel.log" 2>/dev/null
 tar -czf "$archive" -C "$root" .
 archive_rc=$?
 if [ "$archive_rc" -eq 0 ]; then
  if [ "$rc" -eq 0 ]; then
   printf '只读采集完成：%s\n' "$archive" >&3
  else
   printf '采集未完成：阶段=%s，退出码=%s；已保存诊断包：%s\n' "$stage" "$rc" "$archive" >&4
   [ ! -f "$report" ] || tail -12 "$report" >&4
  fi
 else
  printf '诊断打包失败（退出码%s）；原始文件仍在：%s\n' "$archive_rc" "$root" >&4
  [ "$rc" -ne 0 ] || rc="$archive_rc"
 fi
 printf '报告目录：%s\n未切换槽位、未写misc或固件分区、未重启。\n' "$root" >&3
 exit "$rc"
}
trap 'finish $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
die() { printf '%s\n' "$2" >> "$report"; printf '%s\n' "$2" >&4; exit "$1"; }
{
 echo 'collector_version=2'
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
stage=partition-scan
for sys in /sys/class/block/mmcblk0p*; do
 [ -r "$sys/uevent" ] || continue
 name=$(sed -n 's/^PARTNAME=//p' "$sys/uevent")
 case "$name" in lk_a|lk_b) ;; *) continue;; esac
 stage="identity:$name"
 echo "=== LK candidate: $sys ===" >> "$report"
 cat "$sys/uevent" "$sys/size" "$sys/dev" >> "$report" 2>&1 || :
 devname=$(sed -n 's/^DEVNAME=//p' "$sys/uevent")
 case "$devname" in mmcblk0p[0-9]*) ;; *) die 95 'DEVNAME不是预期的eMMC分区名称';; esac
 case "${devname#mmcblk0p}" in *[!0-9]*) die 95 '分区名称后缀不是纯数字';; esac
 [ "$devname" = "${sys##*/}" ] || die 95 'DEVNAME与sysfs分区目录名称不一致'
 sectors=$(cat "$sys/size")
 case "$sectors" in ''|*[!0-9]*) die 95 '无法识别分区大小';; esac
 [ "$sectors" -gt 0 ] && [ "$sectors" -le 16384 ] || die 27 'LK超过8MiB采集上限，未读取镜像'
 device="/dev/$devname"
 stage="device:$name"
 [ -b "$device" ] || die 95 "未找到块设备：$device"
 [ ! -e "$root/$name.img" ] || die 95 '检测到重复的LK分区名称'
 echo "=== $name $device sectors=$sectors ===" >> "$report"
 stage="read:$name"
 reading="$root/$name.img"
 # Keep each read below the budget; no whole-eMMC or rootfs hash scan.
 timeout 12 dd if="$device" of="$reading" bs=65536 count="$(((sectors * 512 + 65535) / 65536))" 2>> "$report"
 stage="verify:$name"
 [ "$(wc -c < "$reading")" -eq "$((sectors * 512))" ] || die 5 'LK读取不完整'
 reading=
 found=$((found+1))
 sleep 1
done
stage=partition-scan
[ "$found" -gt 0 ] || die 95 '未找到lk_a/lk_b分区，保留分区诊断信息'
stage=kernel-log
dmesg > "$root/kernel.log" 2>/dev/null || :
stage=hashes
(cd "$root"; sha256sum ./*.img > SHA256SUMS)
stage=complete
