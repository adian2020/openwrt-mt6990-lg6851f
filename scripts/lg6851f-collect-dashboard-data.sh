#!/bin/sh
# 手动运行的只读采集：不打开 AT/MIPC 通道，不切换射频，不操作锁频。
# 不读取 Wi-Fi 密码、APN 密码或完整 SIM 身份号码。
if [ "${1:-}" = --help ]; then
	echo '用法：sh lg6851f-collect-dashboard-data.sh > /tmp/mt6990-dashboard-data.txt'
	exit 0
fi
board="$(cat /tmp/sysinfo/board_name 2>/dev/null)"
case "$board" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '仅适用于 LG6851F/MT6990；未采集。' >&2; exit 1 ;; esac

section() { printf '\n===== %s =====\n' "$1"; }
read_value() { [ ! -r "$1" ] || { printf '%s=' "$1"; cat "$1"; }; }
mask_id() { awk 'length($0)>6 { print substr($0,1,3) "***" substr($0,length($0)-2); next } { print "未获取" }'; }

section '固件与运行时间'
date -u
ubus call system board 2>/dev/null
cat /proc/uptime
cat /etc/mt6990-firmware-id 2>/dev/null
section '蜂窝状态缓存（不新增模组查询）'
state=/tmp/lg6851f-modem-status.state
if [ -r "$state" ]; then
	grep -E '^(UPDATED|UP|UPTIME|WAN|IPV4|SIM|REGISTRATION|REGISTERED|RAT|RAT_RAW|SIGNAL|RSRP|RADIO|OPERATOR|CESQ|RSSI|RSRQ|SINR)=' "$state"
	for key in IMEI IMSI ICCID; do
		printf '%s=' "$key"
		sed -n "s/^$key=//p" "$state" | head -n 1 | mask_id
	done
else
	echo '状态缓存不存在'
fi
section '蜂窝网络、IP、DNS、APN与连接时长'
net="$(ubus call network.interface.modem5g status 2>/dev/null)"
printf '%s\n' "$net"
printf 'APN='; uci -q get network.modem5g.apn
printf 'RADIO_ENABLED='; uci -q get network.modem5g.radio_enabled
wan="$(printf '%s' "$net" | jsonfilter -e '@.l3_device' 2>/dev/null)"
case "$wan" in ''|*[!a-zA-Z0-9_.:-]*) wan= ;; esac
section '接口流量与CPU利用率（间隔1秒采样）'
first_cpu="$(head -n 1 /proc/stat)"
rx0=; tx0=
[ -z "$wan" ] || {
	rx0="$(cat "/sys/class/net/$wan/statistics/rx_bytes" 2>/dev/null)"
	tx0="$(cat "/sys/class/net/$wan/statistics/tx_bytes" 2>/dev/null)"
}
sleep 1
second_cpu="$(head -n 1 /proc/stat)"
printf '%s\n%s\n' "$first_cpu" "$second_cpu" | awk '
{ total=0; for(i=2;i<=9 && i<=NF;i++) total+=$i; idle=$5+$6 }
NR==1 { t0=total; i0=idle; next }
NR==2 && total>t0 { printf "CPU_BUSY_PERCENT=%.2f\n",100*((total-t0)-(idle-i0))/(total-t0) }
'
if [ -n "$wan" ]; then
	rx1="$(cat "/sys/class/net/$wan/statistics/rx_bytes" 2>/dev/null)"
	tx1="$(cat "/sys/class/net/$wan/statistics/tx_bytes" 2>/dev/null)"
	printf 'TRAFFIC_DEVICE=%s\nRX_BYTES=%s\nTX_BYTES=%s\n' "$wan" "$rx1" "$tx1"
	printf '%s %s %s %s\n' "$rx0" "$rx1" "$tx0" "$tx1" | awk 'NF==4 && $2>=$1 && $4>=$3 { printf "RX_BYTES_PER_APPROX_SECOND=%.0f\nTX_BYTES_PER_APPROX_SECOND=%.0f\n",$2-$1,$4-$3 }'
fi
section '内存与实际可写存储'
grep -E '^(MemTotal|MemAvailable|MemFree|Buffers|Cached):' /proc/meminfo
df -k /overlay /mnt/mt6990-data 2>/dev/null
section 'CPU频率（sysfs通常为kHz）'
for dir in /sys/devices/system/cpu/cpufreq/policy*; do
	[ -d "$dir" ] || continue
	for name in scaling_cur_freq scaling_max_freq cpuinfo_max_freq; do read_value "$dir/$name"; done
done
section '温度传感器名称与原始读数'
for dir in /sys/class/thermal/thermal_zone*; do
	[ -d "$dir" ] || continue
	read_value "$dir/type"; read_value "$dir/temp"
done
for dir in /sys/class/hwmon/hwmon*; do
	[ -d "$dir" ] || continue
	read_value "$dir/name"
	for file in "$dir"/temp*_input "$dir"/temp*_label; do read_value "$file"; done
done
section '连接跟踪总数（不是PPE硬件绑定数）'
read_value /proc/sys/net/netfilter/nf_conntrack_count
read_value /proc/sys/net/netfilter/nf_conntrack_max
section 'PPE接口是否存在（不读取会遍历条目/清计数的调试节点）'
ls -ld /proc/hnat /proc/hnat/* /sys/kernel/debug/mtk_ppe* 2>/dev/null
section 'Wi-Fi状态和关联客户端'
ubus call network.wireless status 2>/dev/null | jsonfilter -e '@.*.up' -e '@.*.interfaces[*].ifname' 2>/dev/null
for dir in /sys/class/net/*; do
	[ -d "$dir/phy80211" ] || [ -d "$dir/wireless" ] || continue
	dev="${dir##*/}"
	iw dev "$dev" info 2>/dev/null
	iw dev "$dev" station dump 2>/dev/null
done
section '无线配置白名单（不读取key等密码选项）'
uci -q show wireless | sed -n '/=wifi-device$/p; /=wifi-iface$/p; /\.ssid=/p; /\.device=/p; /\.channel=/p; /\.country=/p; /\.txpower=/p; /\.encryption=/p; /\.hidden=/p'
section 'LAN地址与DHCP租约'
ubus call network.interface.lan status 2>/dev/null
[ ! -r /tmp/dhcp.leases ] || cat /tmp/dhcp.leases
section '只列出固件版本信息文件位置，未猜测模组固件值'
ls -l /etc/quectel-project-version /tmp/imei /etc/modem5g-lock.state 2>/dev/null
printf '\n采集结束。CA/MCS/AMBR/QCI等未验证字段未填入示例值。\n'
