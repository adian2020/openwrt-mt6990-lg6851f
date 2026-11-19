#!/bin/sh
# Disposable comparison with the pre-safety-default QoS implementation.
# Original programs and committed UCI configuration are never replaced.
set -eu
umask 077
work=/tmp/lg6851f-qos-legacy-test
state=/var/run/lg6851f-fair-qos.state
stopped=/var/run/lg6851f-fair-qos.stopped
service=/etc/init.d/lg6851f_fair_qos
program=/usr/sbin/lg6851f-fair-qos
hook=/etc/hotplug.d/iface/95-lg6851f-fair-qos
legacy_sha=3f8c535dbc2a28909955181232c3c06041959b5b7e69718660856e937a8c5496
die() { echo "$*" >&2; exit 75; }
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
device_ok() { [ -n "$1" ] && [ "${#1}" -le 15 ] && case "$1" in *[!A-Za-z0-9_.:@-]*) false;; *) true;; esac; }
wan() {
 local value
 value=$(ubus -S call network.interface.modem5g status | jsonfilter -e '@.l3_device') || return 1
 device_ok "$value" && [ -d "/sys/class/net/$value" ] || return 1
 printf '%s\n' "$value"
}
guard() {
 [ "$(id -u)" = 0 ] || die '请使用root执行'
 [ "$(cat /tmp/sysinfo/board_name 2>/dev/null)" = fiberhome,lg6851f ] || die '设备不匹配'
 case "$(uname -r)" in 6.18.*) ;; *) die '仅支持本项目6.18固件';; esac
 [ ! -e /tmp/sysupgrade ] && [ ! -e /tmp/lg6851f-bootctrl.lock ] || die '存在升级或槽位操作，未测试'
 [ "$(hash "$program")" = ddc2efc299fc921e486f187b2c7c10eb210c705361e14d92a26f26842db480ef ] || die '现有QoS程序已变化，未覆盖'
 [ "$(hash "$service")" = 4af6d476a18410cf734b519375e3ce38fac388d77835d096bba7901fc68f9468 ] || die '现有QoS服务已变化'
 [ "$(hash "$hook")" = a3495ba77489f2b527caf8414503d17811d3e6778bb5f4b1a711970baae64763 ] || die '现有接口事件脚本已变化'
 [ "$(uci -q get lg6851f_fair_qos.main.enabled)" = 0 ] || die '请先在页面关闭当前QoS，再运行旧版测试'
 [ -z "$(uci -q changes lg6851f_fair_qos)" ] || die 'QoS存在未保存改动，请先处理'
 [ "$(uci -q get lg6851f_fair_qos.main.network_interface)" = modem5g ] || die '网络接口配置不匹配'
 [ "$(uci -q get lg6851f_fair_qos.main.ifb_device)" = ifb-cellular ] || die 'IFB配置不匹配'
}
legacy_ok() {
 [ -d "$work" ] && [ ! -L "$work" ] || die '尚未准备旧版测试'
 [ "$(cat "$work/boot-id")" = "$(cat /proc/sys/kernel/random/boot_id)" ] || die '启动身份已经变化'
 [ "$(hash "$work/legacy.sh")" = "$legacy_sha" ] || die '旧版脚本指纹不匹配'
}
# The old cleanup removes an entire clsact/root. Refuse unrelated TC owners.
queue_guard() {
 local dev="$1" owned="$2" q ingress egress prefs
 device_ok "$dev" || return 1
 [ -d "/sys/class/net/$dev" ] || return 0
 q=$(tc qdisc show dev "$dev") || return 1
 if printf '%s\n' "$q" | grep ' root ' | grep -Ev '^qdisc (fq_codel|fq|noqueue|pfifo_fast|mq) ' >/dev/null; then
  [ "$owned" = 1 ] && ! printf '%s\n' "$q" | grep ' root ' | grep -Ev '^qdisc cake ' >/dev/null || return 1
 fi
 ingress=$(tc filter show dev "$dev" ingress) || return 1
 egress=$(tc filter show dev "$dev" egress) || return 1
 [ -z "$egress" ] || return 1
 if [ -n "$ingress" ]; then
  [ "$owned" = 1 ] && printf '%s\n' "$ingress" | grep -Fq 'device ifb-cellular' || return 1
  prefs=$(printf '%s\n' "$ingress" | sed -n 's/.*pref \([0-9][0-9]*\).*/\1/p')
  [ -n "$prefs" ] && [ -z "$(printf '%s\n' "$prefs" | grep -v '^10$')" ] || return 1
 fi
}
ownership() {
 # A modern three-line state means another controller has taken over.
 if [ -e "$state" ]; then
  [ "$(wc -l < "$state" | tr -d ' ')" = 1 ] || return 1
  device_ok "$(cat "$state")" || return 1
 fi
}
tick() {
 guard; legacy_ok
 exec 9>/var/lock/lg6851f-fair-qos.lock
 flock 9
 [ -e "$work/enabled" ] && [ -e "$stopped" ] || return 76
 ownership || return 76
 if [ -e "$work/armed" ] && [ ! -e "$state" ]; then return 76; fi
 local current old owned=0
 current=$(wan) || return 2
 if [ -f "$work/attempted" ]; then owned=1; fi
 old=$(cat "$state" 2>/dev/null || :)
 queue_guard "$current" "$owned" || die '发现其他TC规则，旧版测试暂停'
 [ -z "$old" ] || queue_guard "$old" 1 || die '旧接口存在其他TC规则，未覆盖'
 printf '%s\n' "$current" > "$work/attempted"
 UCI_CONFIG_DIR="$work/config" sh "$work/legacy.sh" start
 [ -s "$state" ] || return 1
 touch "$work/armed"
}
off() {
 legacy_ok
 rm -f "$work/enabled"
 # Kill the periodic worker BEFORE the final cleanup; no automatic respawn.
 /bin/sh /etc/rc.common "$work/lg6851f-qos-legacy-test" stop || echo '未确认服务删除；已先禁止周期重配，继续串行清理。'
 exec 9>/var/lock/lg6851f-fair-qos.lock
 flock 9
 ownership || die '规则已由其他控制器接管，未清理其规则'
 local current old
 current=$(wan) || current=
 old=$(cat "$state" 2>/dev/null || :)
 [ -z "$current" ] || queue_guard "$current" 1 || die '当前接口存在其他TC规则，未删除'
 [ -z "$old" ] || queue_guard "$old" 1 || die '旧接口存在其他TC规则，未删除'
 if [ -f "$work/attempted" ]; then
  UCI_CONFIG_DIR="$work/config" sh "$work/legacy.sh" stop
 fi
 [ ! -e "$state" ] || die '旧版状态仍存在，未宣称清理完成'
 if ip link show dev ifb-cellular >/dev/null 2>&1; then die 'IFB仍存在，需核查'; fi
 rm -f "$work/armed" "$work/attempted"
 echo '旧版QoS已关闭并停止周期任务，可对照测速；没有修改持久配置。'
}
status() {
 if [ -e "$work/enabled" ]; then echo '临时旧版QoS：已请求开启（以以下实际队列为准）'; else echo '临时旧版QoS：未请求周期运行（是否清理以以下实际队列为准）'; fi
 local dev
 dev=$(wan) || dev=
 if [ -n "$dev" ]; then echo "=== $dev ==="; tc -s qdisc show dev "$dev"; tc filter show dev "$dev" ingress; fi
 if ip link show dev ifb-cellular >/dev/null 2>&1; then tc -s qdisc show dev ifb-cellular; fi
}
action=${1:-help}
case "$action" in
 status) status; exit;;
 _run)
  while [ -e "$work/enabled" ]; do
   rc=0; sh "$work/control.sh" _tick >> "$work/test.log" 2>&1 || rc=$?
   case "$rc" in 0) sleep 30;; 1|2) sleep 3;; *) rm -f "$work/enabled"; exit "$rc";; esac
  done
  exit;;
 _tick) tick; exit;;
 on|off|restore) guard;;
 *) echo "用法：sh $0 on [https://v6.gh-proxy.org/] | off | restore | status"; exit 22;;
