"""Private-data-free lifecycle evidence through real logging/report boundaries."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'KFPS.UI/src'), str(ROOT / 'KFPS.Editor/src'),
               str(ROOT / 'tools/livery-studio/src/kfps_livery_lab')]

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import delete, isValid

from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService
from kfps_ui.support_report import build_support_report
from kfps_ui.workspace_controller import WorkspaceController
from kfps_ui.workspace_diagnostics import COMPONENT_REVISION, MAX_EVENTS, REPORT_EVENTS, SCHEMA, clean_event, operation, record
from kfps_ui.workspace_host import WorkspaceWindow
from kfps_ui.workspace_session import SessionStore, WorkspaceSession

APP = QApplication.instance() or QApplication([])
PRIVATE = 'C:/Private/Artwork.png https://127.0.0.1/SECRET_URL_TOKEN/?password=PRIVATE_SECRET'


class Owner(QObject):
    closed = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.callback = None
        self.fail_cleanup = False

    def prepare_close(self, callback):
        self.callback = callback

    def commit_close(self):
        return None

    def cancel_close(self):
        return None

    def shutdown(self):
        if self.fail_cleanup:
            raise OSError(PRIVATE)


class WorkspaceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workspace-diagnostics-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Finish fixture directory creation before the asynchronous writer starts.
        (self.root / 'runtime/workspace').mkdir(parents=True)
        self.log = LogService(runtime_root=self.root / 'runtime')
        self.addCleanup(self.log.close)
        self.log.configure_diagnostics('3.1.124', 'unified')

    def events(self, name=None):
        rows = self.log.workspace_snapshot()
        return [row for row in rows if name is None or row['event'] == name]

    def assert_private_absent(self, value):
        text = json.dumps(value)
        for private in ('Private', 'Artwork', 'SECRET_URL_TOKEN', 'PRIVATE_SECRET', '127.0.0.1'):
            self.assertNotIn(private, text)

    def workspace(self):
        main = QWindow()
        shell = WorkspaceWindow(main, offscreen=True, log=self.log)

        def close():
            shell.shutdown()
            delete(shell)
            if isValid(main):
                delete(main)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.addCleanup(close)
        return shell

    def controller(self, shell):
        service = SimpleNamespace(log=self.log, _finish_launch=Mock())
        paths = SimpleNamespace(app_root=self.root, runtime_root=self.root / 'runtime')
        runtime = SimpleNamespace(baseline={'status': 'development'}, borrow_guard=Mock())
        controller = WorkspaceController(shell, paths, service, runtime)
        self.addCleanup(controller.close)
        return controller

    def test_allowlists_reject_private_fields_and_malformed_numbers(self):
        record(self.log, 'handoff.studio', 'failed', error=ValueError(PRIVATE),
               surface=PRIVATE, stage=PRIVATE, path=PRIVATE, url=PRIVATE,
               shapes=[{'name': PRIVATE}], file_count=True, byte_count=-1,
               cache_hits=2**54, elapsed_ms=float('nan'), verification_ms=float('inf'))
        row = self.events()[0]
        self.assertEqual(row['error_type'], 'ValueError')
        for field in ('path', 'url', 'shapes', 'surface', 'stage', 'file_count', 'byte_count',
                      'cache_hits', 'elapsed_ms', 'verification_ms'):
            self.assertNotIn(field, row)
        self.log.diagnostic(PRIVATE, 'failed')
        self.log.diagnostic('app.startup', PRIVATE)
        self.assertEqual(len(self.events()), 1)
        self.assert_private_absent(self.log.diagnostic_snapshot()[0])
        for value in (None, [], {'schema': SCHEMA, 'event': [], 'outcome': 'failed'}):
            self.assertIsNone(clean_event(value))

    def test_correlation_timings_and_build_identity_survive_without_ui_updates(self):
        with patch('kfps_ui.workspace_diagnostics.time.monotonic', return_value=10):
            op = operation()
            record(self.log, 'app.startup', 'started', op=op, verification_ms=12000.25)
        with patch('kfps_ui.workspace_diagnostics.time.monotonic', return_value=12):
            record(self.log, 'app.startup', 'ready', op=op)
        start, end = self.events()
        self.assertEqual(start['operation'], end['operation'])
        self.assertEqual(end['elapsed_ms'], 2000)
        self.assertEqual(start['verification_ms'], 12000.25)
        self.assertNotIn('verification_ms', end)
        self.assertEqual(start['component_revision'], COMPONENT_REVISION)
        self.assertEqual(self.log.workspace_identity()['version'], '3.1.124')
        self.assertEqual(self.log.workspace_identity()['mode'], 'unified')
        self.assertEqual(self.log.plainText, '')
        self.assertTrue(self.log._pending.empty())
        self.assertEqual(self.log.status, 'Ready')
        self.assertEqual(start['session'], end['session'])
        self.assertLess(start['serial'], end['serial'])

    def test_bounded_events_are_thread_safe_and_writer_retains_json(self):
        def write():
            for _ in range(180):
                record(self.log, 'cache.clear', 'completed', file_count=3)
        workers = [threading.Thread(target=write) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(len(self.log._workspace_events), MAX_EVENTS)
        self.assertEqual(len(self.events()), REPORT_EVENTS)
        self.assertTrue(self.log._pending.empty())
        serials = [row['serial'] for row in self.events()]
        self.assertEqual(serials, sorted(set(serials)))
        self.log.close()
        self.assertFalse(self.log._writer.thread.is_alive())
        self.assertFalse(self.log._writer.failed)
        raw = next((self.root / 'runtime/app-logs').glob('app-*.log')).read_text(encoding='utf-8')
        for line in raw.splitlines():
            self.assertEqual(json.loads(line)['schema'], SCHEMA)
        before = self.events()
        record(self.log, 'app.shutdown', 'completed')
        self.assertEqual(self.events(), before)

    def test_diagnostic_failure_cannot_interrupt_a_caller(self):
        record(SimpleNamespace(diagnostic=Mock(side_effect=OSError(PRIVATE))), 'workspace.close', 'started')
        record(None, 'workspace.close', 'started')
        self.assertEqual(self.events(), [])

    def test_unavailable_or_extreme_timings_are_omitted_not_zero_or_overflow(self):
        for invalid in (None, True, -1, float('inf'), float('nan'), 10**1000, '12000'):
            with self.subTest(value_type=type(invalid).__name__):
                self.log.diagnostic('app.startup', 'started', elapsed_ms=invalid, verification_ms=invalid)
                row = self.events()[-1]
                self.assertNotIn('elapsed_ms', row)
                self.assertNotIn('verification_ms', row)

    def test_actual_workspace_close_cancel_timeout_and_cleanup_failure(self):
        shell = self.workspace()
        owner = Owner()
        shell.add_surface('Source PRIVATE_SECRET', QWidget(), owner)
        self.assertTrue(shell.close_surface('Source PRIVATE_SECRET'))
        owner.callback(False)
        self.assertEqual(self.events('workspace.close')[-1]['outcome'], 'cancelled')
        self.assertIn('Source PRIVATE_SECRET', shell.owners)
        shell.close_surface('Source PRIVATE_SECRET')
        owner.callback(True)
        APP.processEvents()
        shell._commit_timeout()
        self.assertIn('timeout', [row['outcome'] for row in self.events('workspace.close')])
        owner.fail_cleanup = True
        self.assertFalse(shell._retire_surface('Source PRIVATE_SECRET', owner))
        self.assertEqual(self.events('workspace.owner')[-1]['error_type'], 'OSError')
        self.assert_private_absent(self.events())
        owner.fail_cleanup = False
        delete(owner)

    def test_actual_controller_editor_fallback_and_source_validation_failure(self):
        shell = self.workspace()
        controller = self.controller(shell)
        with patch('kfps_editor.launch_preferences.use_chrome', return_value=True):
            self.assertFalse(controller.open_editor({'mode': 'activate'}))
        self.assertEqual(self.events('handoff.editor')[-1]['outcome'], 'fallback')
        with self.assertRaises(ValueError):
            controller._open_source({'mode': 'activate', 'project': '../PRIVATE_SECRET'})
        self.assertEqual(self.events('handoff.source')[-1]['outcome'], 'failed')
        shell._closing = True
        with self.assertRaises(RuntimeError):
            controller.open_editor({'mode': 'activate'})
        self.assertEqual(self.events('handoff.editor')[-1]['error_type'], 'RuntimeError')
        shell._closing = False
        self.assert_private_absent(self.events())

    def test_actual_studio_bridge_failure_and_cancelled_install(self):
        shell = self.workspace()
        controller = self.controller(shell)
        controller._bridge = SimpleNamespace(launch_from_host=Mock(side_effect=OSError(PRIVATE)))
        module = ROOT / 'tools/livery-studio/src/kfps_livery_lab/host_bridge.py'
        with patch('kfps_ui.workspace_controller._studio_module_path', return_value=module), \
                patch('studio_window.use_chrome', return_value=False):
            with self.assertRaises(OSError):
                controller.prepare_studio({})
        self.assertEqual(self.events('handoff.studio')[-1]['error_type'], 'OSError')
        cancelled = threading.Event()
        cancelled.set()
        pending = {'done': threading.Event(), 'error': '', 'cancelled': cancelled,
                   'diagnostic': operation(), 'result': {'url': PRIVATE}}
        controller._install_studio(pending)
        self.assertTrue(pending['done'].is_set())
        self.assertNotIn('Studio', shell.owners)
        self.assertEqual(self.events('handoff.studio')[-1]['outcome'], 'failed')
        self.assert_private_absent(self.events())

    def test_actual_session_read_write_failure_and_restore_timeout(self):
        shell = self.workspace()
        controller = self.controller(shell)
        store = SessionStore(self.root)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text('{broken', encoding='utf-8')
        session = WorkspaceSession(controller, SimpleNamespace(currentPage='create'))
        self.addCleanup(session.close)
        self.assertTrue(session.blocked)
        self.assertEqual(self.events('session.read')[-1]['outcome'], 'failed')
        session.blocked = False
        with patch.object(session.store, 'write', side_effect=OSError(PRIVATE)):
            self.assertFalse(session.persist())
        self.assertEqual(self.events('session.persist')[-1]['error_type'], 'OSError')
        session.staged['Editor'] = {'project': 'PRIVATE_SECRET.fabric-project.json', 'dirty': False}
        session.take('Editor')
        session.restore_timeout('Editor', session.nonces['Editor'])
        rows = self.events('session.restore')
        self.assertEqual([row['outcome'] for row in rows], ['started', 'timeout'])
        self.assertEqual(rows[0]['operation'], rows[1]['operation'])
        self.assert_private_absent(self.events())

    def test_actual_startup_failure_ready_and_registry_error(self):
        from kfps_ui.startup_sequence_service import StartupSequenceService
        jsons = SimpleNamespace(warmIndex=Mock(), indexing=False)
        startup = StartupSequenceService(SimpleNamespace(runtime_root=self.root, asset_root=self.root),
                                         jsons, SimpleNamespace(checking=False), self.log, theme='app')
        self.addCleanup(startup.close)
        startup.beginLoading()
        self.assertEqual(self.events('startup.index')[-1]['outcome'], 'ready')
        startup._record_registry_result({'result': 'error', 'error': PRIVATE})
        self.assertEqual(self.events('startup.registry')[-1]['outcome'], 'failed')
        failing = StartupSequenceService(SimpleNamespace(runtime_root=self.root, asset_root=self.root),
            SimpleNamespace(warmIndex=Mock(side_effect=OSError(PRIVATE))), SimpleNamespace(checking=False), self.log, theme='app')
        self.addCleanup(failing.close)
        with self.assertRaises(OSError):
            failing.beginLoading()
        self.assertEqual(self.events('startup.index')[-1]['error_type'], 'OSError')
        self.assert_private_absent(self.events())

    def test_actual_cache_failure_cancel_success_and_stale_completion(self):
        from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
        from kfps_ui.full_livery_service import FullLiveryService
        ui = ROOT / 'KFPS.UI'
        paths = AppPaths(self.root, ui, ui / 'qml', ui / 'assets', self.root / 'runtime', Path(sys.executable))
        with patch('kfps_ui.full_livery_service.discover_fh6_game_folder', return_value=None):
            service = FullLiveryService(paths, self.log, demo=True)
        self.addCleanup(service.close)
        service._gate = FullLiveryFeatureGate('candidate', 'test')
        for result, expected in (({'ok': False, 'error': PRIVATE}, 'failed'),
                                 ({'cancelled': True, 'error': PRIVATE}, 'cancelled'),
                                 ({'ok': True, 'payload': {'files': 2, 'bytes': 80}}, 'completed')):
            with patch.object(service._tasks, 'start') as start:
                service.clearFullLiveryCache()
                metadata = start.call_args.kwargs['metadata']
            service._apply_result({'kind': 'clear-cache', **metadata, **result})
            row = self.events('cache.clear')[-1]
            self.assertEqual(row['outcome'], expected)
            self.assertEqual(row['operation'], metadata['diagnostic_operation'][0])
            if expected == 'completed':
                self.assertEqual((row['file_count'], row['byte_count']), (2, 80))
            else:
                self.assertNotIn('file_count', row)
            service._apply_result({'kind': 'clear-cache', **metadata, 'ok': True, 'payload': {}})
            self.assertEqual(self.events('cache.clear')[-1]['outcome'], 'discarded')
        self.assert_private_absent(self.events())

    def test_report_service_gathers_events_identity_source_hash_and_real_bundle(self):
        record(self.log, 'handoff.studio', 'failed', op=operation(), error=OSError(PRIVATE))
        source = self.root / 'KFPS.UI/src/kfps_ui/workspace_host.py'
        source.parent.mkdir(parents=True)
        source.write_text('# synthetic code identity\n', encoding='utf-8')
        paths = SimpleNamespace(app_root=self.root, runtime_root=self.root / 'runtime')
        service = ReportService(paths, self.log, SimpleNamespace(localVersion='3.1.124'))
        self.addCleanup(service.close)
        def build(root, context, *, since):
            return build_support_report(root, context, since=since, collect=lambda: {})
        with patch('kfps_ui.report_service.build_support_report', side_effect=build), \
                patch('kfps_ui.report_service.open_support_handoff') as browser:
            service.openSupportForm('editor')
            result = service._future.result(timeout=15)
            service.close()
            browser.assert_not_called()
        saved = json.loads(Path(result['path']).read_text(encoding='utf-8'))
        self.assertEqual(saved['technical']['workspace_events'][-1]['event'], 'handoff.studio')
        self.assertEqual(saved['technical']['workspace_identity']['component_revision'], COMPONENT_REVISION)
        package = json.loads(gzip.decompress((Path(result['path']).parent / 'report.kfps-report.json.gz').read_bytes()))
        logs = json.loads(gzip.decompress(base64.b64decode(package['logs_base64'])))
        files = {file['name']: file['text'] for file in logs['files']}
        self.assertIn('handoff.studio', files['app-status-0000.log'])
        self.assertIn('handoff.studio', files['app-session-0000.log'])
        context = json.loads(files['diagnostic-context-0000.log'])
        identity = context['installation']['workspace-host']
        self.assertEqual(''.join(identity['sha256_groups']), hashlib.sha256(source.read_bytes()).hexdigest())
        for component in ('workspace-tools', 'workspace-tasks', 'workspace-shell', 'workspace-theme',
                          'theme-catalog', 'studio-shared-host', 'studio-preparation', 'studio-atlas-reuse'):
            self.assertIn(component, context['installation'])
        self.assertLess(len(Path(result['path']).read_bytes()), 48 * 1024)
        self.assert_private_absent(saved)
        self.assert_private_absent(files)


if __name__ == '__main__':
    unittest.main()
