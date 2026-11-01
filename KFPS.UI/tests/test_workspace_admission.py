"""Actual offscreen shell admission, duplicate exit, cleanup and lease reuse."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkspaceAdmissionTests(unittest.TestCase):
    def test_real_shell_owns_lease_duplicate_exits_and_restart_can_acquire(self):
        script = textwrap.dedent(r'''
            import importlib.util
            import json
            import logging
            import os
            from pathlib import Path
            import sys
            from types import SimpleNamespace
            from unittest.mock import patch

            root, profile = map(Path, sys.argv[1:])
            app_root = profile / 'app'
            app_root.mkdir()
            (app_root/'.git').mkdir()
            (app_root/'VERSION').write_text('3.1.124', encoding='utf-8')
            def audit(event, args):
                if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system'}:
                    raise AssertionError('No network or child processes in admission test')
                if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
                    mode, flags = args[1:3]
                    writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                        isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                    if writing and not Path(args[0]).resolve().is_relative_to(profile):
                        raise AssertionError('Write outside admission sandbox')
            sys.addaudithook(audit)
            spec = importlib.util.spec_from_file_location('workspace_entry', root/'KFPS.UI/workspace.py')
            entry = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(entry)
            from kfps_editor import baseline, graphics
            from kfps_ui import workspace_paths
            connection_directory = app_root / 'runtime/workspace'
            with patch.object(baseline, 'verify', return_value={'status':'development'}) as verify, \
                    patch.object(workspace_paths, 'workspace_connection_dir', return_value=connection_directory) as connection_path, \
                    patch.object(graphics, 'select_policy', return_value=SimpleNamespace(backend='software')), \
                    patch.object(graphics, 'configure_environment'), \
                    patch.object(baseline, 'isolated_environment', side_effect=lambda:dict(os.environ)):
                runtime = entry.WorkspaceRuntime()
                try:
                    verify.assert_called_once_with(root)
                    assert entry.ROOT == root
                    connection_path.assert_called_once_with(root)
                    assert runtime.workspace_lock.isLocked()
                    import app as application
                    from PySide6.QtCore import QTimer
                    from PySide6.QtQml import QQmlApplicationEngine
                    from shiboken6 import isValid
                    from kfps_ui.workspace_host import WorkspaceWindow
                    from kfps_ui.workspace_controller import WorkspaceController
                    from kfps_ui.app_paths import AppPaths
                    paths = AppPaths(app_root, root/'KFPS.UI', root/'KFPS.UI/qml', root/'KFPS.UI/assets',
                                     app_root/'runtime', Path(sys.executable))
                    events, errors, engines = [], [], []
                    class Engine(QQmlApplicationEngine):
                        def __init__(self, *args, **kwargs):
                            super().__init__(*args, **kwargs)
                            engines.append(self)
                            self.destroyed.connect(lambda:events.append('engine-destroyed'))
                    old_editor_close = application.EditorService.close
                    def editor_close(owner):
                        assert runtime.workspace_lock.isLocked()
                        events.append('editor-closed')
                        return old_editor_close(owner)
                    def install(app, window, controller, community, settings, jsons, args):
                        def inspect():
                            try:
                                shell = next(item for item in app.topLevelWidgets() if isinstance(item, WorkspaceWindow))
                                assert shell.testAttribute(application.Qt.WA_DontShowOnScreen)
                                owner = shell.findChild(WorkspaceController)
                                assert owner.lock is runtime.workspace_lock
                                assert owner.lock.runtime == connection_directory
                                assert any(call.args == (app_root,) for call in connection_path.call_args_list)
                                assert owner.lock.isLocked()
                                assert entry.main() == 0
                                assert owner.lock.isLocked() and not owner.closed
                                assert len([item for item in app.topLevelWidgets() if isinstance(item, WorkspaceWindow)]) == 1
                                events.append('duplicate-exited-first-still-live')
                            except BaseException as exc:
                                errors.append(repr(exc))
                            finally:
                                app.quit()
                        QTimer.singleShot(0, inspect)
                    supporter = application.SupporterService
                    sys.argv = ['app.py', '--demo', '--page', 'settings', '--skip-startup-index',
                                '--skip-startup-thumbnails', '--screenshot', str(profile/'capture-mode.png')]
                    with patch.object(application.AppPaths, 'discover', return_value=paths), \
                            patch.object(application, 'QQmlApplicationEngine', Engine), \
                            patch.object(application, 'install_development_harness', side_effect=install), \
                            patch.object(application.EditorService, 'close', new=editor_close), \
                            patch.object(application.FullLiveryService, '_resolve_initial_game_folder', return_value=''), \
                            patch.object(application.FullLiveryService, 'scanSaves'), \
                            patch.object(application.FullLiveryService, 'refreshPackages'), \
                            patch.object(application, 'SupporterService', side_effect=lambda path:supporter(path, endpoint='')):
                        assert application.main(workspace_runtime=runtime) == 0
                    assert not errors, errors
                    assert events == ['duplicate-exited-first-still-live','editor-closed','engine-destroyed'], events
                    assert all(not isValid(engine) for engine in engines)
                    assert runtime.workspace_lock.isLocked()
                finally:
                    runtime.close()
                    runtime.close()
                    assert runtime.workspace_lock is None
                    logging.shutdown()
                restarted = entry.WorkspaceRuntime()
                assert restarted.workspace_lock.isLocked()
                restarted.close()
                print(json.dumps({'events':events,'restart_lease':True,'errors':errors}))
        ''')
        with tempfile.TemporaryDirectory(prefix="workspace-admission-") as directory:
            profile = Path(directory)
            env = {key:value for key,value in os.environ.items() if not key.startswith("KFPS_")}
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1",
                       KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1", KFPS_STARTUP_MUTED="1",
                       QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-background-networking")
            for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
                path = profile / key.lower()
                path.mkdir()
                env[key] = str(path)
            # Exercise duplicate admission in this controlled process even when
            # the selected installation has a packaged baseline.
            process = subprocess.run([sys.executable,"-I","-B","-X",f"pycache_prefix={profile/'bytecode'}",
                                      "-c",script,str(ROOT),str(profile)],
                cwd=profile,env=env,capture_output=True,text=True,timeout=30,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            self.assertIn('"restart_lease": true',process.stdout)


if __name__ == "__main__":
    unittest.main()
