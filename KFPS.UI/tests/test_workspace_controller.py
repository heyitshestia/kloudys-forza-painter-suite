"""Workspace admission keeps private source jobs separate from normal documents."""
import json
from pathlib import Path
import secrets
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QUrl
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import delete
from kfps_ui.workspace_host import WorkspaceWindow
from kfps_ui.workspace_controller import WorkspaceController

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / 'tools/livery-studio'
sys.path.insert(0, str(LAB / 'src'))
from kfps_livery_lab.source_editor import SourceEditor, PROJECT_ID, DESCRIPTOR

APP = QApplication.instance() or QApplication([])


class FakeEditor(QWidget):
    instances = []

    def __init__(self, root, runtime, **options):
        super().__init__()
        self.root, self.runtime, self.options = root, runtime, options
        self.server = SimpleNamespace()
        self.requests = []
        self.workspace_present = None
        self.instances.append(self)

    def start(self, request):
        self.requests.append(request)
        return True

    def shutdown(self):
        pass


class WorkspaceControllerTests(unittest.TestCase):
    def setUp(self):
        (LAB / 'runs').mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='workspace-test-', dir=LAB / 'runs')
        self.directory = Path(self.temporary.name)
        self.main = QWindow()
        self.shell = WorkspaceWindow(self.main, offscreen=True)
        self.paths = SimpleNamespace(app_root=self.directory, runtime_root=self.directory / 'runtime')
        self.service = Mock()
        self.runtime = SimpleNamespace(baseline={'status':'development'}, borrow_guard=Mock(return_value=Mock()))
        self.controller = WorkspaceController(self.shell, self.paths, self.service, self.runtime)
        self.token = secrets.token_urlsafe(32)
        self.url = 'http://127.0.0.1:32100/' + self.token + '/'
        self.studio = SimpleNamespace(page=SimpleNamespace(url=lambda: QUrl(self.url)), shutdown=lambda: None)
        self.shell.install_surface('Studio', QWidget(), self.studio)
        self.manager = SourceEditor(self.directory, self.directory, launch=lambda *_: None)
        job = self.manager.start({'documentId':'document-1', 'sourceId':'source-1', 'sourceRevision':0,
            'source':{'name':'Fixture', 'shapes':[{'type':1048677,'data':[0,0,1,1,0,0,0],'color':[255,0,0,255]}]}},
            self.token, self.url, lambda _: True)
        self.job = self.manager.jobs[job['id']]
        self.project = self.job['runtime'] / 'projects' / PROJECT_ID
        self.request = {'mode':'activate', 'project':self.project.relative_to(self.directory).as_posix(), 'background':True}
        FakeEditor.instances.clear()
        self.patch = patch('kfps_editor.host.EditorDesktop', FakeEditor)
        self.patch.start()
        self.module_patch = patch('kfps_ui.workspace_controller._studio_module_path',
                                  return_value=LAB / 'src/kfps_livery_lab/source_editor.py')
        self.module_patch.start()

    def tearDown(self):
        self.patch.stop()
        self.module_patch.stop()
        self.controller.close()
        self.manager.close()
        self.shell.shutdown()
        delete(self.shell)
        delete(self.main)
        self.temporary.cleanup()

    def test_source_job_opens_private_runtime_once(self):
        self.controller._open_source(self.request)
        self.controller._open_source(self.request)
        self.assertEqual(len(FakeEditor.instances), 1)
        host = FakeEditor.instances[0]
        self.assertEqual(host.runtime, self.job['runtime'])
        self.assertEqual(host.workspace_source_name, 'Fixture')
        self.assertEqual(self.shell.tabs.tabText(self.shell._index('Source ' + self.job['id'][:8])),
                         'Source artwork: Fixture')
        self.assertEqual(host.requests, [{'mode':'activate', 'project':PROJECT_ID}])
        self.assertNotIn('Editor', self.shell.owners)
        self.assertTrue(callable(host.server.workspace_source_returned))

    def test_explicit_project_open_supersedes_deferred_studio_restore(self):
        session = self.controller._session = Mock()
        for kind in ("project", "layout", "vinyl"):
            session.reset_mock()
            with patch('kfps_ui.workspace_controller._studio_module_path', side_effect=RuntimeError('stop before launch')):
                with self.assertRaisesRegex(RuntimeError, 'stop before launch'):
                    self.controller._prepare_studio({kind: {}}, None, 'test')
            session.explicit_open.assert_called_once_with('Studio')
        session.reset_mock()
        with patch('kfps_ui.workspace_controller._studio_module_path', side_effect=RuntimeError('stop before launch')):
            with self.assertRaises(RuntimeError):
                self.controller._prepare_studio({}, None, 'test')
        session.explicit_open.assert_not_called()

    def test_other_studio_session_cannot_open_source(self):
        self.studio.page.url = lambda: QUrl('http://127.0.0.1:32101/' + self.token + '/')
        with self.assertRaisesRegex(ValueError, 'another Studio'):
            self.controller._open_source(self.request)
        self.assertEqual(FakeEditor.instances, [])

    def test_expired_descriptor_cannot_open_source(self):
        marker = self.job['runtime'] / DESCRIPTOR
        data = json.loads(marker.read_text(encoding='utf-8'))
        data['expiresAt'] = 1
        marker.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError): self.controller._open_source(self.request)
        self.assertEqual(FakeEditor.instances, [])

    def test_wrong_project_name_rejected(self):
        request = dict(self.request, project=self.request['project'].replace(PROJECT_ID,'Other.fabric-project.json'))
        with self.assertRaises(ValueError): self.controller._open_source(request)

    def test_traversal_and_unknown_operations_rejected(self):
        for value in ({'project':'../escape.fabric-project.json'}, {'project':'C:/escape.fabric-project.json'},
                      {'mode':'new'}, {'mode':'activate','json':'imgs/generated/test.json'},
                      dict(self.request, execute='something')):
            with self.subTest(value=value), self.assertRaises((ValueError, KeyError)):
                self.controller._open_source(value)
        self.assertEqual(FakeEditor.instances, [])

    def test_closing_workspace_rejects_source_and_editor(self):
        self.shell._closing = True
        with self.assertRaises(ValueError): self.controller._open_source(self.request)
        with self.assertRaises(RuntimeError): self.controller.open_editor({'mode':'activate'})
        self.assertEqual(FakeEditor.instances, [])

    def test_chrome_preference_keeps_standalone_launch(self):
        with patch('kfps_editor.launch_preferences.use_chrome', return_value=True):
            self.assertFalse(self.controller.open_editor({'mode':'activate'}))
        self.assertEqual(FakeEditor.instances, [])

    def test_existing_separate_editor_is_not_duplicated(self):
        with patch('kfps_editor.launch_preferences.use_chrome', return_value=False), \
             patch('kfps_ui.workspace_controller.editor_is_open', return_value=True):
            self.assertFalse(self.controller.open_editor({'mode':'activate'}))
        self.assertEqual(FakeEditor.instances, [])

    def test_close_releases_waiting_workers_and_callbacks(self):
        import threading
        pending = {'done':threading.Event(), 'error':''}
        self.controller._pending.append(pending)
        self.controller.close()
        self.assertTrue(pending['done'].is_set())
        self.assertEqual(pending['error'], 'Workspace closed.')
        self.assertIsNone(self.service.workspace_editor)
        self.assertIsNone(self.service.workspace_studio)
        self.assertFalse(self.controller.lock.isLocked())

    def test_backend_cleanup_waits_for_final_shutdown_and_is_idempotent(self):
        stop = Mock(return_value='stopped')
        self.controller._bridge = SimpleNamespace(launcher=SimpleNamespace(stop_workspace_backend=stop))
        backend = {'pid': 123, 'created': 12.0, 'workspace': str(self.directory), 'managed': True, 'url': self.url}
        self.controller._remember_studio_backend(backend)
        self.controller._remember_studio_backend(backend)
        self.controller.close()
        stop.assert_not_called()
        self.assertTrue(self.controller.shutdown_studio_backends())
        self.controller.shutdown_studio_backends()
        stop.assert_called_once_with(backend, expected_kfps_root=self.directory)

    def test_late_startup_completion_is_stopped_without_installing_a_tab(self):
        stop = Mock(return_value='stopped')
        self.controller._bridge = SimpleNamespace(launcher=SimpleNamespace(stop_workspace_backend=stop))
        self.controller.close()
        self.controller.shutdown_studio_backends()
        backend = {'pid': 123, 'created': 12.0, 'workspace': str(self.directory), 'managed': True, 'url': self.url}
        self.controller._remember_studio_backend(backend)
        stop.assert_called_once()
        self.assertEqual({}, self.controller._studio_backends)

    def test_cleanup_failure_does_not_skip_other_backend_and_shared_is_retained(self):
        stop = Mock(side_effect=[OSError('fixture'), 'shared'])
        self.controller._bridge = SimpleNamespace(launcher=SimpleNamespace(stop_workspace_backend=stop))
        for pid in (123, 124):
            self.controller._remember_studio_backend({'pid': pid, 'created': 12., 'managed': True})
        self.controller.close()
        self.assertFalse(self.controller.shutdown_studio_backends())
        self.assertEqual(2, stop.call_count)

    def test_cancelled_studio_request_cannot_install_a_tab(self):
        import threading
        event = threading.Event()
        event.set()
        pending = {'done':threading.Event(), 'error':'', 'cancelled':event,
                   'result':{'url':self.url}}
        self.controller._install_studio(pending)
        self.assertTrue(pending['done'].is_set())
        self.assertTrue(pending['error'])
        self.assertIs(self.shell.owners['Studio'], self.studio)
        self.assertEqual(self.controller._pending, [])

    def test_marker_records_no_url_or_secret_and_clears_only_own_session(self):
        self.controller._write_studio_owner(self.studio)
        marker = self.controller._studio_marker
        value = json.loads(marker.read_text(encoding='utf-8'))
        self.assertEqual(value['format'], 'kfps-workspace-studio/1')
        self.assertEqual(len(value['session']), 64)
        self.assertNotIn(self.token, marker.read_text(encoding='utf-8'))
        other = dict(value, session='0' * 64)
        marker.write_text(json.dumps(other), encoding='utf-8')
        self.controller._clear_studio_owner(self.studio)
        self.assertEqual(json.loads(marker.read_text(encoding='utf-8')), other)
        self.controller._write_studio_owner(self.studio)
        self.controller._clear_studio_owner(self.studio)
        self.assertFalse(marker.exists())

    def test_marker_checks_late_runtime_directory_or_file_redirection(self):
        self.controller._write_studio_owner(self.studio)
        marker = self.controller._studio_marker
        original = marker.read_bytes()
        for target in (self.directory / 'runtime', marker.parent, marker):
            for method in ('is_symlink', 'is_junction'):
                with self.subTest(target=str(target), method=method), \
                     patch.object(Path, method, autospec=True, side_effect=lambda path: path == target):
                    self.assertFalse(self.controller._marker_directory_valid())
                    with patch('kfps_ui.workspace_controller.os.replace') as replace:
                        self.controller._write_studio_owner(self.studio)
                        replace.assert_not_called()
                    self.controller._clear_studio_owner(self.studio)
                    self.assertEqual(marker.read_bytes(), original)
        self.assertTrue(self.controller._marker_directory_valid())
        self.controller._clear_studio_owner(self.studio)
        self.assertFalse(marker.exists())

    def test_second_workspace_cannot_take_owned_ipc(self):
        with self.assertRaisesRegex(RuntimeError, 'already open'):
            WorkspaceController(self.shell, self.paths, Mock(), self.runtime)
        self.assertTrue(self.controller.ipc.isListening())
