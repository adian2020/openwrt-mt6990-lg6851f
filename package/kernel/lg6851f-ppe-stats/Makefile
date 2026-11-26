include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=lg6851f-ppe-stats
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
HNAT_SOURCE:=$(TOPDIR)/package/vendor/mt6990-hwnat/src
HNAT_SYMVERS:=$(KERNEL_BUILD_DIR)/symvers/mt6990-hwnat.symvers
PKG_FILE_DEPENDS:=$(HNAT_SOURCE) $(HNAT_SYMVERS)

include $(INCLUDE_DIR)/package.mk

define KernelPackage/lg6851f-ppe-stats
  SUBMENU:=Network Devices
  TITLE:=LG6851F read-only PPE table occupancy
  DEPENDS:=@TARGET_mediatek_mt6990 +kmod-mt6990-hwnat
  FILES:=$(PKG_BUILD_DIR)/lg6851f_ppe_stats.ko
  AUTOLOAD:=$(call AutoProbe,lg6851f_ppe_stats)
endef

define Build/Prepare
	$(CP) ./src/. $(PKG_BUILD_DIR)/
	sed -n '/^ccflags-y += -D/p' "$(HNAT_SOURCE)/Makefile" >> "$(PKG_BUILD_DIR)/Makefile"
endef

define Build/Compile
	test -s "$(HNAT_SYMVERS)"
	+$(KERNEL_MAKE) $(PKG_JOBS) M="$(PKG_BUILD_DIR)" HNAT_SOURCE="$(HNAT_SOURCE)" \
		KBUILD_EXTRA_SYMBOLS="$(HNAT_SYMVERS)" modules
endef

$(eval $(call KernelPackage,lg6851f-ppe-stats))
