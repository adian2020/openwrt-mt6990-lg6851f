# cloud-build: File Manager and UU Game Booster

UU source: https://github.com/xiaodoudou/luci-app-uugamebooster
User-provided mirror: https://tvwatch.su/xiaodoudou/luci-app-uugamebooster
Vendored revision: `2be324a780053ac2567d0ed96dedc68b6b90ffbf` (2.3.1).
Read the upstream README and docs/builds.md, docs/device-list.md,
docs/firewall.md, and docs/testing.md before updating this package.

## Build integration

The existing cloud-build workflow remains the entry point: save .config,
update feeds, prepare packages, install feeds, restore .config, make defconfig,
then scripts/mt6990-build-and-record.sh (make -j4 V=s and image verification).

- File Manager comes from the existing LuCI feed, with its Chinese translation.
- UU's scripts, Lua views and Chinese translation are vendored under
  package/vendor/luci-app-uugamebooster.
- This integration targets aarch64 only. LuCI builds src/uu-view-preload.c with
  OpenWrt's target compiler and installs uu-view-preload-aarch64.so, covering
  both the native generic client and the native h3c-nx30pro vendor client.
  The package therefore uses the target architecture, not upstream's `all`.
  Zig, five foreign-architecture shims, QEMU and a foreign sysroot are unnecessary
  for these two native ARM64 paths. ARM32 h3c-bx54 is not supported on this image.
- Use this source tree's libstdcpp (ABI 6), ip-full, nftables-json and
  iptables-nft instead of the upstream libstdcpp6 name and virtual providers.
  kmod-tun, kmod-ipt-nat, luci-compat, ca-bundle and unshare remain dependencies.
  The kernel already enables namespaces required by the device view.
- Script executable bits are set at build time; LuCI's standard post-install
  hook is retained instead of upstream's unconditional chmod of live /etc.

## First use and limits

UU remains disabled until enabled in Services / UU Game Booster. The default
is the generic console-only client. For PC/phone boosting, upstream describes
selecting the native h3c-nx30pro vendor client. On first start the service
requires Internet access to download the official core and verify its MD5.
No official UU binary is bundled or redistributed here. Binding and use
require the NetEase UU app/account.

Keep the upstream tunnel firewall option enabled (addfw=1). OpenClash
integration defaults to off because this firmware uses Nikki + Mihomo Alpha;
OpenClash is not installed. Upstream's OpenClash/UA3F coexistence does not
establish Nikki compatibility. Concurrent acceleration and Nikki policy routing
must be verified on an LG6851F; building the package cannot establish that.
