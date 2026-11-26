include $(TOPDIR)/rules.mk

PKG_NAME:=lg6851f-ipv6-prefix
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/lg6851f-ipv6-prefix
  SECTION:=net
  CATEGORY:=Network
  TITLE:=LG6851F cellular IPv6 prefix calculator
  DEPENDS:=@TARGET_mediatek_mt6990
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) \
		-o $(PKG_BUILD_DIR)/lg6851f-ipv6-prefix $(PKG_BUILD_DIR)/ipv6-prefix.c
endef

define Package/lg6851f-ipv6-prefix/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/lg6851f-ipv6-prefix $(1)/usr/bin/
endef

$(eval $(call BuildPackage,lg6851f-ipv6-prefix))
