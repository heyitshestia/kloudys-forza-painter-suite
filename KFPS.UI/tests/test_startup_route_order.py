"""Exercise the real main body with doubles up to its first QML load."""
import ast
import builtins
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock


APP = Path(__file__).resolve().parents[1] / "app.py"


class AtQmlLoad(Exception):
    pass


class StartupRouteOrderTests(unittest.TestCase):
    def run_to_load(self, page):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        controller_node = next(node for node in ast.parse(
            (APP.parent / "src/kfps_ui/app_controller.py").read_text(encoding="utf-8")
        ).body if isinstance(node, ast.ClassDef) and node.name == "AppController")
        controller_namespace = {
            "QObject": object,
            "Signal": lambda: MagicMock(),
            "Property": lambda *args, **kwargs: property,
            "Slot": lambda *args, **kwargs: lambda function: function,
        }
        # QObject construction is the only Qt behavior needed by this controller.
        class Object:
            def __init__(self, *args):
                pass
        controller_namespace["QObject"] = Object
        exec(compile(ast.Module(body=[controller_node], type_ignores=[]), str(APP), "exec"), controller_namespace)
        args = SimpleNamespace(
            community_preview_test=None, community_preview=False, theme_preview=None,
            thumbnail_worker=False, full_livery_worker=False, full_livery_inspector=False,
            demo=True, allow_unsupported_python=False, allow_source_download=False,
            terminal_green_text=False, motion_preview=False, motion_capture_dir=None, skip_startup_index=True,
            startup_preview=False, screenshot=None, screenshot_dir=None,
            interaction_capture_dir=None, output_menu_capture=None, output_actions_report=None,
            navigation_timing_report=None, page=page,
        )
        namespace = {node.id: MagicMock(name=node.id) for node in ast.walk(main)
                     if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                     and not hasattr(builtins, node.id)}
        namespace.update(__builtins__=__builtins__, parse_args=lambda: args,
                         AppController=controller_namespace["AppController"],
                         bool=bool, str=str, hasattr=hasattr, getattr=getattr,
                         sys=SimpleNamespace(argv=["app.py"], version_info=(3, 12)),
                         os=SimpleNamespace(environ={}))
        engine = namespace["QQmlApplicationEngine"].return_value
        namespace["evaluate_source_download_guard"].return_value = SimpleNamespace(blocked=False)
        context = {}
        engine.rootContext.return_value.setContextProperty.side_effect = context.__setitem__
        observed = []

        def load(*args):
            observed.append(context["appController"].currentPage)
            raise AtQmlLoad

        engine.load.side_effect = load
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(APP), "exec"), namespace)
        with self.assertRaises(AtQmlLoad):
            namespace["main"]()
        return observed

    def test_requested_route_is_selected_before_qml_load(self):
        for page in ("editor", "settings", "update", "community"):
            with self.subTest(page=page):
                self.assertEqual(self.run_to_load(page), [page])

    def test_alias_is_canonical_before_qml_load(self):
        self.assertEqual(self.run_to_load("json"), ["outputs"])

    def test_default_and_invalid_routes_keep_create(self):
        for page in ("create", "not-a-page"):
            with self.subTest(page=page):
                self.assertEqual(self.run_to_load(page), ["create"])

    def test_real_qml_skips_unused_create_then_can_navigate_and_show_update(self):
        script = textwrap.dedent(r'''
            import importlib.util
            import json
            import logging
            import os
            from dataclasses import replace
            from pathlib import Path
            import sys
            from unittest.mock import patch

            profile = Path(sys.argv[1]).resolve()
            def audit(event, args):
                if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
                    raise AssertionError("External activity is forbidden")
                if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                    mode, flags = args[1:3]
                    writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                        isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                    if writing and not Path(args[0]).resolve().is_relative_to(profile):
                        raise AssertionError("Write outside isolated test")
            sys.addaudithook(audit)
            spec = importlib.util.spec_from_file_location("startup_route_app", Path.cwd() / "KFPS.UI/app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from PySide6.QtCore import QTimer
            from PySide6.QtQml import QQmlExpression
            from PySide6.QtQuick import QQuickItem

            paths = replace(module.AppPaths.discover(), app_root=profile / "app", runtime_root=profile / "runtime")
            paths.runtime_root.mkdir()
            paths.settings_file.write_text(json.dumps({"reducedMotion": True, "ambientMotion": False}))
            supporter = module.SupporterService
            module.SupporterService = lambda root: supporter(root, endpoint="")
            execute = module.exec_qml_application
            checked = []
            errors = []

            def run(app, engine, shutdown):
                assert app.platformName() == "offscreen"
                window = engine.rootObjects()[0]
                context = engine.rootContext()
                controller = context.contextProperty("appController")
                assert controller.currentPage == "editor"
                assert not any(item.metaObject().className().startswith("CreatePage_")
                               for item in window.findChildren(QQuickItem))
                state = ["editor"]
                timer = QTimer()
                def check():
                    try:
                        host = window.findChild(QQuickItem, "CachedPageHost")
                        ready = QQmlExpression(context, host, "item !== null && item.visible")
                        if not ready.evaluate()[0]:
                            return
                        checked.append(controller.currentPage)
                        if state[0] == "editor":
                            assert not any(item.metaObject().className().startswith("CreatePage_")
                                           for item in window.findChildren(QQuickItem))
                            state[0] = "create"
                            controller.navigate("create")
                        elif state[0] == "create":
                            assert any(item.metaObject().className().startswith("CreatePage_")
                                       for item in window.findChildren(QQuickItem))
                            version = context.contextProperty("versionService")
                            version._available = True
                            version.changed.emit()
                            assert controller.currentPage == "update"
                            state[0] = "update"
                        else:
                            timer.stop()
                            app.quit()
                    except BaseException as error:
                        errors.append(repr(error))
                        timer.stop()
                        app.quit()
                timer.timeout.connect(check)
                timer.start(30)
                QTimer.singleShot(8000, app.quit)
                return execute(app, engine, shutdown)
            module.exec_qml_application = run
            sys.argv = ["app.py", "--demo", "--skip-startup-index", "--page", "editor"]
            with patch.object(module.AppPaths, "discover", return_value=paths), \
                    patch.object(module.FullLiveryService, "_resolve_initial_game_folder", return_value=""):
                assert module.main() == 0
            logging.shutdown()
            assert not errors, errors
            assert checked == ["editor", "create", "update"], checked
        ''')
        with tempfile.TemporaryDirectory(prefix="kfps-startup-route-") as directory:
            profile = Path(directory)
            env = {key: value for key, value in os.environ.items() if not key.startswith("KFPS_")}
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1",
                       KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1", KFPS_STARTUP_MUTED="1",
                       QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-background-networking")
            for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                location = profile / key.lower()
                location.mkdir()
                env[key] = str(location)
            process = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(profile)],
                                     cwd=APP.parents[1], env=env, capture_output=True, text=True, timeout=20,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
