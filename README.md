# OpenWrt for MT6990 / FiberHome LG6851F

本仓库是基于 OpenWrt SNAPSHOT 的完整源码树，增加 MediaTek MT6990 和烽火 Pro LG6851F 支持。仓库目标是在干净 Linux 环境中克隆后，使用 OpenWrt 原生 `make` 流程生成完整可刷写文件，不需要另行调用外部打包脚本。

## 产品与硬件实物

以下图片默认以缩略图显示，点击图片可查看大图。

### 1. 产品外观

<p align="center">
  <a href="docs/images/lg6851f/01-product-overview.jpg"><img src="docs/images/lg6851f/01-product-overview.jpg" alt="FiberHome LG6851F Pro Wi-Fi 7 BE7200 产品外观" width="420"></a>
</p>

烽火 LG6851F Pro 是一款集成 5G 蜂窝网络、Wi-Fi 7（BE7200）和双 2.5G 网口的 CPE。本图用于帮助确认产品外形；不同销售批次的包装、配件和硬件版本可能不同。

### 2. 设备底部与型号识别

<p align="center">
  <a href="docs/images/lg6851f/02-device-label-redacted.png"><img src="docs/images/lg6851f/02-device-label-redacted.png" alt="FiberHome LG6851F 设备底部铭牌（已脱敏）" width="160"></a>
</p>

底部铭牌可用于核对型号、电源规格和管理地址。公开图片已遮挡 Wi-Fi 密码、管理密码、IMEI、序列号和 CMITID；请勿公开自己设备的完整铭牌。

### 3. 主板拆解与主要器件

<p align="center">
  <a href="docs/images/lg6851f/03-mainboard-components.jpg"><img src="docs/images/lg6851f/03-mainboard-components.jpg" alt="FiberHome LG6851F 主板拆解和主要器件参考标注" width="420"></a>
</p>

主板参考标注包括 MT6990V SoC、MT7996CV Wi-Fi 基带/MAC、MT7977 射频、2.4G/5G FEM、RG620T-EU 5G 模组和 YT8821C 2.5G PHY。器件丝印、内存容量和射频布局可能随批次变化，移植或刷机前仍须以实机为准。

### 4. TTL 串口与 USB 调试连接

<p align="center">
  <a href="docs/images/lg6851f/04-ttl-usb-connection.jpg"><img src="docs/images/lg6851f/04-ttl-usb-connection.jpg" alt="FiberHome LG6851F TTL 串口和 USB 调试连接实物" width="320"></a>
</p>

图中展示拆机状态下的 USB 转 TTL 调试连接。串口必须使用 **3.3V TTL 电平**，连接前应实测并确认 GND、设备 TX 和设备 RX；TX/RX 交叉连接，通常只接 GND/TX/RX，**不要连接转接板 VCC**。线材颜色不能作为引脚定义，接错电压或引脚可能损坏设备。

## 设备适用与批次说明

- 目标设备：烽火 LG6851F Pro WiFi 7 BE7200。
- 2024 年和 2025 年批次的测试设备已完成刷机与启动验证，目前测试正常。

## 已支持功能

- MT6990 Linux 6.18 内核、时钟、PCIe、以太网、SGMII、CCCI/5G 模组等设备支持
- FiberHome LG6851F 设备树和 B 槽启动布局
- MT7996/MT7990 Wi-Fi 支持
- LuCI 5G 模组管理
- 已修复并实机验证 MT6990 专用 ADB USB：纯 FunctionFS ADB、通用 `18d1:4ee7` 标识，系统稳定启动 60 秒后自动启用，不创建 RNDIS/ECM/NCM USB 网卡
- 兼容新旧硬件的双通道 PWM 风扇温控
- CAKE 多用户公平性与空闲速率保护
- APK 用户态兼容软件源
- 编译完成后自动导出签名 `boot_b.img`、`rootfs_b.img` 和 LuCI Web 升级包

## 主机环境

建议使用 Ubuntu 22.04/24.04 x86_64，文件系统需区分大小写。

