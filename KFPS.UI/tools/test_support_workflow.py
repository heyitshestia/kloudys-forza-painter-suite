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

OUT = Path(os.environ.get("KFPS_SUPPORT_TEST_OUTPUT", str(ROOT / "runtime/support-testing/qml"))).resolve()
if not OUT.is_relative_to(ROOT / "runtime"):
    raise ValueError("Support test output must stay inside this clone's runtime directory")
OUT.mkdir(parents=True, exist_ok=True)
results = {"cases": [], "browser_opened": False, "errors": []}
THEMES = sorted(filter(None, os.environ.get("KFPS_SUPPORT_TEST_THEMES", "").split("|"))) or sorted(KNOWN_THEME_NAMES)
if not set(THEMES).issubset(KNOWN_THEME_NAMES):
    raise ValueError("Unknown support test theme")


def install(app, window, controller, community, settings, jsons, args):
    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def find_item(name):
        return next((item for item in visual_items(window.contentItem()) if item.objectName() == name and item.isVisible()), None)

    def click(item):
        position = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))

    def steps():
        try:
            context = QQmlEngine.contextForObject(window)
            reports = context.contextProperty("reportService")
            palette = context.engine().singletonInstance("Kfps.Theme", "Theme")
            button = window.property("supportReportTarget")
            credits = window.findChild(QObject, "SidebarCreditsButton")
            assert button is not None and credits is not None, "Support QML controls did not load"
            for theme in THEMES:
                settings.theme = theme
                yield 150
                assert palette.property("activeThemeName") == theme, (theme,"theme preview did not apply")
                if window.property("dashboardNavigationVisible"):
                    browser = find_item("Ps2HomeBrowser")
                    if browser is not None and browser.isVisible():
                        click(browser)
                        yield 150
                    route = next((item for prefix in ("ApexRoute:", "NierDashboardRoute:", "XboxDashboardRoute:", "Ps2DashboardRoute:")
                                  if (item := find_item(prefix + "create")) is not None), None)
                    assert route is not None, (theme, "workspace entry unavailable")
                    click(route)
                    yield 150
                    assert not window.property("dashboardNavigationVisible"), (theme, "workspace did not open")
                for width, height in ((960,600),(1760,1040)):
                    window.resize(width, height)
                    yield 150
                    for page in ("create","outputs","community","editor","liveries","tools","help","update","settings"):
                        controller.navigate(page)
                        yield 350
                        button = window.property("supportReportTarget")
                        top = button.mapToScene(QPointF(0,0)); bottom = button.mapToScene(QPointF(button.width(),button.height()))
                        assert button.isVisible() and button.isEnabled(), (theme,page,"button unavailable")
                        if theme == "Redline":
                            assert button.property("text") == "REPORT", "Software rendering needs a visible report label"
                        assert top.x() >= 0 and top.y() >= 0 and bottom.x() <= window.width()+1 and bottom.y() <= window.height()+1, (theme,page,"footer outside window")
                        results["cases"].append({"theme":theme,"size":[width,height],"page":page,"footer_visible":True})
                    reports._support_status = "Report saved. Synthetic reviewer startup failure."
                    reports.changed.emit()
                    yield 100
                    recovery = window.findChild(QObject, "SupportReportRecovery")
                    assert recovery.property("visible"), (theme, "recovery popup unavailable")
                    assert 0 <= recovery.property("x") <= window.width() - recovery.property("width"), (theme, "popup outside width")
                    assert 0 <= recovery.property("y") <= window.height() - recovery.property("height"), (theme, "popup outside height")
                    slug = ''.join(c if c.isalnum() else '-' for c in theme)
                    assert window.grabWindow().save(str(OUT / f"{slug}-{width}x{height}-recovery.png"))
                    QTest.keyClick(window, Qt.Key_Escape)
                    yield 50
                    assert not recovery.property("visible"), (theme, "Escape did not dismiss recovery")
                    reports.changed.emit()
                    yield 50
                    with patch("kfps_ui.support_browser.open_browser_url", return_value="system-handler") as recovery_browser:
                        click(window.findChild(QObject, "SupportOpenWebsite"))
                        yield 100
                        assert recovery_browser.call_count == 1, (theme, "browser recovery not clickable")
                    assert not recovery.property("visible"), (theme, "recovery did not close")
                    results["cases"].append({"theme":theme,"size":[width,height],"recovery_click":True})
                    assert window.grabWindow().save(str(OUT / f"{slug}-{width}x{height}.png"))
            controller.navigate("outputs")
            yield 150
            button = window.property("supportReportTarget")
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
            window.grabWindow().save(str(OUT / "failure.png"))
            results["visible_items"] = [{"name": item.objectName(), "width": item.width(), "height": item.height()}
                for item in visual_items(window.contentItem()) if item.objectName() and item.isVisible()]
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
