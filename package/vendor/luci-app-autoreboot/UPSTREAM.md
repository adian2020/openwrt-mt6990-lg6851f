# 来源与适配

界面、菜单、权限和简体中文翻译来自ImmortalWrt LuCI，Apache-2.0：
https://github.com/immortalwrt/luci/tree/319f7c96e3530246cf91cfdd9bacb3fa44dc3a4e/applications/luci-app-autoreboot

默认计划关闭。MT6990后端增加服务端cron字段校验及原子计划更新，仅管理带autoreboot标记的行；无效配置保留旧计划，不修改其他插件的任务，不通过执行重启验证。
