"""Startup import ordering and unchanged headless entry routes."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class StartupImportOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(prefix="kfps-startup-imports-") as directory:
            profile = Path(directory)
            env = os.environ.copy()
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       KFPS_ACTIVITY_DISABLED="1", QML_DISABLE_DISK_CACHE="1")
            for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                location = profile / key.lower()
                location.mkdir()
                env[key] = str(location)
            probe = textwrap.dedent(r'''
                import importlib.abc
                import json
                import runpy
                import sys
                import types
                from unittest.mock import patch

                def forbid_external(event, args):
                    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
                        raise AssertionError("External activity is forbidden in startup tests")

                sys.addaudithook(forbid_external)
                first_qt = []

                class ImportOrder(importlib.abc.MetaPathFinder):
                    def find_spec(self, fullname, path=None, target=None):
                        if fullname == "PySide6" and not first_qt:
                            first_qt.append("numpy" in sys.modules)
                        return None

                finder = ImportOrder()
                sys.meta_path.insert(0, finder)
                app = runpy.run_path(str(__import__("pathlib").Path.cwd() / "KFPS.UI/app.py"))
                sys.meta_path.remove(finder)
                from PySide6.QtWidgets import QApplication
                result = {
                    "numpy_before_qt": first_qt == [True],
                    "no_application": QApplication.instance() is None,
                    "hosts_lazy": not any(name in sys.modules for name in (
                        "kfps_editor.host", "kfps_livery_lab.studio_host",
                        "kfps_ui.workspace_host", "kfps_ui.workspace_controller")),
                }
                calls = []

                def dispatch(name, function, argv, expected, code):
                    module = types.ModuleType(name)
                    def worker(*args):
                        calls.append(args)
                        return code
                    setattr(module, function, worker)
                    with patch.dict(sys.modules, {name: module}), patch.object(sys, "argv", ["app.py", *argv]):
                        assert app["main"]() == code
                    assert calls[-1] == expected, calls[-1]

                dispatch("kfps_ui.json_thumbnail_worker", "main", [
                    "--thumbnail-worker", "--thumbnail-worker-app-root", "app-root",
                    "--thumbnail-worker-ui-root", "ui-root", "--thumbnail-worker-runtime-root", "runtime-root",
                    "--thumbnail-worker-cache-file", "cache.json", "--thumbnail-worker-max-seconds", "2.5",
                    "--thumbnail-worker-max-items", "7", "--thumbnail-worker-preferred-source", "source.json",
                    "--thumbnail-worker-regenerate"], ([
                    "--app-root", "app-root", "--ui-root", "ui-root", "--runtime-root", "runtime-root",
                    "--max-seconds", "2.5", "--cache-file", "cache.json", "--max-items", "7",
                    "--preferred-source", "source.json", "--regenerate"],), 31)
                dispatch("kfps_ui.experimental.full_livery.worker_main", "run_request", [
                    "--full-livery-worker", "--full-livery-worker-request", "request.json",
                    "--full-livery-worker-result", "result.json", "--full-livery-worker-parent-pid", "123"],
                    ("request.json", "result.json", 123), 32)
                dispatch("kfps_ui.experimental.full_livery.inspector_main", "run", [
                    "--full-livery-inspector", "--full-livery-inspector-config", "config.json",
                    "--full-livery-inspector-ready", "ready.json", "--full-livery-inspector-stop", "stop.json",
                    "--full-livery-worker-parent-pid", "124"],
                    ("config.json", "ready.json", "stop.json", 124), 33)
                result["worker_routes"] = len(calls) == 3 and QApplication.instance() is None
                for theme in ("Original PS2", "Original Xbox"):
                    with patch.object(sys, "argv", ["app.py", "--demo", "--theme-preview", theme, "--startup-preview"]):
                        args = app["parse_args"]()
                        assert args.demo and args.startup_preview and args.theme_preview == theme
                    with patch.object(sys, "argv", ["app.py", "--theme-preview", theme]):
                        try:
                            app["main"]()
                        except SystemExit as error:
                            assert "only with --demo" in str(error)
                        else:
                            raise AssertionError("Theme preview validation was skipped")
                result["theme_routes"] = True

                import numpy as np
                from PIL import Image
                from kfps_ui.background_remove_document import paint_mask
                from kfps_ui import background_remove_service as service
                original = Image.new("RGBA", (8, 8), (100, 150, 200, 255))
                edited = paint_mask(original, original, "erase", [(0.5, 0.5)], diameter=2)
                result["image_processing"] = (
                    int(np.asarray(edited)[4, 4, 3]) == 0
                    and original.getpixel((4, 4)) == (100, 150, 200, 255)
                    and service.MaskDocument.__module__ == "kfps_ui.background_remove_document")
                print(json.dumps(result))
            ''')
            process = subprocess.run([sys.executable, "-I", "-B", "-c", probe],
                                     cwd=ROOT, env=env, capture_output=True, text=True,
                                     timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if process.returncode:
                raise AssertionError(process.stderr + process.stdout)
            cls.result = json.loads(process.stdout)

    def test_required_numpy_loads_before_qt_import_inspection(self):
        self.assertTrue(self.result["numpy_before_qt"])

    def test_import_does_not_create_an_application(self):
        self.assertTrue(self.result["no_application"])

    def test_editor_studio_and_workspace_hosts_remain_lazy(self):
        self.assertTrue(self.result["hosts_lazy"])

    def test_worker_routes_preserve_arguments_and_results_without_application(self):
        self.assertTrue(self.result["worker_routes"])

    def test_theme_preview_and_intro_arguments_remain_available(self):
        self.assertTrue(self.result["theme_routes"])

    def test_required_image_processing_remains_usable(self):
        self.assertTrue(self.result["image_processing"])


if __name__ == "__main__":
    unittest.main()
