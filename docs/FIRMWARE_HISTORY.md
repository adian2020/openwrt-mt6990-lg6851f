# LG6851F-Pro 固件更新历史

按版本记录已发布固件的时间与更新内容，最新版本在前。发布时间统一使用 UTC（GitHub Release 的实际发布时间）。旧版摘要据原发布说明整理；没有明确记录的差异不补写。

<!-- firmware-history -->

<!-- release:v1.0.20 -->
## v1.0.20

发布时间：2026-11-15 23:07:30 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.20) · [源码 11dd25e](https://github.com/adian2020/openwrt-mt6990-lg6851f/commit/11dd25e3839e5da76b9c38d7bc674020f3d435d9)

### 新增

- 系统菜单增加“原厂固件切换到自编译固件说明”，提供 A→B、B→A 两组 SSH 命令及复制按钮。
- 打开启动槽位页面时显示说明弹窗，支持“已读，不再显示”。

### 修改

- 修复启动槽位按钮无法点击，以及点击后因进程误判导致设置不生效的问题。
- 切槽确认框显示输入提示、执行进度与失败原因；设置并重启前核对写入结果。
- 风扇换为金属渐变扇叶、青紫灯带和六边形 RGB 轴心，看板与 PWM 页面同步。
- 看板“启动确认”更名为“系统启动就绪确认”。

### 删除

- 删除切槽说明中重复的“确认目标槽已安装自编译固件”提示。

<!-- release:v1.0.19 -->
## v1.0.19

发布时间：2026-11-15 17:48:40 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.19)

- 新增系统“启动槽位”页面及独立工具，区分当前槽和下次偏好，手动选槽前备份、校验及读回。
- 新增正常启动确认，仅清当前槽 TRY；初始化完成、核心服务响应后确认，正常关机补检查。
- 取消早期固定 120 秒和稳定 30 秒等待，保留未完成启动的重试计数及原厂失败保护。
- 看板显示启动确认状态与加大的当前槽位文字。
- A/B 取证工具和最近 8 份报告保存到共享 P46，兼容原厂 /data 与自编译 /overlay。
- 加入标准 ccache 和源码下载缓存，保留完整插件、软件库和签名检查。

<!-- release:v1.0.18 -->
## v1.0.18

发布时间：2026-11-15 04:44:59 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.18)

- 修复短信队列依赖 BusyBox 缺失参数导致无法启动任务；修复 UCS2 尾部 0000、四位年份与跨日长短信分组。
- 风扇三档动画调整为 1.8/1.35/0.8 秒，并统一扇叶颜色。
- OpenClash 改为 Smart Alpha 核心；新增默认关闭的 UPnP 中文插件。
- 增加开机后台 A/B 压缩报告归档。
- 扩充同批签名 APK 软件库：9 个可选 LuCI 插件及中文、27 项工具/运行库，新增项不预装。
- 增加启动细分计时与 PHY/热点观测；修复 Smart APK 版本、libffi 缺失和虚拟 CA 依赖验证。

<!-- release:v1.0.17 -->
## v1.0.17

发布时间：2026-11-14 01:53:12 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.17)

- 移植 MU300 式短信会话和短信转发界面，加入持久短信池、异步 Unicode 发送及分片归档。
- 转发增加推送预设、请求格式、响应条件、钉钉加签、黑名单、多号码及私密投递记录。
- PWM 风扇菜单直达；看板与风扇页共享三档透明动画和变色龙圆环。
- 看板显示实际 A/B 槽，网络模式按模组读回高亮；加入漫游配置、默认关闭的 QoS 手动开关并删除 EN-DC。
- 显示真实 IMS 注册能力，不伪造 VoLTE/VoNR 独立控制或调制名称。
- 每轮构建更新 OpenClash、Mihomo、UU，修复宿主摘要模块的 json-c 头文件路径。

<!-- release:v1.0.16 -->
## v1.0.16

发布时间：2026-11-13 16:22:30 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.16)

- 新增系统菜单下默认关闭的定时重启插件。
- 蜂窝 QoS 默认关闭并对旧默认启用配置安全迁移；改为事件触发，修复停止后规则复活与不完整清理。
- 增加 A/B 回退只读取证脚本。
- 温度取消黑底；取消 CPU 频率占位；Aurora 恢复原版自动/明暗选择。
- 按 MU300 结构调整网络锁定页，完善邻区 n78 消歧并加入 mDNS 名称发现。
- 修复 Qt6 配置依赖环及 QoS/mDNS 宿主回归夹具问题；未据此认定内核卡死根因已解决。

<!-- release:v1.0.15 -->
## v1.0.15

