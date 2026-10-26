"""Real offscreen application buttons; dialogs are mocked, never desktop input."""
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


def native(root, evidence, width, height):
    import importlib.util
    import traceback
    from unittest.mock import patch

    sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(ROOT)]
    from PySide6.QtCore import QObject, QPointF, Qt, QTimer
    from PySide6.QtQml import QQmlEngine
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtTest import QTest
    from test_fh3_offline_files import fixture_header, shape
    from test_fh3_save_discovery import build_fh3_fixture
    from tools.cgroup.cgroup_codec import wrap_payload
    from tools.cgroup.vinyl_document import encode_vinyl_document

    source = root / "imgs/exported/test.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"shapes": [shape(0), shape(1, ("A", "B")), shape(2, ("A", "B"))]}), encoding="utf-8")
    (root / "VERSION").write_text((ROOT / "VERSION").read_text())
    (root / "generator_backend.py").write_text("# isolated test root\n")
    for game in ("fh3",):
        folder = root / game
        folder.mkdir()
        (folder / "header").write_bytes(fixture_header(game, 3))
        payload, _ = encode_vinyl_document(json.loads(source.read_text(encoding="utf-8")), game)
        (folder / "C_group").write_bytes(wrap_payload(payload))
    os.environ["LOCALAPPDATA"] = str(root / "local")
    wgs, _, _, _ = build_fh3_fixture(root / "local/Packages", json.loads(source.read_text()))
    evidence.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("kfps_application_under_test", UI / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {"passed": False, "checks": []}

    def install(app, window, controller, community, settings, jsons, args):
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
            font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        service = QQmlEngine.contextForObject(window).contextProperty("cgroupLibraryService")
        state = {"game_index": 0, "phase": "read"}
        games = ("fh3", "fh3-file", "fh3-folder")
        settings._data.update(reducedMotion=True, ambientMotion=False)
        settings.changed.emit()

        def wait_for(predicate, label):
            deadline = time.monotonic() + 3
            while not predicate() and time.monotonic() < deadline:
                QTest.qWait(20)
            assert predicate(), label

        def finish(code, error=""):
            result.update(passed=code == 0, error=error)
            (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            app.exit(code)

        def reveal(button):
            scroll = window.findChild(QObject, "OfflineImportSetupScroll")
            flick = scroll.property("contentItem")
            center = button.mapToItem(flick, QPointF(button.width() / 2, button.height() / 2))
            y = flick.property("contentY") + center.y() - flick.height() / 2
            flick.setProperty("contentY", max(0, min(y, flick.property("contentHeight") - flick.height())))
            QTest.qWait(60)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
            in_scroll = scroll.mapFromScene(point)
            assert 0 <= in_scroll.y() < scroll.height(), "Button could not be scrolled into view"
            return point.toPoint()

        def step():
            try:
                if service.running:
                    QTimer.singleShot(25, step)
                    return
                mode = games[state["game_index"]]
                game = mode.split("-")[0]
                combo = window.findChild(QObject, "OfflineLibraryGame")
                read = window.findChild(QObject, "ScanOfflineLibrary")
                install = window.findChild(QObject, "ImportOfflineLibrary")
                controls = window.findChild(QObject, "OfflineLibraryControls")
                assert combo and read and install and controls, "Missing real Outputs controls"
                assert "FH2" not in service.gameTargets, "Retired FH2 is offered"
                assert not window.findChild(QObject, "FH2ExtractionGuide"), "Retired FH2 guide is present"
                if state["phase"] == "read":
                    combo.setProperty("currentIndex", service.gameTargets.index("FH3"))
                    wait_for(lambda: read.property("text") == "Scan FH3 Saves", "FH3 label did not settle")
                    QTest.qWait(200)
                    fh3_height = controls.height()
                    combo.setProperty("currentIndex", service.gameTargets.index("FH6"))
                    wait_for(lambda: combo.property("currentText") == "FH6", "FH6 selection did not settle")
                    assert install.property("visible"), "FH6 import must remain available"
                    combo.setProperty("currentIndex", service.gameTargets.index(game.upper()))
                    wait_for(lambda: read.property("text") == "Scan FH3 Saves", "FH3 label did not return")
                    QTest.qWait(200)
                    jsons.setSource(2)
                    jsons.refresh()
                    jsons.selectPath(str(source))
                    assert read.property("text") == "Scan FH3 Saves", str(read.property("text"))
                    if mode == "fh3-file":
                        read = window.findChild(QObject, "ExtractFh3File")
                    elif mode == "fh3-folder":
                        read = window.findChild(QObject, "BrowseFh3Saves")
                    assert not install.property("visible"), "Legacy game import must be hidden"
                    assert not install.property("enabled"), "Legacy game import must be disabled"
                    assert abs(controls.height() - fh3_height) < 1, f"FH3 height changed: {fh3_height} -> {controls.height()}"
                    position = reveal(read)
                    image = window.grabWindow()
                    assert not image.isNull()
                    image.save(str(evidence / f"{mode}.png"))
                    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(root / game / "C_group"), "")) as file_picker, patch.object(
                        QFileDialog, "getExistingDirectory", return_value=str(wgs)
                    ) as folder_picker:
                        previous = service._future
                        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)
                        if mode == "fh3":
                            file_picker.assert_not_called()
                            folder_picker.assert_not_called()
                        elif mode == "fh3-folder":
                            folder_picker.assert_called_once()
                        else:
                            file_picker.assert_called_once()
                    assert service._future is not previous, "Extraction button did not receive the click"
                    state["phase"] = "verify"
                else:
                    assert service.status == "Complete", service.summary
                    saved = json.loads(Path(service.lastOutput).read_text(encoding="utf-8"))
                    assert len(saved["shapes"]) == 3
                    assert len(saved["shapes"][1]["editor_group_path"]) == 2
                    assert Path(jsons.selectedPath) == Path(service.lastOutput)
                    window.grabWindow().save(str(evidence / f"{mode}-complete.png"))
                    result["checks"].append({"game": game, "mode": mode, "layers": 3,
                                             "group_depth": 2, "extraction_only": True})
                    state["game_index"] += 1
                    state["phase"] = "read"
                    if state["game_index"] == len(games):
                        finish(0)
                        return
                QTimer.singleShot(150, step)
            except Exception:
                finish(1, traceback.format_exc())

        QTimer.singleShot(1200, step)
        QTimer.singleShot(25000, lambda: finish(1, "UI test timeout"))

    module.install_development_harness = install
    sys.argv = [str(UI / "app.py"), "--page", "outputs", "--demo", "--width", str(width), "--height", str(height),
                "--skip-startup-index", "--skip-startup-thumbnails", "--allow-source-download",
                "--screenshot", str(evidence / "unused.png")]
    return module.main()


