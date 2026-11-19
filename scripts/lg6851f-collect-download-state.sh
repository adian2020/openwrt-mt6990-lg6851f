#!/bin/sh
# Passive download diagnosis: writes only a private /tmp report. Never runs AT,
# steering scripts, traffic generators, service controls or configuration writes.
umask 077
seconds=${1:-10}
case "$seconds" in 0|10|20) ;; *) echo '用法：sh lg6851f-collect-download-state.sh [0|10|20]'; exit 2 ;; esac
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in
 fiberhome,lg6851f|fiberhome_lg6851f) ;;
 *) echo '仅适用于 LG6851F；未执行采集。'; exit 95 ;;
esac
command -v timeout >/dev/null 2>&1 || { echo '缺少 timeout；未执行采集。'; exit 2; }
report=$(mktemp /tmp/lg6851f-download-state.XXXXXX) || exit 5

bounded()
{
 command -v "$1" >/dev/null 2>&1 || { printf '不可用：%s\n' "$1"; return 0; }
 timeout 8 "$@"
 rc=$?
 [ "$rc" = 0 ] || printf '查询退出码=%s\n' "$rc"
}

# Whitelist individual UCI option names, including for old upper/ archives.
# Do not export whole network/wireless configurations (passwords and keys).
config_fields()
{
 [ -r "$1" ] && [ ! -L "$1" ] || return 0
 printf '\n--- %s ---\n' "$1"
 awk '
  $1 == "config" { print; next }
  $1 == "option" || $1 == "list" {
   key=$2; gsub(/[\047\042]/, "", key)
   if (key ~ /^(proto|device|ifname|apn|pdptype|mtu|packet_steering|steering_flows|flow_offloading|flow_offloading_hw|band|hwmode|channel|htmode|country|txpower|encryption|wmm|disabled|enabled|max_hosts|overhead|diffserv|seed_bandwidth|safety_migration)$/) print
  }' "$1"
}

irq_affinity()
{
 for linux_irq in $1; do
  irq_proc="/proc/irq/$linux_irq"
  irq_sys="/sys/kernel/irq/$linux_irq"
  printf '\nIRQ %s\n' "$linux_irq"
  for path in "$irq_sys"/actions "$irq_sys"/chip_name "$irq_sys"/hwirq \
      "$irq_sys"/per_cpu_count "$irq_proc"/smp_affinity "$irq_proc"/effective_affinity; do
   printf '%s=' "${path##*/}"
   if [ -r "$path" ]; then cat "$path"; else echo '未提供'; fi
  done
 done
}

sample()
{
 printf '\n=== 流量/CPU采样 %s ===\n' "$1"
 cat /proc/uptime
 grep '^cpu' /proc/stat
 cat /proc/net/softnet_stat
 for netpath in /sys/class/net/*; do
  interface=${netpath##*/}
  case "$interface" in ccmni[012]|eth[01]|phy*-ap*) ;; *) continue ;; esac
  printf '\ninterface=%s\n' "$interface"
  for key in rx_bytes tx_bytes rx_packets tx_packets rx_dropped tx_dropped rx_errors tx_errors; do
   printf '%s=' "$key"; cat "/sys/class/net/$interface/statistics/$key" 2>/dev/null
  done
 done
 # Interface discovery only, no scan, connect, disconnect or radio commands.
 if command -v iw >/dev/null 2>&1; then
  for interface in $(timeout 8 iw dev 2>/dev/null | awk '$1 == "Interface" {print $2}'); do
   printf '\n--- station dump %s ---\n' "$interface"
   bounded iw dev "$interface" station dump
  done
 fi
 echo '--- 本次采样的中断和 DSCP 计数 ---'
 awk '/DPMAIF_AP|MED_RX_IRQ|CCIF_AP_DATA|mt7996e|GICv3[[:space:]]+(310|320)[[:space:]]/' /proc/interrupts
 for linux_irq in $pcie_parent_irqs; do
  path="/sys/kernel/irq/$linux_irq/per_cpu_count"
  [ -r "$path" ] || continue
  printf 'PCIe parent IRQ %s per_cpu_count=' "$linux_irq"; cat "$path"
 done
 bounded nft list table inet lg6851f_dscp_test
}

