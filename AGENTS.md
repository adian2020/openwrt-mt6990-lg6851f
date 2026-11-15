# 维护说明的语言

- Git commit titles and bodies use English, as requested by the user.
- 固件发布标题、更新说明、修复说明和面向用户的修改摘要使用简体中文。
- 插件名称、命令、文件路径、版本号和提交编号保留原文，便于核对。
- Automatically generated package commit messages also use English.
- RELEASE_NOTES.md 只记录相对上次已发布版本的新增、修改和删除；不累计历史过程、旧版功能或测试流水。发布后为下一版本重新整理。历史说明保存于 docs，运行中构建的补充说明放在 docs/releases/<完整源码SHA>.md，不以新分支版本冒充旧构建。
- docs/FIRMWARE_HISTORY.md 按版本保存已发布固件的实际发布时间及更新内容；新 Release 正文顶部先放该文档链接，下面列本版改动。发布成功后自动补入历史，时间取 GitHub published_at（明确标注 UTC），未发布运行不预填版本或时间。
- 固件源码和编译工作在 cloud-build 分支进行；main 的修改范围须遵守用户授权。
