#!/bin/sh
# 只读取状态，在 /tmp 写诊断结果；不重启、不重拨、不修改配置。
umask 077
report=/tmp/lg6851f-boot-dashboard.txt
# 排除高频 CCCI 收发统计；它们会挤掉 tail 中真正需要的启动事件。
boot_pattern='===== MT6990 BOOT|^boot_id=|Linux version|Kernel command line|Run /etc/preinit|procd.*(early|ubus|init|stop|timeout)|lg6851f-wifi|lg6851f-modem-stack|mt799|mt76|hostapd.*(AP-ENABLED|AP-DISABLED|state|setup|failed|error)|netifd.*(Wireless|radio[0-9]|Interface .modem5g. is now up)|wifi.*(held down|enabl|preserv|PHY|generating)|EXT4-fs.*mmcblk0p46'
{
 echo '=== 采集版本 ==='
 echo 'collector_version=2'
 echo '=== 固件与运行时间 ==='
 cat /etc/mt6990-firmware-id /proc/sys/kernel/random/boot_id /proc/uptime 2>/dev/null
 uptime
 echo '=== 内核日志保留范围（运行秒数） ==='
 dmesg 2>/dev/null | awk '/^\[[ \t]*[0-9]+([.][0-9]+)?\]/ {
  stamp=$0; sub(/\].*$/, "]", stamp)
  if (!seen++) first=stamp
  last=stamp
 } END { if (seen) print "first=" first " last=" last; else print "内核日志时间范围不可用" }'
 echo '=== 无线启动日志 ==='
 logread 2>/dev/null | grep -Ei "$boot_pattern"
 echo '=== 驱动启动时间 ==='
 dmesg 2>/dev/null | grep -Ei "$boot_pattern"
 echo '=== 厂商启动时间记录（若内核提供） ==='
 if [ -r /proc/bootprof ]; then cat /proc/bootprof; else echo '未提供 /proc/bootprof'; fi
 echo '=== P46 持久启动日志（按内容筛选，不修改原文件） ==='
 found=0
 for saved in /mnt/mt6990-data/MT6990_RUNTIME_LOGS/runtime.log*; do
  [ -f "$saved" ] && [ -r "$saved" ] || continue
  found=1
  printf '\n--- %s ---\n' "$saved"
  grep -Ei "$boot_pattern" "$saved"
 done
 [ "$found" = 1 ] || echo '未找到可读取的 P46 持久日志'
 echo '=== 服务启动项 ==='
 ls -l /etc/rc.d/ 2>/dev/null | grep -Ei 'wifi|modem|mihomo|p46_runtime'
 echo '=== 当前看板缓存（卡号默认掩码） ==='
 timeout 8 ubus call luci.modem5g get_dashboard
 echo '=== 设备识别 ==='
 timeout 8 ubus call system board
} > "$report" 2>&1
printf '诊断已保存至 %s；无需为此再次重启。\n' "$report"
