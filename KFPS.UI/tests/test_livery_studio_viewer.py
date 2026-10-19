from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / 'src'), str(UI.parent)]

from kfps_ui.experimental.full_livery import jobs, operations, inspector_main


class StudioBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = SimpleNamespace(app_root=self.root, vehicle_index=self.root / 'index.json')
        self.manifest = {'package_id': 'package', 'livery': {'target_car_id': 42},
                         'sharing': {'exportable': True, 'preview_only': False}}
        self.payload = {'package_id': 'package', 'car_id': 42, 'package_path': str(self.root / 'test.kfpslivery'),
                        'game_folder': str(self.root / 'game'), 'quality_scale': 2}
        self.asset = SimpleNamespace(car_id=42, model_code='TEST', archive_path=str(self.root / 'car.zip'))
        self.adapter = SimpleNamespace(prepare_readonly=Mock(return_value={'readonly_descriptor': 'descriptor', 'quality_notes': []}))

    def tearDown(self):
        self.temp.cleanup()

    def call(self):
        with patch('tools.livery.package.validate_livery_inspection_artifact', return_value=self.manifest), \
             patch('tools.livery.vehicle_assets.load_or_build_vehicle_asset_index', return_value={42: self.asset}), \
             patch.object(operations, 'studio_module', return_value=self.adapter), \
             patch.object(operations.psutil, 'virtual_memory', return_value=SimpleNamespace(available=8 * 1024**3)):
            return operations.prepare_mesh(self.paths, self.payload, threading.Event())

    def test_dispatch_uses_shared_studio_preparation(self):
        result = {'readonly_descriptor': 'shared'}
        cancel = threading.Event()
        with patch.object(operations, 'prepare_mesh', return_value=result) as prepare:
            self.assertIs(jobs.prepare_mesh(self.paths, self.payload, cancel), result)
        prepare.assert_called_once_with(self.paths, self.payload, cancel, progress=None)

    def test_owned_package_retains_high_quality_provider(self):
        self.assertEqual(self.call()['readonly_descriptor'], 'descriptor')
        kwargs = self.adapter.prepare_readonly.call_args.kwargs
        self.assertEqual(kwargs['quality_scale'], 2)
        self.assertTrue(callable(kwargs['layer_provider']))

    def test_preview_only_does_not_create_source_layer_capability(self):
        self.manifest['sharing'] = {'exportable': False, 'preview_only': True, 'local_unowned_preview': True}
        self.payload['package_path'] = str(self.root / 'test.kfpspreview')
        self.payload['source_path'] = str(self.root / 'C_livery')
        self.call()
        self.assertIsNone(self.adapter.prepare_readonly.call_args.kwargs['layer_provider'])

    def test_private_preview_without_source_does_not_get_layer_provider(self):
        self.payload['package_path'] = str(self.root / 'test.kfpspreview')
        self.call()
        self.assertIsNone(self.adapter.prepare_readonly.call_args.kwargs['layer_provider'])

    def test_car_and_package_identity_mismatch_fail_before_preparation(self):
        for key, value in [('car_id', 9), ('package_id', 'other')]:
            with self.subTest(key=key):
                original = self.payload[key]
                self.payload[key] = value
                with self.assertRaises(ValueError):
                    self.call()
                self.payload[key] = original
        self.adapter.prepare_readonly.assert_not_called()

    def test_invalid_package_never_reaches_studio(self):
        with patch('tools.livery.package.validate_livery_inspection_artifact', side_effect=ValueError('invalid')), \
             patch.object(operations, 'studio_module') as load:
            with self.assertRaises(ValueError):
                operations.prepare_mesh(self.paths, self.payload, threading.Event())
        load.assert_not_called()

    def test_missing_studio_is_explicit_not_an_old_viewer_fallback(self):
        with self.assertRaisesRegex(ValueError, 'required'):
            operations.studio_package(self.root)

    def test_sibling_discovery_checks_host_identity(self):
        repo = self.root / 'repo'
        repo.mkdir()
        studio = self.root / 'livery'
        (studio / 'settings').mkdir(parents=True)
        config = studio / 'settings/local-launch.json'
        config.write_text(json.dumps({'kfpsRoot': str(self.root / 'other')}))
        with self.assertRaisesRegex(ValueError, 'different'):
            operations.studio_package(repo)

    def test_inspector_never_loads_the_authoring_server_or_old_fallback(self):
        config, ready, stop = [self.root / name for name in ('config.json', 'ready.json', 'stop')]
        config.write_text(json.dumps({'app_root': str(self.root), 'readonly_descriptor': str(self.root / 'descriptor'),
                                     'package_id': 'package', 'readonly_descriptor_sha256': 'a' * 64}))
        stop.touch()
        server = Mock()
        server.start.return_value = 'http://127.0.0.1:1234/session/'
        module = SimpleNamespace(ReadonlyPreviewServer=Mock(return_value=server))
        with patch.object(inspector_main, 'studio_module', return_value=module) as loader:
            self.assertEqual(inspector_main.run(config, ready, stop, os.getpid()), 0)
        loader.assert_called_once_with(str(self.root), 'readonly_server')
        module.ReadonlyPreviewServer.assert_called_once_with(str(self.root / 'descriptor'), self.root,
            expected_package_id='package', expected_descriptor_sha256='a' * 64)
        server.close.assert_called_once()
        self.assertEqual(json.loads(ready.read_text())['url'], server.start.return_value)

    def test_missing_descriptor_reports_start_error_and_closes(self):
        config, ready, stop = [self.root / name for name in ('config.json', 'ready.json', 'stop')]
        config.write_text('{}')
        with patch.object(inspector_main, 'studio_module') as loader:
            self.assertEqual(inspector_main.run(config, ready, stop, os.getpid()), 2)
        loader.assert_not_called()
        self.assertIn('not prepared', (self.root / 'error.txt').read_text())


if __name__ == '__main__':
    unittest.main()
