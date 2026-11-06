#!/bin/sh
# Run after feeds update and before feeds install / metadata generation.
set -eu
cd "$(dirname "$0")/.."

# This firmware uses only Alpha. Removing Meta's recipe also avoids the
# mutually recursive CONFLICTS declarations in the two upstream recipes.
test -f feeds/nikki/mihomo-alpha/Makefile
test -f feeds/nikki/nikki/Makefile
rm -rf feeds/nikki/mihomo-meta
rm -f package/feeds/nikki/mihomo-meta
sed -i 's/+mihomo\([[:space:]]\|$\)/+mihomo-alpha\1/g' feeds/nikki/nikki/Makefile
grep -q '+mihomo-alpha' feeds/nikki/nikki/Makefile

# Remove the obsolete vendored application and its bundled core from scans.
rm -rf package/vendor/luci-app-openclash package/vendor/mihomo-openclash-core
# These unselected feed recipes have package-local Kconfig option cycles
# with this older buildroot. Refuse to silently drop an explicitly enabled app.
for recipe in video/frameworks/qt5/qt5base luci/applications/luci-app-fwknopd packages/sound/squeezelite; do
    case "$recipe" in
        */qt5base) pattern='qt5base[^=]*' ;;
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
