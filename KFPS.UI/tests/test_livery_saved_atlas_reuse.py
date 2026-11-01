"""Saved-atlas regression contracts using only disposable synthetic inputs."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/livery-studio/src')]
from kfps_livery_lab import prepare, readonly_prepare as subject, saved_atlas_reuse as reuse
from tools.livery import render_contract as native


class SavedAtlasReuseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='saved-atlas-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'saved-atlases/test'
        self.package = self.root / 'synthetic.kfpslivery'
        buffer = io.BytesIO()
        with Image.new('RGBA', (2048, 1024), (20, 120, 240, 255)) as image:
            image.paste((250, 30, 150, 255), (1000, 480, 1048, 544))
            image.save(buffer, format='PNG')
        with zipfile.ZipFile(self.package, 'w') as bundle:
            bundle.writestr('projection/rendered/Top.png', buffer.getvalue())
        (self.root / 'mesh.glb').write_bytes(b'not decoded: direct-UV fixture only')
        self.asset = SimpleNamespace(car_id=42, model_code='SYNTHETIC', archive_name='synthetic.zip',
                                     archive_size=1, archive_mtime_ns=1)
        self.layers = [{'type': 1048679, 'source_section': 'Top',
                        'data': [0, 0, .18, .18, 19, 0, 0], 'color': [255, 30, 150, 255]}]
        self.prepared = {
            'signature': {'fixture_revision': 1}, 'files': {'mesh': 'mesh.glb'},
            'validation': {'projected_livery_meshes': 0},
            'manifest': {'inspection_runtime': {'render_contract': {'mask_size': [1024, 1024]}}},
            'editor_config': {'sections': [{'section': 'Top', 'slot_index': 0,
                'source_region': [472/1024, 472/1024, 552/1024, 552/1024],
                'atlasToLocal': [.5, 0, 512, 0, 1, 0]}]}}

    def build(self, *, quality=1, provider=None, event=None, output=None):
        return subject.build_saved_atlas(self.package, self.prepared, self.asset,
            output or self.output, self.root, quality=quality, layer_provider=provider,
            game_root=None, cancel_event=event, progress=None)

    def snapshot(self):
        return {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.output.iterdir()}

    def receipt_path(self):
        return next(self.output.glob('saved-atlas-*.json'))

    def test_square_hit_preserves_contract_pixels_and_inputs_without_staging(self):
        inputs = copy.deepcopy(self.prepared)
        source = self.package.read_bytes()
        first = self.build()
        before = self.snapshot()
        with patch.object(subject, 'square_mask_atlas', side_effect=AssertionError('rerender')), \
             patch.object(subject.tempfile, 'TemporaryDirectory', side_effect=AssertionError('staging')):
            second = self.build()
        self.assertFalse(first['cache_hit'])
        self.assertTrue(second['cache_hit'])
        self.assertEqual(reuse.stable_contract(first), reuse.stable_contract(second))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(inputs, self.prepared)
        self.assertEqual(source, self.package.read_bytes())

    def test_rectangle_hit_skips_native_builder(self):
        self.prepared['manifest']['inspection_runtime']['render_contract']['mask_size'] = [2048, 1024]
        mask = Image.new('L', (2048, 1024), 0)
        self.addCleanup(mask.close)
        mask.paste(255, (984, 472, 1064, 552))
        projection = dict(left='-40', right='40', top='40', bottom='-40',
                          xAxis='x', yAxis='y', xScale='1', yScale='1')
        with patch.object(native, '_archive_masks', return_value={'top': (mask, projection, 'synthetic')}), \
             patch.object(native, 'read_vehicle_assembly_metadata', return_value={}):
            first = self.build()
        before = self.snapshot()
        with patch.object(native, 'build_local_livery_atlases', side_effect=AssertionError('native miss')):
            second = self.build()
        self.assertEqual(reuse.stable_contract(first), reuse.stable_contract(second))
        self.assertEqual(before, self.snapshot())

    def test_same_size_and_mtime_corruption_is_rejected_without_repair(self):
        self.build()
        path = self.output / 'section-paint.png'
        info = path.stat()
        body = bytearray(path.read_bytes())
        body[len(body) // 2] ^= 1
        path.write_bytes(body)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(before, self.snapshot())

    def test_missing_asset_or_receipt_is_not_adopted(self):
        for missing in ('asset', 'receipt'):
            with self.subTest(missing=missing):
                self.output = self.root / 'saved-atlases' / missing
                self.build()
                path = self.receipt_path() if missing == 'receipt' else self.output / 'section-paint.png'
                path.unlink()
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertEqual(before, self.snapshot())

    def test_receipt_digest_and_schema_are_both_checked(self):
        self.build()
        path = self.receipt_path()
        body = path.read_bytes()
        self.assertIn(hashlib.sha256(body).hexdigest(), path.name)
        path.write_bytes(body + b' ')
        with self.assertRaises(ValueError):
            self.build()
        for value in (None, [], {'format': reuse.FORMAT}):
            with self.subTest(value=value):
                path.unlink()
                body = json.dumps(value).encode('utf-8')
                path = self.output / (reuse.PREFIX + hashlib.sha256(body).hexdigest() + '.json')
                path.write_bytes(body)
                with self.assertRaises(ValueError):
                    self.build()

    def test_unknown_files_directories_and_hardlinks_are_rejected(self):
        self.build()
        extra = self.output / 'unknown'
        extra.write_bytes(b'not owned')
        with self.assertRaises(ValueError):
            self.build()
        extra.unlink()
        extra.mkdir()
        with self.assertRaises(ValueError):
            self.build()
        extra.rmdir()
        os.link(self.output / 'section-paint.png', self.root / 'linked.png')
        with self.assertRaises(ValueError):
            self.build()

    def test_prepared_quality_and_package_changes_invalidate(self):
        self.build()
        before = self.snapshot()
        self.prepared['signature']['fixture_revision'] = 2
        with self.assertRaises(ValueError):
            self.build()
        self.prepared['signature']['fixture_revision'] = 1
        with self.assertRaises(ValueError):
            self.build(quality=2, provider=lambda: self.layers)
        with self.package.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(before, self.snapshot())

    def test_vector_hit_revalidates_provider_and_layer_identity(self):
        self.build(quality=2, provider=lambda: self.layers)
        with patch.object(subject, 'square_mask_atlas', side_effect=AssertionError('rerender')):
            provider = Mock(return_value=self.layers)
            self.assertTrue(self.build(quality=2, provider=provider)['cache_hit'])
            provider.assert_called_once_with()
            def revoked():
                raise ValueError('ownership revoked')
            with self.assertRaisesRegex(ValueError, 'ownership revoked'):
                self.build(quality=2, provider=revoked)
        self.layers[0]['color'][0] = 5
        with self.assertRaises(ValueError):
            self.build(quality=2, provider=lambda: self.layers)

    def test_bounds_and_traversal_reject_without_publication(self):
        with self.assertRaises(ValueError):
            self.build(output=self.root / '..' / 'escaped-atlas')
        for name in ('MAX_BYTES', 'MAX_RECEIPT_BYTES'):
            with self.subTest(limit=name), patch.object(reuse, name, 64):
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_cancellation_before_hit_and_after_render_does_not_publish(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            self.build(event=event)
        self.assertFalse(self.output.exists())
        event.clear()
        original = subject.square_mask_atlas
        def cancel_after_render(*args, **kwargs):
            result = original(*args, **kwargs)
            event.set()
            return result
        with patch.object(subject, 'square_mask_atlas', side_effect=cancel_after_render):
            with self.assertRaises(InterruptedError):
                self.build(event=event)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.a-*')))
        event.clear()
        self.build()
        before = self.snapshot()
        event.set()
        with self.assertRaises(InterruptedError):
            self.build(event=event)
        self.assertEqual(before, self.snapshot())

    def test_readonly_caller_passes_event_to_actual_shared_preparation(self):
        event = threading.Event()
        def enter_shared(*args, **kwargs):
            self.assertIs(event, kwargs.get('cancel_event'))
            event.set()
            return prepare.prepare_car(*args, **kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch('tools.livery.package.validate_livery_inspection_artifact',
                                      return_value={'livery': {'target_car_id': 42}}))
            stack.enter_context(patch.object(subject, 'cache_root', return_value=self.root / 'cache'))
            for name in ('installation_cache_lease', 'cache_lease', 'workspace_lock'):
                stack.enter_context(patch.object(subject, name, side_effect=lambda *a, **k: nullcontext()))
            mocks = {name: stack.enter_context(patch.object(subject, name)) for name in
                     ('verify_inventory', 'admit_artifact', 'seal_inventory', 'enforce_budget',
                      'build_saved_atlas', 'write_descriptor')}
            shared = stack.enter_context(patch.object(subject, 'prepare_car', side_effect=enter_shared))
            with self.assertRaises(InterruptedError):
                subject.prepare_readonly(ROOT, self.root, self.asset, self.package, cancel_event=event)
            shared.assert_called_once()
            mocks['build_saved_atlas'].assert_not_called()
            mocks['write_descriptor'].assert_not_called()
            mocks['seal_inventory'].assert_called_once()
            mocks['enforce_budget'].assert_called_once()


if __name__ == '__main__':
    unittest.main()
