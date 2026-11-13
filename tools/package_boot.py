#!/usr/bin/env python3
"""Package a local DFE boot and verify every preserved component."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-boot', required=True, type=Path)
parser.add_argument('--base-sha256')
parser.add_argument('--kernel-release', default='4.19.157-GolfCore-v0.3')
parser.add_argument('--kernel', type=Path, default=ROOT / 'artifacts/Image.gz')
parser.add_argument('--abi-report', type=Path, default=ROOT / 'artifacts/vendor-abi.json')
parser.add_argument('--magiskboot', required=True, type=Path)
parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/boot-rmx3491-dfe.img')
parser.add_argument('--partition-size', type=int, default=167772160)
args = parser.parse_args()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


boot, kernel, tool, output = map(Path.resolve,
                                [args.base_boot, args.kernel, args.magiskboot, args.output])
partial = output.with_suffix(output.suffix + '.partial')
if output.exists() or partial.exists():
    parser.error('Output exists; choose a new --output')
output.parent.mkdir(parents=True, exist_ok=True)
audit = json.loads(args.abi_report.read_text())
if not audit['all_imports_match'] or len(audit['modules']) != 33:
    raise SystemExit('ABI audit has not passed for all 33 vendor modules')
kernel_sha = sha(kernel)
if audit.get('kernel_sha256') != kernel_sha:
    raise SystemExit('ABI report is not bound to this Image.gz; run build.sh first')
base_sha = sha(boot)
if args.base_sha256 and args.base_sha256 != base_sha:
    raise SystemExit('Base boot SHA-256 mismatch')
raw = gzip.decompress(kernel.read_bytes())
releases = set(re.findall(rb'Linux version ([0-9]+[.][0-9]+[.][0-9]+[^\x00\n ]*) [(]', raw))
if releases != {args.kernel_release.encode()}:
    raise SystemExit('Unexpected kernel release')
if (ROOT / 'certs/stock-module-cert.der').read_bytes() not in raw:
    raise SystemExit('Stock module certificate is missing from Image')

with tempfile.TemporaryDirectory(prefix='rmx3491-boot-') as temporary:
    temp = Path(temporary)
    original, candidate = temp / 'original', temp / 'candidate'
    original.mkdir()
    candidate.mkdir()
    with output.with_suffix('.package.log').open('w') as log:
        def run(cwd, *command):
            subprocess.run([str(tool), *map(str, command)], cwd=cwd,
                           stdout=log, stderr=subprocess.STDOUT, check=True)

        run(original, 'unpack', '-h', boot)
        preserved = {name: sha(original / name) for name in ['ramdisk.cpio', 'dtb', 'header']}
        # MagiskBoot rewrites cpio even on extract, so inspect a separate copy.
        inspection = temp / 'inspection.cpio'
        shutil.copyfile(original / 'ramdisk.cpio', inspection)
        base_fstab = temp / 'base.fstab'
        run(original, 'cpio', inspection, f'extract fstab.default {base_fstab}')
        shutil.copyfile(kernel, original / 'kernel')
        run(original, 'repack', boot, partial)
        if not 0 < partial.stat().st_size <= args.partition_size:
            raise SystemExit('Candidate exceeds the boot partition size')
        run(candidate, 'unpack', '-h', partial)
        for name, digest in preserved.items():
            if sha(candidate / name) != digest:
                raise SystemExit(f'Base boot component changed: {name}')
        if (candidate / 'kernel').read_bytes() != raw:
            raise SystemExit('Kernel changed during repacking')
        fstab = temp / 'candidate.fstab'
        run(candidate, 'cpio', candidate / 'ramdisk.cpio', f'extract fstab.default {fstab}')
        if fstab.read_bytes() != base_fstab.read_bytes():
            raise SystemExit('Base fstab changed')
        data = [line for line in fstab.read_text().splitlines()
                if len(line.split()) > 1 and line.split()[1] == '/data']
        if len(data) != 1 or any(flag in data[0] for flag in
                ['fileencryption', 'metadata_encryption', 'keydirectory', 'forceencrypt', 'inlinecrypt']):
            raise SystemExit('Expected an existing working DFE base boot')
        if 'checkpoint=fs' not in data[0]:
            raise SystemExit('Expected checkpoint=fs in the working base')
        result = {'image': output.name, 'bytes': partial.stat().st_size,
                  'kernel_release': args.kernel_release,
                  'sha256': sha(partial), 'base_boot_sha256': base_sha,
                  'kernel_sha256': kernel_sha, 'unchanged_components': preserved,
                  'all_vendor_import_crcs_match': True, 'fbe_disabled': True,
                  'checkpoint_fs_preserved': True, 'device_tested': False}
        partial.rename(output)
        output.with_suffix('.qa.json').write_text(json.dumps(result, indent=2) + '\n')
        output.with_suffix(output.suffix + '.sha256').write_text(
            result['sha256'] + '  ' + output.name + '\n')
        print(json.dumps(result, indent=2))
