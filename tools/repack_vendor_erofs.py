#!/usr/bin/env python3
"""Repack an EROFS vendor.img with rebuilt kernel modules and exact SELinux xattrs."""

import argparse
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def parse_meta(meta_path: Path) -> dict[str, tuple[int, int, int, str]]:
    meta = {}
    for line in meta_path.read_text().splitlines():
        parts = line.strip().split(" ", 4)
        if len(parts) == 5:
            uid, gid, mode, ctx, path = parts
            meta[path] = (int(uid), int(gid), int(mode, 8), ctx)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-vendor", required=True, type=Path, help="Original vendor.img (EROFS)")
    ap.add_argument("--meta", required=True, type=Path, help="uid gid mode selinux_ctx path table")
    ap.add_argument("--modules-dir", required=True, type=Path, help="Directory with rebuilt *.ko")
    ap.add_argument("--output", required=True, type=Path, help="Output vendor.img")
    ap.add_argument("--uuid", default="5fbb99c0-fae2-43a5-a2e2-0d8cd7f96836")
    ap.add_argument("--mtime", type=int, default=1731953099)
    args = ap.parse_args()

    meta = parse_meta(args.meta)
    with tempfile.TemporaryDirectory(prefix="vendor_repack_") as tmp:
        tmp_path = Path(tmp)
        extract_dir = tmp_path / "root"
        tar_path = tmp_path / "vendor.tar"

        subprocess.run(
            ["fsck.erofs", f"--extract={extract_dir}", str(args.base_vendor)],
            check=True,
        )

        mod_dst = extract_dir / "lib" / "modules"
        for ko in sorted(args.modules_dir.glob("*.ko")):
            shutil.copy2(ko, mod_dst / ko.name)

        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tf:
            # Explicit '.' entry ensures '/' keeps uid=0, gid=2000, mode=0755, security.selinux
            ti_root = tf.gettarinfo(str(extract_dir), arcname=".")
            uid, gid, mode, ctx = meta["/vendor"]
            ti_root.uid, ti_root.gid = uid, gid
            ti_root.uname = ti_root.gname = ""
            ti_root.mode = mode
            ti_root.mtime = args.mtime
            ti_root.pax_headers["SCHILY.xattr.security.selinux"] = ctx
            tf.addfile(ti_root)

            for dirpath, dirnames, filenames in os.walk(extract_dir):
                dirnames.sort()
                filenames.sort()
                for name in dirnames + filenames:
                    full = Path(dirpath) / name
                    rel = str(full.relative_to(extract_dir))
                    vpath = "/vendor/" + rel
                    if vpath in meta:
                        uid, gid, mode, ctx = meta[vpath]
                    elif vpath.startswith("/vendor/lib/modules/"):
                        uid, gid, mode, ctx = 0, 0, 0o644, "u:object_r:vendor_file:s0"
                    else:
                        raise RuntimeError(f"Missing metadata for {vpath}")

                    ti = tf.gettarinfo(str(full), arcname=rel)
                    ti.uid, ti.gid = uid, gid
                    ti.uname = ti.gname = ""
                    ti.mode = mode
                    ti.mtime = args.mtime
                    ti.pax_headers["SCHILY.xattr.security.selinux"] = ctx
                    if ti.isreg():
                        with open(full, "rb") as f:
                            tf.addfile(ti, f)
                    else:
                        tf.addfile(ti)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "mkfs.erofs",
                "-zlz4hc,12",
                "-T",
                str(args.mtime),
                "--tar=f",
                "-U",
                args.uuid,
                str(args.output),
                str(tar_path),
            ],
            check=True,
        )
        subprocess.run(["fsck.erofs", "-p", str(args.output)], check=True)


if __name__ == "__main__":
    main()
