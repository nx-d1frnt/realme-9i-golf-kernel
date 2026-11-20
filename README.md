# GolfCore — Realme 9i 4G (`RMX3491` / `khaje` / `bengal`)

Custom Linux `4.19.157-GolfCore-v0.6-susfs` kernel for **Realme 9i 4G (Snapdragon 680 / SM6225)** with **KernelSU-Next**, **SUSFS 1.5.5 NON-GKI**, **Clang ThinLTO**, **TCP BBRv2**, **MGLRU**, and reproducible vendor module rebuilding.

Prebuilt images (`AnyKernel3.zip`, DFE `boot.img`, EROFS `vendor.img`, `ksu_susfs_arm64`) are published in **Releases**. Personal backups, device logs, toolchains, and signing keys are excluded from Git.

> [!WARNING]
> The prebuilt `vendor` images in Releases (`vendor_golfcore_v06*.img` and inside `AnyKernel3.zip`) are derived from stock **Realme UI 4.0** vendor with custom modifications and GSI overlays. **Flash at your own risk** and back up your working `boot` and `vendor` partitions beforehand.

## Key Features (`v0.6-susfs`)

- **Root & Hiding:**
  - **KernelSU-Next** (`legacy`, `CONFIG_KSU_MANUAL_HOOK=y`, UAPI v6 — requires KernelSU-Next Manager with UAPI v6 support such as `v3.4.2-198+`).
  - **SUSFS 1.5.5 NON-GKI** (`CONFIG_KSU_SUSFS=y`, 13 features enabled: `SUS_PATH`, `SUS_MOUNT`, `AUTO_ADD_SUS_KSU_DEFAULT_MOUNT`, `AUTO_ADD_SUS_BIND_MOUNT`, `SUS_KSTAT`, `TRY_UMOUNT`, `AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT`, `SPOOF_UNAME`, `ENABLE_LOG`, `HIDE_KSU_SUSFS_SYMBOLS`, `SPOOF_CMDLINE_OR_BOOTCONFIG`, `OPEN_REDIRECT`, `HAS_MAGIC_MOUNT`).
- **Compiler & CPU Tuning:**
  - **Clang ThinLTO** (`CONFIG_LTO_CLANG=y`, `CONFIG_THINLTO=y`, `CONFIG_LD_IS_LLD=y`, `CONFIG_RELR=y`).
  - Snapdragon 680 instruction scheduling tuning (`-mtune=cortex-a73` in [arch/arm64/Makefile](kernel/msm-4.19/arch/arm64/Makefile)).
  - `CONFIG_JUMP_LABEL=y` (`static_branch` instruction patching).
- **Power, Scheduler & Overhead Reduction:**
  - `CONFIG_WQ_POWER_EFFICIENT_DEFAULT=y`, `CONFIG_UCLAMP_TASK=y`, `CONFIG_UCLAMP_TASK_GROUP=y`, `CONFIG_HZ_300=y`.
  - Disabled `CORESIGHT`, `KPROBES`, `SLUB_DEBUG`, `FTRACE`, and `SCHEDSTATS` (keeping `SCHED_DEBUG=y`).
- **Memory & ZRAM:**
  - **MGLRU** (`CONFIG_LRU_GEN=y`, `CONFIG_LRU_GEN_ENABLED=y`, `CONFIG_LRU_GEN_STATS=y`), `CONFIG_PROACTIVE_COMPACT=y`, `CONFIG_CRYPTO_ZSTD=y`, `CONFIG_ZRAM_DEDUP=y`.
- **Networking:**
  - Backported **TCP BBRv2** (`CONFIG_DEFAULT_BBR2=y`), default qdisc **`fq_codel`** (`CONFIG_DEFAULT_FQ_CODEL=y`), **`CAKE`** (`CONFIG_NET_SCH_CAKE=y`), **`WireGuard`** (`CONFIG_WIREGUARD=y`), and inlined `sk_security_struct` (`CONFIG_SECURITY_SMACK=n`).
- **Vendor Modules:**
  - All 33 vendor `.ko` modules (Wi-Fi `qca_cld3_wlan.ko`, audio, `rdbg.ko`) rebuilt from source, stripped, and signed with the kernel build's local key (`CONFIG_MODULE_SIG_FORCE=y`).

## Repository Layout

- [kernel/msm-4.19/](kernel/msm-4.19/): Full kernel source tree (`KernelSU-Next`, `SUSFS 1.5.5`, BBRv2, MGLRU, ION/LZ4/touch fixes).
- [vendor/](vendor/): Full vendor module sources (`audio-kernel`, `wlan/qcacld-3.0`, `oplus/kernel_4.19/audio`, etc.).
- [build.sh](build.sh): Configures (`stock.config` + feature toggles), validates config constraints, and builds `Image.gz` + in-tree modules.
- [build_vendor_modules.sh](build_vendor_modules.sh): Two-pass cross-module CRC build, strip, and PKCS#7 signing for all 33 vendor `.ko` modules.
- [config/](config/): `stock.config`, reference ABI/vermagic JSONs, and offline EROFS metadata table [vendor_meta.txt](config/vendor_meta.txt).
- [certs/](certs/): Public stock module certificate (`stock-module-cert.pem` / `.der`).
- [anykernel/anykernel.sh](anykernel/anykernel.sh): Portable `AnyKernel3` installer script (kernel + optional EROFS `vendor.img` flashing).
- [tools/](tools/): Boot/vendor/AnyKernel3 packaging helpers ([package_boot.py](tools/package_boot.py), [extract_vendor_meta.py](tools/extract_vendor_meta.py), [repack_vendor_erofs.py](tools/repack_vendor_erofs.py), [package_anykernel3.py](tools/package_anykernel3.py)) and `ksu_susfs` JNI sources in [tools/susfs/jni/](tools/susfs/jni/).
- [docs/](docs/): Release notes and test reports ([SUSFS.md](docs/SUSFS.md), [GOLFCORE_V0.6.md](docs/GOLFCORE_V0.6.md), [GOLFCORE_V0.5.md](docs/GOLFCORE_V0.5.md), [TESTED.md](docs/TESTED.md)).
- [patches/](patches/) & [SOURCES.json](SOURCES.json): Upstream origin metadata and patch provenance.

