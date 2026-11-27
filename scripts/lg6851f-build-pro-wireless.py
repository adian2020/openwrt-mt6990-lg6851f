#!/usr/bin/env python3
"""Build the pinned LG6851F-Pro wireless stack against this target's kernel."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


PRO_REVISION = "0e1518ed632388e814032e0831560d22d9488981"
PRO_BUILD_REVISION = "b942f071af127ece3d40321aca41f4f96f2ab800"
REPAIR_SOURCE = "development-history/systemfix-source/systemfix-20261021-30/driver-build/repair-source"
RX_REPAIR = "development-history/V2.10/wifi-rebuild/patch-source.py"
HOSTAPD_SOURCE = "development-history/V2.10/hostapd-native"
IMAGE_RUNTIME = (
    "etc/config/wireless", "etc/init.d/lg6851f-vendor618", "etc/init.d/lg6851f_hostapd",
    "etc/init.d/wpad", "etc/uci-defaults/zzzz-lg6851f-public-firstboot",
    "etc/lg6851f-vendor618/firmware", "etc/lg6851f-vendor618/wireless",
    "lib/netifd/hostapd.sh", "lib/netifd/netifd-wireless.sh", "lib/netifd/vendor618-client64.sh",
    "lib/netifd/wireless-device.uc", "lib/netifd/wireless.uc", "lib/netifd/wireless/vendor618.sh",
    "usr/libexec/lg6851f-detach", "usr/sbin/lg6851f-auth-recover", "usr/sbin/lg6851f-hostapd-ctl",
    "usr/sbin/lg6851f-hostapd-run", "usr/sbin/lg6851f-mwctl", "usr/sbin/lg6851f-public-calibration",
    "usr/sbin/lg6851f-vendor618-start", "usr/sbin/lg6851f-wifi-power",
    "usr/share/rpcd/acl.d/luci-lg6851f-wifi-power.json", "usr/share/rpcd/acl.d/luci-vendor618-wireless.json",
    "usr/share/ucode/lg6851f/auth-plan.uc", "usr/share/ucode/lg6851f/bss-fingerprint.uc",
    "usr/share/ucode/lg6851f/bss-prepare.uc", "usr/share/ucode/lg6851f/client64-plan.uc",
    "usr/share/ucode/lg6851f/mlo-policy.uc", "usr/share/ucode/lg6851f/prepare-wireless-profile.uc",
    "usr/share/ucode/lg6851f/wifi-power-cli.uc", "usr/share/ucode/lg6851f/wifi-power-engine.uc",
    "usr/share/ucode/lg6851f/wifi-power-model.uc", "usr/share/ucode/wifi/hostapd.uc",
    "www/luci-static/resources/view/network/wireless.js",
)
PARTS = {
    "coex": ("wifi_md_coex", ("wifi_md_coex",)),
    "cmn": ("mt_wifi_cmn", ("mt_wifi_cmn",)),
    "warp": ("wifi/warp_driver/warp", ("mtk_warp",)),
    "wifi": ("wifi/mt_wifi_ap", ("mt_wifi",)),
    "hwifi": ("wifi/wlan_hwifi", ("mtk_hwifi", "connac_if", "mtk_pci", "mtk_wed", "mt7990", "mt7991")),
}
BACKPORT_HEADERS = (
    "mac80211-backport", "mac80211-backport/uapi", "mac80211", "mac80211/uapi",
)
ROOT = Path(__file__).resolve().parents[1]
DTS = ROOT / "target/linux/mediatek/dts/mt6990-fiberhome-lg6851f-pro-warp.dts"


def require_file(path):
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"缺少有效构建输入 {path}")


def extract_source(repository, work, revision, paths):
    with subprocess.Popen(
        ["git", "-C", str(repository), "archive", revision, *paths],
        stdout=subprocess.PIPE,
    ) as archive:
        with tarfile.open(fileobj=archive.stdout, mode="r|") as source:
            source.extractall(work, filter="data")
        if archive.wait():
            raise ValueError(f"无法导出 Pro 源提交 {revision}")


def prepare_wifi_source(work):
    path = work / "vendor-source/wifi/mt_wifi/hw_ctrl/hwifi_main.c"
    source = path.read_bytes()
    before = b'#include "debug.h"\n#include "rt_config.h"'
    after = b'#include "rt_config.h"\n#include "debug.h"'
    if source.count(before) != 1:
        raise ValueError(f"厂商 Wi-Fi 头文件顺序与固定源码不符 {path}")
    # debug.h uses vendor typedefs declared through rt_config.h.
    path.write_bytes(source.replace(before, after))


def prepare_repairs(args):
    work = args.work_dir
    extract_source(args.vendor_repo, work, PRO_BUILD_REVISION,
                   [REPAIR_SOURCE, RX_REPAIR, "scripts/cloud/vendor_repair.py", "scripts/cloud/elf64.py"])
    wifi = work / "vendor-source/wifi/mt_wifi_ap"
    shutil.copytree(work / REPAIR_SOURCE, wifi / "cloud-repairs")
    with (wifi / "Makefile").open("a", encoding="utf-8") as makefile:
        makefile.write("\n$(MOD_NAME)-objs += cloud-repairs/parser-repair.o cloud-repairs/action-repair.o "
                       "cloud-repairs/pmksa-repair.o\n")
    receive = work / "vendor-source/wifi/mt_wifi/ap/ap_data.c"
    if b"An authenticated STA may send a complete" not in receive.read_bytes():
        subprocess.run([sys.executable, work / RX_REPAIR, receive], check=True)
    cfg = work / "vendor-source/wifi/mt_wifi/os/linux/cfg80211/cfg80211.c"
    source = cfg.read_bytes()
    old = b"(sizeof(u32)+sizeof(u32))*6, vendor_event, GFP_KERNEL)"
    new = b"(sizeof(u32)+sizeof(u32))*6, vendor_event - 1, GFP_KERNEL)"
    if source.count(old) != 1:
        raise ValueError("厂商雷达事件源码与固定版本不符")
    cfg.write_bytes(source.replace(old, new))


def build_dtb(args, environment):
    preprocessed = args.work_dir / "pro-warp.pp.dts"
    dtb = args.work_dir / "pro-warp.dtb"
    log_path = args.work_dir / "dtb.log"
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(
            [args.cross_compile + "gcc", "-E", "-nostdinc", "-undef", "-D__DTS__",
             "-x", "assembler-with-cpp", "-I", args.kernel / "include", DTS, "-o", preprocessed],
            env=environment, stderr=log, check=True,
        )
        subprocess.run(
            [args.kernel / "scripts/dtc/dtc", "-q", "-I", "dts", "-O", "dtb", "-o", dtb, preprocessed],
            env=environment, stderr=log, check=True,
        )
    require_file(dtb)
    print(dtb, flush=True)


def build_part(args, part, sources, includes, config, environment):
    path = sources[part]
    names = PARTS[part][1]
    flags = [f"-I{args.staging / 'usr/include' / header}" for header in BACKPORT_HEADERS]
    flags += ["-DBACKPORT_NOSTDINC", "-include", "backport/backport.h"]
    settings = {}
    symvers = args.kernel.parent / "symvers"
    symbols = [symvers / "mac80211.symvers"]

    if part == "coex":
        flags = [f"-I{args.kernel / 'drivers/misc/mediatek/include'}",
                 "-DCOEX_DIRECT_PATH", "-DCONFIG_WIFI_MD_COEX_SUPPORT=1"]
        symbols = []
        settings = {"CONFIG_SUPPORT_OPENWRT": "y", "CONFIG_COEXISTENCE_SUPPORT": "m"}
    elif part == "cmn":
        flags += ["-DMT_WIFI_COMMON_SUPPORT", "-DRT_CFG80211_SUPPORT", f"-I{path}"]
    elif part == "warp":
        flags = []
        symbols = []
        settings = {
            "CONFIG_WARP_VERSION": "2", "CONFIG_WARP_CHIPSET": "mt6990",
            "CONFIG_WARP_WO_EMBEDDED_LOAD": "y", "CONFIG_WED_HW_RRO_SUPPORT": "y",
            "CONFIG_WARP_DBG_SUPPORT": "y", "CONFIG_ARCH_MEDIATEK": "y",
            "PKG_BUILD_DIR": f"{path}/",
        }
    elif part == "wifi":
        flags += ["-DMT_WIFI_COMMON_SUPPORT", f"-I{path.parent}", f"-I{path.parent / 'include'}",
                  f"-I{includes / 'mtk_nl80211_inc'}", "-include", str(includes / "vendor618_wext.h")]
        settings = {f"CONFIG_{key}": value for key, value in config.items()}
        settings.update(CFG_CFG80211_VERSION="6.18.0", LINUX_DIR=str(args.kernel.parent))
        symbols += [sources[name] / "Module.symvers" for name in ("cmn", "coex")]
        symbols.append(symvers / "mt6990-hwnat.symvers")
    else:  # hwifi
        flags.append("-DMT_WIFI_COMMON_SUPPORT")
        settings = {
            "CONFIG_SUPPORT_OPENWRT": "y", "CONFIG_HWIFI_HIF_WED": "m",
            "CONFIG_HWIFI_HIF_NPU": "n", "CONFIG_HWIFI_MD_COEX_SUPPORT": "y",
        }
        for chip in ("MT7915", "MT7916", "BELLWETHER", "MT7992", "MT799A", "MT7993", "MT799B"):
            settings[f"CONFIG_HWIFI_CHIP_{chip}"] = "n"
            settings[f"CONFIG_HWIFI_CHIP_{chip}_DBG"] = "n"
        symbols += [sources[name] / "Module.symvers" for name in ("cmn", "wifi", "warp", "coex")]

    if not args.objects:
        for table in symbols:
            require_file(table)
    command = ["make", "-C", str(args.kernel), f"-j{args.jobs}", "ARCH=arm64",
               f"CROSS_COMPILE={args.cross_compile}", f"M={path}", "CONFIG_WERROR=n"]
    command += [f"{key}={value}" for key, value in settings.items()]
    command += [f"KCFLAGS=-Wno-error -include {includes / 'vendor618_compat.h'}",
                "NOSTDINC_FLAGS=" + " ".join(flags)]
    if args.objects:
        command += [f"{module}.o" for module in names]
    else:
        command += ["KBUILD_EXTRA_SYMBOLS=" + " ".join(map(str, symbols)),
                    "KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=", "modules"]

    log_path = args.work_dir / f"{part}.log"
    print(f"{part} → {log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f"{part} 构建失败，退出码 {result.returncode}，日志 {log_path}")
    suffix = "o" if args.objects else "ko"
    if part == "wifi" and not args.objects:
        subprocess.run([sys.executable, args.work_dir / "scripts/cloud/vendor_repair.py", path / "mt_wifi.ko",
                        args.work_dir / "driver-repair.json"], env=environment, check=True)
    for module in names:
        output = path / f"{module}.{suffix}"
        require_file(output)
        header = subprocess.check_output(["readelf", "-h", output], env=environment, text=True)
        if "AArch64" not in header:
            raise ValueError(f"产物架构不匹配 {output}")
        if not args.objects:
            metadata = subprocess.check_output(["readelf", "-p", ".modinfo", output], env=environment, text=True)
            release = (args.kernel / "include/config/kernel.release").read_text().strip()
            if f"vermagic={release} " not in metadata:
                raise ValueError(f"模块 vermagic 不匹配 {output}")
        print(output, flush=True)


def build_hostapd(args, includes, environment):
    extract_source(args.vendor_repo, args.work_dir, PRO_BUILD_REVISION, [HOSTAPD_SOURCE])
    tree = args.work_dir / HOSTAPD_SOURCE
    staging = args.staging / "usr"
    env = dict(environment, PKG_CONFIG_LIBDIR=str(staging / "lib/pkgconfig"),
               PKG_CONFIG_SYSROOT_DIR=str(args.staging),
               LDFLAGS=f"-L{staging / 'lib'} -Wl,-rpath-link,{args.staging / 'lib'} "
                       f"-Wl,-rpath-link,{staging / 'lib'}")
    command = ["make", "-C", tree / "hostapd", f"-j{args.jobs}", f"CC={args.cross_compile}gcc",
               "CONFIG_LIBNL32=y", "CONFIG_TLS=openssl", f"LIBNL_INC={staging / 'include/libnl3'}",
               f"EXTRA_CFLAGS=-I{staging / 'include'} -I{includes / 'mtk_nl80211_inc'} "
               f"-I{tree / 'wpa_supplicant'}", "hostapd"]
    log_path = args.work_dir / "hostapd.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f"厂商 hostapd 构建失败，日志 {log_path}")
    output = args.work_dir / "lg6851f-hostapd"
    shutil.copyfile(tree / "hostapd/hostapd", output)
    output.chmod(0o755)
    subprocess.run([args.cross_compile + "strip", "--strip-debug", output], env=env, check=True)
    header = subprocess.check_output(["readelf", "-h", output], env=env, text=True)
    libraries = subprocess.check_output(["readelf", "-d", output], env=env, text=True)
    required = ("libnl-3", "libnl-genl-3", "libssl", "libcrypto", "libubox", "libubus")
    if "AArch64" not in header or any(f"[{library}.so" not in libraries for library in required):
        raise ValueError("厂商 hostapd 的 ARM64 架构或目标动态链接库不符")
    print(output, flush=True)


def stage_image(args, sources, environment):
    work = args.work_dir / "image-runtime"
    work.mkdir()
    extract_source(args.vendor_repo, work, PRO_BUILD_REVISION, [f"files/{path}" for path in IMAGE_RUNTIME])
    payload = work / "files"
    vendor = payload / "etc/lg6851f-vendor618"
    (vendor / "firmware/MT7990_EEPROM.bin").unlink()
    for calibration in (vendor / "wireless/mediatek").glob("e2p*"):
        calibration.unlink()
    shutil.rmtree(vendor / "wireless/sigma_test")

    start = payload / "usr/sbin/lg6851f-vendor618-start"
    script = start.read_text()
    slot_gate = "grep -q 'bootslot=b' /proc/cmdline\n"
    handoff = "touch /tmp/lg6851f-vendor618-ready\n/usr/bin/timeout -k 2 15 ubus call network.wireless up\n"
    health_start = "n=0\nuntil /usr/sbin/lg6851f-a-mark-healthy --now; do\n"
    health_end = "stage 'check both WO processors'\n"
    if any(script.count(text) != 1 for text in (slot_gate, handoff, health_start, health_end)):
        raise ValueError("固定 Pro 启动脚本的槽位、交接或确认流程与预期不符")
    script = script.replace(slot_gate, "/usr/sbin/lg6851f-prepare-vendor-wireless\n", 1)
    script = script.replace(handoff, "", 1)
    script = script[:script.index(health_start)] + script[script.index(health_end):]
    script, end, _ = script.partition('if [ -e "$cfg/enabled" ]; then\n')
    if not end:
        raise ValueError("固定 Pro 启动脚本的持久标记流程与预期不符")
    start.write_text(script + "touch /tmp/lg6851f-vendor618-ready\n/usr/bin/timeout -k 2 15 /sbin/wifi up\n")

    materials = ROOT / "package/lg6851f/pro-material"
    for filename, where in (("vendor618-prepare.init", "etc/init.d/lg6851f-vendor618-prepare"),
                            ("prepare-vendor-wireless.sh", "usr/sbin/lg6851f-prepare-vendor-wireless")):
        shutil.copyfile(materials / filename, payload / where)
        (payload / where).chmod(0o755)
    rc = payload / "etc/rc.d"
    rc.mkdir()
    for order, name in (("S01", "lg6851f-vendor618-prepare"), ("S19", "lg6851f_hostapd"),
                        ("K20", "lg6851f_hostapd"), ("S95", "lg6851f-vendor618")):
        (rc / (order + name)).symlink_to(f"../init.d/{name}")

    modules = payload / "usr/lib/lg6851f-vendor618/modules"
    modules.mkdir(parents=True)
    for part, (_, names) in PARTS.items():
        for name in names:
            filename = name + ".ko"
            subprocess.run([args.cross_compile + "strip", "--strip-debug", sources[part] / filename,
                            "-o", modules / filename], env=environment, check=True)
    shutil.copy2(args.work_dir / "lg6851f-hostapd", payload / "usr/sbin/lg6851f-hostapd")
    shutil.copytree(payload, args.image_overlay, dirs_exist_ok=True, symlinks=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-repo", required=True, type=Path, help="local LG6851F-Pro Git repository")
    parser.add_argument("--kernel", required=True, type=Path, help="prepared target Linux 6.18.44 directory")
    parser.add_argument("--staging", required=True, type=Path, help="matching OpenWrt target staging directory")
    parser.add_argument("--cross-compile", required=True, help="ARM64 cross-compiler prefix, including trailing -")
    parser.add_argument("--work-dir", required=True, type=Path, help="new or empty output directory")
    parser.add_argument("--objects", action="store_true", help="compile linked objects without module ABI checks")
    parser.add_argument("--hostapd", action="store_true", help="also rebuild the vendor hostapd with target libraries")
    parser.add_argument("--image-overlay", type=Path, help="stage the experimental vendor wireless image overlay")
    parser.add_argument("-j", "--jobs", type=int, default=4)
    args = parser.parse_args()
    args.kernel = args.kernel.resolve()
    args.staging = args.staging.resolve()
    args.work_dir = args.work_dir.resolve()

    if args.image_overlay and (args.objects or not args.hostapd):
        parser.error("--image-overlay requires the ABI-checked module and hostapd builds")

    try:
        if args.jobs < 1:
            raise ValueError("编译并行数须为正整数")
        if not shutil.which(args.cross_compile + "gcc") or not shutil.which("readelf"):
            raise ValueError("缺少 ARM64 GCC 或 readelf")
        require_file(args.kernel / "include/config/kernel.release")
        release = (args.kernel / "include/config/kernel.release").read_text().strip()
        if release.split("-", 1)[0] != "6.18.44":
            raise ValueError(f"内核版本应为 6.18.44，实际为 {release}")
        require_file(args.staging / "usr/include/mac80211-backport/backport/backport.h")
        if not args.objects:
            for table in (args.kernel / "Module.symvers", args.kernel.parent / "symvers/mac80211.symvers",
                          args.kernel.parent / "symvers/mt6990-hwnat.symvers"):
                require_file(table)
        args.work_dir.mkdir(parents=True, exist_ok=True)
        if next(args.work_dir.iterdir(), None) is not None:
            raise ValueError(f"输出目录须为空 {args.work_dir}")
        environment = dict(os.environ, STAGING_DIR=str(args.staging), LC_ALL="C")
        build_dtb(args, environment)
        extract_source(args.vendor_repo, args.work_dir, PRO_REVISION,
                       ["vendor-source", "vendor-include", "vendor-config.json"])
        prepare_wifi_source(args.work_dir)
        if not args.objects:
            prepare_repairs(args)
        config = json.loads((args.work_dir / "vendor-config.json").read_text())
        sources = {part: args.work_dir / "vendor-source" / path for part, (path, _) in PARTS.items()}
        includes = args.work_dir / "vendor-include"
        for part in PARTS:
            build_part(args, part, sources, includes, config, environment)
        if args.hostapd:
            build_hostapd(args, includes, environment)
        if args.image_overlay:
            stage_image(args, sources, environment)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
