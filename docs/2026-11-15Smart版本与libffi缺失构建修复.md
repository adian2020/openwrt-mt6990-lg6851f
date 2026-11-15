# Smart版本与libffi缺失构建修复

## 失败证据

运行43645921552，cloud-build，3061ef9。插件更新、前置回归和配置生成通过，Build and verify LG6851F images失败，软件库/固件上传与发布未执行。本轮不能视为已生成可用新固件。

取得完整运行日志ZIP及失败步骤日志：

- `/tmp/lg6851f-43645921552-logs.zip`，SHA256 `4d3a6dbade6af05fcd06d5d41c17ee280b516f2f24ffa05e6d91269b39b77301`。
- 完整job文本 `/tmp/lg6851f-43645921552-full.log`，失败步骤 `/tmp/lg6851f-43645921552-failed.log`。直接job日志连接器返回Transport closed，但运行ZIP可用，未因此跳过分析。
- 诊断产物14136834293，661338字节，ZIP SHA256 `dcb210cdb9938353110f7d86210338f34fb67e5865f0c658d620ce1454a2037a`，已下载并解压 `/tmp/lg6851f-43645921552-diagnostics/`。校验值与Actions上传日志一致。

两个独立阻断：

1. mihomo-openclash-core打包调用APK mkpkg，版本 `20261114~alpha.smart.c4df732-r3` 被明确拒绝为 `package version is invalid`，不是下载失败或Smart二进制损坏。前面的版本生成仅做字符串测试，遗漏了APK真实语法验证。
2. Python3.14.10编译 `_ctypes.c` 时缺少 `ffi.h`。feeds安装和元数据阶段已多次报告libffi及libffi/host不存在；诊断配置选择python3-ctypes=m，却没有libffi的实际定义。滚动packages feed依赖本仓库尚未包含的core libffi配方。不能只加一个宿主机头文件路径，也不能以GLib构建过程中出现libffi子项目就认为标准开发文件已正确暂存。

日志中的下载镜像404随后有正常源码回退，不是本轮最终两个致命错误。并行构建在Smart失败后仍输出Python错误，因此两项一并修复，不只处理最后一行。

## 修改

### APK版本

静态Smart配方改为有效的 `20261114_alpha0-r4`。构建更新器按官方资产updated_at生成 `YYYYMMDD.HHMMSS_alpha0`，同日多次更新也能按时间前进；原始alpha-smart-HASH继续保存在PKG_UPSTREAM_VERSION、源文件名、SHA256及插件版本报告中。Smart Alpha通道、官方摘要和ARM64 ELF校验、压缩存储/包装器均保留。

新增真实APK版本检查、空载荷打包、旧格式拒绝和同日/跨日排序测试。标准工具准备后先编译仓库固定APK3.0.5宿主工具并执行此测试，再进入完整固件编译，提前发现版本错误；没有跳过任何签名或后续软件库验证。

### libffi

补入OpenWrt标准core配方 `package/libs/libffi`，固定上游OpenWrt提交 `2777161847b418286c465a0d788ac11ccf9dd514`，libffi3.8.0，保留其22个补丁、宿主构建、目标运行库和InstallDev。源包SHA256 `7da3e2d9a171eb0a038f592ecad3ff2bb2550f3496d87b3b29ad0cf4430c0db4` 已实际下载核验。

配方同时提供目标库、ffi.h/ffitarget.h、pkgconfig以及libffi/host，使Python和GLib等依赖由正常构建系统排序/暂存；没有修改共享feeds链接下的文件，没有添加宿主系统/usr/include绕过交叉依赖。defconfig后的软件库检查在选择python3-ctypes但未选择libffi时明确拒绝，避免缺定义再次被忽略。

原有9个可选插件、中文及27项工具清单不删减，新增项m、不预装的要求不变；libffi作为真实依赖由配置递归选中，而非假称外站库兼容。

## 验证

- 原生APK3.0.9实际拒绝旧版本，接受修正版本；3项版本回归验证真实mkpkg和版本顺序。固定APK3.0.5将在本轮云端完整构建前运行同一测试，本地未冒称使用3.0.5通过。
- libffi3.8.0真实源包验哈希、22个标准补丁应用、本地宿主配置/编译/安装通过；以新安装的ffi.h和libffi.a编译运行ffi_prep_cif/ffi_call，17+25得到42。
- OpenWrt Makefile实际DUMP元数据确认libffi3.8.0-r1及host构建类型；没有执行完整defconfig、修改共享feeds或编译目标固件。
- 更新器5项、软件库10项（新增ctypes/libffi拒绝与通过分支）、真实APK库4项和源码包13入口检查通过；shell/Python语法、workflow YAML和diff检查通过。

这些是原生/配方验证，不等于完整ARM64 Python、固件或实机已经通过。重编仍需检查实际目标构建、同批软件库的全部依赖与最终发布。

## 保留边界

不修改启动时序、procd计时、4秒恢复窗口、内核/HANGDET/Panic/watchdog、QoS默认关闭、500Mbps路径、A/B槽位和签名/Release流程。不向实机执行命令，不实际发送短信/邮件/Webhook，不用旧成功发布替代本轮验证。按用户最新授权推送后开启修复重编并继续本轮监控。

后续云构建43660870689已通过真实ARM64编译及镜像检查，包括本次Smart版本、libffi/Python和固定APK3.0.5的回归；随后在配套库虚拟依赖模拟处失败，未发布固件。该独立后续问题见《2026-11-15APK虚拟依赖验证基线修复》。仍不能据此声称整轮已完成或实机功能已验收。
