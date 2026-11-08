include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI MT6990 integrated 5G modem management
LUCI_DESCRIPTION:=Manage the integrated MT6990 5G modem, cellular status, SMS, network mode and AT commands
LUCI_DEPENDS:=@TARGET_mediatek_mt6990 +luci-base +rpcd-mod-ucode +rpcd-mod-iwinfo +ucode-mod-uci +ucode-mod-fs +ucode-mod-ubus +ucode-mod-uloop +lg6851f-modem-chain-only +iwinfo +curl +ca-bundle +coreutils-sha256sum +@LIBCURL_SMTP +@LIBCURL_HTTP
LUCI_PKGARCH:=all
LUCI_MINIFY_JS:=0
PKG_RELEASE:=16
PKG_BUILD_DEPENDS:=ucode/host

PKG_LICENSE:=Apache-2.0
PKG_MAINTAINER:=OpenWrt MT6990 LG6851F integration

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
