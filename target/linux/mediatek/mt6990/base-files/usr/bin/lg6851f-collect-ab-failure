#!/bin/sh
# Read only; usable after fallback when Android/stock Linux provides these files.
# Never mount/write partitions, mark a slot successful, or change boot control.
umask 077
report=/tmp/lg6851f-ab-failure.txt
[ -d /tmp ] || report=/data/local/tmp/lg6851f-ab-failure.txt
{
 echo 'collector_version=3'
 echo '=== 当前系统与槽位线索（不是失败原因判定） ==='
 uname -a
 cat /etc/mt6990-firmware-id /etc/openwrt_release 2>/dev/null
 cat /proc/cmdline /proc/sys/kernel/random/boot_id /proc/uptime 2>/dev/null
 command -v getprop >/dev/null 2>&1 && getprop ro.boot.slot_suffix
 echo '=== 厂商启动控制记录原始只读快照（不修改，不擅自解释计数） ==='
 if [ -b /dev/mmcblk0p1 ]; then
  dd if=/dev/mmcblk0p1 bs=1 skip=2048 count=32 2>/dev/null | hexdump -C
 fi
 echo '=== 已保留的pstore，切勿先清空或再次重启 ==='
 grep ' /sys/fs/pstore ' /proc/mounts 2>/dev/null || echo 'pstore当前未挂载；本脚本不主动挂载'
 for f in /sys/fs/pstore/* /proc/last_kmsg; do
  [ -r "$f" ] || continue
  echo "--- $f ---"
  cat "$f"
 done
 echo '=== 当前启动内核事件 ==='
 dmesg 2>/dev/null | grep -Ei 'Kernel command line|panic|Oops|BUG:|HANGDET|watchdog|ramoops|pstore|boot.*(fail|slot|reason)|reset.*reason|VFS:|Unable to mount|EXT4-fs.*error|QL_AB|bootctrl=|current_slot=|updating success' || :
 echo '=== 已挂载的共享P46记录（不主动挂载） ==='
 dev=/sys/class/block/mmcblk0p46
 points=
 if [ "$(cat "$dev/partition" 2>/dev/null)" = 46 ] &&
    [ "$(cat "$dev/size" 2>/dev/null)" = 5187456 ] &&
    grep -qx 'PARTNAME=user_data' "$dev/uevent"; then
  devno=$(cat "$dev/dev")
  # Stock can mount /dev/block/... by alias at /data. Match the actual
  # device number rather than the mount source spelling or an /overlay path.
  points=$(awk -v dev="$devno" '$3==dev && $4=="/" {
   for (i=7;i<=NF;i++) if ($i=="-" && $(i+1)=="ext4") {print $5; break}
  }' /proc/self/mountinfo)
  [ -n "$points" ] || echo '已核实P46身份，但未找到其完整ext4挂载'
 else
  echo 'P46身份未通过核对，不扫描其他分区'
 fi
 printf '%s\n' "$points" |
 while IFS= read -r mountpoint; do
  [ -n "$mountpoint" ] || continue
  mountpoint=$(printf '%b' "$mountpoint")
  echo "共享P46挂载位置：$mountpoint"
  for dir in "$mountpoint/MT6990_CRASH_LOGS" "$mountpoint/MT6990_RUNTIME_LOGS" "$mountpoint/lg6851f-ab-reports" "$mountpoint/lg6851f-ab-tools"; do
   [ -d "$dir" ] || continue
   ls -lt "$dir"
  done
  for f in "$mountpoint"/MT6990_RUNTIME_LOGS/runtime.log*; do
   [ -r "$f" ] || continue
   echo "--- $f ---"
   grep -Ei '===== MT6990 BOOT|^boot_id=|^firmware_id=|^cmdline=|LG6851F_BOOT_STAGE|Linux version|Kernel panic|Oops|BUG:|HANGDET|watchdog|Call trace|VFS:|Unable to mount|EXT4-fs.*error|QL_AB|bootctrl=|current_slot=|updating success' "$f" | tail -160
  done
  if [ -r "$mountpoint/openwrt-sysupgrade/upgrade-trace.log" ]; then
   echo '=== 最近升级轨迹 ==='
   tail -100 "$mountpoint/openwrt-sysupgrade/upgrade-trace.log"
  fi
  echo '=== 共享overlay历史固件编号（不代表当前槽内容） ==='
  cat "$mountpoint/.mt6990-firmware-id" 2>/dev/null
 done
} > "$report" 2>&1
printf '已保存只读报告：%s\n' "$report"