发布时间：2026-11-08 04:13:32 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.15)

- 加入有界 NR BLER 回调采集与注销冷却，修复 BusyBox 不支持 flock -w 的通道等待。
- 删除 NR PCC 载波聚合指标行，恢复真实 MCS（含 0），AMBR 统一为 Mbps。
- 修复首次自动 APN 识别后仍使用旧参数的拨号循环。
- 温度改用 SoC、CPU、Wi-Fi、调制解调器真实传感器；删除本机号码行。
- 完善无线/客户端/DHCP 缓存和真实设备名称读取。

<!-- release:v1.0.14 -->
## v1.0.14

发布时间：2026-11-08 00:45:05 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.14)

- 修复分阶段采集中间帧清空无线、客户端、DHCP 和存储数据，失败时保留有效快照。
- 增加持续小区采集，依据实际载波消歧 n77/n78。
- 调整温度、SSID、信道及客户端速率展示，移除电源和 USB 网络入口。
- 首次拨号期间后台查询让行，补齐未连通接口重试。
- 该版 Aurora 默认夜间；后续 v1.0.16 恢复原版自动明暗逻辑。

<!-- release:v1.0.13 -->
## v1.0.13

发布时间：2026-11-07 20:17:57 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.13)

- 按 MU300 界面整理看板、APN 卡片和流量管理；APN 按 SIM 记忆并自动匹配。
- 新增套餐额度、结算日、校准及每日/月流量历史，看板共用持久账本。
- Wi-Fi 首次启用改为等待 PHY 就绪，不再等待蜂窝稳定。
- 删除独立 SIM/CPU 页面、第二 IMEI 占位及 Android 切换入口。
- 补充已有 P46 启动日志与 bootprof 只读采集。

<!-- release:v1.0.12 -->
## v1.0.12

发布时间：2026-11-07 09:27:38 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.12)

- 看板慢采集移出 RPC，独立后台分阶段发布缓存，修复网页超时。
- 补齐固定基础软件源签名公钥，恢复基础软件列表更新。
- 修复无管理标记旧 overlay 的清理接管，保留匹配槽位及升级策略检查。
- 修复锁频按钮禁用、选中高亮和状态回显；锁频释放通道后恢复拨号，并展示任务进度。
- 补齐 LTE 频点到频段映射及看板刷新后的真实速率缓存。

<!-- release:v1.0.11 -->
## v1.0.11

发布时间：2026-11-07 04:04:05 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.11)

- 短信转发接入 Webhook、SMTP、本机短信三渠道，默认关闭；增加模板、黑名单和持久去重。
- 默认主题从 Vantage 改为 Aurora，新增独立状态看板及 APN 管理。
- 完善本机频段、小区及高级参数读取，区分实际值与未确认数据。
- 修正 P46 软件层迁移时机、首次射频拨号及手机锁定页面布局。
- 补齐宿主构建顺序、固定版本 ucode 测试及成品资源核验。

<!-- release:v1.0.10 -->
## v1.0.10

发布时间：2026-11-06 17:04:45 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.10)

- 修复缺少 audio-support 导致 5G 服务和页面被取消选择的问题，补齐蜂窝菜单与 LED 服务。
- 修复不保留配置升级仍复用 P46 旧软件层，单独迁移 LED 配置。
- 恢复预装 OpenClash/Meta；Nikki 改为可选 APK 与配套签名软件源。
- 新增 SFTP，保留文件管理与默认关闭的 UU 加速器。

<!-- release:v1.0.9 -->
## v1.0.9

发布时间：2026-11-06 13:12:28 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.9)

- 发布说明继续列出 Vantage 主题、Nikki 和 Mihomo Meta 核心。
- 原说明与 v1.0.8 相同，未单独列出新增差异。

<!-- release:v1.0.8 -->
## v1.0.8

发布时间：2026-11-06 10:49:22 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.8)

- 发布说明列出 Vantage 主题、Nikki 和 Mihomo Meta 核心。
- 原说明与上一构建版相同，未单独列出新增差异。

<!-- release:LG6851F-Pro-42134370952 -->
## LG6851F-Pro-42134370952

发布时间：2026-11-06 01:15:54 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/LG6851F-Pro-42134370952)

- 新增 Vantage 主题及管理界面。
- 新增 Nikki 代理管理插件和 Mihomo Meta 核心。

<!-- release:LG6851F-Pro-42101509307 -->
## LG6851F-Pro-42101509307

发布时间：2026-11-05 22:18:25 UTC · [查看该版 Release](https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/LG6851F-Pro-42101509307)

- 早期固件构建发布；原 Release 仅提供提交历史链接，没有逐项更新说明。
