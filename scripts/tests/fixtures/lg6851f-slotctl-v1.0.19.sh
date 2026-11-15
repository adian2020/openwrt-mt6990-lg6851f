#!/bin/sh
# LG6851F Quectel BCAB only. Never clones partitions or reboots the device.
set -eu
umask 077
misc=/dev/mmcblk0p1
lock=/tmp/lg6851f-bootctrl.lock
work=
locked=0
quote_json() { printf '%s' "$1" | sed 's/\\/\\\\/g;s/"/\\"/g'; }
fail() { printf '{"code":%s,"error":"%s","backup":"%s"}\n' "$1" "$(quote_json "$2")" "$(quote_json "${backup:-}")"; exit "$1"; }
cleanup() { [ -z "$work" ] || rm -rf "$work"; [ "$locked" = 0 ] || rmdir "$lock" 2>/dev/null || :; }
trap cleanup EXIT
hex_read() { dd if="$1" bs=1 skip="$2" count="$3" 2>/dev/null | hexdump -v -e '1/1 "%02x"'; }
byte() { printf '%s' "$1" | cut -c"$(($2 * 2 + 1))-$(($2 * 2 + 2))"; }
number() { printf '%d' "0x$1"; }
patch_byte() {
 local input="$1" index="$2" value="$3" left right
 if [ "$index" = 0 ]; then left=; else left=$(printf '%s' "$input" | cut -c1-"$((index * 2))"); fi
 right=$(printf '%s' "$input" | cut -c"$((index * 2 + 3))"-)
 printf '%s%s%s' "$left" "$value" "$right"
}
write_byte() {
 local offset="$1" value="$2" octal
 octal=$(printf '%03o' "$(number "$value")")
 printf "\\$octal" | dd of="$misc" bs=1 seek="$offset" count=1 conv=notrunc 2>/dev/null
}
layout() {
 local part="$1" name="$2" size="$3" sys="/sys/class/block/mmcblk0p$1"
 [ -b "/dev/mmcblk0p$part" ] && [ "$(cat "$sys/partition" 2>/dev/null)" = "$part" ] &&
 [ "$(cat "$sys/size" 2>/dev/null)" = "$size" ] && grep -qx "PARTNAME=$name" "$sys/uevent" || fail 95 '设备分区布局不符，拒绝操作'
}
read_control() {
 record=$(hex_read "$misc" 2048 32)
 [ "${#record}" = 64 ] || fail 5 '无法完整读取启动控制记录'
 case "$record" in *[!0-9a-f]*) fail 5 '启动记录格式错误';; esac
 [ "$(printf '%s' "$record" | cut -c9-16)" = 42434142 ] &&
 [ "$(byte "$record" 8)" = 01 ] && [ "$(byte "$record" 9)" = 02 ] || fail 95 '不支持的BCAB格式'
 pa=$(number "$(byte "$record" 12)"); pb=$(number "$(byte "$record" 17)")
 ra=$(number "$(byte "$record" 13)"); rb=$(number "$(byte "$record" 18)")
 sa=$(number "$(byte "$record" 14)"); sb=$(number "$(byte "$record" 19)")
 ua=$(number "$(byte "$record" 15)"); ub=$(number "$(byte "$record" 20)")
 [ "$pa" -le 15 ] && [ "$pb" -le 15 ] && [ "$sa" -le 1 ] && [ "$sb" -le 1 ] && [ "$ua" -le 4 ] && [ "$ub" -le 4 ] || fail 95 '启动字段不在已核实范围内'
 next=
 if [ "$pa" -gt "$pb" ]; then next=a; elif [ "$pb" -gt "$pa" ]; then next=b; fi
}
image_ok() {
 local boot="$1" rootfs="$2" ksize page version used high
 [ "$(hex_read "$boot" 0 8)" = 414e44524f494421 ] || return 1
 [ "$(hex_read "$rootfs" 0 4)" = 68737173 ] || return 1
 [ "$(hex_read "$rootfs" 28 2)" = 0400 ] || return 1
 # Little-endian uint32 on this AArch64 board; bounded header reads only.
 ksize=$(dd if="$boot" bs=1 skip=8 count=4 2>/dev/null | hexdump -v -e '1/4 "%u"')
 page=$(dd if="$boot" bs=1 skip=36 count=4 2>/dev/null | hexdump -v -e '1/4 "%u"')
 version=$(dd if="$boot" bs=1 skip=40 count=4 2>/dev/null | hexdump -v -e '1/4 "%u"')
 used=$(dd if="$rootfs" bs=1 skip=40 count=4 2>/dev/null | hexdump -v -e '1/4 "%u"')
 high=$(dd if="$rootfs" bs=1 skip=44 count=4 2>/dev/null | hexdump -v -e '1/4 "%u"')
 case "$ksize:$page:$version:$used:$high" in *[!0-9:]*) return 1;; esac
 [ -n "$page" ] && [ -n "$version" ] && [ -n "$used" ] && [ "$high" = 0 ] || return 1
 [ "$used" -ge 96 ] && [ "$used" -le 134217728 ] || return 1
 [ -n "$ksize" ] && [ "$ksize" -gt 0 ] && [ "$ksize" -lt 33550336 ] || return 1
 case "$page" in 2048|4096) ;; *) return 1;; esac
 [ "$version" -le 2 ]
}
state() {
 printf '{"code":0,"current":"%s","next":"%s","control":"%s","slots":{"a":{"priority":%s,"retry":%s,"success":%s,"upgrade":%s,"image_headers_ok":%s},"b":{"priority":%s,"retry":%s,"success":%s,"upgrade":%s,"image_headers_ok":%s}},"signature_status":"not_checked"}\n' \
 "$current" "$next" "$record" "$pa" "$ra" "$sa" "$ua" "$valid_a" "$pb" "$rb" "$sb" "$ub" "$valid_b"
}
shared_backup_dir() {
 local sys=/sys/class/block/mmcblk0p46 devno point
 [ -b /dev/mmcblk0p46 ] && [ "$(cat "$sys/partition" 2>/dev/null)" = 46 ] &&
 [ "$(cat "$sys/size" 2>/dev/null)" = 5187456 ] && grep -qx 'PARTNAME=user_data' "$sys/uevent" || fail 95 '共享P46身份不符，无法保存备份'
 devno=$(cat "$sys/dev")
 point=$(awk -v dev="$devno" '$3==dev && $4=="/" && $6 ~ /(^|,)rw(,|$)/ {for(i=7;i<=NF;i++)if($i=="-" && $(i+1)=="ext4"){print $5;exit}}' /proc/self/mountinfo)
 [ -n "$point" ] || fail 75 '未找到可写的共享P46，拒绝无备份设置槽位'
 point=$(printf '%b' "$point")
 backup_dir="$point/lg6851f-slot-backups"
 [ ! -L "$backup_dir" ] || fail 22 '备份目录不能为符号链接'
 mkdir -p "$backup_dir"; chmod 700 "$backup_dir"
}
# The bootloader and stock services do not honor this lock. Never use this
# command during startup or a firmware upgrade. Our upgrade path shares it.
[ "$(id -u)" = 0 ] || fail 1 '需要root权限'
layout 1 misc 1024
layout 25 boot_a 65536
layout 26 rootfs_a 262144
layout 38 boot_b 65536
layout 39 rootfs_b 262144
current=$(awk '{for(i=1;i<=NF;i++)if($i~/^bootslot=/){sub(/^bootslot=/,"",$i);print $i}}' /proc/cmdline)
rootdev=$(awk '{for(i=1;i<=NF;i++)if($i~/^root=/){sub(/^root=/,"",$i);print $i}}' /proc/cmdline)
case "$current:$rootdev" in a:/dev/mmcblk0p26|b:/dev/mmcblk0p39) ;; *) fail 95 '实际启动槽与根分区不匹配，拒绝推测槽位';; esac
read_control
valid_a=false; image_ok /dev/mmcblk0p25 /dev/mmcblk0p26 && valid_a=true
valid_b=false; image_ok /dev/mmcblk0p38 /dev/mmcblk0p39 && valid_b=true
case "${1:-show}" in
 show) [ "$#" -le 1 ] || fail 22 '用法：lg6851f-slotctl show'; state; exit 0;;
 select) ;;
 *) fail 22 '用法：show；或select a|b --expect 控制记录 --confirm [--allow-vendor-recovery]';;
