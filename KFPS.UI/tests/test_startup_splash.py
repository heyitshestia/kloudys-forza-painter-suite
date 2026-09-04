import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]


class StartupSplashTests(unittest.TestCase):
    def test_splash_is_circular_translucent_and_loads_mini_kloudy(self):
        script = textwrap.dedent(
            """
            import os
            from pathlib import Path

            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor, QImage
            from PySide6.QtWidgets import QApplication

            from kfps_ui.startup_splash import StartupSplash

            ui = Path(os.environ["KFPS_TEST_UI_ROOT"])
            app = QApplication([])
            splash = StartupSplash(ui / "assets")
            assert (splash.width(), splash.height()) == (440, 440)
            assert splash.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            assert splash.art.pixmap() is not None
            assert not splash.art.pixmap().isNull()
            assert splash.brand.text() == "MINI KLOUDY"
            assert splash.title.text() == "Kloudy's Forza Painter Suite"

            splash.set_progress(1, 4)
            splash.set_status("Checking paint pots...", "Mini Kloudy has the clipboard.")
            assert splash.progress_value == 25
            assert splash.progress_label.text() == "25%"
            assert splash.detail.text() == "Checking paint pots..."

            image_format = QImage.Format.Format_RGBA8888
            first_frame = splash.grab().toImage().convertToFormat(image_format)
            start_rotation = splash._ring_rotation
            splash._advance_ring_animation()
            assert splash._ring_rotation > start_rotation
            second_frame = splash.grab().toImage().convertToFormat(image_format)
            assert first_frame != second_frame

            splash.show()
            app.processEvents()
            assert splash._animation_timer.isActive()
            splash.hide()
            app.processEvents()
            assert not splash._animation_timer.isActive()

            assert second_frame.pixelColor(0, 0) == QColor(0, 0, 0, 0)
            assert second_frame.pixelColor(220, 220).alpha() > 0
            print("startup splash subprocess passed")
            """
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["KFPS_TEST_UI_ROOT"] = str(UI)
        src = str(UI / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=UI.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("startup splash subprocess passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
