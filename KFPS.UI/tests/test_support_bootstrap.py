import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
from kfps_ui import support_bootstrap as bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_pre_qt_import_failure_retains_type_not_credentials_or_paths(self):
        with patch.object(bootstrap.importlib, "import_module", side_effect=ImportError("token=PRIVATE C:/secret")), \
             patch.object(bootstrap, "show_failure") as show:
            self.assertEqual(bootstrap.run(self.root), 1)
        show.assert_called_once()
        text = (self.root / "runtime/support-reports/report-window.log").read_text()
        self.assertIn("bootstrap-failed type=ImportError", text)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("C:/secret", text)
        self.assertFalse(logging.getLogger("kfps-report-window").handlers)

    def test_bootstrap_keeps_logger_until_normal_shutdown(self):
        def main(root):
            self.assertIsNone(bootstrap.setup_logging(root))
            logging.getLogger("kfps-report-window").info("fixture-main")
            return 0
        with patch.object(bootstrap.importlib, "import_module", return_value=SimpleNamespace(main=main)):
            self.assertEqual(bootstrap.run(self.root), 0)
        text = (self.root / "runtime/support-reports/report-window.log").read_text()
        self.assertEqual(text.count("fixture-main"), 1)
        self.assertIn("reviewer-exit code=0", text)

    def test_bad_arguments_are_logged_as_exit_code_only(self):
        with patch.object(bootstrap.importlib, "import_module", return_value=SimpleNamespace(main=Mock(side_effect=SystemExit(2)))), \
             patch.object(bootstrap, "show_failure") as show:
            self.assertEqual(bootstrap.run(self.root), 2)
        self.assertIn("reviewer-exit code=2", (self.root / "runtime/support-reports/report-window.log").read_text())
        show.assert_not_called()

    def test_hardlinked_log_is_not_overwritten(self):
        import os
        folder = self.root / "runtime/support-reports"
        folder.mkdir(parents=True)
        target = self.root / "private.txt"
        target.write_text("private")
        os.link(target, folder / "report-window.log")
        with patch.object(bootstrap, "show_failure"):
            self.assertEqual(bootstrap.run(self.root), 1)
        self.assertEqual(target.read_text(), "private")


if __name__ == "__main__":
    unittest.main()