class LegacyUiTests(unittest.TestCase):
    def test_real_outputs_extract_only_and_reopen_at_two_display_scales(self):
        for scale, width, height in (("1", 1760, 1040), ("1.5", 1760, 1040), ("1", 1280, 800), ("1.5", 1280, 800)):
            with self.subTest(scale=scale, width=width), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                evidence = Path(os.environ.get("KFPS_FH3_TEST_EVIDENCE", str(ROOT / "runtime/test-runs/fh3-offline"))) / f"ui-{width}-scale-{scale}"
                process = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--native", str(root), str(evidence), str(width), str(height)],
                    env={**os.environ, "KFPS_APP_ROOT": str(root), "QT_QPA_PLATFORM": "offscreen",
                         "QT_QUICK_BACKEND": "software", "QT_SCALE_FACTOR": scale,
                         "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox"},
                    cwd=ROOT, capture_output=True, text=True, timeout=40,
                )
                self.assertEqual(0, process.returncode, process.stdout + process.stderr +
                                 ((evidence / "result.json").read_text() if (evidence / "result.json").exists() else ""))
                report = json.loads((evidence / "result.json").read_text())
                self.assertTrue(report["passed"], report)
                self.assertEqual(3, len(report["checks"]))
                for error in ("ReferenceError", "TypeError", "Binding loop"):
                    self.assertNotIn(error, process.stderr)


if __name__ == "__main__":
    if "--native" in sys.argv:
        raise SystemExit(native(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])))
    unittest.main()
