"""Disposable cache failures must not disable unrelated livery previews."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/livery-studio/src'))
from kfps_livery_lab import readonly_cache as cache
from kfps_livery_lab.file_io import logical_path


class CacheRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='kfps-cache-recovery-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'owned'
        self.root.mkdir()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(cache, 'cache_roots', return_value=[self.root]))
        self.stack.enter_context(patch.object(cache, 'cache_root', return_value=self.root))

    def entry(self, key='a' * 32):
        root = self.root / 'cars' / key
        root.mkdir(parents=True)
        cache.verify_inventory(root, create=True)
        (root / 'mesh').mkdir()
        (root / 'mesh/vehicle.glb').write_bytes(b'preserve this generated model')
        cache.seal_inventory(root)
        return root

    def test_unreadable_other_car_does_not_block_admission(self):
        bad, good = self.entry(), self.entry('b' * 32)
        original = cache.file_inventory

        def inaccessible(path):
            if logical_path(path) == bad:
                raise PermissionError('synthetic Windows access failure')
            return original(path)

        with patch.object(cache, 'file_inventory', side_effect=inaccessible):
            result = cache.admit_artifact(self.base, 0, protected=[good])
        self.assertEqual(1, result['preserved_entries'])
        self.assertTrue((bad / 'mesh/vehicle.glb').exists())
        self.assertTrue((good / 'mesh/vehicle.glb').exists())

    def test_unreadable_selected_car_gets_a_stable_replacement(self):
        bad = self.entry()
        original = cache.file_inventory
        messages = []

        def inaccessible(path):
            if logical_path(path) == bad:
                raise PermissionError('synthetic access failure')
            return original(path)

        with patch.object(cache, 'file_inventory', side_effect=inaccessible):
            fresh = cache.prepare_entry(self.root, bad.name, progress=messages.append)
            self.assertEqual(fresh, cache.prepare_entry(self.root, bad.name))
        self.assertNotEqual(bad, fresh)
        self.assertEqual(1, len(messages))
        self.assertIn('preserved', messages[0])

    def test_healthy_entry_is_reused_without_changing_payload(self):
        root = self.entry()
        payload = root / 'mesh/vehicle.glb'
        before = payload.read_bytes(), payload.stat().st_mtime_ns
        self.assertEqual(root, cache.prepare_entry(self.root, root.name))
        self.assertEqual(before, (payload.read_bytes(), payload.stat().st_mtime_ns))

    def test_unknown_files_and_interrupted_staging_are_not_adopted(self):
        root = self.root / 'cars' / ('a' * 32)
        root.mkdir(parents=True)
        (root / '.k-interrupted.tmp').write_bytes(b'incomplete output')
        fresh = cache.prepare_entry(self.root, root.name)
        self.assertNotEqual(root, fresh)
        self.assertFalse((root / cache.INVENTORY).exists())
        self.assertEqual(b'incomplete output', (root / '.k-interrupted.tmp').read_bytes())

    def test_low_disk_space_stops_rebuild_without_deleting_old_files(self):
        root = self.entry()
        with patch.object(cache.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(ValueError, 'free disk space'):
                cache.admit_artifact(self.base, 10 * 1024**2)
        self.assertTrue((root / 'mesh/vehicle.glb').exists())

    def test_verified_active_cache_still_obeys_budget(self):
        root = self.entry()
        with patch.object(cache, 'MAX_CACHE_BYTES', 16):
            with self.assertRaisesRegex(ValueError, 'full or in use'):
                cache.admit_artifact(self.base, 1, protected=[root])

    def test_locked_entry_is_not_removed_when_clearing(self):
        root = self.entry()
        with cache.cache_lease(root):
            result = cache.prune_cache(self.base, clear=True)
        self.assertEqual(0, result['removed_files'])
        self.assertTrue((root / 'mesh/vehicle.glb').exists())

    def test_scan_is_bounded_even_when_every_entry_is_invalid(self):
        for number in range(4):
            root = self.root / 'cars' / f'{number:032x}'
            root.mkdir(parents=True)
        with patch.object(cache, 'MAX_CACHE_ENTRIES', 3):
            with self.assertRaisesRegex(ValueError, 'too many'):
                cache.prune_cache(self.base)

    def test_allocation_cannot_push_combined_roots_over_limit(self):
        self.entry()
        legacy = self.base / 'legacy'
        for number in range(2):
            (legacy / 'cars' / f'{number:032x}').mkdir(parents=True)
        with patch.object(cache, 'cache_roots', return_value=[self.root, legacy]), \
             patch.object(cache, 'MAX_CACHE_ENTRIES', 3):
            with self.assertRaisesRegex(ValueError, 'entry limit'):
                cache.prepare_entry(self.root, 'b' * 32, kfps_root=self.base)
            self.assertEqual(1, len(list((self.root / 'cars').iterdir())))
            self.assertEqual(2, cache.prune_cache(self.base)['preserved_entries'])

    def test_denied_initial_stat_does_not_escape_recovery(self):
        bad = self.entry()
        original = Path.stat

        def inaccessible(path, *args, **kwargs):
            if logical_path(path) == bad:
                raise PermissionError('stat denied')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'stat', new=inaccessible):
            fresh = cache.prepare_entry(self.root, bad.name)
        self.assertNotEqual(bad, fresh)

    def test_later_payload_read_failure_marks_entry_for_next_attempt(self):
        bad = self.entry()
        with self.assertRaises(PermissionError):
            with cache.preserve_failed_entry(bad):
                raise PermissionError(13, 'read denied after open', str(bad / 'mesh/vehicle.glb'))
        cache.seal_inventory(bad)
        self.assertNotEqual(bad, cache.prepare_entry(self.root, bad.name))
        self.assertTrue((bad / 'mesh/vehicle.glb').exists())

    def test_cancellation_does_not_spend_a_recovery_slot(self):
        root = self.entry()
        with self.assertRaises(InterruptedError):
            with cache.preserve_failed_entry(root):
                raise InterruptedError('cancelled')
        self.assertEqual(root, cache.prepare_entry(self.root, root.name))

    def test_repeated_external_source_errors_do_not_exhaust_recovery(self):
        root = self.entry()
        for error in (FileNotFoundError(2, 'missing archive', str(self.base / 'game.zip')),
                      PermissionError('external stream read denied')):
            for unused in range(cache.MAX_RECOVERY_ENTRIES + 1):
                with self.assertRaises(OSError):
                    with cache.preserve_failed_entry(root):
                        raise error
                self.assertEqual(root, cache.prepare_entry(self.root, root.name))
        self.assertEqual(1, len(list((self.root / 'cars').iterdir())))
        with cache.preserve_failed_entry(root):
            cache.seal_inventory(root)

    @unittest.skipUnless(os.name == 'nt', 'Windows byte-range lock test')
    def test_lock_in_middle_of_mesh_marks_only_the_unusable_cache(self):
        import msvcrt
        root = self.entry()
        with (root / 'mesh/vehicle.glb').open('r+b', buffering=0) as owner:
            owner.seek(12)
            msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                self.assertEqual(root, cache.prepare_entry(self.root, root.name))
                with self.assertRaises(OSError), cache.preserve_failed_entry(root):
                    with (root / 'mesh/vehicle.glb').open('rb', buffering=0) as reader:
                        reader.seek(12)
                        reader.read(1)
                self.assertNotEqual(root, cache.prepare_entry(self.root, root.name))
            finally:
                owner.seek(12)
                msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows byte-range lock test')
    def test_locked_payload_read_is_detected_without_reading_whole_mesh(self):
        import msvcrt
        bad = self.entry()
        with (bad / 'mesh/vehicle.glb').open('r+b') as owner:
            msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                fresh = cache.prepare_entry(self.root, bad.name)
                self.assertNotEqual(bad, fresh)
            finally:
                owner.seek(0)
                msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)

    def test_active_and_legacy_roots_are_both_isolated(self):
        good = self.entry()
        legacy = self.base / 'legacy'
        old = legacy / 'cars' / ('c' * 32)
        old.mkdir(parents=True)
        (old / 'unknown.txt').write_text('old data')
        with patch.object(cache, 'cache_roots', return_value=[self.root, legacy]):
            result = cache.admit_artifact(self.base, 0, protected=[good])
        self.assertEqual(1, result['preserved_entries'])
        self.assertEqual('old data', (old / 'unknown.txt').read_text())

    def test_changed_selected_entry_is_preserved_and_rebuilt_once(self):
        old = self.entry()
        (old / 'unexpected.txt').write_text('user file: do not delete')
        before = {p.relative_to(old): p.read_bytes() for p in old.rglob('*') if p.is_file()}
        fresh = cache.prepare_entry(self.root, old.name)
        self.assertNotEqual(old, fresh)
        self.assertEqual({}, cache.verify_inventory(fresh))
        self.assertEqual(fresh, cache.prepare_entry(self.root, old.name))
        self.assertEqual(before, {p.relative_to(old): p.read_bytes() for p in old.rglob('*') if p.is_file()})

    def test_clear_only_deletes_verified_entries(self):
        bad, good = self.entry(), self.entry('b' * 32)
        (bad / 'viewer-owned.json').write_text('{broken')
        result = cache.prune_cache(self.base, clear=True)
        self.assertEqual(1, result['preserved_entries'])
        self.assertTrue((bad / 'mesh/vehicle.glb').exists())
        self.assertFalse(good.exists())

    def test_hardlinked_payload_is_never_used_or_deleted(self):
        bad = self.entry()
        external = self.base / 'external.bin'
        external.write_bytes(b'external content')
        (bad / 'mesh/vehicle.glb').unlink()
        os.link(external, bad / 'mesh/vehicle.glb')
        with self.assertRaisesRegex(ValueError, 'linked'):
            cache.file_inventory(bad)
        fresh = cache.prepare_entry(self.root, bad.name)
        cache.prune_cache(self.base, clear=True)
        self.assertEqual(b'external content', external.read_bytes())
        self.assertTrue((bad / 'mesh/vehicle.glb').exists())
        self.assertFalse(fresh.exists())

    def test_recovery_has_a_finite_directory_limit(self):
        for unused in range(cache.MAX_RECOVERY_ENTRIES):
            root = cache.prepare_entry(self.root, 'a' * 32)
            (root / 'unknown').write_bytes(b'do not adopt')
        with self.assertRaisesRegex(ValueError, 'recovery limit'):
            cache.prepare_entry(self.root, 'a' * 32)
        self.assertEqual(cache.MAX_RECOVERY_ENTRIES, len(list((self.root / 'cars').iterdir())))

    def test_zero_link_metadata_is_reported_as_access_failure_not_a_link(self):
        root = self.entry()
        original = Path.stat
        target = root / 'mesh/vehicle.glb'

        def no_access(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if logical_path(path) == target:
                fields = list(value)
                fields[3] = 0
                return os.stat_result(fields)
            return value

        with patch.object(Path, 'stat', new=no_access):
            with self.assertRaisesRegex(ValueError, 'access'):
                cache.file_inventory(root)

    def test_invalid_entry_key_cannot_escape_cache(self):
        for key in ('../escape', 'a' * 31, 'A' * 32, 'x' * 32):
            with self.subTest(key=key), self.assertRaises(ValueError):
                cache.prepare_entry(self.root, key)
        self.assertFalse((self.base / 'escape').exists())

    def test_directory_symlink_is_preserved_without_following_it(self):
        external = self.base / 'external'
        external.mkdir()
        (external / 'keep').write_text('external data')
        cars = self.root / 'cars'
        cars.mkdir()
        link = cars / ('a' * 32)
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('Directory symlink creation is unavailable')
        fresh = cache.prepare_entry(self.root, link.name)
        result = cache.prune_cache(self.base, clear=True)
        self.assertEqual(1, result['preserved_entries'])
        self.assertTrue(link.is_symlink())
        self.assertEqual('external data', (external / 'keep').read_text())
        self.assertFalse(fresh.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction test')
    def test_windows_junction_is_preserved_without_traversal(self):
        import _winapi
        external = self.base / 'junction-target'
        external.mkdir()
        (external / 'keep').write_text('external data')
        cars = self.root / 'cars'
        cars.mkdir()
        link = cars / ('a' * 32)
        _winapi.CreateJunction(str(external), str(link))
        self.addCleanup(lambda: link.rmdir() if link.is_junction() else None)
        fresh = cache.prepare_entry(self.root, link.name)
        result = cache.prune_cache(self.base, clear=True)
        self.assertEqual(1, result['preserved_entries'])
        self.assertTrue(link.is_junction())
        self.assertEqual('external data', (external / 'keep').read_text())
        self.assertFalse(fresh.exists())


if __name__ == '__main__':
    unittest.main()
