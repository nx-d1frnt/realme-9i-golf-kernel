import itertools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'module'
NODES = {
    'boost_ms': '/sys/devices/system/cpu/cpu_boost/input_boost_ms',
    'up_little': '/sys/devices/system/cpu/cpufreq/policy0/schedutil/up_rate_limit_us',
    'up_big': '/sys/devices/system/cpu/cpufreq/policy4/schedutil/up_rate_limit_us',
    'swappiness': '/proc/sys/vm/swappiness',
    'direct_swappiness': '/proc/sys/vm/direct_swappiness',
    'watermark': '/proc/sys/vm/watermark_scale_factor',
}
BASE = dict(boost_ms=80, up_little=0, up_big=0, swappiness=160,
            direct_swappiness=60, watermark=25)
BOOT = '11111111-2222-4333-8444-555555555555'


class Profiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='golfcore-profile-test-')
        self.root = Path(self.temp.name) / 'phone'
        self.module = Path(self.temp.name) / 'module'
        shutil.copytree(MODULE, self.module)
        for key, path in NODES.items():
            self.write(path, str(BASE[key]))
        self.write('/proc/version', 'Linux version 4.19.157-perf+ (golfcore@balanced-v0.2-rc1)')
        self.write('/proc/sys/kernel/random/boot_id', BOOT)
        self.env = {**os.environ, 'GOLFCORE_TEST_ROOT': str(self.root)}

    def tearDown(self):
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(0o600)
        self.temp.cleanup()

    def write(self, path, value):
        target = self.root / path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + '\n')

    def values(self):
        return {key: int((self.root / path.lstrip('/')).read_text()) for key, path in NODES.items()}

    def run_profile(self, *args, ok=True):
        result = subprocess.run(['sh', str(self.module / 'profile.sh'), *args],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_all_profile_transitions_and_exact_restore(self):
        selections = list(itertools.product(['balanced', 'battery', 'gaming'], ['stock', 'balanced']))
        for previous, following in itertools.product(selections, repeat=2):
            with self.subTest(previous=previous, following=following):
                self.run_profile('apply', *previous)
                self.run_profile('apply', *following)
                expected = BASE.copy()
                if following[0] == 'battery':
                    expected.update(boost_ms=40, up_little=2000, up_big=2000)
                if following[0] == 'gaming':
                    expected.update(boost_ms=120)
                if following[1] == 'balanced':
                    expected.update(direct_swappiness=40, watermark=30)
                self.assertEqual(self.values(), expected)
                self.run_profile('restore')
                self.assertEqual(self.values(), BASE)

    def test_invalid_input_never_writes(self):
        for args in [('apply', 'turbo'), ('memory', 'bad'), ('apply', 'gaming', 'bad'),
                     ('autostart', 'bad'), ('apply', 'battery; touch /tmp/bad')]:
            self.run_profile(*args, ok=False)
            self.assertEqual(self.values(), BASE)

    def test_missing_node_fails_before_any_write(self):
        (self.root / NODES['watermark'].lstrip('/')).unlink()
        self.run_profile('apply', 'battery', ok=False)
        self.assertEqual((self.root / NODES['boost_ms'].lstrip('/')).read_text().strip(), '80')

    @unittest.skipIf(os.geteuid() == 0, 'Permission failure requires a non-root test user')
    def test_mid_transaction_write_failure_rolls_back(self):
        self.run_profile('apply', 'balanced', 'stock')
        path = self.root / NODES['watermark'].lstrip('/')
        path.chmod(0o400)
        self.run_profile('apply', 'battery', 'balanced', ok=False)
        self.assertEqual(self.values(), BASE)
        self.assertFalse((self.module / 'state/pending').exists())

    def test_status_detects_drift_without_overwriting_it(self):
        self.run_profile('apply', 'battery', 'balanced')
        self.write(NODES['boost_ms'], '97')
        result = self.run_profile('status')
        self.assertIn('97', result.stdout)
        self.assertIn('40', result.stdout)
        self.assertEqual(self.values()['boost_ms'], 97)

    def test_restore_does_not_replay_previous_boot_baseline(self):
        self.run_profile('apply', 'gaming', 'balanced')
        self.write('/proc/sys/kernel/random/boot_id', 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.write(NODES['boost_ms'], '65')
        before = self.values()
        self.run_profile('restore')
        self.assertEqual(self.values(), before)
        self.assertIn('autostart=0', (self.module / 'state/selection').read_text())

    def test_new_boot_captures_new_baseline_before_applying(self):
        self.run_profile('apply', 'gaming', 'balanced')
        self.write('/proc/sys/kernel/random/boot_id', 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        for key, value in BASE.items():
            self.write(NODES[key], str(value))
        self.write(NODES['boost_ms'], '90')
        self.run_profile('boot')
        self.assertEqual(self.values()['boost_ms'], 120)
        self.run_profile('restore')
        self.assertEqual(self.values()['boost_ms'], 90)

    def test_boot_obeys_autostart_and_disable_flags(self):
        self.run_profile('apply', 'gaming', 'balanced')
        self.run_profile('autostart', 'off')
        self.write(NODES['boost_ms'], '92')
        self.run_profile('boot')
        self.assertEqual(self.values()['boost_ms'], 92)
        self.run_profile('autostart', 'on')
        (self.module / 'disable').touch()
        self.run_profile('boot')
        self.assertEqual(self.values()['boost_ms'], 92)

    def test_live_lock_refuses_concurrent_writer(self):
        state = self.module / 'state'
        (state / 'lock').mkdir(parents=True)
        (state / 'lock/owner').write_text(f'{BOOT} {os.getpid()}\n')
        self.run_profile('apply', 'battery', ok=False)
        self.assertEqual(self.values(), BASE)

    def test_stale_transaction_is_recovered_before_next_apply(self):
        self.run_profile('apply', 'balanced', 'stock')
        state = self.module / 'state'
        (state / 'lock').mkdir()
        (state / 'lock/owner').write_text(f'{BOOT} 99999999\n')
        (state / 'pending').write_text(f'boot={BOOT}\nboost_ms 80 40\nup_little 0 2000\n')
        self.write(NODES['boost_ms'], '40')
        # An external writer changed this node: recovery must leave it alone.
        self.write(NODES['up_little'], '17')
        self.run_profile('autostart', 'off')
        self.assertEqual(self.values()['boost_ms'], 80)
        self.assertEqual(self.values()['up_little'], 17)
        self.assertFalse((state / 'pending').exists())

    def test_unsupported_kernel_never_writes(self):
        self.write('/proc/version', 'Linux version 4.19.157-perf+ (stock@host)')
        self.run_profile('apply', 'battery', ok=False)
        self.assertEqual(self.values(), BASE)

    def test_branded_release_accepts_golfcore_and_restores(self):
        self.write('/proc/version', 'Linux version 4.19.157-GolfCore-v0.3 (golfcore@balanced-v0.3-rc1)')
        self.run_profile('apply', 'battery', 'balanced')
        self.assertEqual(self.values()['boost_ms'], 40)
        self.run_profile('restore')
        self.assertEqual(self.values(), BASE)

    def test_branded_release_with_wrong_builder_is_rejected(self):
        self.write('/proc/version', 'Linux version 4.19.157-GolfCore-v0.3 (stock@host)')
        self.run_profile('apply', 'battery', ok=False)
        self.assertEqual(self.values(), BASE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
