#!/bin/sh
# 一次性诊断，不安装服务、不设置射频/频段、不发送短信。
umask 077
mode="${1:-}"
case "$mode" in phone|bler) ;; *) echo '用法: sh 脚本 phone 或 bler'; exit 2;; esac
case "$(cat /tmp/sysinfo/board_name 2>/dev/null)" in fiberhome,lg6851f|fiberhome_lg6851f) ;; *) echo '仅适用于LG6851F';exit 95;; esac
[ "$(ubus call network.interface.modem5g status | jsonfilter -e '@.up')" = true ] || { echo '请先确保蜂窝已连接';exit 11; }
exec 9>/var/lock/luci-modem5g-control.lock
waited=0
until flock -n 9;do
 [ "$waited" -lt 60 ] || { echo '模组通道持续忙，未开始测试';exit 75; }
 [ "$waited" != 0 ] || echo '等待模组通道空闲（最多60秒）……'
 sleep 1;waited=$((waited+1))
done
if [ -e /tmp/lg6851f-modem-control.active ] || [ -d /var/lock/lg6851f-modem-recovery.lock ];then echo '模组控制或恢复正在执行，未开始测试';exit 75;fi
work="$(mktemp -d /tmp/lg6851f-probe.XXXXXX)" || exit 5
reader=''
registered=0
cleanup() {
 trap - EXIT INT TERM
 if [ -n "$reader" ];then
  printf '45\n0\n1\n-1\n' >&7 2>/dev/null
  # 只结束本测试的子进程，绝不结束其他模组进程。
  i=0
  while kill -0 "$reader" 2>/dev/null && [ "$i" -lt 6 ];do sleep 1;i=$((i+1));done
  kill "$reader" 2>/dev/null
  wait "$reader" 2>/dev/null
 fi
 if [ "$registered" = 1 ];then
  echo '测试被中断或超时，补发注销……'
  sleep 6
  printf '0\n45\n0\n1\n-1\n' | timeout -k 5 20 /usr/bin/sample_nw
  echo '请保留以上注销返回结果；失败时不要反复运行测试。'
 fi
 sleep 6
 flock -u 9
 rm -f "$work/input" "$work/report" "$work/phone.uc"
 rmdir "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$mode" = phone ];then
 cat > "$work/phone.uc" <<'UCODE'
'use strict';
import { connect, error } from 'ubus';
// 已核对ql_sim_get_phone_num: 请求0xB02，载荷为SIM槽标识0xB01。
// SDK以83字节缓冲区接收号码；这里只发出这一项读取请求。
let b=connect('/var/run/ubus/ubus.sock',8);
if(!b){printf('%J\n',{status:'UBUS_CONNECT_FAILED',error:error()});exit(5);}
// ubus STRING会补末尾NUL，3字节加该NUL正好构成01 0b 00 00。
let r=b.call('ril','ril_request',{id:0xb02,data_len:4,data:chr(1)+chr(11)+chr(0)});
let report={request_id:0xb02,slot:0xb01,response_id:r?.id,result:r?.result,data_len:r?.data_len};
if(!r){report.status='SDK_REQUEST_FAILED';report.error=error();}
else if(r.id!=0xb02 || r.result!=0 || r.data_len!=83 || type(r.data)!='string' || index([82,83],length(r.data))<0)report.status='SDK_RESPONSE_NOT_CONFIRMED';
else {
 let candidate=trim(split(r.data,chr(0))[0]);
 report.status=!candidate?'NUMBER_NOT_PROVIDED':match(candidate,/^\+?[0-9]{3,20}$/)?'NUMBER_RETURNED':'NUMBER_FORMAT_UNCONFIRMED';
 if(report.status=='NUMBER_RETURNED')report.phone=candidate;
}
printf('%J\n',report);
UCODE
 timeout -k 3 15 ucode "$work/phone.uc"
 exit "$?"
fi
[ -x /usr/bin/sample_nw ] || { echo '缺少sample_nw，未注册回调';exit 2; }
mkfifo "$work/input" || exit 5
exec 7<>"$work/input"
timeout -k 5 45 /usr/bin/sample_nw <"$work/input" >"$work/report" 2>&1 &
reader=$!
registered=1
printf '0\n45\n1\n' >&7
sleep 20
printf '45\n0\n1\n-1\n' >&7
wait "$reader"
rc=$?
reader=''
[ "$rc" != 0 ] || registered=0
cat "$work/report"
echo "测试进程退出码=$rc；正常流程已发送NR回调注销、SDK释放和退出。"
exit "$rc"
