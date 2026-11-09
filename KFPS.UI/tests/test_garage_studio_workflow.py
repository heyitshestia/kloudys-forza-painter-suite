"""Garage handoffs using isolated files, no user saves or windows."""
from contextlib import ExitStack, nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'KFPS.UI/src'), str(ROOT / 'tools/livery-studio/src')]
from PySide6.QtCore import QCoreApplication
from kfps_ui import garage_notes as notes
from kfps_ui.app_paths import AppPaths
from kfps_ui.editor_service import EditorService
from kfps_ui.log_service import LogService
from kfps_livery_lab import host_bridge as bridge
from kfps_livery_lab.project_storage import ProjectStore
from test_garage_launch import build
from test_studio_package_handoff import make_package

VEHICLE = {'car_id': 3307, 'model_code': 'TEST_CAR'}


def project():
    shape = {'type': 1048677, 'data': [10, 20, 1, -1, 33, .2, 0], 'color': [10, 30, 40, 255],
             'editor_group_path': [{'id': 'nested', 'name': 'Nested'}],
             'editor_group_id': 'nested', 'editor_group_name': 'Nested'}
    return {'format': 'kfps-livery-layout-v1', 'vehicle': dict(VEHICLE),
            'vinyls': [{'id': 'custom-source', 'name': 'Original source', 'shapes': [shape]}],
            'placements': [{'id': pid, 'vinylId': 'custom-source', 'section': 'Front', 'x': x, 'y': 2,
                            'scaleX': .8, 'scaleY': 1.2, 'rotation': 31, 'opacity': .75,
                            'visible': True, 'skew': .1} for pid, x in [('one', 5), ('two', -5)]],
            'vehicle_parts': {'RearWing': 7},
            'authoring': {'version': 1, 'groups': [{'id': 'group', 'name': 'Pair', 'placements': ['one', 'two']}],
                          'locked': ['one'], 'links': []}}


class LinkedProjectReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_current_managed_revision_is_frozen_and_store_stays_unchanged(self):
        store = ProjectStore(self.root / 'projects')
        value = project()
        first = store.save(VEHICLE, {'name': 'Linked', 'project': value})['entry']
        info = notes.inspect_project(next(store.root.rglob(first['file_name'])), VEHICLE['car_id'], ROOT)
        value['vehicle_parts']['RearWing'] = 8
        store.save(VEHICLE, {'id': first['id'], 'expected_revision': first['revision'], 'name': 'Linked', 'project': value})
        before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        frozen = notes.read_linked_project(info, ROOT)
        self.assertEqual(value, frozen)
        self.assertEqual(before, {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()})
        for p in store.root.rglob('*.json'):
            p.unlink()
        self.assertEqual(value, frozen)

    def test_wrong_car_invalid_reference_and_changed_catalogue_fail_closed(self):
        file = self.root / 'project.json'
        file.write_text(json.dumps(project()))
        info = notes.inspect_project(file, VEHICLE['car_id'], ROOT)
        value = project()
        value['vehicle']['model_code'] = 'OTHER'
        file.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            notes.read_linked_project(info, ROOT)
        with self.assertRaises(ValueError):
            notes.read_linked_project({**info, 'injected': True}, ROOT)
        file.write_text(json.dumps(project()))
        info.update(managedId='a' * 32, managedRoot=str(self.root))
        with patch.object(notes, '_managed_path', side_effect=[(file, info['revision'], file.stat().st_size),
                                                              (file, 'f' * 64, file.stat().st_size)]):
            with self.assertRaisesRegex(ValueError, 'chang'):
                notes.read_linked_project(info, ROOT)

    def test_hardlinked_project_and_cancelled_read_are_rejected(self):
        import threading
        file = self.root / 'project.json'
        file.write_text(json.dumps(project()))
        info = notes.inspect_project(file, VEHICLE['car_id'], ROOT)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            notes.read_linked_project(info, ROOT, cancel=cancel)
        os.link(file, self.root / 'alias.json')
        with self.assertRaises(ValueError):
            notes.read_linked_project(info, ROOT)


class ProjectHandoffTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for target, name, value in [(bridge, 'LAB_ROOT', self.root), (bridge, 'HANDOFF_ROOT', self.root / 'runs/inbox'),
                                    (bridge.launcher, 'LAB_ROOT', self.root),
                                    (bridge.launcher, 'CONTROL', self.root / 'runs/control')]:
            self.stack.enter_context(patch.object(target, name, value))

    def test_full_project_roundtrip_is_detached_and_separate_from_packages(self):
        original = project()
        request = {'name': 'Linked project', 'project': original}
        identifier = bridge.stage_handoff(request)
        original['authoring']['groups'].clear()
        self.assertEqual(project(), bridge.read_project_handoff(identifier, resolve_resource=lambda _: True)['project'])
        with self.assertRaises(bridge.HandoffError):
            bridge.read_layout_handoff(identifier)
        with self.assertRaises(ValueError):
            bridge.validate_request({'name': 'Not a package', 'layout': project()})

    def test_project_created_from_decoded_artwork_preserves_all_source_metadata(self):
        path = self.root / 'fixture.kfpslivery'
        make_package(path)
        value = bridge.request_for_package(path)['layout']
        value['vinyls'][0]['shapes'][0].update(shape_name='Original layer', editor_locked=True)
        result = bridge.validate_request({'project': value})
        self.assertEqual(value, result['project'])

    def test_stock_project_needs_no_owned_snapshot_or_artwork(self):
        request = bridge.request_for_stock(VEHICLE)
        self.assertEqual({'format': 'kfps-livery-layout-v1', 'vehicle': VEHICLE, 'vinyls': [], 'placements': []}, request['project'])
        self.assertNotIn('garage_build', json.dumps(request))
        self.assertNotIn('instanceId', json.dumps(request))

    def test_unknown_or_path_bearing_metadata_rejected_without_sanitizing(self):
        for change in (lambda p: p.update(path='C:/private/project.json'),
                       lambda p: p['vehicle'].update(path='C:/private'),
                       lambda p: p['vinyls'][0]['shapes'][0].update(resource='C:/private/image.png')):
            value = project()
            change(value)
            with self.assertRaises(ValueError):
                bridge.validate_request({'project': value})

    def test_real_save_decode_rechecks_ownership_car_and_groups(self):
        package = self.root / 'fixture.kfpslivery'
        raw = make_package(package)
        file = self.root / 'C_livery'
        file.write_bytes(raw)
        before = file.read_bytes()
        result = bridge.request_for_garage_artwork(VEHICLE, build(), file, 'save')
        self.assertEqual(build(), result['layout']['garage_build'])
        self.assertEqual([2, 2, 1, 0], [len(s.get('editor_group_path', [])) for s in result['layout']['vinyls'][0]['shapes']])
        self.assertEqual(before, file.read_bytes())
        with self.assertRaises(ValueError):
            bridge.request_for_garage_artwork({**VEHICLE, 'car_id': 123}, build(), file, 'save')
        blocked = bytearray(raw)
        blocked[8:12] = (1).to_bytes(4, 'little')
        file.write_bytes(blocked)
        with self.assertRaises(ValueError):
            bridge.request_for_garage_artwork(VEHICLE, build(), file, 'save')

    def test_package_artwork_is_same_car_and_frozen_with_selected_build(self):
        path = self.root / 'fixture.kfpslivery'
        make_package(path)
        before = path.read_bytes()
        result = bridge.request_for_garage_artwork(VEHICLE, build(), path, 'package')
        self.assertEqual(build(), result['layout']['garage_build'])
        self.assertEqual(before, path.read_bytes())
        with self.assertRaises(ValueError):
            bridge.request_for_garage_artwork({**VEHICLE, 'model_code': 'Other'}, build(), path, 'package')
        with self.assertRaises(ValueError):
            bridge.request_for_garage_artwork(VEHICLE, build(), path, 'unknown')

    def test_expected_artwork_digest_accepts_exact_package_and_save_bytes(self):
        package = self.root / 'fixture.kfpslivery'
        raw = make_package(package)
        save = self.root / 'C_livery'
        save.write_bytes(raw)
        for kind, path in (('package', package), ('save', save)):
            with self.subTest(kind=kind):
                expected = hashlib.sha256(path.read_bytes()).hexdigest()
                previous = bridge.request_for_garage_artwork(VEHICLE, build(), path, kind)
                received = bridge.request_for_garage_artwork(VEHICLE, build(), path, kind, expected=expected)
                self.assertEqual(previous, received)
                self.assertNotIn(expected, json.dumps(received))

    def test_changed_artwork_with_same_name_size_and_time_fails_before_decoding(self):
        package = self.root / 'fixture.kfpslivery'
        raw = make_package(package)
        save = self.root / 'C_livery'
        save.write_bytes(raw)
        for kind, path, decoder in (
                ('package', package, 'kfps_livery_lab.package_handoff.unwrap_bounded'),
                ('save', save, 'kfps_livery_lab.save_codec.SaveTemplate.read')):
            with self.subTest(kind=kind):
                original = path.read_bytes()
                expected = hashlib.sha256(original).hexdigest()
                stamp = path.stat()
                changed = bytearray(original)
                changed[-1] ^= 1
                path.write_bytes(changed)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                self.assertEqual(stamp.st_size, path.stat().st_size)
                self.assertEqual(stamp.st_mtime_ns, path.stat().st_mtime_ns)
                with patch(decoder, side_effect=AssertionError('Changed bytes reached decoding')) as decode:
                    with self.assertRaisesRegex(ValueError, 'changed') as caught:
                        bridge.request_for_garage_artwork(VEHICLE, build(), path, kind, expected=expected)
                    decode.assert_not_called()
                    self.assertNotIn(expected, str(caught.exception))
                    self.assertNotIn(str(path), str(caught.exception))

    def test_invalid_expected_artwork_fingerprints_fail_explicitly(self):
        for expected in (None, False, 'bad', 'a' * 63, 'a' * 65, 'A' * 64):
            for kind in ('package', 'save'):
                with self.subTest(kind=kind, expected=expected), self.assertRaisesRegex(ValueError, 'fingerprint'):
                    bridge.request_for_garage_artwork(VEHICLE, build(), self.root / 'missing', kind, expected=expected)

    def test_project_envelope_expiry_limits_and_resources_are_checked(self):
        identifier = bridge.stage_handoff({'name': 'Project', 'project': project()})
        with self.assertRaises(bridge.HandoffError) as caught:
            bridge.read_project_handoff(identifier, resolve_resource=lambda _: None)
        self.assertEqual(422, caught.exception.status)
        with patch.object(bridge, 'MAX_LAYOUT_BYTES', 10), self.assertRaises(bridge.HandoffError) as caught:
            bridge.read_project_handoff(identifier)
        self.assertEqual(413, caught.exception.status)
        path = bridge.HANDOFF_ROOT / (identifier + '.json')
        envelope = json.loads(path.read_bytes())
        envelope['created'] = 1
        path.write_text(json.dumps(envelope))
        with self.assertRaises(bridge.HandoffError) as caught:
            bridge.read_project_handoff(identifier)
        self.assertEqual(410, caught.exception.status)
        with self.assertRaises(ValueError):
            bridge.validate_request({'project': project(), 'vinyl': None})

    def test_project_launch_preserves_native_shared_and_chrome_guards(self):
        url = 'http://127.0.0.1:1234/' + 'a' * 43 + '/'
        request = {'name': 'Linked', 'project': project()}
        for chrome, shared, owned, different, permitted in (
                (True, True, False, False, True), (True, True, False, True, False),
                (False, False, True, True, True), (False, True, True, True, False),
                (False, False, False, True, False)):
            ready = {'url': url, 'reused': True, 'chrome_exposed': shared, 'host_project_handoff': True,
                     'vehicle': {'car_id': 99, 'model_code': 'OTHER'} if different else VEHICLE}
            window = SimpleNamespace(use_chrome=lambda _: chrome, owns_native_url=lambda *_: owned)
            with self.subTest(chrome=chrome, shared=shared, owned=owned, different=different), \
                    patch.object(bridge.launcher, 'ensure_ready', return_value=ready) as ensure, \
                    patch.object(bridge.launcher, '_window_module', return_value=window), \
                    patch.object(bridge, '_native_admission', return_value=nullcontext()):
                if permitted:
                    result = bridge.launch_from_host(ROOT, request, native_owner=object())
                    self.assertIn('#project=', result['url'])
                    frozen = bridge.read_project_handoff(result['url'].split('=')[-1])
                    self.assertEqual(project(), frozen['project'])
                    self.assertEqual(owned and not chrome and not shared, 'startup_session' in frozen)
                else:
                    with self.assertRaises(ValueError):
                        bridge.launch_from_host(ROOT, request, native_owner=object())
                self.assertEqual(VEHICLE, ensure.call_args.kwargs['initial_vehicle'])

    def test_project_native_and_chrome_urls_are_opaque_only(self):
        from kfps_livery_lab.studio_window import validate_window_url
        url = 'http://127.0.0.1:1234/' + 'a' * 43 + '/'
        with patch.dict(os.environ, {'KFPS_LIVERY_NO_OPEN': '1'}):
            self.assertFalse(bridge.launcher.open_studio_window(url + '#project=' + 'b' * 32))
            validate_window_url(url + '#project=' + 'b' * 32)
            for fragment in ('project=C:/private.json', 'project=' + 'b' * 32 + '&path=private'):
                with self.assertRaises(ValueError):
                    validate_window_url(url + '#' + fragment)

    def test_save_rejects_hardlinks_and_oversize_without_reading(self):
        path = self.root / 'C_livery'
        path.write_bytes(b'not a save')
        os.link(path, self.root / 'alias')
        with self.assertRaises(ValueError):
            bridge.request_for_garage_artwork(VEHICLE, build(), path, 'save')
        (self.root / 'alias').unlink()
        from kfps_livery_lab import package_handoff
        with patch.object(package_handoff, 'MAX_PAYLOAD', 1), self.assertRaises(ValueError):
            bridge.request_for_garage_artwork(VEHICLE, build(), path, 'save')


class NativeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        ui = ROOT / 'KFPS.UI'
        paths = AppPaths(self.root, ui, ui / 'qml', ui / 'assets', self.root / 'runtime', Path(sys.executable))
        log = LogService()
        self.addCleanup(log.close)
        with patch.object(EditorService, 'refresh'):
            self.editor = EditorService(paths, Mock(), Mock(), log)
        self.addCleanup(self.editor.close)
        self.stack.enter_context(patch('kfps_ui.editor_service._studio_module_path',
                                      return_value=ROOT / 'tools/livery-studio/src/kfps_livery_lab/host_bridge.py'))

    def test_linked_reference_is_frozen_without_reading_on_ui_thread(self):
        path = self.root / 'linked.json'
        path.write_text(json.dumps(project()))
        info = notes.inspect_project(path, VEHICLE['car_id'], ROOT)
        with patch.object(self.editor, '_start_thread') as start, patch.object(notes, 'read_linked_project') as read:
            self.editor.launchLinkedProjectInLiveryStudio(info)
            start.assert_called_once()
            read.assert_not_called()
            frozen = copy.deepcopy(info)
            info['path'] = 'changed'
            self.assertEqual(frozen, start.call_args.kwargs['args'][0])
            self.editor.launchLinkedProjectInLiveryStudio(info)
            start.assert_called_once()

    def test_linked_worker_freezes_current_body_before_launch_and_honors_cancel(self):
        path = self.root / 'linked.json'
        path.write_text(json.dumps(project()))
        info = notes.inspect_project(path, VEHICLE['car_id'], ROOT)
        with patch.object(self.editor, '_launch_project_studio_worker') as launch:
            self.editor._launch_linked_project_studio_worker(info, None)
            path.write_text('{}')
            self.assertEqual(project(), launch.call_args.args[0]['project'])
            launch.reset_mock()
            self.editor._cancel_event.set()
            self.editor._launch_linked_project_studio_worker(info, None)
            launch.assert_not_called()

    def test_stock_public_api_uses_existing_launcher_and_cancellation(self):
        with patch.object(self.editor, '_start_thread') as start:
            self.editor.launchStockInLiveryStudio(VEHICLE)
            start.assert_called_once()
            self.assertNotIn('garage_build', json.dumps(start.call_args.kwargs['args']))
        self.editor._cancel_event.set()
        with patch.object(self.editor, '_launch_studio_worker') as launch:
            start.call_args.kwargs['target'](*start.call_args.kwargs['args'])
            launch.assert_not_called()

    def test_artwork_api_freezes_identity_build_and_theme(self):
        value, snapshot = dict(VEHICLE), build()
        theme = {'name': 'Test', 'variables': {'--accent': '#ee4477'}}
        with patch.object(self.editor, '_start_thread') as start:
            self.editor.launchGarageArtworkInLiveryStudio(value, snapshot, str(self.root / 'C_livery'), 'save', theme)
            start.assert_called_once()
            value['car_id'] = 99
            snapshot['parts']['RearWing'] = 99
            theme['variables']['--accent'] = 'changed'
            args = start.call_args.kwargs['args']
            self.assertEqual((VEHICLE, build(), 'save', '#ee4477'), (args[0], args[1], args[3], args[4]['variables']['--accent']))
            self.assertEqual('', args[5])

    def test_artwork_api_keeps_legacy_slots_and_appends_expected_digest(self):
        for signature in (
                'launchGarageArtworkInLiveryStudio(QVariantMap,QVariantMap,QString,QString)',
                'launchGarageArtworkInLiveryStudio(QVariantMap,QVariantMap,QString,QString,QVariantMap)',
                'launchGarageArtworkInLiveryStudio(QVariantMap,QVariantMap,QString,QString,QVariantMap,QString)'):
            self.assertGreaterEqual(self.editor.metaObject().indexOfMethod(signature), 0, signature)
        expected = 'a' * 64
        with patch.object(self.editor, '_start_thread') as start:
            self.editor.launchGarageArtworkInLiveryStudio(VEHICLE, build(), str(self.root / 'C_livery'), 'save', None, expected)
            self.assertEqual(expected, start.call_args.kwargs['args'][5])
            self.assertEqual(6, len(start.call_args.kwargs['args']))

    def test_artwork_worker_forwards_expected_digest_to_bridge(self):
        value = {'name': 'Artwork', 'layout': {}}
        adapter = SimpleNamespace(request_for_garage_artwork=Mock(return_value=value), validate_request=lambda request: request)
        with patch.object(self.editor, '_garage_studio_bridge', return_value=adapter), \
                patch.object(self.editor, '_resolve_studio_vehicle'), patch.object(self.editor, '_launch_studio_worker') as launch:
            self.editor._launch_garage_artwork_studio_worker(VEHICLE, build(), 'source', 'save', None, 'a' * 64)
            adapter.request_for_garage_artwork.assert_called_once_with(VEHICLE, build(), 'source', 'save', expected='a' * 64)
            launch.assert_called_once_with(value)

    def test_invalid_expected_digest_never_queues_native_work(self):
        with patch.object(self.editor, '_start_thread') as start:
            self.editor.launchGarageArtworkInLiveryStudio(VEHICLE, build(), str(self.root / 'C_livery'), 'save', None, 'bad')
            start.assert_not_called()
            self.assertIn('fingerprint', self.editor.studioStatus)

    def test_new_launch_diagnostics_do_not_record_error_paths_or_ids(self):
        with patch.object(self.editor, '_start_thread') as start:
            self.editor.launchStockInLiveryStudio({})
            start.assert_not_called()
        self.editor._studio_garage_workflow = True
        self.editor._finish_studio_launch(False, 'C:/private/1234567890.json')
        log = '\n'.join(self.editor.log._diagnostic_lines)
        self.assertIn('Garage Studio: outcome=unavailable', log)
        self.assertNotIn('private', log)
        self.assertNotIn('1234567890', log)