```bash
sudo apt update
sudo apt install -y build-essential clang flex bison g++ gawk gcc-multilib \
  gettext git libncurses-dev libssl-dev python3 python3-distutils rsync \
  unzip zlib1g-dev file wget curl swig python3-setuptools jq xsltproc \
  libelf-dev
```

Ubuntu 版本的包名如有变化，请参考 [OpenWrt Build System Setup](https://openwrt.org/docs/guide-developer/toolchain/install-buildsystem)。

## 下载与编译

```bash
git clone https://github.com/13179415360/openwrt-mt6990-lg6851f.git
cd openwrt-mt6990-lg6851f

./scripts/feeds update -a
./scripts/feeds install -a

make defconfig
make -j4 V=s
```

仓库根目录已提供 LG6851F/MT6990 默认 `.config`。如果内存较少或需要更容易定位错误，使用单线程：

```bash
make -j1 V=s
```

更新到仓库最新源码：

```bash
git pull --ff-only
./scripts/feeds update -a
./scripts/feeds install -a
make defconfig
make -j4 V=s
```

`make` 会按 OpenWrt 原生流程自动下载依赖源码、构建工具链、编译内核与软件包，然后执行 LG6851F 签名和 Web 升级包封装。

## 输出文件

主要文件位于：

```text
bin/targets/mediatek/mt6990/
A槽单刷boot和rootfs签名成功包/
B槽单刷boot和rootfs签名成功包/
```

关键产物包括：

```text
A槽单刷boot和rootfs签名成功包/boot_a.img
A槽单刷boot和rootfs签名成功包/rootfs_a.img
B槽单刷boot和rootfs签名成功包/boot_b.img
B槽单刷boot和rootfs签名成功包/rootfs_b.img
bin/targets/mediatek/mt6990/lg6851f-mt6990-a-signed-sysupgrade.tar.gz
bin/targets/mediatek/mt6990/lg6851f-mt6990-b-signed-sysupgrade.tar.gz
```

A 槽和 B 槽均可按个人使用方式选择刷机：需要使用哪个槽，就选择对应槽位的单刷 `boot+rootfs` 包；设备已经在某个槽正常运行时，也可选择同槽位的 Web 升级包继续更新。A 槽 Web 包只能在 A 槽使用，B 槽 Web 包只能在 B 槽使用，升级程序会检查当前启动槽位并拒绝跨槽刷写。刷写前必须核对设备型号、槽位和 SHA256。

传统 OpenWrt 构建产物仍包括：

```text
boot_b.img
rootfs_b.img
SHA256SUMS
```

## 配置与开发

如需调整软件包：

```bash
make menuconfig
make -j4 V=s
```

常用单包编译方式：

```bash
make package/<package-name>/clean
make package/<package-name>/compile V=s
```

## MT6990 专用 APK 软件库

本项目不要求软件源使用某个固定域名，要求的是软件包与固件的工具链、libc、依赖 ABI、内核 ABI 和签名配套。相同 CPU 架构或同为 Linux 6.18.44，不代表可以混用官方滚动 SNAPSHOT 或其他设备的 APK。不能通过修改架构、关闭验签或忽略依赖解决兼容性。

### 新增的同批扩充库

`cloud-build` 保存固件源码及构建流程，`main` 承担现有自动发布流程。新增的 `firmware-apk` 分支只保存构建产出的 APK 软件库，每个目录使用 `RUN_ID-RUN_ATTEMPT` 标识一次构建，包括同一源码的重新运行。发布器同时创建 `apk-lib-RUN_ID-RUN_ATTEMPT` 标签，不覆盖已有快照或标签；固件使用标签对应的地址，避免同一源码重编时 feeds 或签名密钥变化造成混用。

**本节描述源码已加入的下一次构建流程，并不表示扩充库已生成或已发布。** 已发布的 v1.0.17 及正在使用的设备不会被远程改源。待正常构建、验签、依赖检查和发布全部成功后，新固件才带有对应的软件库。

第一批清单保存在 [`config/mt6990-apk-extras.json`](config/mt6990-apk-extras.json)：

- 9 个可选 LuCI 插件及中文包：DDNS、网络唤醒、ttyd 终端、Watchcat、nlbwmon、vnStat2、PBR、adblock-fast、Aria2。
- 27 项工具/运行库：Bash、常用 coreutils/findutils、diffutils、gawk/grep/sed、压缩工具、jq、OpenSSL 命令、Python 常用组件、Lua 及 LuCI 兼容库等。
- 原来内置的软件保持内置；新增项选择为 `<M>`，编译为可安装 APK，不默认安装或启动。依赖由配置生成过程递归选入构建。Nikki 继续只构建、不预装，并合并到同批软件库。

软件库包含本次目标包和所有 feeds 的 APK，而非只收录上述清单。最终包数与依赖集合以实际构建后的 `repository.manifest.json` 为准，不预先承诺数量，也不保证任意外站插件的所有依赖都已收录。后续添加软件时扩充此清单，重新构建匹配固件及软件库；基础库与内核模块尤其不能混用另一批产物。

### 新固件如何使用

新流程在镜像中保存只读的构建身份、软件源模板和本次公钥。首次启动或保留配置升级时，配置脚本核对本机板型、源码身份和架构，再生成：

```text
/etc/apk/repositories.d/firmware.list
https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/apk-lib-RUN_ID-RUN_ATTEMPT/RUN_ID-RUN_ATTEMPT/packages.adb
```

上面的 `RUN_ID-RUN_ATTEMPT` 是格式示意，实际地址由构建自动写入，不能原样复制。安装当前 ROM 公钥时使用快照专属文件名，避免保留配置带回的旧 `public-key.pem` 遮盖新公钥。原固定基础源和本仓库旧 Nikki 源会备份到 `/etc/apk/library-backups/本次快照/` 后停用；用户自定义源保持原样，仍需自行确认兼容性。身份或公钥缺失时直接报错，不静默改回旧源，不联网下载未知公钥。

进入“系统 → 软件包”更新列表并搜索安装，或使用：

```sh
cat /usr/share/mt6990-apk/build.json
cat /etc/apk/repositories.d/firmware.list
apk update
apk search -v luci-app-wol
apk add --simulate luci-app-wol
apk add luci-app-wol
```

`apk add --simulate` 只解析依赖，不安装。不要把新库地址复制到旧固件。旧版本的已安装插件也可能因新版 ABI 变化需要重新安装对应版本，软件源匹配不等于所有跨版本插件配置均已验证。

默认使用 GitHub Raw，避免部分 CDN 对大文件的限制。可将同一快照的全部 APK、签名索引、公钥及清单完整镜像到其他可达服务器；必须保持字节和版本一致，并确认服务支持较大的代理核心包。域名可以换，不能把镜像换成其他批次的软件。Raw 不可达时也不能通过关闭验签或换成通用源绕过。

### 旧固定软件库

旧固件继续使用原来核验的二进制提交 [`760d829021769a0aff5d713e7316c7d36ff40c71`](https://github.com/13179415360/openwrt-mt6990-lg6851f/tree/760d829021769a0aff5d713e7316c7d36ff40c71) 中的 target/base/luci/packages 四类源，默认通过 jsDelivr 访问。该库及其公钥仅适用于原配固件，保留旧说明用于辨认，不能充当新版的基础依赖源。新版完整同批库覆盖其职责，旧资产不删除、不改写。

### 开发者扩充与发布

额外软件已在 feeds 中时，修改 JSON 清单即可；不在 feeds 中时，先加入符合 OpenWrt 包规范的源码包或 feed，声明完整依赖与源码哈希。不要直接导入其他设备的成品 APK。保留现有插件更新、本机适配、签名和标准 A/B 打包流程。

云工作流自动按以下顺序执行，不需要手工拼接源：

1. 更新 feeds 和原有插件，安装配方；恢复本仓库配置。
2. 应用额外软件清单，生成本次源码及运行快照身份，再执行 `make defconfig`。核对新增项仍为 `<M>`、原内置项仍为 `<*>`，签名与目标保持正确。
3. 完成标准固件构建与原有测试。
4. 执行 `./scripts/mt6990-build-apk-repository.sh`，合并 APK 并重新生成签名索引。只允许本次公钥，逐批核对全部 APK 和索引签名、架构、包名、内核版本、镜像身份及公钥；从空数据库开始显式请求本次镜像的`/etc/apk/world`基础包集合，再逐包模拟安装；保留真实虚拟包提供者选择，验证完整依赖可从该库解析。
5. 将验证后的快照追加发布到 `firmware-apk`，原子推送分支及标签；失败不覆盖旧库。随后上传原有固件产物及软件库元数据。

独立构建机还需在配置生成前执行身份准备（`--snapshot` 填入本次唯一的数字运行号和尝试次数）：

```sh
python3 scripts/mt6990-apk-library.py select
python3 scripts/mt6990-apk-library.py prepare --repository adian2020/openwrt-mt6990-lg6851f --snapshot 运行号-尝试次数 --source "$(git rev-parse HEAD)"
# 沿用现有流程生成 files/etc/mt6990-firmware-id，再执行 defconfig 和标准构建。
```

生成目录为 `bin/mt6990-apk-repository/`，其中直接包含所有 APK、`packages.adb`、`public-key.pem`、`build.json`、`selection.json`、`PLUGIN_VERSIONS.json`、`firmware.world`、`repository.manifest.json` 与 `SHA256SUMS`。检查清单：

```sh
cat bin/mt6990-apk-repository/repository.manifest.json
(cd bin/mt6990-apk-repository && sha256sum -c SHA256SUMS)
```

公钥可公开；私钥不进入软件库、固件或上传产物。A/B 下载包附带 `APK_LIBRARY.json` 便于核对本次软件库，原固件镜像签名和刷写流程保持不变。

## A/B回退后的共享取证

最新源码将取证工具和最近8份报告明确保存在核实过的共享P46中，不依赖当前系统是否挂载`/overlay`。原固件将P46挂在`/data`时，对应：

```sh
ls -lt /data/lg6851f-ab-reports/
sh /data/lg6851f-ab-tools/collect-ab-failure.sh
cat /tmp/lg6851f-ab-failure.txt
```

须先运行包含此修改的固件到后台归档服务，工具才会保存到共享区；旧版v1.0.17没有此能力。原固件不会自动执行共享脚本，早期失败也不保证生成报告。操作不切槽、不写启动标记、不清除崩溃证据。详见[跨槽共享取证说明](docs/2026-11-15跨槽共享取证工具与报告.md)。

## 手动选择启动槽位

最新源码新增“系统 → 启动槽位”，显示实际启动槽、下次启动偏好、原始重试/成功字段和镜像头检查结果。确认备份与原厂恢复风险、输入目标槽字母后，可选“仅设置”或“设置并重启”。仅修改两个优先级和目标槽的重试字节，不复制系统、不修改成功标记或另一槽计数，保留原厂失败回退。

命令行只读查看：`/usr/sbin/lg6851f-slotctl show`。写入前须提供刚读取的控制记录及明确确认；共享P46保存32字节控制记录、完整512KiB misc及元数据，读回不符会停止或在状态可确认时恢复原值。进入原厂可能触发另一槽镜像恢复，不能把手动选槽当作恢复已被覆盖的6.18镜像。该功能尚未在实机验收，未因此触发云编译，旧v1.0.17没有此页面。

原厂“引导另一槽”和“Linux启动后复制镜像恢复另一槽”是两个阶段。本机preloader证据及420组回放已确认：先检查旧计数，当前>3、另一槽<=3且异常检查允许时回退；特定WDT复位路径随后才递增，计数不等同于Linux启动失败次数。最新源码在PID1初始化完成且核心服务实际响应后，仅清当前槽TRY一次，不再固定等120秒；正常关机提供有初始化凭据的补确认，启动未完成仍保留计数。共享P46先保存原始记录并整段读回，不改SUCCESS、另一槽或失败阈值。手动切槽根据实际bootslot与root分区显示A→B或B→A，不假定哪槽装原厂/6.18；普通重启保留所选槽，原厂在线升级交替写入另属一条流程。实机及完整新固件仍待验收。详见[快速重启确认与动态切槽](docs/2026-11-15动态切槽与快速重启确认优化.md)、[preloader实证](docs/2026-11-15preloader重试累计与回退条件实证.md)及[手动选槽](docs/2026-11-15手动选槽与引导器取证.md)。

云编译保留全部插件更新、扩充软件包、测试、验签及A/B打包，增加标准ccache编译对象缓存；下载缓存成功后使用新快照保存，避免固定键不能收录后续源码包。只缓存dl与.ccache，不缓存镜像、暂存目录或签名私钥；首次填充仍需完整编译，后续收益以命中统计为准，未承诺固定分钟数。详见[构建耗时与缓存方案](docs/2026-11-15构建耗时与编译缓存优化.md)。

## 2026-08-21 维修固化说明

- OpenClash 使用 Mihomo 时，核心包装器必须以 `/tmp/clash` 为运行文件名。OpenClash 的服务与防火墙脚本通过 `pidof clash` 检测核心；使用其他文件名会导致核心已经监听端口却被误判为启动失败。修复包含在 `mihomo-openclash-core 1.19.29-r2`。
- `mt6990-userdata-storage 1-r3` 支持从当前根 overlay 的真实 `upperdir` 迁移数据，不再假定源目录恒为 `/overlay/upper`。
- LG6851F Web 升级保留设置时，preinit 仅对带 `.mt6990-extroot-managed` 标记的软件层刷新新 squashfs UUID 绑定，使 `/dev/mmcblk0p46` 的软件、管理员密码和 Wi-Fi 配置在升级后继续挂载；该流程不格式化分区、不修改 GPT，也不触碰 A 槽。
- 本次修复保持 Linux 6.18.44，不包含内核版本升级。

## 安全说明

仓库不包含设备分区备份、SSH 密钥、用户账号、维修现场日志和崩溃证据。构建链内的 MTK `hsm_test_keys` 仅用于当前已验证的测试签名流程，不应用于生产密钥管理。

## 上游与许可证

本项目基于 [OpenWrt](https://github.com/openwrt/openwrt)。OpenWrt 主体代码使用 GPL-2.0，各组件以其源文件中标注的许可证为准。

## 设备刷机工具

<p align="center">
  <img alt="法律与授权声明" src="https://img.shields.io/badge/%E6%B3%95%E5%BE%8B%E4%B8%8E%E6%8E%88%E6%9D%83%E5%A3%B0%E6%98%8E-6f42c1?style=for-the-badge">
  <img alt="刷机安全警告" src="https://img.shields.io/badge/%E5%88%B7%E6%9C%BA%E5%AE%89%E5%85%A8%E8%AD%A6%E5%91%8A-d4af37?style=for-the-badge&labelColor=6f42c1">
</p>

> **第三方权利、授权与风险提示**
>
> 本仓库及下方下载包仅用于 FiberHome LG6851F / MT6990 的合法维修、研究和已获授权的设备维护。仓库中源自 OpenWrt 的内容遵循其各自开源许可证；MediaTek、FiberHome 或其他第三方的工具、配置、测试密钥、证书、参考镜像及相关材料，其权利仍归相应权利人所有，**不因被收录在本项目中而自动适用本项目或 OpenWrt 的开源许可证**，亦不表示相关权利人对本项目提供认可、授权或担保。
>
> 下载、使用、复制或再分发前，请自行确认已取得所在地区法律法规及权利人许可。严禁用于未授权设备、绕过安全机制、制作或传播恶意固件及其他违法用途。刷写存在设备变砖、数据丢失、网络中断和安全风险；操作前请完整备份并核对设备型号、分区和文件校验值。使用者应对自己的操作和合规性承担责任。本声明不排除或限制依法不能排除或限制的责任。
>
> 如权利人认为相关材料侵犯其合法权益，请通过本仓库的 [Issues](https://github.com/13179415360/openwrt-mt6990-lg6851f/issues) 提供材料名称、权利依据及处理请求；维护者将在核实后及时采取标注、限制分发或移除等适当措施。

- 123云盘：[下载设备刷机工具](https://4001579968.share.123pan.cn/123pan/gl1cMh-P7nP?pwd=Mvrn#)
- 访问密码：`Mvrn`
