#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/kernel/msm-4.19"
OUT="${OUT:-$ROOT/out}"
MOD_OUT="${MOD_OUT:-$ROOT/out_modules}"

TOOLCHAIN_DIR="${TOOLCHAIN_DIR:-/mnt/40608C3F38E3B991/golf2rom/toolchains}"
CLANG_BIN="$TOOLCHAIN_DIR/clang-r383902/bin"
BINUTILS_BIN="$TOOLCHAIN_DIR/proton-clang/bin"

export PATH="$CLANG_BIN:$BINUTILS_BIN:$PATH"
export ARCH=arm64
export SUBARCH=arm64

MAKE_COMMON=(
  -j"$(nproc)"
  -C "$SRC"
  O="$OUT"
  ARCH=arm64
  CC=clang
  HOSTCC=clang
  CLANG_TRIPLE=aarch64-linux-gnu-
  CROSS_COMPILE=aarch64-linux-gnu-
  CROSS_COMPILE_ARM32=arm-linux-gnueabi-
  LD=ld.lld
  AR=llvm-ar
  NM=llvm-nm
  OBJCOPY=llvm-objcopy
  OBJDUMP=llvm-objdump
  STRIP=llvm-strip
)

# Short symlinks avoid "/bin/sh: Argument list too long" in qcacld-3.0 linking
ln -sfn "$ROOT/vendor/qcom/opensource/wlan" /tmp/wl
ln -sfn "$ROOT/vendor/qcom/opensource/audio-kernel" /tmp/ak
ln -sfn "$ROOT/vendor/oplus/kernel_4.19/audio" /tmp/op_ak

rm -rf "$MOD_OUT"
mkdir -p "$MOD_OUT"

echo "=== Cleaning stale module build artifacts ==="
find "$ROOT/vendor/qcom/opensource/audio-kernel" \
     "$ROOT/vendor/oplus/kernel_4.19/audio" \
     "$ROOT/vendor/qcom/opensource/wlan/qcacld-3.0" \
     \( -name '*.o' -o -name '*.ko' -o -name '*.mod.c' -o -name '*.cmd' -o -name 'Module.symvers' -o -name 'modules.order' \) \
     -delete

EXTRA_SYMS=""

build_audio_dir() {
  local m_dir="$1"
  local modname="$2"
  echo "=== Building $m_dir ($modname) ==="
  make "${MAKE_COMMON[@]}" \
    M="$m_dir" \
    AUDIO_ROOT=/tmp/ak \
    BOARD_PLATFORM=bengal \
    CONFIG_SND_SOC_BENGAL=m \
    MODNAME="$modname" \
    KBUILD_EXTRA_SYMBOLS="$EXTRA_SYMS" \
    modules
  if [[ -f "$m_dir/Module.symvers" ]]; then
    EXTRA_SYMS="${EXTRA_SYMS:+$EXTRA_SYMS }$m_dir/Module.symvers"
  fi
}

# Pass 1: compile all objects and collect every Module.symvers
AUDIO_DIRS=(
  "/tmp/ak/soc soc_dlkm"
  "/tmp/ak/dsp q6_dlkm"
  "/tmp/ak/ipc apr_dlkm"
  "/tmp/ak/dsp/codecs native_dlkm"
  "/tmp/ak/asoc/codecs wcd_core_dlkm"
  "/tmp/ak/asoc/codecs/bolero bolero_cdc_dlkm"
  "/tmp/ak/asoc/codecs/wcd937x wcd937x_dlkm"
  "/tmp/ak/asoc/codecs/rouleur rouleur_dlkm"
  "/tmp/op_ak/codecs/common pa_manager_dlkm"
  "/tmp/op_ak/codecs/sia81xx_1.2.0 sia81xx_dlkm"
  "/tmp/op_ak/codecs/aw87xxx aw87xxx_dlkm"
  "/tmp/op_ak/codecs/aw882xx aw882xx_dlkm"
  "/tmp/ak/asoc platform_dlkm"
)

for entry in "${AUDIO_DIRS[@]}"; do
  read -r dir mod <<< "$entry"
  build_audio_dir "$dir" "$mod"
done

