#!/bin/sh
# 只读取状态，在 /tmp 写诊断结果；不重启、不重拨、不修改配置。
umask 077
report=/tmp/lg6851f-boot-dashboard.txt
{
 echo '=== 固件与运行时间 ==='
 cat /etc/mt6990-firmware-id /proc/uptime 2>/dev/null
 uptime
 echo '=== 无线启动日志 ==='
 logread 2>/dev/null | grep -Ei 'lg6851f-wifi|netifd.*Wireless|hostapd|phy[0-9]|procd.*(stop|timeout)' | tail -160
 echo '=== 驱动启动时间 ==='
 dmesg 2>/dev/null | grep -Ei 'mt799|mt76|firmware|wlan|ccci|watchdog' | tail -90
 echo '=== 服务启动项 ==='
 ls -l /etc/rc.d/*wifi* /etc/rc.d/*modem* /etc/rc.d/*mihomo* 2>/dev/null
 echo '=== 当前看板缓存（卡号默认掩码） ==='
 timeout 8 ubus call luci.modem5g get_dashboard
 echo '=== 设备识别 ==='
 timeout 8 ubus call system board
} > "$report" 2>&1
printf '诊断已保存至 %s；无需为此再次重启。\n' "$report"
