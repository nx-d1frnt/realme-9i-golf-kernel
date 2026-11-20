#!/usr/bin/env python3
"""Extract exact uid, gid, mode, and security.selinux metadata offline from an EROFS vendor.img."""

import argparse
import mmap
import re
import struct
import subprocess
from collections import deque
from pathlib import Path

LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.+)$")


def dump_ls(img: Path, path: str) -> list[tuple[int, int, str]]:
    out = subprocess.check_output(
        ["dump.erofs", "--ls", f"--path={path}", str(img)],
        text=True,
    )
    entries = []
    in_table = False
    for line in out.splitlines():
        if line.strip().startswith("NID ") and "FILENAME" in line:
            in_table = True
            continue
        if not in_table:
            continue
        m = LINE_RE.match(line)
        if m:
            nid = int(m.group(1))
            ftype = int(m.group(2))
            name = m.group(3).rstrip()
            if name not in (".", ".."):
                entries.append((nid, ftype, name))
    return entries


def read_inode_meta(
    mm: mmap.mmap, blksz: int, meta_blkaddr: int, xattr_blkaddr: int, nid: int
) -> tuple[int, int, int, str]:
    off = meta_blkaddr * blksz + nid * 32
    fmt, xic, mode = struct.unpack_from("<HHH", mm, off)
    is_ext = fmt & 1
    isize = 64 if is_ext else 32
    if is_ext:
        uid, gid = struct.unpack_from("<II", mm, off + 24)
    else:
        uid, gid = struct.unpack_from("<HH", mm, off + 24)

    ctx = None
    if xic > 0:
        xoff = off + isize
        xend = xoff + (xic - 1) * 4 + 12
        sh_cnt = mm[xoff + 4]
        p = xoff + 12
        sh_idxs = struct.unpack_from(f"<{sh_cnt}I", mm, p)
        p += sh_cnt * 4

        def parse_ent(pos: int):
            nlen, nidx, vlen = struct.unpack_from("<BBH", mm, pos)
            name = mm[pos + 4 : pos + 4 + nlen]
            val = mm[pos + 4 + nlen : pos + 4 + nlen + vlen]
            nxt = pos + ((4 + nlen + vlen + 3) & ~3)
            return nidx, name, val, nxt

        for idx in sh_idxs:
            nidx, name, val, _ = parse_ent(xattr_blkaddr * blksz + idx * 4)
            if nidx == 6 and name == b"selinux":
                ctx = val.rstrip(b"\x00").decode("utf-8")

        while p < xend:
            nidx, name, val, p = parse_ent(p)
            if nidx == 6 and name == b"selinux":
                ctx = val.rstrip(b"\x00").decode("utf-8")

    if ctx is None:
        raise RuntimeError(f"Missing security.selinux xattr for nid={nid}")
    return uid, gid, mode & 0o7777, ctx


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor-img", required=True, type=Path, help="Source EROFS vendor.img")
    ap.add_argument("--output", required=True, type=Path, help="Output vendor_meta.txt")
    args = ap.parse_args()

    vendor_img = args.vendor_img.resolve()
    with open(vendor_img, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        sb = mm[1024 : 1024 + 128]
        blkszbits = sb[12]
        blksz = 1 << blkszbits
        root_nid = struct.unpack_from("<H", sb, 14)[0]
        meta_blkaddr, xattr_blkaddr = struct.unpack_from("<II", sb, 40)

        results: list[tuple[str, int, int, int, str]] = []
        uid, gid, mode, ctx = read_inode_meta(mm, blksz, meta_blkaddr, xattr_blkaddr, root_nid)
        results.append(("/vendor", uid, gid, mode, ctx))

        queue = deque([("/")])
        visited = {"/"}
        while queue:
            cur = queue.popleft()
            for nid, ftype, name in dump_ls(vendor_img, cur):
                erofs_path = f"/{name}" if cur == "/" else f"{cur}/{name}"
                vpath = "/vendor" + erofs_path
                uid, gid, mode, ctx = read_inode_meta(mm, blksz, meta_blkaddr, xattr_blkaddr, nid)
                results.append((vpath, uid, gid, mode, ctx))
                if ftype == 2 and erofs_path not in visited:
                    visited.add(erofs_path)
                    queue.append(erofs_path)

        mm.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as out:
        for vpath, uid, gid, mode, ctx in results:
            out.write(f"{uid} {gid} {mode:o} {ctx} {vpath}\n")

    print(f"Wrote {len(results)} entries to {args.output}")


if __name__ == "__main__":
    main()
