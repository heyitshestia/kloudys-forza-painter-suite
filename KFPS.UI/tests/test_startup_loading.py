"""The real main window must not wait for unrelated library preparation."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class StartupLoadingTests(unittest.TestCase):
    def test_main_opens_before_library_preparation(self):
        script = textwrap.dedent(r'''
            import importlib.util, json, logging, tempfile, time
            from dataclasses import replace
            from pathlib import Path
            from unittest.mock import patch
            root = Path.cwd()
            spec = importlib.util.spec_from_file_location("startup_test_app", root / "KFPS.UI/app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from PySide6.QtCore import QTimer
            from kfps_ui import startup_sequence_service

            def reject_preindex(*args, **kwargs):
                raise AssertionError("Main window is still gated by synchronous output preparation")
            module.run_startup_output_index = reject_preindex
            module.refresh_runtime_registry = lambda *_: {"result": "test-offline"}
            startup_sequence_service.refresh_runtime_registry = module.refresh_runtime_registry
            for name in ("VersionService", "AnnouncementService", "RuntimeService", "CommunityService"):
                original = getattr(module, name)
                def offline(*args, _original=original, **kwargs):
                    kwargs["demo"] = True
                    return _original(*args, **kwargs)
                setattr(module, name, offline)
            original_changelog = module.ChangelogService
            module.ChangelogService = lambda *args, **kwargs: original_changelog(args[0], auto_refresh=False)
            original_exec = module.exec_qml_application
            checked = []
            def execute(app, engine, shutdown):
                def check():
                    window = engine.rootObjects()[0]
                    checked.append(bool(window.isVisible()))
                    app.quit()
                QTimer.singleShot(350, check)
                QTimer.singleShot(10000, app.quit)
                return original_exec(app, engine, shutdown)
            module.exec_qml_application = execute
            with tempfile.TemporaryDirectory() as temp:
                paths = replace(module.AppPaths.discover(), runtime_root=Path(temp))
                paths.settings_file.write_text(json.dumps({"reducedMotion": True, "ambientMotion": False}))
                try:
                    with patch.object(module.AppPaths, "discover", return_value=paths):
                        assert module.main() == 0
                finally:
                    logging.shutdown()
            assert checked == [True], checked
        ''')
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                   KFPS_QML_GRAPHICS="software", KFPS_APP_ROOT=str(ROOT),
                   QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --no-sandbox",
                   KFPS_ACTIVITY_DISABLED="1", KFPS_STARTUP_MUTED="1",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        env.pop("KFPS_SKIP_STARTUP_INDEX", None)
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=45,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