esac
exec 8>/var/lock/lg6851f-qos-legacy-test.lock
flock -n 8 || die '另一个旧版测试操作正在执行'
if [ "$action" = off ]; then off; exit; fi
if [ "$action" = restore ]; then
 off
 # Release the TC lock before invoking the current controller.
 flock -u 9
 if [ ! -e "$work/previously-stopped" ]; then /bin/sh /etc/rc.common "$service" start; fi
 rm -rf "$work"
 echo '已退出测试；当前正式QoS仍保持关闭。重启也会自动退出临时测试。'
 exit
fi
prefix=${2:-}
case "$#:$prefix" in 1:|2:https://v6.gh-proxy.org/) ;; *) die '仅支持可选的既有代理前缀';; esac
if [ ! -d "$work" ]; then
 mkdir -m 700 "$work"; mkdir "$work/config" "$work/delta"
 cat /proc/sys/kernel/random/boot_id > "$work/boot-id"
 cp "$0" "$work/control.sh"
 wget -T 30 -O "$work/legacy.sh" "${prefix}https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/78a0547bc38311f6cfb48d707c1203534d1d5ea7/target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-fair-qos"
 legacy_ok; sh -n "$work/legacy.sh"
 cp /etc/config/lg6851f_fair_qos "$work/config/lg6851f_fair_qos"
 uci -c "$work/config" -t "$work/delta" set lg6851f_fair_qos.main.enabled=1
 uci -c "$work/config" -t "$work/delta" commit lg6851f_fair_qos
 [ -e "$stopped" ] && touch "$work/previously-stopped" || :
 backup=$(mktemp -d /root/lg6851f-qos-before-test.XXXXXX)
 mkdir "$backup/program" "$backup/service" "$backup/hotplug" "$backup/config"
 cp -p "$program" "$backup/program/"
 cp -p "$service" "$backup/service/"
 cp -p "$hook" "$backup/hotplug/"
 cp -p /etc/config/lg6851f_fair_qos "$backup/config/"
 printf '%s\n' "$backup" > "$work/backup"
 cat > "$work/lg6851f-qos-legacy-test" <<'EOF'
