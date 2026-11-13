#!/bin/sh
# One-shot read-only probe: no radio settings, subscriptions or service changes.
set -u
umask 077
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in
 fiberhome,lg6851f|fiberhome_lg6851f) ;;
 *) echo '仅适用于LG6851F';exit 95;;
esac
[ -x /usr/bin/mipc_wan_cli ] && [ -x /usr/bin/modem5g-at ] || { echo '缺少模组查询工具';exit 2; }
exec 9>/var/lock/luci-modem5g-control.lock
waited=0
echo '等待模组通道空闲，最多60秒；不会停止后台服务。'
until flock -n 9; do
 [ "$waited" -lt 60 ] || { echo '模组通道持续忙，未执行MIPC查询；请保留当前状态，不要删锁文件或杀后台进程。';exit 75; }
 sleep 1;waited=$((waited+1))
done
# Keep ownership through the measured vendor close latency, even on interruption.
cleanup(){ sleep 6;flock -u 9; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -e /tmp/lg6851f-modem-control.active ] || [ -d /var/lock/lg6851f-modem-recovery.lock ];then
 echo '已有模组控制或恢复任务，未执行查询。';exit 75
fi
report="$(mktemp /tmp/lg6851f-mode-ims-readonly.XXXXXX)" || exit 5
echo "开始三个只读MIPC查询；每条最多15秒加6秒冷却。报告：$report"
{
 for opt in nw_get_rat ims_get_config ims_get_status; do
  printf '\n=== MIPC %s ===\n' "$opt"
  timeout -k 3 12 /usr/bin/mipc_wan_cli "--$opt"
  rc=$?;printf '退出码=%s\n' "$rc"
  sleep 6
 done
} >"$report" 2>&1
flock -u 9
trap - EXIT
# modem5g-at serializes its separate atcid channel; no MIPC lock is held here.
{
 while IFS= read -r command; do
  printf '\n=== %s ===\n' "$command"
  timeout -k 3 12 /usr/bin/modem5g-at "$command"
  rc=$?;printf '退出码=%s\n' "$rc"
 done <<'AT_COMMANDS'
AT+QCFG=?
AT+QCFG="ims"
AT+QCAINFO
AT+QNWCFG="nr5g_cainfo"
AT_COMMANDS
} >>"$report" 2>&1
cat "$report"
printf '\n完整只读报告：%s\n' "$report"
