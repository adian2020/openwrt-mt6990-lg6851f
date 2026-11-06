# Copyright (C) 2021 Openwrt.org
#
# This is free software, licensed under the Apache License, Version 2.0 .
#

include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI support for NetEase UU Game Booster
# MT6990 uses the native ARM64 client; keep firewall4's nft providers.
LUCI_DEPENDS:=@aarch64 +kmod-tun +luci-compat +libstdcpp +kmod-ipt-nat +ca-bundle +unshare +ip-full +nftables-json +iptables-nft
PKG_LICENSE:=Apache-2.0

PKG_NAME:=luci-app-uugamebooster
PKG_VERSION:=2.3.1
PKG_RELEASE:=2
PKG_MAINTAINER:=Fork of lmq8267/luci-app-uugamebooster

include $(TOPDIR)/feeds/luci/luci.mk
# call BuildPackage - OpenWrt buildroot signature
