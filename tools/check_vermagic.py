#!/usr/bin/env python3
"""Test the unmodified MODVERSIONS loader against pinned vendor vermagic data."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('module_object', type=Path)
parser.add_argument('reference', type=Path)
parser.add_argument('release')
parser.add_argument('--cc', default='cc')
args = parser.parse_args()
reference = json.loads(args.reference.read_text())
text = args.source.read_text()
start = text.index('static inline int same_magic(')
end = text.index('\n}', start) + 2
function = text[start:end]
if function != reference['loader_function']:
    raise SystemExit('Loader comparison changed; review before accepting a branded release')
magics = set(re.findall(re.escape(args.release.encode()) + rb' SMP [^\x00\n]+',
                        args.module_object.read_bytes()))
if len(magics) != 1:
    raise SystemExit('Cannot identify the compiled kernel vermagic')
kernel_magic = magics.pop()
results = []
with tempfile.TemporaryDirectory(prefix='golfcore-vermagic-') as directory:
    temp = Path(directory)
    code = '#include <string.h>\n#include <stdbool.h>\n' + function
    code += '\nint compare(const char*a,const char*b,int crc){return same_magic(a,b,crc);}\n'
    (temp / 'check.c').write_text(code)
    subprocess.run([args.cc, '-shared', '-fPIC', '-O2', str(temp / 'check.c'),
                    '-o', str(temp / 'check.so')], check=True)
    library = ctypes.CDLL(str(temp / 'check.so'))
    library.compare.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    library.compare.restype = ctypes.c_int
    for module in reference['modules']:
        if not module['has_versions_section']:
            raise SystemExit('Unversioned module: ' + module['name'])
        matched = bool(library.compare(module['vermagic'].encode(), kernel_magic, 1))
        wrong_tail = bool(library.compare(module['vermagic'].encode(), kernel_magic + b' bad', 1))
        no_crc = bool(library.compare(module['vermagic'].encode(), kernel_magic, 0))
        if not matched or wrong_tail or no_crc:
            raise SystemExit('Vermagic comparison failed: ' + module['name'])
        results.append({'module': module['name'], 'sha256': module['sha256'],
                        'accepted': True, 'negative_controls_rejected': True})
report = {'kernel_release': args.release, 'kernel_vermagic': kernel_magic.decode(),
          'unmodified_loader_function_sha256': hashlib.sha256(function.encode()).hexdigest(),
          'modules': results, 'all_match': len(results) == 33}
print(json.dumps(report, indent=2))
if not report['all_match']:
    raise SystemExit('Expected exactly 33 vendor modules')
