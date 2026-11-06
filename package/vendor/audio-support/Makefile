# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 OpenWrt.org
# Audio-only backport of package/system/hardware-support for this older tree.
include $(TOPDIR)/rules.mk

PKG_NAME:=audio-support
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/audio-support
  SECTION:=hardware
  CATEGORY:=Hardware support
  TITLE:=Audio device support
  DEPENDS:=+procd
  PKGARCH:=all
  USERID:=:audio=29 :audio-capture=32 :midi=55
endef

define Build/Compile
endef

define Package/audio-support/install
	$(INSTALL_DIR) $(1)/etc/hotplug.json.d
	$(INSTALL_CONF) ./files/20-audio.json $(1)/etc/hotplug.json.d/
endef

$(eval $(call BuildPackage,audio-support))
