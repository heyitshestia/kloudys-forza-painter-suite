"""Exercise the real Settings page without personal state, network or focus."""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
from PySide6.QtCore import QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import THEME_PRESETS
import app as application


def main():
    out = Path(sys.argv[1]).resolve()
    assert out.is_relative_to(ROOT / "runtime/test-runs") and not out.exists()
    out.mkdir(parents=True)
    isolated = out / "profile"
    isolated.mkdir()
    paths = AppPaths(isolated, UI, UI / "qml", UI / "assets", isolated / "runtime", Path(sys.executable))
    result = {"cases": [], "errors": [], "qmlErrors": []}
    detected_chrome = {"path": None}

    def messages(kind, context, text):
        if any(word in text for word in ("ReferenceError", "TypeError", "Cannot assign", "Binding loop")):
            result["qmlErrors"].append(text)

    def install(app, window, controller, community, settings, jsons, args):
        window.setFlag(Qt.WindowDoesNotAcceptFocus, True)
        window.show()
        window.lower()

        def items():
            pending = [window.contentItem()]
            while pending:
                item = pending.pop()
                yield item
                pending.extend(item.childItems())

        def evaluate(item, expression):
            query = QQmlExpression(QQmlEngine.contextForObject(item), item, expression)
            value, _ = query.evaluate()
            assert not query.hasError(), query.error().toString()
            return value.toVariant() if hasattr(value, "toVariant") else value

        def steps():
            try:
                controller.navigate("settings")
                yield 700
                selector = next(i for i in items() if i.objectName() == "editorGraphicsSelector")
                chrome = next(i for i in items() if i.objectName() == "editorChromeToggle")
                download = next(i for i in items() if i.objectName() == "editorChromeDownload")
                chrome_status = next(i for i in items() if i.objectName() == "editorChromeStatus")
                for theme in THEME_PRESETS:
                    settings.theme = theme.name
                    for width, height in ((1760, 1040), (1280, 800)):
                        window.resize(width, height)
                        evaluate(selector, "pageScroll.contentItem.contentY = 0")
                        yield 220
                        assert selector.isVisible()
                        position = selector.mapToScene(QPointF())
                        if position.y() + selector.height() > window.height():
                            evaluate(selector, f"pageScroll.contentItem.contentY = {position.y() - window.height() / 2}")
                            yield 150
                            position = selector.mapToScene(QPointF())
                        assert position.x() >= 0 and position.y() >= 0
                        assert position.x() + selector.width() <= window.width() + 1
                        assert position.y() + selector.height() <= window.height() + 1
                        for enabled in (True, False):
                            center = chrome.mapToScene(QPointF(chrome.width()/2, chrome.height()/2)).toPoint()
                            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                            yield 80
                            assert settings.editorUseChrome is enabled, (theme.name, enabled)
                            assert SettingsService(paths.settings_file).editorUseChrome is enabled
                            assert evaluate(chrome, "checked") is enabled
                            assert selector.isEnabled() is not enabled
                            assert download.isVisible() is enabled
                            assert chrome.width() > 100 and chrome.height() >= chrome.implicitHeight()
                            if enabled:
                                assert evaluate(chrome_status, "text") == "Google Chrome: not found"
                                count = opened.call_count
                                center = download.mapToScene(QPointF(download.width()/2, download.height()/2)).toPoint()
                                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                                yield 80
                                assert opened.call_count == count + 1
                                assert opened.call_args.args[0].toString() == "https://www.google.com/chrome/"
                                detected_chrome["path"] = Path("C:/test-only/chrome.exe")
                                if not result["cases"]:
                                    # Exercise automatic detection after installing outside KFPS.
                                    yield 2200
                                else:
                                    evaluate(download, "desktop.refreshChromeStatus()")
                                    yield 80
                                assert not download.isVisible()
                                assert evaluate(chrome_status, "text") == "Google Chrome: installed"
                                assert settings.editorUseChrome is True
                                detected_chrome["path"] = None
                                evaluate(download, "desktop.refreshChromeStatus()")
                                yield 80
                                assert download.isVisible()
                        for index, mode in ((0, "auto"), (1, "opengl"), (2, "d3d11")):
                            # Native Qt input to this window, without moving the OS pointer.
                            center = selector.mapToScene(QPointF(selector.width()/2, selector.height()/2)).toPoint()
                            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                            yield 80
                            QTest.keyClick(window, Qt.Key_Home)
                            for _ in range(index):
                                QTest.keyClick(window, Qt.Key_Down)
                            QTest.keyClick(window, Qt.Key_Return)
                            yield 60
                            assert settings.editorGraphics == mode, (theme.name, mode, settings.editorGraphics)
                            assert SettingsService(paths.settings_file).editorGraphics == mode
                            assert evaluate(selector, "currentText") == ["Auto", "OpenGL", "Direct3D 11"][index]
                        result["cases"].append({"theme": theme.name, "size": [width, height], "passed": True})
                        if width == 1760 and theme.name in ("Windows 94", "Apex Vector", "Night Blossom"):
                            settings.editorUseChrome = True
                            yield 80
                            assert window.grabWindow().save(str(out / (theme.name.replace(" ", "-") + ".png")))
                            settings.editorUseChrome = False
                result["passed"] = True
            except Exception:
                result["errors"].append(traceback.format_exc())
                window.grabWindow().save(str(out / "failure.png"))
            finally:
                app.exit(int(bool(result["errors"] or result["qmlErrors"])))

        iterator = steps()
        def advance():
            try:
                QTimer.singleShot(next(iterator), advance)
            except StopIteration:
                pass
        QTimer.singleShot(500, advance)

    sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom",
                "--screenshot", str(out / "capture-mode.png"), "--skip-startup-index",
                "--skip-startup-thumbnails", "--width", "1760", "--height", "1040"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), \
             patch.object(FullLiveryService, "scanSaves"), patch.object(FullLiveryService, "refreshPackages"), \
             patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
             patch.object(CommunityApiClient, "json", side_effect=AssertionError("Unexpected network request")), \
             patch("kfps_ui.desktop_service.find_chrome", side_effect=lambda: detected_chrome["path"]), \
             patch("kfps_ui.desktop_service.QDesktopServices.openUrl", return_value=True) as opened, \
             patch.object(application, "install_development_harness", side_effect=install):
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
        (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return code or int(bool(result["errors"] or result["qmlErrors"]))


if __name__ == "__main__":
    raise SystemExit(main())
