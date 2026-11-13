#!/bin/sh
# Read only; usable after fallback when Android/stock Linux provides these files.
# Never mount/write partitions, mark a slot successful, or change boot control.
umask 077
report=/tmp/lg6851f-ab-failure.txt
[ -d /tmp ] || report=/data/local/tmp/lg6851f-ab-failure.txt
{
 echo '=== 当前系统与槽位线索（不是失败原因判定） ==='
 uname -a
 cat /proc/cmdline /proc/sys/kernel/random/boot_id /proc/uptime 2>/dev/null
 command -v getprop >/dev/null 2>&1 && getprop ro.boot.slot_suffix
 echo '=== 厂商启动控制记录原始只读快照（不修改，不擅自解释计数） ==='
 if [ -b /dev/mmcblk0p1 ]; then
  dd if=/dev/mmcblk0p1 bs=1 skip=2048 count=32 2>/dev/null | hexdump -C
 fi
 echo '=== 已保留的pstore，切勿先清空或再次重启 ==='
 for f in /sys/fs/pstore/* /proc/last_kmsg; do
  [ -r "$f" ] || continue
  echo "--- $f ---"
  cat "$f"
 done
 echo '=== 当前启动内核事件 ==='
 dmesg 2>/dev/null | grep -Ei 'Kernel command line|panic|Oops|BUG:|HANGDET|watchdog|ramoops|pstore|boot.*(fail|slot|reason)|reset.*reason|VFS:|Unable to mount|EXT4-fs.*error' || :
 echo '=== 已挂载的共享P46记录（不主动挂载） ==='
 awk '$1 ~ /(^|\/)mmcblk0p46$/ {print $2}' /proc/mounts 2>/dev/null |
 while IFS= read -r mountpoint; do
  for dir in "$mountpoint/MT6990_CRASH_LOGS" "$mountpoint/MT6990_RUNTIME_LOGS"; do
   [ -d "$dir" ] || continue
   ls -lt "$dir"
  done
  for f in "$mountpoint"/MT6990_RUNTIME_LOGS/runtime.log*; do
   [ -r "$f" ] || continue
   echo "--- $f ---"
   grep -Ei '===== MT6990 BOOT|^boot_id=|^cmdline=|Linux version|Kernel panic|Oops|BUG:|HANGDET|watchdog|Call trace|VFS:|Unable to mount|EXT4-fs.*error' "$f" | tail -160
  done
 done
} > "$report" 2>&1
printf '已保存只读报告：%s\n' "$report"
