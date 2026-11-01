"""Normal launcher routing without opening Qt, backends, or user profiles."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
from kfps_ui.entrypoint import LEGACY_ROUTES, uses_workspace


class WorkspaceEntrypointTests(unittest.TestCase):
    def test_ordinary_routes_select_workspace(self):
        for args in ([], ["--page", "editor"], ["--width", "1280", "--height", "800"],
                     ["--skip-startup-index"], ["--allow-source-download"]):
            with self.subTest(args=args):
                self.assertTrue(uses_workspace(args))

    def test_worker_inspector_and_explicit_testing_routes_stay_legacy(self):
        for route in LEGACY_ROUTES:
            with self.subTest(route=route):
                self.assertFalse(uses_workspace([route]))
                self.assertFalse(uses_workspace([route + "=value"]))
        self.assertTrue(uses_workspace(["--page", "full-livery-worker"]))

    def run_entry(self, mode, flags):
        script = textwrap.dedent(r'''
            import importlib.abc
            import importlib.util
            import json
            import os
            from pathlib import Path
            import runpy
            import sys
            import types
            from unittest.mock import patch

            root, profile, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
            events = []
            def audit(event, args):
                if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
                    raise AssertionError("External activity is forbidden")
                if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                    access, flags = args[1:3]
                    writing = (isinstance(access, str) and any(c in access for c in "wax+")) or (
                        isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                    if writing and not Path(args[0]).resolve().is_relative_to(profile):
                        raise AssertionError("Write outside isolated test")
            sys.addaudithook(audit)

            class NoQt(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] in {'numpy', 'PySide6', 'shiboken6'}:
                        raise AssertionError('UI imported before workspace routing: ' + fullname)
            sys.meta_path.insert(0, NoQt())
            spec = importlib.util.spec_from_file_location('baseline_contract',
                root / 'KFPS.Editor/src/kfps_editor/baseline.py')
            baseline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline)
            real_launch_command = baseline.launch_command
            baseline.development_root = lambda path: mode not in {'release', 'unexpected-relaunch'}
            real_exists = Path.exists
            def baseline_exists(path):
                # Model the requested installation, not this checkout's bundle marker.
                if path == root / baseline.CONTRACT:
                    return mode == 'release'
                return real_exists(path)
            def verify(path):
                events.append('verify')
                assert Path(path) == root
                if mode == 'verify-fails':
                    raise RuntimeError('injected verification failure')
                return {'status':'verified-sentinel'}
            baseline.verify = verify
            baseline.managed_python = lambda path: Path(path) / 'python/pythonw.exe'
            def launch_command(path, entry, arguments):
                events.append('isolated-relaunch')
                command, env = real_launch_command(path, entry, arguments)
                assert command[1:4] == ['-I', '-B', '-X'], command
                assert command[4].startswith('pycache_prefix='), command
                assert command[5:] == [str(root/'KFPS.UI/workspace.py'), '--page', 'settings'], command
                assert 'QT_QPA_PLATFORM' not in env
                assert env['PYTHONDONTWRITEBYTECODE'] == '1'
                return command, env
            baseline.launch_command = launch_command
            graphics = types.ModuleType('kfps_editor.graphics')
            graphics.select_policy = lambda path: types.SimpleNamespace(backend='sentinel')
            def configure(env, policy):
                events.append('graphics')
                assert events[-2] == 'verify'
            graphics.configure_environment = configure
            guard = types.ModuleType('kfps_editor.update_guard')
            guard.updater_state_root = lambda path: profile
            class Guard:
                def Close(self): events.append('guard-close')
            def acquire(path):
                events.append('guard-acquire')
                return Guard()
            guard.acquire_update_guard = acquire
            locks = types.ModuleType('kfps_editor.instance_lock')
            class Lock:
                def __init__(self, directory): self.runtime, self.held = directory, False
                def tryLock(self, timeout):
                    events.append('lock-acquire')
                    self.held = mode != 'duplicate'
                    return self.held
                def unlock(self):
                    if self.held: events.append('lock-release')
                    self.held = False
            locks.EditorInstanceLock = Lock
            app = types.ModuleType('app')
            def main(*, workspace_runtime):
                events.append('app-main')
                assert workspace_runtime.baseline == {'status':'verified-sentinel'}
                assert os.environ['KFPS_QML_GRAPHICS'] == 'sentinel'
                assert sys.argv[1:] == ['--page', 'settings']
                return 37
            app.main = main
            sys.argv = [str(root/'KFPS.UI/app.py'), '--page', 'settings']
            with patch.dict(sys.modules, {'kfps_editor.baseline':baseline,
                    'kfps_editor.graphics':graphics, 'kfps_editor.update_guard':guard,
                    'kfps_editor.instance_lock':locks, 'app':app}), patch.object(Path, 'mkdir'), \
                    patch.object(Path, 'exists', baseline_exists), \
                    patch('subprocess.call', return_value=38) as child:
                try:
                    runpy.run_path(str(root/'KFPS.UI/app.py'), run_name='__main__')
                except SystemExit as exc:
                    assert mode != 'verify-fails'
                    code = exc.code
                except RuntimeError as exc:
                    assert mode == 'verify-fails' and str(exc) == 'injected verification failure'
                    code = 39
                else:
                    raise AssertionError('Entry did not propagate exit status')
                if mode == 'release':
                    assert child.call_count == 1, 'Expected one isolated relaunch; count=' + str(child.call_count)
                    assert child.call_args.kwargs['cwd'] == root
                    assert events == ['isolated-relaunch'], events
                else:
                    # Mock call repr includes inherited environment values. Never print it.
                    assert child.call_count == 0, 'Unexpected isolated relaunch; count=' + str(child.call_count)
                    expected = ['guard-acquire', 'verify'] if os.name == 'nt' else ['verify']
                    if mode != 'verify-fails':
                        expected += ['graphics', 'lock-acquire']
                        if mode != 'duplicate': expected += ['app-main', 'lock-release']
                    if os.name == 'nt': expected += ['guard-close']
                    assert events == expected, events
            print(json.dumps({'code':code, 'events':events, 'isolated':bool(sys.flags.isolated),
                              'no_bytecode':sys.dont_write_bytecode}))
        ''')
        with tempfile.TemporaryDirectory(prefix="workspace-entry-") as directory:
            profile = Path(directory)
            env = os.environ.copy()
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       PYTHONDONTWRITEBYTECODE="1", KFPS_ACTIVITY_DISABLED="1")
            for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
                path = profile / key.lower()
                path.mkdir()
                env[key] = str(path)
            process = subprocess.run([sys.executable, *flags, "-c", script, str(ROOT), str(profile), mode],
                cwd=profile, env=env, capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            return json.loads(process.stdout)

    def test_actual_script_routes_before_qt_with_and_without_isolation(self):
        for flags in ([], ["-B"], ["-I", "-B"]):
            with self.subTest(flags=flags):
                result = self.run_entry("development", flags)
                self.assertEqual(result["code"], 37)
                # Windows' bundled ._pth runtime is isolated even without -I.
                if "-I" in flags:
                    self.assertTrue(result["isolated"])

    def test_packaged_entry_delegates_to_existing_isolated_runtime_contract(self):
        self.assertEqual(self.run_entry("release", ["-B"])["code"], 38)

    def test_unexpected_relaunch_failure_does_not_disclose_environment(self):
        with patch.dict(os.environ, {"TEST_PRIVATE_CREDENTIAL": "private-test-sentinel"}):
            with self.assertRaises(AssertionError) as caught:
                self.run_entry("unexpected-relaunch", ["-I", "-B"])
        message = str(caught.exception)
        self.assertIn("Unexpected isolated relaunch; count=1", message)
        self.assertNotIn("TEST_PRIVATE_CREDENTIAL", message)
        self.assertNotIn("private-test-sentinel", message)
        self.assertNotIn("env={", message)

    def test_verification_failure_releases_guard_without_importing_qt(self):
        self.assertEqual(self.run_entry("verify-fails", ["-I", "-B"])["code"], 39)

    def test_duplicate_exits_before_importing_app_or_creating_services(self):
        self.assertEqual(self.run_entry("duplicate", ["-I", "-B"])["code"], 0)

    def test_actual_script_preserves_worker_dispatch_and_legacy_argument(self):
        script = textwrap.dedent(r'''
            import json
            from pathlib import Path
            import runpy
            import sys
            import types
            from unittest.mock import patch
            root = Path(sys.argv[1])
            sys.path.insert(0, str(root/'KFPS.UI/src'))
            from kfps_ui import entrypoint
            def audit(event, args):
                if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system'}:
                    raise AssertionError('External activity is forbidden')
            sys.addaudithook(audit)
            # Load shared helpers before replacing only the worker entry modules.
            runpy.run_path(str(root/'KFPS.UI/app.py'))
            routes = [
                ('kfps_ui.json_thumbnail_worker', 'main', ['--thumbnail-worker'],
                 (['--app-root', '', '--ui-root', '', '--runtime-root', '', '--max-seconds', '0.0'],)),
                ('kfps_ui.experimental.full_livery.worker_main', 'run_request',
                 ['--full-livery-worker', '--full-livery-worker-request', 'request.json',
                  '--full-livery-worker-result', 'result.json', '--full-livery-worker-parent-pid', '123'],
                 ('request.json', 'result.json', 123)),
                ('kfps_ui.experimental.full_livery.inspector_main', 'run',
                 ['--full-livery-inspector', '--full-livery-inspector-config', 'config.json',
                  '--full-livery-inspector-ready', 'ready.json', '--full-livery-inspector-stop', 'stop.json',
                  '--full-livery-worker-parent-pid', '124'], ('config.json', 'ready.json', 'stop.json', 124)),
            ]
            with patch.object(entrypoint, 'launch_workspace', side_effect=AssertionError('Workspace must stay lazy')):
                for name, function, args, expected in routes:
                    calls = []
                    module = types.ModuleType(name)
                    def worker(*values):
                        calls.append(values)
                        return 41
                    setattr(module, function, worker)
                    with patch.dict(sys.modules, {name:module}), patch.object(sys, 'argv', ['app.py', *args]):
                        try: runpy.run_path(str(root/'KFPS.UI/app.py'), run_name='__main__')
                        except SystemExit as exc: assert exc.code == 41, exc.code
                        else: raise AssertionError('Worker result lost')
                    assert calls == [expected], calls
                with patch.object(sys, 'argv', ['app.py', '--legacy-ui', '--theme-preview', 'Night Blossom']):
                    try: runpy.run_path(str(root/'KFPS.UI/app.py'), run_name='__main__')
                    except SystemExit as exc: assert 'only with --demo' in str(exc), exc
                    else: raise AssertionError('Legacy validation bypassed')
            from PySide6.QtWidgets import QApplication
            assert QApplication.instance() is None
            print(json.dumps({'worker_routes':3, 'legacy_validated':True}))
        ''')
        process = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["worker_routes"], 3)

    def test_direct_python_script_worker_and_legacy_fail_before_any_application(self):
        cases = ((["--full-livery-worker"], "worker request is incomplete"),
                 (["--legacy-ui", "--theme-preview", "Night Blossom"], "only with --demo"))
        for args, message in cases:
            with self.subTest(args=args), tempfile.TemporaryDirectory(prefix="workspace-direct-") as directory:
                profile = Path(directory)
                env = os.environ.copy()
                env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                           KFPS_ACTIVITY_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")
                for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
                    path = profile / key.lower()
                    path.mkdir()
                    env[key] = str(path)
                process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "KFPS.UI/app.py"), *args],
                    cwd=profile, env=env, capture_output=True, text=True, timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(message, process.stderr)


if __name__ == "__main__":
    unittest.main()