esac
[ "$#" = 5 ] || [ "$#" = 6 ] || fail 22 '设置槽位需要明确确认及刚读取的控制记录'
target="$2"; expected="$4"; allow=false
[ "$3" = --expect ] && [ "$5" = --confirm ] || fail 22 '缺少确认参数'
if [ "$#" = 6 ]; then [ "$6" = --allow-vendor-recovery ] || fail 22 '未知参数'; allow=true; fi
case "$target" in a) [ "$valid_a" = true ] || fail 95 'A槽镜像头检查未通过';; b) [ "$valid_b" = true ] || fail 95 'B槽镜像头检查未通过';; *) fail 22 '目标槽只能为a或b';; esac
[ "${#expected}" = 64 ] || fail 22 '控制记录长度错误'
case "$expected" in *[!0-9a-f]*) fail 22 '控制记录格式错误';; esac
[ "$expected" = "$record" ] || fail 75 '启动记录已变化，请刷新后重新确认'
if [ -e /tmp/sysupgrade ] || ps w | grep -Eq '[/]etc/init.d/(rcS|zmtk_boot_done)|[z]mtk_boot_done|[/]sbin/(sysupgrade|upgraded)|[/]lib/upgrade/(do_stage2|stage2)'; then
 fail 75 '检测到启动/升级过程或遗留标记，拒绝同时切槽'
