#!/bin/sh
# Read-only, bounded boot-chain collection. Never writes boot partitions.
set -eu
umask 077
mode=lk
case "$#:${1:-}" in
 0:) ;;
 1:--preloader) mode=preloader;;
 *) echo '用法：sh lg6851f-probe-bootloader.sh [--preloader]' >&2; exit 22;;
esac
root=$(mktemp -d /tmp/lg6851f-bootchain.XXXXXX)
report="$root/identity.txt"
exec 3>&1 4>&2
stage=identity
found=0
preloaders=0
reading=
reader_pid=
reader_stamp=
guard_pid=
guard_stamp=
# Only inspect our own children. Compare start time as well as PID before kill.
process_root=/proc
child_stamp() { awk -v parent="$$" '$4==parent {print $22}' "$process_root/$1/stat" 2>/dev/null || :; }
same_child() { [ -n "$2" ] && [ "$(child_stamp "$1")" = "$2" ]; }
stop_child() {
 [ -n "$1" ] || return 0
 if same_child "$1" "$2"; then kill -KILL "$1" 2>/dev/null || :; fi
 wait "$1" 2>/dev/null || :
}
read_image() {
 local rc timed_out="$root/read-timed-out"
 rm -f "$timed_out"
 dd if="$device" of="$reading" bs="$read_bs" count="$read_count" 2>> "$report" &
 reader_pid=$!
 reader_stamp=$(child_stamp "$reader_pid")
 (
  trap - EXIT INT TERM HUP
  exec 3>&- 4>&-
  sleep 12
  if same_child "$reader_pid" "$reader_stamp"; then
   : > "$timed_out"
   kill -TERM "$reader_pid" 2>/dev/null || :
   sleep 1
   if same_child "$reader_pid" "$reader_stamp"; then kill -KILL "$reader_pid" 2>/dev/null || :; fi
  fi
 ) </dev/null >/dev/null 2>&1 &
 guard_pid=$!
 guard_stamp=$(child_stamp "$guard_pid")
 if wait "$reader_pid"; then rc=0; else rc=$?; fi
 reader_pid=; reader_stamp=
 stop_child "$guard_pid" "$guard_stamp"
 guard_pid=; guard_stamp=
 [ ! -f "$timed_out" ] || { echo '引导镜像读取超过12秒，已请求停止采集子进程' >> "$report"; return 124; }
 return "$rc"
}
finish() {
 local rc="$1" archive="$root.tar.gz" archive_rc
 trap - EXIT INT TERM HUP
 set +e
 stop_child "$guard_pid" "$guard_stamp"
 stop_child "$reader_pid" "$reader_stamp"
 if [ "$rc" -ne 0 ] && [ -n "$reading" ] && [ -f "$reading" ]; then
  mv "$reading" "$reading.partial"
 fi
 {
  printf 'collector_version=4\nmode=%s\nexit_code=%s\nstage=%s\ncompleted_lk_images=%s\ncompleted_preloader_prefixes=%s\n' "$mode" "$rc" "$stage" "$found" "$preloaders"
  [ "$mode" != preloader ] || echo 'scope=boot0/boot1 prefixes only; at most 1MiB each; not full partition backups'
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
 printf 'collector_version=4\nmode=%s\n' "$mode"
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
if [ "$mode" = lk ]; then
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
 read_bs=65536
 read_count=$(((sectors * 512 + 65535) / 65536))
 read_image
 stage="verify:$name"
 [ "$(wc -c < "$reading")" -eq "$((sectors * 512))" ] || die 5 'LK读取不完整'
 reading=
 found=$((found+1))
 sleep 1
done
stage=partition-scan
[ "$found" -gt 0 ] || die 95 '未找到lk_a/lk_b分区，保留分区诊断信息'
else
 # The uploaded stock upgrade library maps preloader_a/b to boot0/boot1.
 # Check the known board layout before reading either hardware boot area.
 stage=preloader-layout
 for spec in '1 misc 1024' '25 boot_a 65536' '26 rootfs_a 262144' '38 boot_b 65536' '39 rootfs_b 262144' '46 user_data 5187456'; do
  set -- $spec
  sys="/sys/class/block/mmcblk0p$1"
  [ -b "/dev/mmcblk0p$1" ] && [ "$(cat "$sys/partition" 2>/dev/null)" = "$1" ] &&
   [ "$(cat "$sys/size" 2>/dev/null)" = "$3" ] && grep -qx "PARTNAME=$2" "$sys/uevent" || die 95 '不是已核实的LG6851F分区布局，未读取preloader'
 done
 for name in mmcblk0boot0 mmcblk0boot1; do
  stage="identity:$name"
  sys="/sys/class/block/$name"
  device="/dev/$name"
  [ -b "$device" ] && grep -qx "DEVNAME=$name" "$sys/uevent" &&
   grep -qx 'DEVTYPE=disk' "$sys/uevent" || die 95 'eMMC启动区身份不匹配，拒绝读取'
  major=$(sed -n 's/^MAJOR=//p' "$sys/uevent")
  minor=$(sed -n 's/^MINOR=//p' "$sys/uevent")
  case "$major:$minor" in *[!0-9:]*|:*|*:) die 95 '启动区设备号无效';; esac
  [ "$(cat "$sys/dev")" = "$major:$minor" ] || die 95 '启动区sysfs设备号不一致'
  sectors=$(cat "$sys/size")
  case "$sectors" in ''|*[!0-9]*) die 95 '启动区大小无效';; esac
  [ "$sectors" -gt 0 ] && [ "$sectors" -le 16384 ] || die 27 '启动区超过已核实的8MiB容量边界，未读取'
  read_count="$sectors"
  [ "$read_count" -le 2048 ] || read_count=2048
  read_bs=512
  {
   echo "=== $name: prefix only; partition_sectors=$sectors read_sectors=$read_count ==="
   cat "$sys/uevent" "$sys/size" "$sys/dev"
   if [ -r "$sys/force_ro" ]; then printf 'force_ro='; cat "$sys/force_ro"; fi
  } >> "$report" 2>&1
  reading="$root/$name.prefix.img"
  stage="read:$name"
  read_image
  stage="verify:$name"
  [ "$(wc -c < "$reading")" -eq "$((read_count * 512))" ] || die 5 'preloader前缀读取不完整'
  reading=
  preloaders=$((preloaders+1))
  sleep 1
 done
fi
stage=kernel-log
dmesg > "$root/kernel.log" 2>/dev/null || :
stage=hashes
(cd "$root"; sha256sum ./*.img > SHA256SUMS)
stage=complete
