"""Exercise the real shell footer and report action offscreen with synthetic app data."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
import app as application

OUT = ROOT / "runtime/support-testing/qml"
OUT.mkdir(parents=True, exist_ok=True)
results = {"cases": [], "browser_opened": False, "errors": []}


def install(app, window, controller, community, settings, jsons, args):
    def click(item):
        position = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))

    def steps():
        try:
            context = QQmlEngine.contextForObject(window)
            reports = context.contextProperty("reportService")
            palette = context.engine().singletonInstance("Kfps.Theme", "Theme")
            button = window.findChild(QObject, "OpenPrefilledSupportForm")
            credits = window.findChild(QObject, "SidebarCreditsButton")
            assert button is not None and credits is not None, "Support QML controls did not load"
            for theme in sorted(KNOWN_THEME_NAMES):
                settings.theme = theme
                yield 150
                assert palette.property("activeThemeName") == theme, (theme,"theme preview did not apply")
                for width, height in ((960,600),(1760,1040)):
                    window.resize(width, height)
                    yield 150
                    for page in ("create","outputs","community","editor","liveries","tools","help","update","settings"):
                        controller.navigate(page)
                        yield 350
                        top = button.mapToScene(QPointF(0,0)); bottom = button.mapToScene(QPointF(button.width(),button.height()))
                        assert button.isVisible() and button.isEnabled(), (theme,page,"button unavailable")
                        assert top.x() >= 0 and top.y() >= 0 and bottom.x() <= window.width()+1 and bottom.y() <= window.height()+1, (theme,page,"footer outside window")
                        assert top.y() >= credits.mapToScene(QPointF(0,credits.height())).y(), (theme,page,"report must be below Credits")
                        assert bottom.x() < window.width()/3, (theme,page,"report must be in the left sidebar")
                        results["cases"].append({"theme":theme,"size":[width,height],"page":page,"footer_visible":True})
                    slug = ''.join(c if c.isalnum() else '-' for c in theme)
                    assert window.grabWindow().save(str(OUT / f"{slug}-{width}x{height}.png"))
            controller.navigate("outputs")
            yield 150
            with patch("kfps_ui.report_service.open_support_handoff", return_value="prefilled") as browser:
                click(button)
                deadline = time.monotonic() + 15
                while reports.supportBusy and time.monotonic() < deadline: yield 25
                assert not reports.supportBusy, "Report collection did not finish"
                assert browser.call_count == 1, reports.supportStatus
                report = json.loads(Path(reports.latestPath).read_text())
                assert report["source"] == "kfps" and report["feature"] == "Import and export"
                results["browser_opened"] = True
                results["report_size"] = Path(reports.latestPath).stat().st_size
                results["gpu_detected"] = bool(report["technical"].get("hardware",{}).get("gpus"))
                shutil.copy2(reports.latestPath, OUT / "collected-report.json")
        except Exception:
            results["errors"].append(traceback.format_exc())
        finally:
            (OUT / "workflow-results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
            app.exit(1 if results["errors"] else 0)
    iterator = steps()
    def advance():
        try:
            delay = next(iterator)
        except StopIteration:
            return
        QTimer.singleShot(delay, advance)
    QTimer.singleShot(800, advance)


def main():
    with tempfile.TemporaryDirectory(prefix="app-", dir=OUT) as temporary:
        root = Path(temporary)
        shutil.copy2(ROOT / "VERSION", root / "VERSION")
        paths = AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",Path(sys.executable))
        sys.argv = [str(UI/"app.py"),"--demo","--theme-preview","Night Blossom","--screenshot",str(OUT/"capture-mode.png"),"--skip-startup-index","--skip-startup-thumbnails","--allow-source-download","--width","960","--height","600"]
        with patch.object(AppPaths,"discover",return_value=paths), patch.object(application,"install_development_harness",side_effect=install):
            code = application.main()
    print(json.dumps({"cases":len(results["cases"]),"errors":results["errors"],"browser_opened":results["browser_opened"],"qt_exit":code,"result":str(OUT/"workflow-results.json")}))
    return code or int(bool(results["errors"]) or not results["browser_opened"])


if __name__ == "__main__": raise SystemExit(main())