# Pass 2: re-link modules with complete EXTRA_SYMS so all MODVERSIONS CRCs match
echo "=== Pass 2: resolving cross-module symbol CRCs ==="
for entry in "${AUDIO_DIRS[@]}"; do
  read -r dir mod <<< "$entry"
  rm -f "$dir"/*.ko "$dir"/*.mod.c "$dir"/*.mod.o
  build_audio_dir "$dir" "$mod"
done

echo "=== Building qca_cld3_wlan (MODNAME=wlan) ==="
make "${MAKE_COMMON[@]}" \
  M=/tmp/wl/qcacld-3.0 \
  WLAN_ROOT=/tmp/wl/qcacld-3.0 \
  MODNAME=wlan \
  CONFIG_QCA_CLD_WLAN=m \
  CONFIG_QCA_WIFI_ISOC=0 \
  CONFIG_QCA_WIFI_2_0=1 \
  modules

copy_mod() {
  local src_ko="$1"
  local dst_path="$2"
  cp -f "$src_ko" "$dst_path"
}

# soc
copy_mod /tmp/ak/soc/pinctrl_lpi_dlkm.ko "$MOD_OUT/audio_pinctrl_lpi.ko"
copy_mod /tmp/ak/soc/snd_event_dlkm.ko "$MOD_OUT/audio_snd_event.ko"
copy_mod /tmp/ak/soc/swr_dlkm.ko "$MOD_OUT/audio_swr.ko"
copy_mod /tmp/ak/soc/swr_ctrl_dlkm.ko "$MOD_OUT/audio_swr_ctrl.ko"

# dsp
copy_mod /tmp/ak/dsp/adsp_loader_dlkm.ko "$MOD_OUT/audio_adsp_loader.ko"
copy_mod /tmp/ak/dsp/q6_dlkm.ko "$MOD_OUT/audio_q6.ko"
copy_mod /tmp/ak/dsp/q6_notifier_dlkm.ko "$MOD_OUT/audio_q6_notifier.ko"
copy_mod /tmp/ak/dsp/q6_pdr_dlkm.ko "$MOD_OUT/audio_q6_pdr.ko"
copy_mod /tmp/ak/dsp/usf_dlkm.ko "$MOD_OUT/audio_usf.ko"

# ipc
copy_mod /tmp/ak/ipc/apr_dlkm.ko "$MOD_OUT/audio_apr.ko"

# dsp/codecs
copy_mod /tmp/ak/dsp/codecs/native_dlkm.ko "$MOD_OUT/audio_native.ko"

# asoc/codecs
copy_mod /tmp/ak/asoc/codecs/mbhc_dlkm.ko "$MOD_OUT/audio_mbhc.ko"
copy_mod /tmp/ak/asoc/codecs/stub_dlkm.ko "$MOD_OUT/audio_stub.ko"
copy_mod /tmp/ak/asoc/codecs/wcd9xxx_dlkm.ko "$MOD_OUT/audio_wcd9xxx.ko"
copy_mod /tmp/ak/asoc/codecs/wcd_core_dlkm.ko "$MOD_OUT/audio_wcd_core.ko"
copy_mod /tmp/ak/asoc/codecs/wsa881x_analog_dlkm.ko "$MOD_OUT/audio_wsa881x_analog.ko"

# asoc/codecs/bolero
copy_mod /tmp/ak/asoc/codecs/bolero/bolero_cdc_dlkm.ko "$MOD_OUT/audio_bolero_cdc.ko"
copy_mod /tmp/ak/asoc/codecs/bolero/rx_macro_dlkm.ko "$MOD_OUT/audio_rx_macro.ko"
copy_mod /tmp/ak/asoc/codecs/bolero/tx_macro_dlkm.ko "$MOD_OUT/audio_tx_macro.ko"
copy_mod /tmp/ak/asoc/codecs/bolero/va_macro_dlkm.ko "$MOD_OUT/audio_va_macro.ko"

# asoc/codecs/wcd937x
copy_mod /tmp/ak/asoc/codecs/wcd937x/wcd937x_dlkm.ko "$MOD_OUT/audio_wcd937x.ko"
copy_mod /tmp/ak/asoc/codecs/wcd937x/wcd937x_slave_dlkm.ko "$MOD_OUT/audio_wcd937x_slave.ko"

# asoc/codecs/rouleur
copy_mod /tmp/ak/asoc/codecs/rouleur/rouleur_dlkm.ko "$MOD_OUT/audio_rouleur.ko"
copy_mod /tmp/ak/asoc/codecs/rouleur/rouleur_slave_dlkm.ko "$MOD_OUT/audio_rouleur_slave.ko"
copy_mod /tmp/ak/asoc/codecs/rouleur/pm2250_spmi_dlkm.ko "$MOD_OUT/audio_pm2250_spmi.ko"

# oplus codecs
copy_mod /tmp/op_ak/codecs/common/pa_manager_dlkm.ko "$MOD_OUT/audio_pa_manager.ko"
copy_mod /tmp/op_ak/codecs/sia81xx_1.2.0/sia81xx_dlkm.ko "$MOD_OUT/audio_sia81xx.ko"
copy_mod /tmp/op_ak/codecs/aw87xxx/aw87xxx_dlkm.ko "$MOD_OUT/audio_aw87xxx.ko"
copy_mod /tmp/op_ak/codecs/aw882xx/aw882xx_dlkm.ko "$MOD_OUT/audio_aw882xx.ko"

# asoc
copy_mod /tmp/ak/asoc/platform_dlkm.ko "$MOD_OUT/audio_platform.ko"
copy_mod /tmp/ak/asoc/machine_dlkm.ko "$MOD_OUT/audio_machine_bengal.ko"

# wlan & in-tree rdbg
copy_mod /tmp/wl/qcacld-3.0/wlan.ko "$MOD_OUT/qca_cld3_wlan.ko"
copy_mod "$OUT/drivers/char/rdbg.ko" "$MOD_OUT/rdbg.ko"

echo "=== Stripping & signing 33 modules ==="
SIGN_FILE="$OUT/scripts/sign-file"
PRIV_KEY="$OUT/certs/signing_key.pem"
PUB_CERT="$OUT/certs/signing_key.x509"

for ko in "$MOD_OUT"/*.ko; do
  llvm-strip --strip-debug "$ko"
  "$SIGN_FILE" sha512 "$PRIV_KEY" "$PUB_CERT" "$ko"
done

echo "=== Built $(ls -1 "$MOD_OUT"/*.ko | wc -l) modules in $MOD_OUT ==="
ls -lh "$MOD_OUT"
