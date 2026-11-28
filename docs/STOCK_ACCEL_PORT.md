# LG6851F-Pro V2.10 功能移植评估

目标是让当前 LG6851F 固件获得原厂硬件加速和设备控制能力，同时沿用现有驱动维护、软件源、A/B 和升级流程。这份评估基于目标 `cloud-build` 的 `ee091339dbaa3da4d38ffae2b51ceae7be2d075e`（包含 v1.0.21）和参考仓库 `main` 的 `0e1518ed632388e814032e0831560d22d9488981`。参考 V2.10 也是 **Linux 6.18.44**，来自 systemfix-94。它移植了厂商无线栈，公开包的 A/B 冷启动和跨设备验收仍未完成，公开复打包入口使用已经验证的镜像。相同内核版本号不足以确定两边模块的 ABI 相同。[参考源码与构建边界](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/docs/releases/V2.10-source.md)

## 各项结论

| 功能 | 目标固件现状 | 移植方案 |
| --- | --- | --- |
| 蜂窝 ↔ Wi-Fi、蜂窝 ↔ 有线、有线 ↔ Wi-Fi HNAT/WED | 已有厂商 `hwnat` 模块和内核核心钩子。发布镜像的设备树没有 `mediatek,wed` 关联，`mt7996e` 加载行没有启用 WED。 | 具备开发基础，需要整合目标的 MT6990 数据路径。先保持 `mt76`，验证 WED 绑定，再接厂商 PPE；厂商整套无线驱动作为独立候选。 |
| 同 BSSID 的 Wi-Fi ↔ Wi-Fi 加速 | 当前使用 `mac80211` 和 `mt76`。 | 参考厂商 AP 的同 BSS 转发、站点生命周期和隔离判定。单独验收两站点的硬件命中及隔离，不能以 CPU→Wi-Fi 或跨接口 NAT 命中代替。 |
| 双频独立保存、5 GHz BE/160 MHz、信道 44 | `mac80211` 的 UCI/hostapd 已识别 `EHT160`。当前首次配置等待真实 PHY，升级后保留已保存的 AP。 | 在现有无线页面验证两个 `wifi-device` 和各自 AP 的保存与恢复，按实际 5 GHz PHY 能力显示 EHT160。信道 44 能否与 160 MHz 同时启用，取决于整段频谱的监管、DFS、校准及驱动支持。 |
| CPU 频率和省电/均衡/性能三档 | 目标设备树有一个共享的四核频率域。当前没有可用于这些档位的已验证硬件策略。 | 参考硬件 LUT、频率档位与散热限频适配，用本工程重编独立驱动，再从标准 `cpufreq` policy 提供界面和读回。2200 MHz 和 CoreMark 7985/30167 是参考值，需要本固件实测。 |
| 五个灯位、4G/5G 三色 | 目标设备树已有 Wi-Fi、4G/5G 七路彩灯 GPIO 和网络灯对应的 `5g_evb_voice`；已有自动状态服务。 | 复用 LED class 和定时触发器，增加五组界面与手动/自动所有权。电源灯单独核对 GPIO80，只在确认该板确实使用它且没有其他占用时注册。 |
| `iperf3`、512 MiB swap | v1.0.21 的签名 APK 库不含 `iperf3`；同一 feed 已有 `iperf3` 和 `libiperf3` 配方。目标启用了 swap 和 BusyBox `mkswap`、`swapon`、`swapoff`。 | `iperf3` 可加入固件匹配的 APK 库。swap 可在核实 P46 挂载和剩余空间后异步启用，保存于 overlay 文件系统的独立目录，首建时先等管理 Wi-Fi 就绪。 |
| CCCI/WED 周期等待 | 目标的 CCCI 轮询为 `msleep(15000)`，目标未采用厂商 WED SER 线程。 | CCCI 的周期等待可独立改为 `schedule_timeout_idle()` 的剩余时间循环。WED SER 等厂商路径接入后再评估同一模式，保留检查、超时、恢复及停止的时序。 |
| 蜂窝状态、小区、信号缓存、锁定读回及恢复 | 目标已有状态看板、异步采集和缓存、原生 AT/MIPC 的锁定与验证、开机恢复、同槽升级的 overlay 管理。 | 保留目标实现和 RPC，按实测补缺的字段或修复，不覆盖整套模组用户态、无线运行层或 A/B 工具。 |

