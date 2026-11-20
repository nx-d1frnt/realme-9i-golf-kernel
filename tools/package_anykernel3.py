#!/usr/bin/env python3
"""Package an AnyKernel3 flashable zip from an upstream osm0sis/AnyKernel3 checkout."""

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anykernel-dir", required=True, type=Path, help="Path to cloned osm0sis/AnyKernel3")
    ap.add_argument("--kernel", type=Path, default=ROOT / "artifacts/susfs/Image.gz", help="Path to Image.gz")
    ap.add_argument("--vendor", type=Path, default=None, help="Optional repacked EROFS vendor.img")
    ap.add_argument("--anykernel-script", type=Path, default=ROOT / "anykernel/anykernel.sh", help="Path to anykernel.sh")
    ap.add_argument("--output", required=True, type=Path, help="Output flashable .zip path")
    args = ap.parse_args()

    ak_dir = args.anykernel_dir.resolve()
    kernel = args.kernel.resolve()
    ak_script = args.anykernel_script.resolve()
    vendor = args.vendor.resolve() if args.vendor is not None else None
    output = args.output.resolve()

    if not ak_dir.is_dir():
        raise SystemExit(f"Missing AnyKernel3 directory: {ak_dir}")
    if not kernel.is_file():
        raise SystemExit(f"Missing kernel Image.gz: {kernel}")
    if not ak_script.is_file():
        raise SystemExit(f"Missing anykernel.sh: {ak_script}")
    if vendor is not None and not vendor.is_file():
        raise SystemExit(f"Missing vendor image: {vendor}")

    with tempfile.TemporaryDirectory(prefix="ak3_stage_") as tmp:
        stage = Path(tmp) / "ak3"
        shutil.copytree(
            ak_dir,
            stage,
            ignore=shutil.ignore_patterns(".git", ".github", "Image*", "vendor.img", "*.zip"),
        )
        shutil.copy2(ak_script, stage / "anykernel.sh")
        shutil.copy2(kernel, stage / "Image.gz")
        if vendor is not None:
            shutil.copy2(vendor, stage / "vendor.img")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for dirpath, dirnames, filenames in os.walk(stage):
                dirnames.sort()
                filenames.sort()
                for fname in filenames:
                    p = Path(dirpath) / fname
                    rel = p.relative_to(stage)
                    comp = zipfile.ZIP_STORED if fname == "vendor.img" else zipfile.ZIP_DEFLATED
                    zf.write(p, str(rel), compress_type=comp)

    print(f"Created: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
