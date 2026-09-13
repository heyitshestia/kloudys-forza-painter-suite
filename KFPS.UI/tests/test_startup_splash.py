import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]


class StartupSplashTests(unittest.TestCase):
    def run_script(self, script):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["KFPS_TEST_UI_ROOT"] = str(UI)
        src = str(UI / "src")
        # The shipped isolated runtime intentionally ignores PYTHONPATH.
        source = f"import sys\nsys.path.insert(0, {src!r})\n" + textwrap.dedent(script)
        result = subprocess.run(
            [sys.executable, "-B", "-c", source], cwd=UI.parent,
            env=env, capture_output=True, text=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def test_all_ten_artworks_fit_without_covering_labels(self):
        self.run_script(
            """
            import os
            from pathlib import Path
            from unittest.mock import patch
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage, QPainter, QColor, QFontDatabase, QFont
            from PySide6.QtWidgets import QApplication
            from kfps_ui import startup_splash as module
            from PIL import Image

            ui=Path(os.environ["KFPS_TEST_UI_ROOT"])
            app=QApplication([])
            # The offscreen Qt plugin does not enumerate Windows system fonts.
            for font in ("segoeui.ttf","segoeuib.ttf","seguisb.ttf"):
                path=Path("C:/Windows/Fonts")/font
                if path.is_file(): QFontDatabase.addApplicationFont(str(path))
            app.setFont(QFont("Segoe UI",10))
            assert len(module.SPLASH_ARTWORK)==len(set(module.SPLASH_ARTWORK))==10
            output=os.environ.get("KFPS_SPLASH_PREVIEW_DIR")
            plate=QImage(2200,960,QImage.Format.Format_RGB32)
            plate.fill(QColor("#dedee3"))
            painter=QPainter(plate)
            for index,relative in enumerate(module.SPLASH_ARTWORK):
                with Image.open(ui/"assets"/relative) as original:
                    assert "A" in original.getbands(), relative
                    assert original.getchannel("A").getextrema()==(0,255), relative
                def prefer(choices):
                    choices.sort(key=lambda item:item!=relative)
                with patch.object(module.random,"shuffle",side_effect=prefer) as shuffled:
                    splash=module.StartupSplash(ui/"assets")
                shuffled.assert_called_once()
                assert splash.artwork_path==ui/"assets"/relative
                splash.layout().activate()
                picture=splash.art.pixmap()
                assert not picture.isNull() and picture.width()<=245 and picture.height()<=220
                labels=[splash.brand,splash.art,splash.title,splash.detail,splash.aside,splash.progress_label]
                for first,second in zip(labels,labels[1:]):
                    assert first.geometry().bottom()<second.geometry().top(), (relative,first.objectName())
                selected=splash.artwork_path
                pixels=picture.toImage()
                for tick in range(3): splash._advance_ring_animation()
                assert splash.artwork_path==selected and splash.art.pixmap().toImage()==pixels
                frame=splash.grab().toImage()
                painter.drawImage((index%5)*440,(index//5)*480,frame)
                painter.setPen(QColor("#242428"))
                painter.drawText((index%5)*440+15,(index//5)*480+462,Path(relative).stem)
                if output:
                    folder=Path(output); folder.mkdir(parents=True,exist_ok=True)
                    assert frame.save(str(folder/(Path(relative).stem+".png")))
                splash.close()
            painter.end()
            if output: assert plate.save(str(Path(output)/"all-ten.png"))
            """
        )

    def test_missing_and_corrupt_variants_fall_back_without_blocking_startup(self):
        self.run_script(
            """
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from PySide6.QtGui import QImage, QColor
            from PySide6.QtWidgets import QApplication
            from kfps_ui import startup_splash as module

            app=QApplication([])
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                fallback=QImage(40,80,QImage.Format.Format_RGBA8888)
                fallback.fill(QColor("#f79dc9"))
                assert fallback.save(str(root/"mini-kloudy.png"))
                corrupt=root/module.SPLASH_ARTWORK[1]
                corrupt.parent.mkdir()
                corrupt.write_bytes(b"not a png")
                with patch.object(module.random,"shuffle",side_effect=lambda choices:choices.reverse()):
                    splash=module.StartupSplash(root)
                assert splash.artwork_path==root/"mini-kloudy.png"
                assert not splash.art.pixmap().isNull()
                splash.close()
                (root/"mini-kloudy.png").unlink()
                splash=module.StartupSplash(root)
                assert splash.artwork_path is None and splash.art.text()=="K"
                splash.set_progress(1,2)
                assert splash.progress_value==50
                splash.close()
            """
        )

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
        result = self.run_script(script)
        self.assertIn("startup splash subprocess passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
