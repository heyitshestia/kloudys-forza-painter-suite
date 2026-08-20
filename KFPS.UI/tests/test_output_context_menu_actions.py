from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent


class OutputContextMenuActionTests(unittest.TestCase):
    def test_visible_context_menu_actions_change_the_expected_files(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td) / "KloudysFH6Painter"
            exported = app_root / "imgs" / "exported"
            destination = exported / "Destination"
            destination.mkdir(parents=True)
            (app_root / "VERSION").write_text((ROOT / "VERSION").read_text(encoding="utf-8"), encoding="utf-8")
            (app_root / "generator_backend.py").write_text("# test root\n", encoding="utf-8")
            (destination / ".kfps-output-folder").write_text(
                json.dumps({"format": "kfps-output-folder-v1", "displayName": "Destination"}) + "\n",
                encoding="utf-8",
            )
            payload = json.dumps({"metadata": {"layers": 1}, "shapes": [{"type": 1048677}]})
            for name in (
                "Copy Source.json",
                "Cut Source.json",
                "Move Source.json",
                "Rename Source.json",
                "Delete Source.json",
            ):
                (exported / name).write_text(payload, encoding="utf-8")

            report = app_root / "runtime" / "output-actions.json"
            environment = os.environ.copy()
            environment.update({
                "KFPS_APP_ROOT": str(app_root),
                "QT_QPA_PLATFORM": "offscreen",
                "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
            })
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(UI / "app.py"),
                    "--page", "outputs",
                    "--width", "1280",
                    "--height", "800",
                    "--skip-startup-index",
                    "--skip-startup-thumbnails",
                    "--allow-source-download",
                    "--output-actions-report", str(report),
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline and not report.is_file() and process.poll() is None:
                time.sleep(0.05)
            if process.poll() is None:
                process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            self.assertTrue(report.is_file(), stdout + stderr)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(result["passed"], json.dumps(result, indent=2) + "\n" + stdout + stderr)


if __name__ == "__main__":
    unittest.main()
