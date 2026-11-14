# Pinned procd patch inputs

Unmodified `state.c`, `ubus.c` and `initd/preinit.c` from OpenWrt procd commit
`60fdbf00e924fff0a510c4ec31c520d35e69bfe1`, matching this repository's recipe.
Original copyright and LGPL notices are retained in each file.

These fixtures allow offline, zero-fuzz patch checks. Native tests compile the
patched upstream `ubus.c` with simulated transport and registration functions;
they do not execute PID 1, start ubusd, change mounts or use a real watchdog.
Fixture Git blob hashes are checked so updating the recipe requires reviewing
these inputs and tests together. This is not a full target procd build.
