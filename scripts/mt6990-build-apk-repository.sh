#!/bin/sh
# Keep the documented entry point; validation and metadata are shared with CI.
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=${1:-"$repo_dir/bin/mt6990-apk-repository"}
rootfs="$repo_dir/build_dir/target-aarch64_cortex-a55+neon-vfpv4_musl/root-mediatek"
exec python3 "$repo_dir/scripts/mt6990-apk-library.py" bundle --output "$output" --rootfs "$rootfs"