fi
risk=false
case "$target" in a) [ "$rb" -le 3 ] && [ "$sa" = 1 ] || risk=true;; b) [ "$ra" -le 3 ] && [ "$sb" = 1 ] || risk=true;; esac
[ "$risk" = false ] || [ "$allow" = true ] || fail 13 '已满足原厂可能恢复另一槽的条件；需要备份镜像并明确接受恢复风险'
mkdir "$lock" 2>/dev/null || fail 75 '启动控制正被操作或有遗留锁，请先核查'
locked=1
work=$(mktemp -d /tmp/lg6851f-slotctl.XXXXXX)
before="$record"
read_control
[ "$record" = "$before" ] || fail 75 '加锁后启动记录已变化，未写入'
shared_backup_dir
backup=$(mktemp "$backup_dir/bootctrl.XXXXXX")
dd if="$misc" of="$backup" bs=1 skip=2048 count=32 2>/dev/null || fail 5 '保存备份失败，未设置槽位'
[ "$(wc -c < "$backup")" = 32 ] && [ "$(hex_read "$backup" 0 32)" = "$before" ] || fail 5 '备份校验失败，未设置槽位'
dd if="$misc" of="$backup.misc" bs=4096 count=128 2>/dev/null || fail 5 '完整misc备份失败，未设置槽位'
[ "$(wc -c < "$backup.misc")" = 524288 ] && [ "$(hex_read "$backup.misc" 2048 32)" = "$before" ] || fail 5 '完整misc备份校验失败，未设置槽位'
printf '{"current":"%s","target":"%s","before":"%s","vendor_recovery_risk":%s}\n' "$current" "$target" "$before" "$risk" > "$backup.json"
sync
[ "$(hex_read "$misc" 2048 32)" = "$before" ] || fail 75 '保存备份期间记录已变化，未写入'
if [ "$target" = a ]; then retry_index=13; target_index=12; other_index=17; else retry_index=18; target_index=17; other_index=12; fi
step1=$(patch_byte "$before" "$retry_index" 00)
step2=$(patch_byte "$step1" "$other_index" 0e)
step3=$(patch_byte "$step2" "$target_index" 0f)
rollback() {
 local now index good=1
 trap '' INT TERM HUP
 now=$(hex_read "$misc" 2048 32)
 case " $before $step1 $step2 $step3 " in *" $now "*) [ "${#now}" = 64 ] || good=0;; *) good=0;; esac
 if [ "$good" = 1 ]; then
  for index in "$retry_index" "$other_index" "$target_index"; do
   write_byte "$((2048 + index))" "$(byte "$before" "$index")" || good=0
  done
  sync
  [ "$(hex_read "$misc" 2048 32)" = "$before" ] || good=0
 fi
 if [ "$good" = 1 ]; then fail 5 '槽位设置失败，已读回确认恢复原记录；未重启'; fi
 fail 5 '槽位设置失败且记录存在异常变化，未覆盖未知状态；不要重启，保留共享区备份核查'
}
trap rollback INT TERM HUP
write_byte "$((2048 + retry_index))" 00 || rollback
[ "$(hex_read "$misc" 2048 32)" = "$step1" ] || rollback
write_byte "$((2048 + other_index))" 0e || rollback
[ "$(hex_read "$misc" 2048 32)" = "$step2" ] || rollback
write_byte "$((2048 + target_index))" 0f || rollback
sync
[ "$(hex_read "$misc" 2048 32)" = "$step3" ] || rollback
trap - INT TERM HUP
printf '{"code":0,"target":"%s","control":"%s","backup":"%s","vendor_recovery_risk":%s,"rebooted":false}\n' "$target" "$step3" "$(quote_json "$backup")" "$risk"
