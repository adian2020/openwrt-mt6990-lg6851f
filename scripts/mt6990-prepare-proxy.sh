#!/bin/sh
# Run after feeds update and before feeds install / metadata generation.
set -eu
cd "$(dirname "$0")/.."

# Keep Nikki available as APKs without preinstalling its service. Meta is
# its installable provider; OpenClash uses the separate bundled Meta core.
test -f feeds/nikki/mihomo-meta/Makefile
test -f feeds/nikki/nikki/Makefile
rm -rf feeds/nikki/mihomo-alpha
rm -f package/feeds/nikki/mihomo-alpha
sed -i 's/+mihomo\([[:space:]]\|$\)/+mihomo-meta\1/g; s/+mihomo-alpha\([[:space:]]\|$\)/+mihomo-meta\1/g' feeds/nikki/nikki/Makefile
grep -q '+mihomo-meta' feeds/nikki/nikki/Makefile

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
