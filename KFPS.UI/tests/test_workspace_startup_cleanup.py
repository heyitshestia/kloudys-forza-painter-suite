"""Actual offscreen app initialization failures must release every started owner."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WorkspaceStartupCleanupTests(unittest.TestCase):
    def test_workspace_admission_failure_drains_services_and_qml(self):
        self.run_failure("ipc")

    def test_failing_workspace_cleanup_does_not_skip_other_services(self):
        self.run_failure("cleanup")

    def test_missing_qml_drains_services_without_entering_event_loop(self):
        self.run_failure("qml")

    def test_session_configuration_failure_releases_started_workspace(self):
        self.run_failure("session")

    def run_failure(self, mode):
        script = r'''
import importlib.util, json, logging, sys, tempfile
from pathlib import Path
from dataclasses import replace
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
root, mode = Path(sys.argv[1]), sys.argv[2]
sys.argv = ['app.py', '--demo', '--skip-startup-index', '--width', '1280', '--height', '800']
spec = importlib.util.spec_from_file_location('cleanup_app', root/'KFPS.UI/app.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
from PySide6.QtNetwork import QLocalServer
from shiboken6 import isValid
from kfps_ui.workspace_tools import WorkspaceTools
from kfps_ui.workspace_host import WorkspaceWindow
from kfps_ui.workspace_controller import WorkspaceController
events, engines = [], []
original_engine = module.QQmlApplicationEngine
class TrackedEngine(original_engine):
    def __init__(self):
        super().__init__(); engines.append(self)
        self.destroyed.connect(lambda: events.append('engine.destroyed'))
    def load(self, url):
        if mode != 'qml': super().load(url)
classes = ['StartupSequenceService', 'EditorService', 'TransferService', 'GenerationService',
           'FullLiveryService', 'CGroupLibraryService', 'CommunityService', 'JsonService',
           'RuntimeService', 'BackupService', 'ChangelogService', 'AnnouncementService',
           'ReleaseAnnouncementService', 'ActivityService', 'VersionService', 'LogService',
           'ReportService', 'UpscaleService', 'BackgroundRemoveService', 'SupporterService']
expected = []
def wrap(name, original):
    def close(owner):
        events.append(name)
        return original(owner)
    return close
with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
    temporary = Path(temporary)
    paths = replace(module.AppPaths.discover(), app_root=temporary, runtime_root=temporary/'runtime')
    paths.runtime_root.mkdir()
    (temporary/'VERSION').write_text('3.1.124')
    stack.enter_context(patch.object(module.AppPaths, 'discover', return_value=paths))
    stack.enter_context(patch.object(module, 'evaluate_source_download_guard', return_value=SimpleNamespace(blocked=False)))
    stack.enter_context(patch.object(module, 'QQmlApplicationEngine', TrackedEngine))
    stack.enter_context(patch.object(module, 'exec_qml_application', side_effect=AssertionError('Event loop reached')))
    if mode == 'session':
        stack.enter_context(patch.object(WorkspaceController, 'configure_session', side_effect=RuntimeError('injected session failure')))
        stack.enter_context(patch.object(WorkspaceController, 'close', wrap('controller.close', WorkspaceController.close)))
    else:
        stack.enter_context(patch.object(QLocalServer, 'listen', return_value=False))
    for name in classes:
        cls = getattr(module, name)
        original = getattr(cls, 'close', None)
        if callable(original):
            expected.append(name)
            stack.enter_context(patch.object(cls, 'close', wrap(name, original)))
    original_tools_close = WorkspaceTools.close
    def tools_close(owner):
        events.append('tools.close')
        original_tools_close(owner)
        if mode == 'cleanup': raise RuntimeError('injected tools cleanup failure')
    stack.enter_context(patch.object(WorkspaceTools, 'close', tools_close))
    original_shutdown = WorkspaceWindow.shutdown
    stack.enter_context(patch.object(WorkspaceWindow, 'shutdown', wrap('workspace.shutdown', original_shutdown)))
    runtime = SimpleNamespace(baseline={'status':'development'}, graphics=SimpleNamespace(backend='opengl'),
                              borrow_guard=lambda:SimpleNamespace(Close=lambda:None))
    try:
        result = module.main(workspace_runtime=runtime)
        assert mode == 'qml' and result == 2, result
    except RuntimeError as exc:
        expected_error = 'injected session failure' if mode == 'session' else 'Could not open the workspace connection.'
        assert mode != 'qml' and str(exc) == expected_error, str(exc)
    finally:
        logging.shutdown()
    assert engines and all(not isValid(engine) for engine in engines), events
    assert events.count('tools.close') == 1, events
    assert all(events.count(name) == 1 for name in expected), (expected, events)
    assert events.index('LogService') > max(events.index(name) for name in expected if name != 'LogService'), events
    assert events[-1] == 'engine.destroyed', events
    if mode != 'qml': assert events.count('workspace.shutdown') == 1, events
    if mode == 'session': assert events.count('controller.close') == 1, events
print(json.dumps({'mode':mode,'closed':events}))
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                   KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1", KFPS_STARTUP_MUTED="1",
                   PYTHONDONTWRITEBYTECODE="1", QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu")
        result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), mode],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=45,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
