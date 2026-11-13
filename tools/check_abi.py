#!/usr/bin/env python3
"""Check kernel exports against CRC metadata from the tested stock vendor."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('symvers', type=Path)
parser.add_argument('reference', type=Path)
args = parser.parse_args()
reference = json.loads(args.reference.read_text())
exports = {}
providers = {}
for line in args.symvers.read_text().splitlines():
    fields = line.split()
    if len(fields) >= 2:
        exports[fields[1]] = int(fields[0], 16)
        providers[fields[1]] = fields[2] if len(fields) > 2 else 'kernel'
conflicts = []
for module in reference['modules']:
    for item in module['exports']:
        symbol, value = item['symbol'], int(item['crc'], 16)
        if symbol in exports:
            conflicts.append({'symbol': symbol, 'existing_provider': providers[symbol],
                              'vendor_provider': module['name']})
        else:
            exports[symbol] = value
            providers[symbol] = module['name']
results = []
failed = bool(conflicts)
for module in reference['modules']:
    missing, mismatched, dependencies = [], [], {}
    for item in module['imports']:
        symbol, expected = item['symbol'], int(item['crc'], 16)
        if symbol not in exports:
            missing.append(symbol)
        elif exports[symbol] != expected:
            mismatched.append({'symbol': symbol, 'expected': item['crc'],
                               'actual': f'0x{exports[symbol]:08x}',
                               'provider': providers[symbol]})
        elif providers[symbol].endswith('.ko'):
            dependencies[symbol] = providers[symbol]
    failed |= bool(missing or mismatched)
    results.append({'module': module['name'], 'missing': missing,
                    'mismatched': mismatched, 'vendor_dependencies': dependencies,
                    'imports_checked': len(module['imports'])})
report = {'modules': results, 'export_conflicts': conflicts,
          'all_imports_match': not failed}
print(json.dumps(report, indent=2))
raise SystemExit(1 if failed else 0)
