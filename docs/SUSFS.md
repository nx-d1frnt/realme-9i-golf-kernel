# GolfCore v0.6 + SUSFS

SUSFS **1.5.5 NON-GKI**, official `kernel-4.19` branch at
`001e69919c6271f690fd00b17e4c721c9e599152`:
https://gitlab.com/simonpunk/susfs4ksu/-/tree/kernel-4.19

Integrated in `kernel/msm-4.19` with the existing KernelSU-Next 3.3.0
manual hooks. KernelSU-Next is retained; its ioctl/manager ABI is unchanged.
The SUSFS control bridge implements the upstream 1.5.5 `prctl(0xDEADBEEF, …)`
ABI for UID 0 only, checks the result pointer before changing state, and
reports errors through the upstream result argument. Unsupported commands
report `-EOPNOTSUPP`. SUS_SU is disabled: this kernel uses manual hooks.

Enabled: path/mount hiding, automatic KSU/bind mount tracking, kstat spoofing,
custom unmounts, uname/cmdline spoofing, symbol filtering and open redirect.
Legacy overlayfs spoofing is disabled. Auto mount tracking is configured for
Magic Mount (`/debug_ramdisk/workdir`); other module mount providers may need
explicit SUSFS rules. No spoofed identity or hidden user path is preconfigured.

Oplus adaptations include explicit task fields (this tree lacks the upstream
spare task KABI slots), existing inotify masks, mount-aware Oplus permission checks, balanced
path references on hidden lookup failures, and existing KernelSU-Next
SELinux domain checks. Custom unmounts run before Next's normal unmount list
inside its existing zygote-only task-work/credential path. Automatic mount
opt-out files from upstream are read at post-fs-data. The optional upstream
system-process unmount switch is not implemented; Next's zygote/user policy
is retained.

## Build

Use the same Clang 11 / GNU binutils toolchains as GolfCore v0.6:

```sh
CLANG_BIN=/path/to/clang-r383902/bin \
BINUTILS_BIN=/path/to/proton-clang/bin \
ARTIFACTS_DIR="$PWD/artifacts/susfs" bash build.sh build
```

The build asserts that required KSU/manual-hook/SUSFS options survived
olddefconfig. The release is `4.19.157-GolfCore-v0.6-susfs`.
Artifacts are kept separately from the previous v0.6 release.
**Rebuild vendor modules** with `build_vendor_modules.sh`: task structure
layout changed, so the old vendor module set must not be assumed compatible.

## Userspace and verification

Use a userspace tool/module supporting the **1.5.5 NON-GKI prctl ABI**.
A recent GKI-only SUSFS module is not automatically compatible.
The exact matching upstream arm64 tool is copied to
`artifacts/susfs/ksu_susfs_arm64`; its source is in `tools/susfs/jni` and can
be rebuilt using Android NDK `ndk-build NDK_PROJECT_PATH=tools/susfs`.
It is not installed on the phone by the kernel build.

After installing a tested kernel/vendor pair, run the matching tool as root:

```sh
ksu_susfs show version
ksu_susfs show variant
ksu_susfs show enabled_features
```

Expected version: `v1.5.5`; variant: `NON-GKI`. Also verify KernelSU root,
boot completion, Wi-Fi/audio/vendor modules, and mount visibility from a
non-root app. Compilation alone does not establish boot/runtime compatibility
or guarantee that an app will accept the device's integrity state.

## Verification — 2026-11-16

- Full Clang 11 / ThinLTO `Image.gz modules` kernel build: passed.
- Gzip integrity, release string, linked SUSFS symbols and exact match between
  embedded and resolved kernel configuration: passed.
- All six changed KernelSU-Next C translation units: compiler syntax checks passed.
- All 33 previous vendor modules have kernel-symbol CRC mismatches with this
  build. They must be replaced with the corresponding rebuilt module set.
- All 33 vendor modules rebuilt and signed; every imported symbol CRC matches
  the new kernel or its vendor-module provider. All vermagic strings match
  the new kernel release.
- No device flashing or boot/runtime validation has been performed.

The machine-readable results are in `artifacts/susfs/build-validation.json`.

Build bundle: `artifacts/susfs/GolfCore-v0.6-SUSFS-build.tar.gz`.
It contains the kernel, matching modules, userspace tool, configs, source patch,
source provenance and validation reports. These are inputs for boot/vendor
packaging. Install the kernel together with all matching vendor modules;
the previous GolfCore vendor module set is incompatible. Boot/runtime testing
is still required after packaging for the target device.

## Updates & Device Verification — 2026-11-20

- **Compiler & Kernel Optimizations:**
  - Added Snapdragon 680 compiler tuning (`-mtune=cortex-a73` in `kernel/msm-4.19/arch/arm64/Makefile`).
  - Enabled `CONFIG_JUMP_LABEL=y` alongside `LTO_CLANG=y` (`THINLTO=y`) and `RELR=y`.
  - Enabled `CONFIG_WQ_POWER_EFFICIENT_DEFAULT=y`.
  - Disabled `CONFIG_SCHEDSTATS` (and dependent `CONFIG_SCHED_INFO`) while retaining `CONFIG_SCHED_DEBUG=y`.
- **Packaging:**
  - Generated offline EROFS metadata table `config/vendor_meta.txt` (`2741` entries) from `vendor_golfcore_v05.img`.
  - Rebuilt all 33 vendor modules (`vermagic=4.19.157-GolfCore-v0.6-susfs`, PKCS#7 signed, matching `Module.symvers` CRCs) and repacked `vendor_golfcore_v06_susfs.img` (`384671744` bytes, preserving native ZRAM `/etc/fstab.default`), `boot-golfcore-v0.6-susfs-ksu-next-rmx3491-dfe.img`, and standalone `GolfCore-v0.6-SUSFS-KSU-Next-RMX3491-AnyKernel3.zip`.
- **Device Verification (`RMX3491`, `afa6d59`):**
  - `uname -a`: `Linux localhost 4.19.157-GolfCore-v0.6-susfs #12 SMP PREEMPT` (`sys.boot_completed=1`).
  - Modules & Connectivity: all 31 active vendor modules loaded (`lsmod | wc -l == 32`), Wi-Fi enabled & connected, `net.ipv4.tcp_congestion_control = bbr2`, `net.core.default_qdisc = fq_codel`.
  - Power, Scheduler & Memory: `/sys/module/workqueue/parameters/power_efficient` = `Y`, `/proc/schedstat` absent (`CONFIG_SCHEDSTATS=n`), `/dev/block/zram0` active (`lzo [lz4] zstd`).
  - Root & SUSFS: KernelSU-Next Manager reports `Working | BUILT-IN (GKI1) | Version: v3.3.0 (30500-6) | Hook mode: Manual` (`ksud 3.4.2-198-g7ccf6147`, UAPI v6); `ksu_susfs` reports `v1.5.5`, `NON-GKI`, and all 13 enabled features (`SUS_PATH`, `SUS_MOUNT`, `AUTO_ADD_SUS_KSU_DEFAULT_MOUNT`, `AUTO_ADD_SUS_BIND_MOUNT`, `SUS_KSTAT`, `TRY_UMOUNT`, `AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT`, `SPOOF_UNAME`, `ENABLE_LOG`, `HIDE_KSU_SUSFS_SYMBOLS`, `SPOOF_CMDLINE_OR_BOOTCONFIG`, `OPEN_REDIRECT`, `HAS_MAGIC_MOUNT`).

