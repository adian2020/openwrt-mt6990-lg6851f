#!/bin/sh
# Add the pinned interpreter's digest module to its host-only test runtime.
# The target package remains OpenWrt's ucode-mod-digest; no target crypto fork.
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${UCODE:?Set UCODE to the pinned host interpreter}"
: "${UCODE_LIBRARY:?Set UCODE_LIBRARY to its native module directory}"
set -- "$repo_dir"/build_dir/hostpkg/ucode-*/lib/digest.c
[ "$#" -eq 1 ] && [ -f "$1" ] || { echo 'ERROR: expected exactly one pinned host ucode digest source' >&2; exit 1; }
${CC:-cc} -shared -fPIC -O2 -I"$repo_dir/staging_dir/hostpkg/include" \
 "$1" -lmd -o "$UCODE_LIBRARY/digest.so"
"$UCODE" -L "$UCODE_LIBRARY" -e 'import {sha256} from "digest"; if(sha256("abc")!="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")die("SHA256 self-test failed");'
