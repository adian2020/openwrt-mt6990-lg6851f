#!/bin/sh
# Reproduce the observed v1.0.15 QoS stop on the current firmware.
set -eu
umask 077
legacy=/tmp/lg6851f-qos-legacy-test.sh
legacy_state=/tmp/lg6851f-qos-legacy-test
table=lg6851f_dscp_test
legacy_sha=d63e37747d591c2d6df98552cf44621bd1d3245368ff315bd48fbc8b36927aac
proxy=${1:-}

fail() { printf '%s\n' "$*" >&2; exit 1; }
case "$#:$proxy" in 0:|1:https://v6.gh-proxy.org/) ;; *) fail '参数仅支持之前使用的下载代理前缀。';; esac
[ "$(id -u)" = 0 ] || fail '请在路由器 SSH 使用 root 执行。'
[ "$(cat /tmp/sysinfo/board_name 2>/dev/null)" = fiberhome,lg6851f ] || fail '仅适用于 LG6851F。'
exec 8>/var/lock/lg6851f-replay-qos-stop.lock
flock -n 8 || fail '已在进行同一项测试。'
[ ! -e "$legacy_state/enabled" ] || fail '旧版 QoS 已在运行。请先用旧版工具 off，再开始这组对照。'
wan=$(ubus -S call network.interface.modem5g status | jsonfilter -e '@.l3_device')
[ "$wan" = ccmni2 ] || fail "实机蜂窝接口是 $wan，和历史记录的 ccmni2 不同，未进入测试。"

work=$(mktemp -d /tmp/lg6851f-replay-qos-stop.XXXXXX)
backup=$work/dscp.nft
cp -p /etc/config/lg6851f_fair_qos "$work/"
if [ -r /sys/fs/pstore/dmesg-ramoops-0 ]; then
    cp -p /sys/fs/pstore/dmesg-ramoops-0 "$work/"
fi
if [ ! -f "$legacy" ]; then
    wget -T 30 -O "$work/legacy-test.sh" "${proxy}https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/ed26974c86b5de4dd16347a0b7b2dcd54d968aaf/scripts/lg6851f-qos-legacy-test.sh"
    legacy=$work/legacy-test.sh
fi
[ "$(sha256sum "$legacy" | cut -d ' ' -f 1)" = "$legacy_sha" ] || fail '旧版对照工具的 SHA256 核对失败。'

table_present() { printf '%s\n' "$1" | grep -Fxq "table inet $table"; }
restore_table() {
    # An exclusive create prevents a concurrent table from acquiring duplicates.
    { printf 'create table inet %s\n' "$table"; cat "$backup"; } | nft -f -
}

paused=0
legacy_started=0
cleanup() {
    result=$?
    trap - EXIT
    if [ "$legacy_started" = 1 ] && ! sh "$legacy" off; then
        printf '旧版 QoS 清理未确认，请保留输出。\n' >&2
        result=1
    fi
    if [ "$paused" = 1 ]; then
        if restore_table; then
            printf '已恢复原来的临时 DSCP 表。\n'
        else
            printf '自动恢复失败。原表备份在 %s\n' "$backup" >&2
            result=1
        fi
    fi
    printf '对照记录目录 %s\n' "$work"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 129' HUP
trap 'exit 143' TERM

# The diagnostic table is separate from fw4. Save and validate before removing.
tables=$(nft list tables) || fail '无法读取 nft 表列表。'
if table_present "$tables"; then
    nft list table inet "$table" > "$backup"
    grep -Fxq "table inet $table {" "$backup" || fail '没有读到完整的临时 DSCP 表。'
    {
        printf 'delete table inet %s\ncreate table inet %s\n' "$table" "$table"
        cat "$backup"
    } | nft -c -f - || fail '临时 DSCP 表的恢复预检失败。'
    nft delete table inet "$table"
    paused=1
    printf '已保存并暂时移开后来添加的 DSCP 表。\n'
fi

printf '先短暂应用旧版队列，请等停用确认后再开始手机下载。\n'
legacy_started=1
if [ -n "$proxy" ]; then sh "$legacy" on "$proxy"; else sh "$legacy" on; fi
qdisc=$(tc qdisc show dev "$wan")
printf '%s\n' "$qdisc" | grep -Eq '^qdisc cake .* root ' || fail '未观察到旧版 CAKE 已应用。'
sh "$legacy" off
legacy_started=0

qdisc=$(tc qdisc show dev "$wan")
ingress=$(tc filter show dev "$wan" ingress)
printf '%s\n' "$qdisc" | tee "$work/qdisc-after-stop.txt"
printf '%s\n' "$qdisc" | grep -Eq '^qdisc fq_codel .* root ' || fail '关闭后未恢复历史记录中的 fq_codel。'
[ -z "$ingress" ] || fail "入口过滤器仍在，未进入测速。$ingress"
[ ! -e /sys/class/net/ifb-cellular ] || fail 'IFB 仍在，未进入测速。'
tables=$(nft list tables) || fail '无法确认当前 nft 规则。'
if table_present "$tables"; then fail '临时 DSCP 表再次出现，未进入测速。'; fi

snapshot() {
    read -r uptime idle < /proc/uptime
    read -r bytes < "/sys/class/net/$wan/statistics/rx_bytes"
    printf '%s %s\n' "$uptime" "$bytes"
}

printf '复现条件已确认。请在手机通过 5 GHz 下载当时的同一文件。接下来采样约 30 秒。\n'
snapshot > "$work/samples.txt"
for sample in 1 2 3 4 5 6; do
    sleep 5
    snapshot >> "$work/samples.txt"
    tail -n 2 "$work/samples.txt" | awk -v n="$sample" '
        NR == 1 {t=$1; bytes=$2; next}
        $1 > t && $2 >= bytes {printf "第 %d 段，%.2f 秒，蜂窝入口 %.1f Mbps\n", n, $1-t, ($2-bytes)*8/($1-t)/1000000; next}
        {print "采样无效，接口计数可能已重置。"}'
done
printf '采样结束。请贴回这 6 段数据和手机实际下载速度。\n'
