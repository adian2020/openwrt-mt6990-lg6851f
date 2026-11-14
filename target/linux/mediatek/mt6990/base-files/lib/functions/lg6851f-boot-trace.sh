#!/bin/sh
# Small monotonic markers only. No AT, ubus, debugfs, mount or sync here.
lg6851f_bootmark() {
 local boot_uptime boot_rest boot_id trace=/tmp/lg6851f-boot-stages.log
 read -r boot_uptime boot_rest < /proc/uptime || return 0
 [ ! -L "$trace" ] || return 0
 if [ ! -e "$trace" ]; then
  read -r boot_id < /proc/sys/kernel/random/boot_id || boot_id=unknown
  (umask 077; set -C; printf 'LG6851F_BOOT_ID=%s\n' "$boot_id" > "$trace") 2>/dev/null || return 0
 fi
 [ -f "$trace" ] || return 0
 printf 'LG6851F_BOOT_STAGE uptime=%s phase=%s\n' "$boot_uptime" "$*" >> "$trace" 2>/dev/null || :
 # Debug priority permits filtering, but ignore_loglevel can still print to
 # serial. Existing bounded logs retain late markers without new fsyncs.
 if [ -c /dev/kmsg ]; then
  printf '<7>LG6851F_BOOT_STAGE uptime=%s phase=%s\n' "$boot_uptime" "$*" > /dev/kmsg 2>/dev/null || :
 fi
 return 0
}