#!/bin/sh /etc/rc.common
USE_PROCD=1
start_service() {
 procd_open_instance
 procd_set_param command /bin/sh /tmp/lg6851f-qos-legacy-test/control.sh _run
 procd_set_param term_timeout 10
 procd_set_param stdout 1
 procd_set_param stderr 1
 procd_close_instance
}
stop_service() { :; }
EOF
 touch "$work/ready"
fi
legacy_ok
[ -f "$work/ready" ] || die '上次准备未完成，未操作网络；请保留临时目录供核查'
[ ! -e "$work/enabled" ] || { echo '临时测试已经开启；请使用status查看，不重复配置。'; exit 0; }
/bin/sh /etc/rc.common "$service" stop
[ ! -e "$state" ] || die '当前QoS未清理完成，未启动旧版'
if ip link show dev ifb-cellular >/dev/null 2>&1; then die 'IFB仍被占用，未启动旧版'; fi
rm -f "$work/armed" "$work/attempted"
touch "$work/enabled"
if ! sh "$work/control.sh" _tick; then
 rm -f "$work/enabled"
 off || :
 die "旧版首次应用失败，日志：$work/test.log；请先核查再测速"
fi
/bin/sh /etc/rc.common "$work/lg6851f-qos-legacy-test" start
echo '已临时开启旧版QoS，恢复旧版30秒/失败3秒的重试节奏（冲突时停止）。'
echo '测试期间不要操作网页QoS开关，请用本脚本on/off；网页仍显示正式配置的关闭状态。'
echo "备份：$(cat "$work/backup")；日志：$work/test.log"
status
