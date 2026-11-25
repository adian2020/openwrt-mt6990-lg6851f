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

本次是分支上的可行性评估。离线已验证 CCCI 的纯等待差异能干净应用，应用结果与参考文件一致；目标的 mt76 固定提交 `59676919` 在应用现有补丁后，参考 995 通过 `git apply --check`，完成的是上下文验证。另运行了目标现有的无线启动、升级迁移、开机恢复、锁定事务共 27 项用例，均通过。本提交仅保存评估和验收顺序，后续功能代码仍需编译和实机验证。