## HNAT/WED 的实际落点

原厂 A 槽的对照数据提供了硬件加速证据。15 秒内 `ccmni2` RX 450.7 Mbps，`rai0` TX 492.2 Mbps，`mt7990-wed`/`mt7991-wed` 在 CPU2 分别增加 1730/8603 次，`MED_RX_IRQ` 在 CPU3 增加 287 次。原厂 CPU 总忙碌约 14.9%，该段未增加 softnet 丢包。已加载 `hw_nat` 说明模块存在，这条下载是否使用 PPE 仍需流级命中证据。当前固件停旧 QoS 后用户实测 350～400 Mbps，WED、分核、无线与蜂窝条件均可能影响结果，不能把所有差距归给其中某项。

两边已有共同基础。`0702-net-add-mt6990-vendor-hwnat-hook-core.patch` 和 `0703-net-mt6990-hwnat-preserve-skb-metadata-lifecycle.patch` 的 Git blob 相同，目标已包含 `kmod-mt6990-hwnat`。参考仓库另有 `975`（MDMA 数据路径和流卸载）、`976`（WED V2/WO）、`977`（MT6990 PCIe 连接和单一 PPE 控制者）、有线 HNAT 补丁及 `995-mt7996-mt6990-vendor-hnat-tx.patch`。`995` 将 WDMA、BSS、WCID 和环信息传到 PPE，MT6990 分支停用不兼容的 WED v3 RRO，并处理站点重用前的流项清理。[参考内核补丁](https://github.com/adian2020/LG6851F-Pro/tree/0e1518ed632388e814032e0831560d22d9488981/target/linux/mediatek/patches-6.18) · [mt76 接口补丁](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/package/kernel/mt76/patches/995-mt7996-mt6990-vendor-hnat-tx.patch)

这两条路线需要区分。V2.10 的公开运行层提供 `mt_wifi`、`mt_wifi_cmn`、`mtk_hwifi`、`mtk_wed`、`wifi_md_coex`，并配有 `vendor618`/原生 hostapd。它从本机 `fh_data` 取得校准，使用各自的双 HIF、固件和 BSS 管理。当前固件运行 `mt76/mt7996e`、`mac80211` 和现有本机 EEPROM 流程。同一 PCI 功能只交给一个无线栈。同一 PPE 表也只由一个实现管理。参考 `977` 明确将两个 PPE 交给厂商 HNAT 时，保留 WED 注册，同时关闭上游 PPE 所有权；不能把 `975` 的上游流卸载设置和厂商所有权混着启用。即使 `CONFIG_NET_MEDIATEK_SOC_WED=y`，设备树、HIF 中断、DMA、WO 固件及描述符缺任一适配都无法靠 `wed_enable=1` 补齐。[参考无线实现](https://github.com/adian2020/LG6851F-Pro/tree/0e1518ed632388e814032e0831560d22d9488981/vendor-source/wifi)

同 BSSID 要单独审查。厂商 AP 代码会按 `wdev`、站点隔离和 VLAN 条件决定是否把数据直接转发到空口；`hnat_lan_accel.c` 的 CPU→Wi-Fi 路径明确排除有入接口的包。它包含 RCU 注册、BSS 索引与代际复用，但这不能作为同 BSSID 两客户端硬件转发的证明。公开清单也把 CPU→Wi-Fi 写为单独能力。验收要观察同 BSSID 双站点的硬件命中、站点重连后旧流退回，以及访客 VLAN、AP 隔离、防火墙和组播仍按策略工作。[厂商 AP 转发](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/vendor-source/wifi/mt_wifi/ap/ap_data.c#L4322) · [参考 HNAT](https://github.com/adian2020/LG6851F-Pro/tree/0e1518ed632388e814032e0831560d22d9488981/development-history/V2.10/hwnat/hw_nat)

## 无线、调频和存储的实现边界

- 参考公开无线配置实际为 2.4 GHz 信道 6/EHT40、5 GHz 信道 44/EHT80，`vendor618.sh` 另外接受 EHT160。要核对目标是两频段独立保存还是还要求改一边时另一边无重启。当前双频可能共享 PHY，后一项需独立验收。延续使用本机校准和真实法规限制，不复制供体配置、MAC、功率覆盖或密钥。[参考无线入口](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/files/lib/netifd/wireless/vendor618.sh#L480)
- CPU 调频不是前端字段的移植。参考驱动对本机频率 LUT、MCUPM/SVS、温控和共享 policy 有专门处理，也会访问控制寄存器。先核对初始化权限、硬件就绪、频率和冷却表，再选择驱动。前端可以显示标准接口的请求档位或经验证的实际频率，并注明各自口径。当前已知 `clk_summary` 读取曾使设备卡死，应继续排除该采集路径，以及裸 `/dev/mem` 和通用时钟寄存器探测。[参考调频驱动](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/drivers/lg6851f_cpufreq_hw.c) · [目标离线核对](2026-11-08MT6990调频驱动与设备树离线核对.md)
- 参考灯控将 4G/5G 颜色映射到既有 LED class，`timer` 提供闪烁，`/tmp/lg6851f-led-overrides` 与自动状态服务协调。应该先复用目标驱动。网络灯与电源灯各自的 GPIO 由 LED class 持有，再为模式及颜色设置引入一个共同的仲裁入口，避免自动状态刷新覆盖手动设定。[参考灯控 RPC](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/files/usr/share/rpcd/ucode/luci.lg6851f-led) · [电源灯注册](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/drivers/lg6851f_panel_leds.c)
- `iperf3` 从本工程 feed 构建 `iperf3` 与 `libiperf3`，沿用当前 APK 仓库校验，不使用对方发布的二进制。512 MiB swap 应用目标已核验的 P46 身份、挂载点和空间检查，复用现有文件时检查大小和状态，失败时保留系统正常运行；大文件首建不进入首次 AP 的启动路径。参考脚本的 `swappiness`、`vfs_cache_pressure` 不属于创建 swap 的必需配置。[参考 swap 服务](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/files/etc/init.d/swap)

## 推荐顺序与验收

实验分支已准备 [`iperf3` 软件包选择和四条链路的基线测法](STOCK_ACCEL_BASELINE.md)。

1. **独立实现低耦合项。** `iperf3` 加入同批 APK 库；验证双频设置和 5 GHz 合规能力；把 CCCI 闲置等待、五灯控制和 512 MiB swap 各自做成可独立回滚的提交。保留已有蜂窝显示、信号缓存、频段/小区锁定读回和升级恢复。测试保留配置/不保留配置、双频单独修改、冷启动及电源灯与风扇 GPIO 无冲突。
2. **建立加速实验。** 先记录当前吞吐和真实中断增量，分开验证 `MED_RX_IRQ` 分核、WED 初始化和 PPE/HNAT 命中。保留 `mt76` 的路线先解决 976/977 的设备树、WO 和所有权依赖，再试 995；厂商 `vendor618` 仅作单独候选。所有流向使用同条件测开/关、双向流量和驱动计数，从蜂窝↔有线、蜂窝↔Wi-Fi及有线↔Wi-Fi逐项到同 BSSID。逐项核对重拨、重新关联、VLAN/隔离、IPv4/IPv6、QoS 与加速路径的覆盖关系，保留必要的正常软件转发。
3. **单独验收调频。** 只有硬件 LUT、散热限频、退出恢复、短时负载及重启结果都匹配，才开放三档。用相同编译、固定核心数与频率策略取得可比 CoreMark，刷新和轮询低开销，避免把参考跑分写成当前成果。

评估阶段在目标 mt76 固定提交 `59676919` 应用现有补丁后，参考 995 通过 `git apply --check`。这确认了补丁上下文，后续仍需验证驱动依赖、编译和实机数据路径。目标现有的无线启动、升级迁移、开机恢复、锁定事务共 27 项用例通过。

## 第一阶段的 CCCI 改动

实验分支采纳了参考仓库的 CCCI 周期等待实现。Linux 6.18.44 的 `msleep()` 与这个实现都把等待毫秒数换算成 jiffies，提前唤醒时继续等待剩余时间。新调用使两次轮询之间的线程处于 `TASK_IDLE`，这段时间不计入系统负载平均值。15 秒轮询间隔、应答超时、故障上报及 200 毫秒恢复等待沿用原逻辑。目标内核编译和实机轮询仍待验证。[参考 CCCI 源码](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/target/linux/mediatek/files-6.18/drivers/misc/mediatek/eccci/fsm/ccci_fsm_poller.c)

## 第二阶段的 WED 发送路径

实验分支将 MT6990 的两个 Wi-Fi PCIe 域连接到各自的 WED v2 实例。设备树中的寄存器、GIC 中断号和路由位来自原厂资源与 WARP 的 MT6990 实现。WED 使用对应 PCIe 域的 INTx 路由，在驱动退出时恢复之前的路由位。PPE 表仍由厂商 HNAT 管理，WED 从自己的设备树节点注册。[参考 WARP 源码](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/vendor-source/wifi/warp_driver/warp/regs/reg_v2/warp_mt6990.c)

`mt7996e` 的 `wed_enable` 默认关闭，只在 PCI 探测时读取。启用时，MT6990 使用 WED v2.3 的 TX 描述符和两路 HIF，接收数据仍由常规 PCIe 队列处理。当前发送路径跳过 WED RX、硬件 RRO 和 WO 微控制器初始化，因此这一阶段无需增加厂商 WO 固件。后续 RX 和 PPE 流卸载分别验收。

离线编译使用本仓库固定的 Linux 6.18.44、无线 backports 6.18.26 和 mt76 `59676919`，编译了 ARM64 Ethernet/WED 驱动对象和 mt7996e 合成对象。DTB 回读与基线相比只新增两个 WED 节点及 Ethernet 的引用，原有 phandle 保持一致。整机启动、WED 中断、硬件环及链路吞吐仍待实机验证。

实机验收先用默认关闭的配置按[测速基线](STOCK_ACCEL_BASELINE.md)采样，再用启用配置复测。按两个 PCIe 域确认各自的 WED 绑定，记录正常联网、重关联和重拨，以及同次测速的 WED 中断、TX 环和吞吐增量。之后再把 PPE 的流表命中和各转发方向纳入对照。

## 只读频率、蜂窝和设备控制

- CPU 读取 MT6990 原设备树 `cpufreq-hybrid` 对应的两个字，使用参考驱动的共享 PLL 和分频公式。两次读数不一致时丢弃该样本。内核提供只读的 `cpu_pll_cur_freq`，当前看板刷新时显示 MHz。
- “状态与小区”复用已存在的 AT 所有者与后台采集锁。小区采用本次启动、当前蜂窝设备和承载的 ECELL 样本。CESQ 以最后一次有效采样的时间计算有效期，制式或服务状态变化时清除旧样本。频段读回沿用模组当前及支持掩码，驻留目标只显示本次启动验证记录。锁定写入、恢复及升级仍由原入口处理。
- 五灯控制使用 LED class。自动服务和 LuCI 通过同一把锁交接写入权，4G、5G 的三色输出彼此独立。GPIO80 按参考机身配置添加电源灯。P46 的 swap 新建前核对分区和空间，待热点就绪或后台等待结束再分配，继续使用 `/overlay/swap/swapfile`。
- 当前无线使用独立的 `wifi-device` 配置段。真实 UCI 测试验证两段配置可单独保存，包含 5 GHz 信道 44 和 `EHT160`。LuCI 按 PHY 上报的能力提供选项，实际信道组合与功率由驱动和监管规则决定。

## PPE 学习和 WED 接收侧的验证

有线驱动可用 `mtk_eth.wired_hnat` 将实际 RX 描述符的学习元数据交给厂商 PPE。Wi-Fi 侧保留独立的 WED 试验，并增加 `mt7996e` 的 `wed_hnat` 参数。两者默认关闭。Wi-Fi PPE 适配只使用带原生 FOE 元数据的单播 802.3 发送数据，在站点释放 WCID 前清除相关流。Ethernet、PPE、mt7996e 和 CPU 读取器均通过 ARM64 对象编译。需要实机验证每个流向的实际绑定、命中和断线恢复。

参考仓库的 WO 文件编号与装载地址不同。`6990_wo_0.bin` 内地址属于第三路，`6990_wo_2.bin` 的地址才匹配 PCIe 域 0，域 1 对应 `6990_wo_1.bin`。现有上游驱动对两路 WO 使用同一复位寄存器的不同位，MT6990 的厂商 WARP 使用各自的复位寄存器。两路 WO 的内存映射、CCIF 以及复位需要一起验证。当前实验源码的 WED 仍使用 TX 路径，同 BSSID 的硬件转发和厂商 WED SER 周期任务仍待接入。[WO 与复位参考](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/vendor-source/wifi/warp_driver/warp/regs/reg_v2/warp_mt6990.c)

## 厂商无线栈的独立构建

`scripts/lg6851f-build-pro-wireless.py` 固定使用 Pro 源码 `0e1518ed632388e814032e0831560d22d9488981`，按顺序构建 `wifi_md_coex`、`mt_wifi_cmn`、`mtk_warp`、`mt_wifi`、`mtk_hwifi`。`hwifi_main.c` 在读取调试声明前先包含提供厂商类型的 `rt_config.h`，解决原顺序在目标头文件下报 `unknown type name 'UINT32'` 的问题。模块构建使用本次目标内核、mac80211 和 HNAT 的符号表。`--objects` 可在内核和头文件已准备、尚未生成符号表时编译并链接 ARM64 对象。每部分的命令和输出单独留在工作目录。入口只产出独立 DTB 和构建结果，现有设备镜像仍选用 `mt76`。[Pro 构建参数](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/scripts/vendor-build-part.py)

```sh
python3 scripts/lg6851f-build-pro-wireless.py \
  --vendor-repo "$PRO_REPO" --kernel "$KERNEL_DIR" \
  --staging "$TARGET_STAGING_DIR" --cross-compile "$CROSS_COMPILE" \
  --work-dir "$OUTPUT_DIR" --objects
```

`CROSS_COMPILE` 使用目标 ARM64 工具链的前缀并带末尾 `-`。`OUTPUT_DIR` 使用新建或空目录。对象模式也检查 `hwifi` 生成的 `connac_if`、`mtk_pci`、`mtk_wed`、`mt7990`、`mt7991`。完整模块模式还使用 Pro 实验构建 `b942f071` 中的源码修复和 APCLI 指令检查，保留 `modpost` 未解析符号的失败行为，并逐个检查模块架构和 `vermagic`。`--hostapd` 使用同一 ARM64 工具链和同批 libnl/OpenSSL 重编厂商 hostapd。[Pro 驱动修复入口](https://github.com/adian2020/LG6851F-Pro/blob/b942f071af127ece3d40321aca41f4f96f2ab800/scripts/cloud/vendor_repair.py)

`cloud-build-stock-accel-port` 的独立 Actions 工作流先构建目标内核、mac80211 和 HNAT，再执行完整模块校验和 hostapd 构建。运行 `45915068532` 的候选 DTB、10 个模块、hostapd 和驱动修复报告已经通过产物 SHA256 校验。该次归档缺少内核 `Image`。新版流程在同一任务内组装并签名 A/B 镜像，再核对内核与符号表散列、候选设备树、实际 SquashFS 内的模块和 hostapd，以及两槽 `CONTROL`。实验镜像由 Actions 保存，实机启动及 WED 收发需要分别验收。[已验证的组件构建](https://github.com/adian2020/openwrt-mt6990-lg6851f/actions/runs/45915068532)

通过 `LG6851F_PRO_WARP_IMAGE=1` 选择候选设备树和厂商无线栈。运行层取自固定 Pro 提交，校准从本机 `fh_data` 只读取得，启动确认继续由本分支负责。全新安装时 `LG6851F-Pro-2G`、`LG6851F-Pro-5G` 默认无密码。保留配置时，实验驱动支持标准 `radio0` 为 2.4 GHz、`radio1` 为 5 GHz 的映射，仅迁移驱动类型，保留 SSID、密码和开关。不兼容的映射会保留原配置，待通过有线管理调整。

配置阶段复用主构建的 feeds 兼容脚本。它从原始 `.config` 检查选项，避免未选配方的 Kconfig 循环进入索引。安装 feeds 后再次恢复原始配置，再核对无线内核模块及 hostapd 依赖仍为 `y`。

候选 DTS 从本分支的板级设备树继承启动和其他外设资源，移除以太网对上游 WED 的引用和两个上游 WED 节点，加入 Pro 的三路 WED、WDMA、AP↔WO CCIF 及 WO 的 ILM、DLM、启动寄存器。编译后的 DTB 回读核对了这八个节点与 Pro 一致，其余基线属性和 phandle 一致。从 ARM64 `mtk_warp.o` 提取的三个内置固件，各自的 ILM/EMI 载荷为 22048/87264 字节，分别落在候选 DTB 的三对地址范围内。该方案使用 WARP 的嵌入固件和复位流程，避免把仓库里的外置 WO 文件按尾号当作 PCI 域编号。[Pro 板级设备树](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/target/linux/mediatek/dts/mt6990-fiberhome-lg6851f.dts)

本地验证目录只有准备后的 Linux 6.18.44 内核和无线 backports 6.18.26。该目录用于核对 ARM64 对象，完整模块 ABI 由独立云流程使用同批符号表验证。

整机接入仍需把当前构建生成的模块与原生 hostapd、`vendor618` 运行层、校准入口及固件成套装配，并确认两个 Wi-Fi PCIe 功能只由厂商驱动绑定。WED RX 需要观察 WO 启动、接收环和每站点 RX 计数。Pro 的同 BSSID 软件直转根据站点隔离与 VLAN 检查选取目标 WCID，进入 `RTMPSendPackets()`。同 BSSID 硬件验收需要同时观察两个客户端的实际流和对应硬件命中，并复测隔离、VLAN 以及重连后的流项失效。[Pro AP 转发](https://github.com/adian2020/LG6851F-Pro/blob/0e1518ed632388e814032e0831560d22d9488981/vendor-source/wifi/mt_wifi/ap/ap_data.c#L4365)

## Pro 蜂窝、状态看板和主题

- 移植固定到 `adian2020/LG6851F-Pro` 的 `main` 提交 `0e1518ed632388e814032e0831560d22d9488981`。`package/vendor` 的 494 个 Git 文件、可执行位和符号链接逐项一致。包管理准备阶段从已跟踪的文件补入原配方引用的五项安装材料，生成文件不计入源码快照。
- 蜂窝沿用 Pro 菜单下的状态与小区、短信、流量统计、拨号与网络、AT 调试和状态缓存。首页使用 `fiberhome/home_stable_v20261026_71`，主题使用 Pro 的 Aurora 模板、资源和路由脚本，同时保留 Pro 的 Argon 包。目标仓库的 LuCI 登录设置和已有用户配置继续生效。
- 目标仍使用本分支的 `mt76` 无线栈和既有 A/B、启动确认、恢复及升级流程。系统的启动槽位工具使用独立的 `luci.lg6851fslots` 对象。自动重启、UU 和 Aurora 配置等本分支已有插件放到 `package/lg6851f`。
- IPv6 前缀工具从 Pro 保留的 C 源码构建。聚合采样调用同机型已记录的 `sample_nw` 只读查询，复用模组锁。PPE 统计模块从 Pro 源码编译，并与本次构建的 HNAT 符号表链接。看板可用时读目标的只读 PLL 频率，未读到的上限和请求频率保持缺失。
- 这些是源码和接口适配。流量统计、实际模组收发、WED 硬件命中、完整签名固件及实机启动需要分别验证。

## Pro 服务插件

从 Pro 实验构建 `b942f071` 的 B 槽根文件系统核对到“服务”下有 OpenClash 和 Nikki。实验分支内置 Nikki、中文包及对应 Mihomo，保留 Pro 的菜单、权限、页面、启动脚本和升级配置保留路径。使用公开版的默认配置，首次安装时两套代理保持关闭。Pro 的 TurboACC 位于“网络”，本次服务插件移植不涉及该入口。现有本分支插件保留。[Pro 参考固件](https://github.com/adian2020/LG6851F-Pro/actions/runs/45776501611)

## 实验镜像的同批 APK 库

运行 `46008042112` 已编译内核、厂商无线组件和 hostapd，并生成通过两槽启动分区和证书检查的签名镜像。实验工作流在 `make defconfig` 前漏掉了同批 APK 软件库准备步骤，组装后的根文件系统缺少 APK 库的构建身份、选包清单、仓库 URL 和 ROM 公钥，产物检查因此停止。[失败日志与诊断](https://github.com/adian2020/openwrt-mt6990-lg6851f/actions/runs/46008042112)

实验工作流现复用固件的选包、APK 签名和逐包依赖验证流程。组装后用实际 SquashFS 核对同批软件库的固件身份、公钥、选包清单和 `firmware.world`，再向 `firmware-apk-stock-accel-port` 追加本次软件库，以 `apk-lib-<运行号>-<尝试号>` 标签固定 URL。A、B 两槽产物都附带同一份 APK 库清单。固定的 Pro 插件从源码记录版本和来源，构建时继续使用该快照。

## 首启无热点与 LAN2 链路诊断

实验版 `47946d5` 的两份 B 槽报告均已进入用户态，分别在约 30.5 秒和 46.1 秒记录到两个无线 PHY。成品曾把 WO 就绪日志检查放在 AP 交接前。离线复现中，就绪记录少于两条时脚本在请求启动 AP 前退出。实验镜像恢复 Pro 的先交接、后检查顺序，并记录 WO 就绪日志计数。LAN2 的实际丢链路原因仍待实机取证。恢复后 LAN2 正常的 `8632af1` 也出现过 `netsys swdvfs: ack(1) timeout`。

诊断服务在后台等待已挂载的共享 P46，然后在两分钟内采集五次 LAN2、LAN1/WAN、网桥、无线和 USB 控制器状态。报告保存无线启动阶段、只读的 netifd 和 hostapd 状态以及精选的网络日志。以太网 MAC 的固定链路载波可能一直显示已连接。外置 PHY 以已绑定的内核设备信息和电脑网卡的实际连接状态核对。

报告存放在 P46 的 `lg6851f-pro-network-diag/boot-<启动ID>.txt`，最多八次启动。恢复到旧固件后可直接经 `/overlay/lg6851f-pro-network-diag/` 或实际 P46 挂载点读取。该目录独立于网页升级清理的运行日志和崩溃目录。采样只读网络与内核状态，使用系统已经挂载的 P46，不操作 A/B 控制状态。
