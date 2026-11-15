#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SRC=${KERNEL_DIR:-"$ROOT/kernel/msm-4.19"}
OUT=${OUT_DIR:-"$ROOT/out"}
ARTIFACTS=${ARTIFACTS_DIR:-"$ROOT/artifacts"}
TC=${CLANG_BIN:-"$ROOT/toolchains/clang-r383902/bin"}
BINUTILS=${BINUTILS_BIN:-"$ROOT/toolchains/proton-clang/bin"}
MODE=${1:-build}
case "$MODE" in configure|probe|build) ;; *) echo 'Usage: bash build.sh [configure|probe|build]' >&2; exit 2;; esac
export PATH="$TC:$BINUTILS:$PATH"
# The unchanged MODVERSIONS loader accepts the branded release for CRC modules.
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-golfcore}
export KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-balanced-v0.4-rc1}
for tool in "$TC/clang" "$TC/clang++" aarch64-linux-gnu-as arm-linux-gnueabi-as; do
  command -v "$tool" >/dev/null
done
mkdir -p "$OUT" "$ARTIFACTS"
ARGS=(-C "$SRC" "O=$OUT" ARCH=arm64 CC=clang
  CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu-
  CROSS_COMPILE_ARM32=arm-linux-gnueabi-
  "HOSTCC=$TC/clang" "HOSTCXX=$TC/clang++")
if [[ -f /usr/lib/libcrypto.so.3 ]]; then
  ARGS+=(HOSTLDLIBS_sign-file=-l:libcrypto.so.3 HOSTLDLIBS_extract-cert=-l:libcrypto.so.3)
fi
cp "$ROOT/config/stock.config" "$OUT/.config"
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION '-GolfCore-v0.4'
"$SRC/scripts/config" --file "$OUT/.config" --set-str SYSTEM_TRUSTED_KEYS "$ROOT/certs/stock-module-cert.pem"
"$SRC/scripts/config" --file "$OUT/.config" \
  --enable TCP_CONG_ADVANCED \
  --enable TCP_CONG_BBR \
  --enable DEFAULT_BBR \
  --set-str DEFAULT_TCP_CONG bbr \
  --enable NET_SCH_FQ_CODEL \
  --enable WIREGUARD \
  --enable PROACTIVE_COMPACT
make "${ARGS[@]}" olddefconfig > "$ARTIFACTS/configure.log" 2>&1
cp "$OUT/.config" "$ARTIFACTS/resolved.config"
python3 "$SRC/scripts/diffconfig" "$ROOT/config/stock.config" "$OUT/.config" > "$ARTIFACTS/config-diff.txt"
python3 - "$ROOT/config/stock.config" "$OUT/.config" <<'PY'
import sys
def settings(path):
    return dict(line.strip().split('=', 1) for line in open(path) if line.startswith('CONFIG_'))
stock, actual = map(settings, sys.argv[1:])
allowed = {
    'CONFIG_CLANG_VERSION',
    'CONFIG_LOCALVERSION',
    'CONFIG_SYSTEM_TRUSTED_KEYS',
    'CONFIG_TCP_CONG_ADVANCED',
    'CONFIG_DEFAULT_TCP_CONG',
}
changed = [key for key, value in stock.items() if key not in allowed and actual.get(key) != value]
if changed:
    raise SystemExit('Stock settings changed: ' + ', '.join(changed))
PY
cat "$ARTIFACTS/config-diff.txt"
if [[ "$MODE" = configure ]]; then exit 0; fi
if [[ "$MODE" = probe ]]; then
  make "${ARGS[@]}" -j"${JOBS:-6}" kernel/module.o > "$ARTIFACTS/probe.log" 2>&1
  exit 0
fi
if ! make "${ARGS[@]}" -j"${JOBS:-6}" Image.gz modules > "$ARTIFACTS/build.log" 2>&1; then
  tail -60 "$ARTIFACTS/build.log" >&2
  exit 1
fi
cp "$OUT/arch/arm64/boot/Image.gz" "$ARTIFACTS/Image.gz"
cp "$OUT/Module.symvers" "$ARTIFACTS/Module.symvers"
cp "$OUT/System.map" "$ARTIFACTS/System.map"
gzip -t "$ARTIFACTS/Image.gz"
python3 "$ROOT/tools/check_abi.py" "$ARTIFACTS/Module.symvers" \
  "$ROOT/config/vendor-abi-reference.json" > "$ARTIFACTS/vendor-abi.json"
python3 "$ROOT/tools/check_vermagic.py" "$SRC/kernel/module.c" "$OUT/kernel/module.o" \
  "$ROOT/config/vendor-vermagic-reference.json" "$(cat "$OUT/include/config/kernel.release")" \
  --cc "$TC/clang" > "$ARTIFACTS/vendor-vermagic.json"
python3 - "$ARTIFACTS" <<'PY'
import hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1])
digest = hashlib.sha256((p / 'Image.gz').read_bytes()).hexdigest()
audit = json.loads((p / 'vendor-abi.json').read_text())
audit['kernel_sha256'] = digest
(p / 'vendor-abi.json').write_text(json.dumps(audit, indent=2) + '\n')
(p / 'Image.gz.sha256').write_text(digest + '  Image.gz\n')
PY
echo "Kernel built and vendor ABI audit passed: $ARTIFACTS"