echo "请保持当前 QoS/DSCP 状态，在原来的互联网测速或下载过程中运行。采集仅写 /tmp，间隔 ${seconds} 秒；不进行局域网测速。报告：$report"
{
 echo 'collector_version=2'
 echo '=== 固件身份（源码HEAD不能代替实际固件身份） ==='
 date -u
 uname -a
 cat /etc/mt6990-firmware-id /rom/etc/mt6990-firmware-id /proc/sys/kernel/random/boot_id /proc/uptime 2>/dev/null
 echo '=== 已安装主要网络包版本 ==='
 bounded apk list --installed |
  awk '/^(kernel|kmod-(mt76[^ ]*|mt79[^ ]*|mac80211|cfg80211|ifb|sched|mt6990-hwnat)|netifd|firewall4|nftables|hostapd|wpad|wifi-scripts|lg6851f-modem-chain-only|ucode|libubus)[ -]/ {print}'
 echo '=== 当前网络配置白名单（不含口令） ==='
 for config in network wireless firewall lg6851f_fair_qos; do
  config_fields "/etc/config/$config"
 done
 echo '=== WAN当前状态（不输出地址、DNS或模组身份） ==='
 for interface in modem5g wan wan6; do
  printf '\ninterface=%s\n' "$interface"
  timeout 8 ubus call "network.interface.$interface" status 2>/dev/null |
   jsonfilter -e '@.up' -e '@.pending' -e '@.uptime' -e '@.l3_device' -e '@.proto' 2>/dev/null
 done
 echo '=== 当前TC队列和重定向 ==='
 for interface in ccmni0 ccmni1 ccmni2 ifb-cellular; do
  [ -d "/sys/class/net/$interface" ] || continue
  printf '\n--- %s ---\n' "$interface"
  bounded ip link show dev "$interface"
  bounded tc -s qdisc show dev "$interface"
  bounded tc filter show dev "$interface" ingress
 done
 echo '=== 临时DSCP表及其他相关规则（仅筛选相关行） ==='
 bounded nft list table inet lg6851f_dscp_test
 timeout 8 nft list ruleset 2>/dev/null |
  awk '/^table / || /chain / || /hook / || /dscp|flowtable|flow (add|offload)|tproxy|redirect|limit rate|tcp option maxseg/ { if (++n <= 180) print }'
 echo '=== 标准GRO/RPS/IRQ状态（不读取调试寄存器） ==='
 for path in /proc/sys/net/core/default_qdisc /proc/sys/net/core/rps_sock_flow_entries /sys/module/ccmni/parameters/ccmni_gro; do
  [ -r "$path" ] || continue
  printf '%s=' "$path"; cat "$path"
 done
 for interface in ccmni0 ccmni1 ccmni2 eth0 eth1; do
  [ -d "/sys/class/net/$interface" ] || continue
  for path in /sys/class/net/"$interface"/gro_flush_timeout /sys/class/net/"$interface"/queues/rx-*/rps_cpus /sys/class/net/"$interface"/queues/rx-*/rps_flow_cnt; do
   [ -r "$path" ] || continue
   printf '%s=' "$path"; cat "$path"
  done
  bounded ethtool -k "$interface"
 done
 cat /proc/interrupts
 pcie_parent_irqs=$(
  # A chained PCIe parent may not appear in /proc/interrupts. These GIC
  # hardware IRQs come from the LG6851F device tree (SPI number + 32).
  for path in /sys/kernel/irq/*/hwirq; do
   [ -r "$path" ] || continue
   case "$(cat "$path")" in 310|320) ;; *) continue ;; esac
   irq_dir=${path%/hwirq}
   [ "$(cat "$irq_dir/chip_name" 2>/dev/null)" = GICv3 ] || continue
   printf '%s\n' "${irq_dir##*/}"
  done
 )
 irq_ids=$(
  awk '/DPMAIF_AP|MED_RX_IRQ|CCIF_AP_DATA|mt7996e|15100000\.ethernet/ {
   if ($1 ~ /^[0-9]+:$/) {sub(/:$/, "", $1); print $1}
  }' /proc/interrupts
  printf '%s\n' "$pcie_parent_irqs"
 )
 irq_affinity "$(printf '%s\n' "$irq_ids" | sort -un)"
 echo '=== 网络脚本与ROM指纹（只计算，不执行脚本） ==='
 for path in /usr/sbin/lg6851f-net-affinity /usr/libexec/platform/packet-steering.sh /etc/init.d/packet_steering /usr/sbin/lg6851f-fair-qos /etc/init.d/lg6851f_fair_qos /etc/hotplug.d/iface/95-lg6851f-fair-qos /usr/bin/lg6851f-cellular-refresh /usr/bin/lg6851f-modem-status /usr/libexec/lg6851f-sms-pool.uc; do
  [ ! -f "$path" ] || sha256sum "$path"
  [ ! -f "/rom$path" ] || sha256sum "/rom$path"
 done
 echo '=== 相关服务实际运行状态（不输出命令行或短信正文） ==='
 for service in lg6851f-sms-pool lg6851f-cellular-refresh lg6851f-sms-forward lg6851f_fair_qos openclash; do
  printf '\nservice=%s\n' "$service"
  timeout 8 ubus call service list "{\"name\":\"$service\"}" 2>/dev/null |
   jsonfilter -e '@.*.instances.*.running' -e '@.*.instances.*.pid' 2>/dev/null
 done
 printf 'OpenClash配置启用='; uci -q get openclash.config.enable
 if [ -r /tmp/lg6851f-sms-current-job.json ]; then
  echo '短信任务仅取类型和状态：'
  jsonfilter -i /tmp/lg6851f-sms-current-job.json -e '@.kind' -e '@.running' -e '@.done'
 fi
 echo '=== 已挂载P46的旧网络配置归档（不据目录时间判定旧固件版本） ==='
 if [ "$(cat /sys/class/block/mmcblk0p46/partition 2>/dev/null)" = 46 ] &&
    [ "$(cat /sys/class/block/mmcblk0p46/size 2>/dev/null)" = 5187456 ] &&
    grep -qx 'PARTNAME=user_data' /sys/class/block/mmcblk0p46/uevent 2>/dev/null; then
  p46id=$(cat /sys/class/block/mmcblk0p46/dev)
  p46=$(awk -v id="$p46id" '$3==id && $4=="/" {print $5; exit}' /proc/self/mountinfo)
  case "$p46" in
   ''|*\\*) echo '没有可直接读取的P46挂载路径；不主动挂载。' ;;
   *)
    printf 'P46=%s\n' "$p46"
    count=0
    for archive in "$p46"/openwrt-extroot-backups/upgrade-*; do
     [ -d "$archive/upper/etc/config" ] && [ ! -L "$archive" ] || continue
     count=$((count+1)); [ "$count" -le 8 ] || { echo '归档超过8份，其余未读。'; break; }
     for config in network wireless firewall lg6851f_fair_qos; do
      config_fields "$archive/upper/etc/config/$config"
     done
    done
    [ "$count" != 0 ] || echo '没有找到归档。'
   ;;
  esac
 else echo 'P46身份未核实，不读取归档。'; fi
 sample start
 [ "$seconds" = 0 ] || sleep "$seconds"
 sample end
 echo '=== 完成；规则、服务、模组和配置均未修改 ==='
} >"$report" 2>&1
printf '报告已保存：%s\n报告含设备MAC和所选规则信息，请仅用于排查。\n' "$report"