class ProjectRouteTests(unittest.TestCase):
    def setUp(self):
        import test_studio_preview_quality_routes as routes
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(routes, 'RUN', ROOT / 'tools/livery-studio/runs/garage-workflow-20261104/http'))
        self.fixture = routes.PreviewQualityRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.stack.enter_context(patch.object(bridge, 'HANDOFF_ROOT', self.fixture.root / 'runs/inbox'))
        self.stack.enter_context(patch.object(bridge, 'LAB_ROOT', self.fixture.root))
        self.stack.enter_context(patch.object(bridge.launcher, '_launch_lock', return_value=nullcontext()))
        self.identifier = bridge.stage_handoff({'name': 'Project', 'project': project()})

    def test_token_scoped_project_http_roundtrip_and_restart(self):
        route = 'api/host-project/' + self.identifier
        request = self.fixture.request
        status, headers, body = request('GET', route)
        self.assertEqual(200, status)
        self.assertEqual('no-store', headers['Cache-Control'])
        self.assertEqual(project(), json.loads(body)['project'])
        self.assertTrue(json.loads(request('GET', 'api/editor-config')[2])['host_project_handoff'])
        old = self.fixture.prefix
        self.fixture.server.close()
        self.fixture.start()
        self.assertEqual(404, request('GET', old + route, raw_path=True)[0])
        self.assertEqual(project(), json.loads(request('GET', route)[2])['project'])
        for method, url, headers, expected in (
                ('POST', route, {}, 405), ('GET', route + '?path=C:/private', {}, 400),
                ('GET', route, {'Origin': 'http://evil.test'}, 403),
                ('GET', 'api/host-project/../private', {}, 400)):
            self.assertEqual(expected, request(method, url, headers=headers)[0])


if __name__ == '__main__':
    unittest.main()
