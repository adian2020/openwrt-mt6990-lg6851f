#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

fail() {
	logger -t lg6851f-vendor618 "$1"
	exit 1
}

# This netifd backend assigns its 2 GHz and 5 GHz interfaces to these names.
[ "$(uci -q get wireless.radio0.band)" = 2g ] &&
	[ "$(uci -q get wireless.radio1.band)" = 5g ] || fail '无线配置与厂商双频映射不符，保留原配置'

type0=$(uci -q get wireless.radio0.type)
type1=$(uci -q get wireless.radio1.type)
case "$type0:$type1" in
	vendor618:vendor618|mac80211:mac80211) ;;
	*) fail '无法识别原有无线驱动类型，保留原配置' ;;
esac

if uci -q show wireless | grep -Eq '(LG6851F-PUBLIC-|PUBLIC-FIRSTBOOT-REPLACES-THIS)'; then
	fail '公开版随机密码尚未初始化'
fi

[ "$type0" = mac80211 ] || exit 0
uci -q batch <<'EOF'
set wireless.radio0.type=vendor618
set wireless.radio1.type=vendor618
commit wireless
EOF
