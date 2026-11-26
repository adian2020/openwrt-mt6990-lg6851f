# Both the generic and h3c-nx30pro clients run natively as aarch64 on MT6990.
# Use OpenWrt's target compiler and musl instead of shipping foreign binaries.
CFLAGS ?= -O2

.PHONY: clean compile install
compile: uu-view-preload-aarch64.so

uu-view-preload-aarch64.so: uu-view-preload.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(FPIC) -fPIC -Wall -shared $(LDFLAGS) -o $@ $< -ldl

install: compile
	install -d $(DESTDIR)/usr/lib/uuplugin
	install -m 755 uu-view-preload-aarch64.so $(DESTDIR)/usr/lib/uuplugin/

clean:
	rm -f uu-view-preload-aarch64.so
