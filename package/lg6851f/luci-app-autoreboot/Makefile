# SPDX-License-Identifier: Apache-2.0
include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI support for Scheduled Reboot
LUCI_DEPENDS:=+luci-base +flock
LUCI_PKGARCH:=all
PKG_RELEASE:=1
PKG_LICENSE:=Apache-2.0

define Package/luci-app-autoreboot/conffiles
/etc/config/autoreboot
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
