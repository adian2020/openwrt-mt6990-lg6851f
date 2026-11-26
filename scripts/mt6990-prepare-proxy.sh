#!/bin/sh
# Run after feeds update and before feeds install / metadata generation.
set -eu
cd "$(dirname "$0")/.."

# The Pro tree contains the four optional Nikki recipes. Do not install feed
# variants with the same package names over the imported copies.
for package in nikki luci-app-nikki luci-i18n-nikki-zh-cn mihomo-meta; do
    test -f "package/vendor/$package/Makefile"
    rm -f "package/feeds/nikki/$package"
done
rm -rf feeds/nikki/mihomo-alpha
rm -f package/feeds/nikki/mihomo-alpha

# These unselected feed recipes have package-local Kconfig option cycles
# with this older buildroot. Refuse to silently drop an explicitly enabled app.
for recipe in video/frameworks/qt5/qt5base video/frameworks/qt6/qt6base luci/applications/luci-app-fwknopd packages/sound/squeezelite; do
    case "$recipe" in
        */qt5base) pattern='qt5base[^=]*' ;;
        # EGLFS -> DRM -> GUI -> OpenGL -> EGLFS also cycles when unselected.
        # All Qt6 users need qt6base, so reject any explicit Qt6 selection.
        */qt6base) pattern='qt6[^=]*' ;;
        */luci-app-fwknopd) pattern='luci-app-fwknopd' ;;
        */squeezelite) pattern='squeezelite[^=]*' ;;
    esac
    if grep -Eq "^CONFIG_PACKAGE_($pattern)=[ym]$" .config; then
        echo "ERROR: $recipe needs a Kconfig compatibility fix before enabling" >&2
        exit 1
    fi
    rm -rf "feeds/$recipe"
done
rm -rf tmp
./scripts/feeds update -i nikki video luci packages
