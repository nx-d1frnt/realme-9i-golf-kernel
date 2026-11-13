#!/usr/bin/env python3
"""Read a rooted phone's kernel, memory and suspend state without changing it."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    parser.error('Output exists; choose a new snapshot filename')


def read(command):
    result = subprocess.run(['adb', 'shell', 'su -c ' + shlex.quote(command)],
                            capture_output=True, text=True, timeout=45)
    return {'exit_code': result.returncode, 'stdout': result.stdout.strip(),
            'stderr': result.stderr.strip()}


identity = read('id')
if identity['exit_code'] or 'uid=0(' not in identity['stdout']:
    raise SystemExit('ADB Shell root is unavailable')
commands = {
    'kernel': 'cat /proc/version',
    'uptime': 'cat /proc/uptime',
    'boot_sha256': 'sha256sum /dev/block/by-name/boot',
    'vendor_sha256': 'sha256sum /dev/block/mapper/vendor',
    'meminfo': 'cat /proc/meminfo',
    'memory_pressure': 'cat /proc/pressure/memory',
    'vmstat': 'cat /proc/vmstat',
    'swaps': 'cat /proc/swaps',
    'zram_algorithm': 'cat /sys/block/zram0/comp_algorithm',
    'zram_size': 'cat /sys/block/zram0/disksize',
    'zram_memory': 'cat /sys/block/zram0/mm_stat',
    'zram_io': 'cat /sys/block/zram0/io_stat',
    'suspend': 'for p in /sys/power/suspend_stats/*; do printf "%s " "$p"; cat "$p"; done',
    'cpu_policy': 'for p in /sys/devices/system/cpu/cpufreq/policy*; do printf "%s\\n" "$p"; '
                  'cat "$p/scaling_governor" "$p/scaling_min_freq" "$p/scaling_max_freq"; done',
    'modules': 'cat /proc/modules',
    'battery': 'dumpsys battery',
}
report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
          'measurements': {key: read(command) for key, command in commands.items()}}
if not report['measurements']['kernel']['stdout'].startswith('Linux version '):
    raise SystemExit('Could not read the running kernel version')
log = read('dmesg')
report['kernel_log'] = {
    'exit_code': log['exit_code'],
    'warnings': [line for line in log['stdout'].splitlines() if 'WARNING: CPU:' in line],
    'critical': [line for line in log['stdout'].splitlines() if re.search(
        r'Kernel panic|Oops:|\bBUG:|disagrees about version of symbol|Unknown symbol|'
        r'module verification failed', line)],
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('x') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(f'Saved read-only snapshot: {args.output}')
