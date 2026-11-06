# LG6851F Pro / MT6990 更新与修复说明

## 本次修复

- 补齐旧主源码缺失的 audio-support 兼容包，修复 alsa-lib 依赖使 Kconfig 取消 5G 调制解调器服务和 luci-app-5gmodem 的问题。
- 在“网络”中增加 5G Modem 入口，升级时刷新 LuCI 菜单缓存并启用蜂窝状态采集和 LED 服务。
- 修复缺少任一蜂窝 LED 节点就退出整个 LED 程序的问题；Wi-Fi LED 检测兼容自定义无线接口和桥名，蜂窝灯每轮清理过期状态。
- 修复不勾选“保留配置”仍复用 P46 旧软件层的问题。升级后归档旧 upper/work 并创建新软件层；仅勾选保留配置时恢复常规配置备份。
- 两种升级模式均单独迁移 lg6851f_network_led 和 system 中的 LED 配置段。旧插件归档不会继续作为活动 overlay 挂载；新固件预装插件仍会存在。恢复出厂设置仍会清空 LED 设置。

## 软件调整

- 恢复预装 OpenClash 和其专用 Meta 核心 mihomo-openclash-core，移除预装 Nikki 与 Alpha 核心。
- 保留 Nikki 运行依赖；Nikki、LuCI 界面、中文包及 mihomo-meta 只构建 APK，不装入 rootfs。成功构建后发布与本固件匹配的签名 Nikki 软件源，方便按需安装。
- 新增 openssh-sftp-server，配合现有 SSH 服务提供 SFTP 文件传输，不另开 SSH 服务。
- 保留 File Manager、UU 加速器及 Vantage。UU 默认关闭，首次启用下载官方核心并需要绑定账号；OpenClash 协作模式恢复为 cooperative。

## 验证与已知限制

- 配置检查确认 5G 菜单、蜂窝后端、audio-support、OpenClash、Meta 和 SFTP 被选中，Nikki 仅构建为 APK。
- 升级软件层迁移的五项隔离回归测试通过。发布流程仅在关联构建成功后发布固件；构建还会检查关键插件文件是否位于 rootfs。
- 网口硬件 LED 尚未实机确认，未写入未经验证的 PHY 寄存器。5G 注册、信号灯、实际升级迁移和 UU/代理共存仍需 LG6851F 实机验收。

## 升级与使用

- 仅适用于 FiberHome LG6851F Pro / MT6990；当前已知支持范围以仓库 README 为准。
- 当前运行 A 槽只能使用 A 槽 signed-sysupgrade.tar.gz；B 槽只能使用 B 槽包。不要改名跨槽，不要把单刷 IMG 上传到网页升级。
- 升级前导出备份、核对 SHA-256，并执行 sysupgrade --test。归档旧层不是已经完成的实机恢复测试。
- 若从旧版升级，新固件会在首次启动时迁移已管理的 P46 软件层；归档保留供追溯，不会格式化整个 P46 数据分区。
- Nikki 源只对应本次固件。安装前先 apk update 和 apk add --simulate；启用 Nikki 前先停止 OpenClash。
- SFTP 使用路由器现有 SSH 地址、端口和账号。包已包含不代表服务已完成实机传输测试。
