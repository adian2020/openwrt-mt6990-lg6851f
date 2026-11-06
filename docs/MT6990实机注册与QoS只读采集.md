# MT6990 实机注册与 QoS 只读采集

## 已收到的注册结果

用户已在联网状态读回：CEREG=0,0、C5GREG=0,1，CSCON 仅返回 OK。
CEREG/C5GREG 第一个 0 是上报模式，第二个值才是注册状态。因此采样时
EPS 未注册、5GS 已注册；结合此前 NR 主载波与正常数据连接，支持当时为 5G SA。
CSCON 没有参数，不用空的 OK 推断核心网或信令状态。

后续只读采集已实机确认 sample_nw 第 7 项：初始化、查询、释放返回码均为零，
tech_domain=3GPP、radio_tech=QL_NW_RADIO_TECH_NR5G、
reg_state=QL_NW_SERVICE_FULL。当前数据注册接口直接确认采样时为 SA，
并与前述 AT 注册结果一致；NSA 分支仍缺实机样本。

该结论是一次实机观测，不能写成固件常量。已有面板继续动态读取厂商当前
数据注册 getter，注册失效或样本过期时不显示为当前 SA/NSA。

## QCI/5QI 接口核对

用户确认 ql-netd 只暴露 datacall(id:Integer,data:String,len:Integer)。这个接口
封装的是二进制消息，不能把 id 误当成活动 CID，也不能用任意猜测命令。
本轮离线核对仓库原有 libqlnet.so 与 ql_netd，未修改厂商程序：

| getter | 请求 id | 输入 | 主要返回 |
|---|---:|---|---|
| ql_data_call_get_list | 8 | 4 字节零值 | 数量及每项 36 字节的 SDK call_id/名称 |
| ql_data_call_get_apn | 12 | 4 字节小端 call_id | 有效标志及 APN |
| ql_data_call_get_qos_info | 13 | 4 字节小端 call_id | 24 字节等级及两项 64 位带宽字段 |

请求字段是 id/len/data；返回字段不同，是 cmd/result/data_len/data。
请求 13 对应 libqlnet.so 的 0xb29c getter。ql_makeblobdata 位于 0x7f78，
把输入以 BLOBMSG_TYPE_STRING、原始长度 4 发送。ql_netd 的 getter 先查 SDK
上下文和连接状态，然后按当前 RAT 选择 EPS QoS 或 5G QoS 路径；它不是设置操作。

默认网络实际由 mipc_wan_cli 拨号；其 MD CID 与 SDK call_id 不能未经匹配就
混用。采集脚本只在 SDK 列表包含活动 CID，且 SDK APN 与当前配置 APN 一致时
读取该条 QoS；没有匹配项则报告未确认，不创建 SDK 会话，也不重新拨号。
若 SDK 不持有当前 MIPC 会话，仍需进一步适配，不能将错误或别的 APN 的等级上屏。

本次实机正是此情况：当前数据连接为 CID 2、ccmni2、APN ctnet；
get_list 返回 cmd=8、result=0、data_len=580，ucode 收到 579 字节，
全部为零，列表计数为零。脚本返回 ACTIVE_CID_NOT_IN_SDK_LIST，
未继续发送 APN/QoS getter 12/13。此结果说明 SDK 未列出当前原生 MIPC 会话，
不代表设备不支持 QoS，也不代表 QCI/5QI 为零。后续需要核对原生 MIPC 的
只读 QoS 获取路径；不得为了读取等级创建另一条 SDK 会话或更换现有拨号方式。

## 采集脚本

scripts/lg6851f-collect-qos.sh 可在现有固件通过 SSH 主动运行，无需先编译新固件。
它检查板型、持有既有控制锁、检查数据接口稳定后，仅发送固定 getter 8/12/13，
并调用 sample_nw 的只读第 7 项。不会调用创建、设置、启动、停止、重拨或射频开关。
后台状态采集和网页查询也使用这把锁；遇到占用时每秒尝试一次，最多等待 45 秒，
拿锁后再次检查是否有模组控制任务。超时则退出，不删除锁文件或强行终止其他任务。

- 用原生 ucode ubus 绑定保留嵌入的零字节。发送 3 字节字符串加绑定自动附加的
  终止零，恰为 SDK 的 4 字节输入；普通 ubus CLI 的字符串路径可能在首个零处截断。
- 按返回长度校验；识别 ubus 字符串转换去掉一个尾字节的行为，不补造该字节，
  仅解析完整的前部字段，不容忍其他截断。实际收到的数据转成十六进制输出，
  避免 UTF-8/JSON 损坏二进制；APN 必须在收到的数据中有明确结束零。
- 核对 APN，拒绝拿 IMS 或其他配置代替默认数据连接。读取后再次检查活动 CID、
  接口和连接时长，期间换连接则丢弃等级。
- 成功时仅报告厂商等级字段 class_id；在实机返回前不加入看板。对 5G QoS 的
  等级需结合 5QI 语义，不能拿 CQI 冒充。带宽字段单位仍保留待验证，不替换
  已确认的网络/IMS AMBR。
- 不输出密码、IMEI、IMSI、ICCID；第 7 项仅保留返回码、制式和注册状态，过滤
  小区标识与位置字段。临时文件权限为 600，并清理本次创建的临时目录。
- 测试用模拟 ubus 服务验证请求字节、只读命令、上下文/APN 匹配、截断与连接变化。
  新增实机同结构的 580 字节空列表样本回归；QCI/5QI 的实机值仍未取得，不填示例值。

## /tmp 重启保留反馈

用户反馈重启后临时文件仍存在；已请求实机 /tmp 挂载、路径和具体文件信息。
源码暂未发现板级将 /tmp 绑定到持久分区的规则，不能据此推定实机正常，
也不能仅凭同名文件判断旧内容被保留。挂载结果和是否由启动服务重建尚待确认。

可用 sh /tmp/lg6851f-collect-qos.sh 运行，将输出保存为 /tmp/mt6990-qos-readonly.txt。
云编译继续暂停。