## Prerequisites & Toolchains

Tested on **Linux x86-64**:

- **Host tools:** `make`, `python3` (3.11+), `bison`, `flex`, `bc`, `perl`, `gzip`, `xz`, `cpio`, OpenSSL dev headers (`libssl-dev`), and `erofs-utils` (`dump.erofs`, `fsck.erofs`, `mkfs.erofs`).
- **Compiler & Binutils:**
  - Android **Clang 11.0.1 (`clang-r383902`, build 6443078)** including `ld.lld`, `llvm-ar`, `llvm-nm`, `llvm-objcopy`, `llvm-objdump`, `llvm-strip`.
  - GNU binutils providing `aarch64-linux-gnu-as` and `arm-linux-gnueabi-as` (e.g., from `proton-clang` or AOSP prebuilt `gcc-linux-x86`).
- Place toolchains under `toolchains/clang-r383902/bin` and `toolchains/proton-clang/bin`, **or** pass `CLANG_BIN` and `BINUTILS_BIN` explicitly.

## Building From Source

```bash
git clone -b golfcore-v0.4 https://github.com/nx-d1frnt/realme-9i-golf-kernel.git
cd realme-9i-golf-kernel
```

### 1. Build the Kernel (`Image.gz` + in-tree modules)

```bash
CLANG_BIN=/path/to/clang-r383902/bin \
BINUTILS_BIN=/path/to/binutils/bin \
JOBS="$(nproc)" \
bash build.sh build
```

Outputs are written to `artifacts/susfs/` (`Image.gz`, `Module.symvers`, `System.map`, `resolved.config`, `config-diff.txt`), and a local module signing keypair is generated in `out/certs/`.

### 2. Build All 33 Vendor Modules

Because **ThinLTO**, **SUSFS**, `JUMP_LABEL`, and `SCHEDSTATS=n` change kernel symbol CRCs and `task_struct` layout, you **must** rebuild all vendor `.ko` modules against the exact `out/` tree from Step 1:

```bash
CLANG_BIN=/path/to/clang-r383902/bin \
BINUTILS_BIN=/path/to/binutils/bin \
bash build_vendor_modules.sh
```

Rebuilt, stripped, and signed modules are placed in `out_modules/`.

### 3. Repack Your `boot.img`

Extract your device's working (stock or DFE) `boot.img` using `magiskboot`, replace `kernel` with `artifacts/susfs/Image.gz`, and repack:

```bash
mkdir -p /tmp/boot_work && cd /tmp/boot_work
magiskboot unpack /path/to/working-boot.img
cp /path/to/realme-9i-golf-kernel/artifacts/susfs/Image.gz kernel
magiskboot repack /path/to/working-boot.img /path/to/boot-golfcore-susfs.img
```

### 4. Repack Your EROFS `vendor.img`

Extract exact `uid`/`gid`/`mode`/`security.selinux` metadata from your base `vendor.img` (no root or ADB required), inject the 33 rebuilt `.ko` modules from `out_modules/`, and verify with `fsck.erofs`:

```bash
python3 tools/extract_vendor_meta.py \
  --vendor-img /path/to/base-vendor.img \
  --output /tmp/vendor_meta.txt

python3 tools/repack_vendor_erofs.py \
  --base-vendor /path/to/base-vendor.img \
  --meta /tmp/vendor_meta.txt \
  --modules-dir out_modules \
  --output /path/to/vendor-golfcore-susfs.img
```

*(For stock Realme UI 4.0 vendor, `config/vendor_meta.txt` is also included directly in this repository.)*

### 5. Optional: Package an Autonomous `AnyKernel3.zip`

Clone upstream `osm0sis/AnyKernel3` and bundle `Image.gz`, [anykernel/anykernel.sh](anykernel/anykernel.sh), and optionally your repacked `vendor.img`:

```bash
git clone --depth=1 https://github.com/osm0sis/AnyKernel3.git /tmp/AnyKernel3

python3 tools/package_anykernel3.py \
  --anykernel-dir /tmp/AnyKernel3 \
  --kernel artifacts/susfs/Image.gz \
  --vendor /path/to/vendor-golfcore-susfs.img \
  --output artifacts/susfs/GolfCore-v0.6-SUSFS-RMX3491-AnyKernel3.zip
```

Omit `--vendor` to produce a kernel-only zip if your device already runs a matching `vendor_golfcore` image.

### 6. Optional: Build `ksu_susfs` Userspace CLI

Source for the matching SUSFS `v1.5.5` NON-GKI `prctl` helper is located in [tools/susfs/jni/](tools/susfs/jni/) and can be built with Android NDK:

```bash
ndk-build NDK_PROJECT_PATH=tools/susfs
```

## Base Upstream Sources & License

- Base kernel & vendor sources: Realme SM6225 Android U open-source drop ([kernel](https://github.com/realme-kernel-opensource/realme9-AndroidU-kernel-source), [vendor](https://github.com/realme-kernel-opensource/realme9-AndroidU-vendor-source)) — full provenance in [SOURCES.json](SOURCES.json).
- Licensed under the Linux kernel license (`GPL-2.0-only` with component-specific notices preserved in source directories) and `tools/susfs/LICENSE`.
