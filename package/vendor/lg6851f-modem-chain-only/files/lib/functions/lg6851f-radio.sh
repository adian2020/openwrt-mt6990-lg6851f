#!/bin/sh
# netifd owns startup. Share LuCI/status's CMIPC6 lock and its close cooldown.
lg6851f_radio_transaction() {
	local output rc
	exec 9>"${LG6851F_RADIO_LOCK:-/var/lock/luci-modem5g-control.lock}"
	flock -n 9 || return 75
	output="$(timeout 10 "${LG6851F_MIPC_CLI:-/usr/bin/mipc_wan_cli}" "$@" 2>&1)"
	rc=$?
	sleep 6
	flock -u 9
	exec 9>&-
	printf '%s\n' "$output"
	return "$rc"
}

lg6851f_ensure_radio_on() {
	local attempt=0 state
	while [ "$attempt" -lt 5 ]; do
		[ "$(uci -q get network.modem5g.radio_enabled 2>/dev/null)" != 0 ] || return 2
		state="$(lg6851f_radio_transaction --nw_radio_state_get)"
		case "$state" in *MIPC_NW_RADIO_STATE_ON*) return 0 ;; esac
		lg6851f_radio_transaction --nw_radio_state_set 1 || :
		attempt=$((attempt + 1))
		state="$(lg6851f_radio_transaction --nw_radio_state_get)"
		case "$state" in *MIPC_NW_RADIO_STATE_ON*) return 0 ;; esac
		sleep 3
	done
	logger -t ql_datacall "radio did not become ready after $attempt serialized attempts"
	return 1
}
