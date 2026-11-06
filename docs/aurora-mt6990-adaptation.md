# Aurora 与 MT6990 CPE 适配记录

参考：adian2020/mu300-linux 的 minikano-openwrt-feats 分支，
openwrt/AURORA.md 与 openwrt/luci-app-mu300/Makefile。

Aurora 与 MU300 控制中心是独立项目。主题采用 eamonxg/luci-theme-aurora
v1.4.0，提交 84c27b66952e6fc4be60128067a6b88bfd34afb5；配置面板采用
eamonxg/luci-app-aurora-config v1.2.5，提交
a5299ce0144859f47683ec3bc40805bf616f534f。仅将其 Makefile、界面、模板、
配置文件、语言文件及许可证放入 package/vendor，不携带开发工具目录。

luci-app-mu300 的 Unisoc 后台包含串口/RIL、充电、电压、OTA、TTL 等硬件
操作，不能直接安装到 MT6990。当前 CPE 仪表盘复用 luci.modem5g 的已适配
状态接口与原生流量统计；没有宣称完整移植 MU300 控制中心。

Aurora 配置面板位于“系统”，支持其上游模板及样式配置。5G 控制仍位于
独立的“5G 模组”，不在“当前网络”添加第二个入口。

本地检查：

    python3 scripts/tests/test_lg6851f_upgrade_state.py
    python3 scripts/tests/test_lg6851f_radio.py

具有 Playwright 和 Chromium 的开发环境可另运行：

    node scripts/tests/test_lg6851f_layout.cjs

布局检查使用模拟 RPC 数据，不连接路由器，不执行锁频、刷机或射频命令。
射频测试只模拟厂商传输层，不代表实机已完成网络注册。

升级钩子必须保持 79_lg6851f_restore_sysupgrade 在 80_mount_root 前注册
preinit_main 的迁移操作。只有复制 sysupgrade 备份到已挂载根目录的动作
注册到 preinit_mount_root。不得再次把活动 upperdir 的移动放到挂载之后。
