# Modem, LEDs, proxy packages and upgrade behavior

The 5G UI and LED service share lg6851f-modem-chain-only. Current alsa-lib
requires audio-support; the older base tree did not define that package.
Kconfig consequently disabled the entire modem chain and UI despite `=y` in
the seed. The audio-only backport from OpenWrt's hardware-support package
restores this dependency. The workflow now requires both packages and checks
modem menu/RPC files, the LED daemon, SFTP and OpenClash's core in rootfs.

The 5G page is also linked from Network / 5G Modem. Upgrades clear LuCI caches
and enable the modem status and network LED services. Missing cellular LED
nodes no longer terminate WiFi LED updates. WiFi detection supports wireless
interfaces with custom names/bridges. Cellular RAT data is reset each poll to
avoid showing stale 4G/5G state. Physical jack LED behavior remains a hardware
validation item; no unverified PHY register values are written.

## Packages

OpenClash and mihomo-openclash-core (the existing pinned Meta binary) are
preinstalled. Nikki, its LuCI UI/translation, and mihomo-meta are built as
optional APKs (`m`) and excluded from rootfs. Nikki's runtime dependencies,
including yq and the netfilter/TUN/dummy modules, remain preinstalled.
The successful workflow publishes the signed Nikki feed under nikki-apk at an
immutable directory named for the source commit. The firmware points APK at
that exact directory. Its signature is produced with the same build key trusted
by that firmware. The official Nikki feed has no Cortex-A55/neon-vfpv4 target;
no generic or rolling kernel feed is mixed in.

After the feed publication succeeds:

    apk update
    apk add --simulate nikki luci-app-nikki luci-i18n-nikki-zh-cn

Stop OpenClash before enabling Nikki; the two proxy services must not compete.
SFTP uses openssh-sftp-server with existing Dropbear authentication on SSH port
22; no second SSH daemon, new password, or extra firewall exposure is added.

## Settings and old plugins after sysupgrade

Previously the preinit hook rebound the old P46 upper/work to every new rootfs,
even when sysupgrade had no configuration backup. This retained APK databases,
old executables and whiteouts which could hide newly bundled files.

The updated preinit archives the old software layer under
`openwrt-extroot-backups/upgrade-<rootfs-uuid>` and starts a fresh upper/work.
Archives are not mounted. Keep-settings upgrades restore the normal
sysupgrade.tgz; no-settings upgrades remove any stale backup. A verified
successful upgrade records its keep/reset policy and slot for the next boot.
On the first migration from older firmware, a changed rootfs UUID detects the
upgrade and an existing sysupgrade backup selects keep mode.

Both modes retain only `/etc/config/lg6851f_network_led` and `config led`
sections from `/etc/config/system`. Network, passwords and other system
settings are not retained in reset mode. Built-in applications remain present
because they are in the new ROM; previously installed APKs are not replayed.
The explicit factory-reset path still clears all settings, including LEDs.
Backups and user data on P46 are not formatted. Old inactive software archives
may be removed separately after validating the new firmware.
