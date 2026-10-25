"""Real QML interaction checks; offscreen events never touch the desktop pointer."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[2]
width, height = (sys.argv[1:3] or ["1760", "1040"])
motion_mode = os.environ.get("KFPS_TEST_PS2_MOTION") == "1"
depth_mode = True
surface_mode = True
run_root = Path(os.environ.get("KFPS_PS2_TEST_OUTPUT", str(ROOT / "runtime/test-runs/ps2-theme")))
run = run_root / f"interaction-{width}x{height}-{os.environ.get('QT_SCALE_FACTOR', '1')}"
profile = run / "profile"
profile.mkdir(parents=True, exist_ok=True)
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", KFPS_QML_GRAPHICS="software",
    QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
    KFPS_ACTIVITY_DISABLED="1", KFPS_SKIP_STARTUP_INDEX="1", KFPS_SKIP_STARTUP_THUMBNAILS="1", KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
os.environ.pop("QSG_RHI_BACKEND", None)
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI"), str(ROOT / "KFPS.UI/src")]
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl, QMetaObject, qInstallMessageHandler
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

warnings = []
qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
spec = importlib.util.spec_from_file_location("capture_app", ROOT / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module.AppPaths.discover()
sample = profile / "app"
sample.mkdir(exist_ok=True)
shutil.copy2(ROOT / "VERSION", sample / "VERSION")
module.AppPaths.discover = classmethod(lambda cls: replace(original, app_root=sample, runtime_root=profile / "runtime"))
settings_path = profile / "runtime/qml-shell-settings.json"
settings_path.parent.mkdir(exist_ok=True)
settings_path.write_text(json.dumps({"theme": "Original PS2", "reducedMotion": True, "ambientMotion": False,
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True,
    "dcinsideKoreanNotice202609Acknowledged": True}), encoding="utf-8")


def install(app, window, controller, community, settings, jsons, args):
    def checks():
        results = []
        def check(condition, name):
            results.append({"test": name, "passed": bool(condition)})
            if not condition:
                raise AssertionError(name)

        def items():
            stack = [window.contentItem()]
            while stack:
                item = stack.pop()
                yield item
                stack.extend(item.childItems())

        def find(name):
            return next((item for item in items() if item.objectName() == name), None)

        def click(name):
            item = find(name)
            check(item is not None and item.isVisible(), "reachable " + name)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, item.mapToScene(item.boundingRect().center()).toPoint())
            QTest.qWait(220)

        def key(value):
            QTest.keyClick(window, value)
            QTest.qWait(80)

        def clocks():
            return [item for item in items() if item.objectName() == "Ps2MotionClock"]

        def active(value):
            for clock in clocks():
                clock.setProperty("applicationActive", value)

        def frozen(name):
            before = [c.property("seconds") for c in clocks()]
            QTest.qWait(180)
            check(before == [c.property("seconds") for c in clocks()], name)

        try:
            dashboard = find("Ps2Dashboard")
            check(dashboard is not None, "PS2 dashboard loaded")
            check(dashboard.parentItem().objectName() == "ApplicationBody", "menu owns body, not modal overlay")
            check(not find("ApplicationWorkspace").isVisible(), "covered workspace hidden")
            check(not find("SidebarNavigationList").isVisible(), "primary navigation is PS2 home")
            check(find("Ps2HomeMenu").isVisible(), "retail-style two-choice home is initial screen")
            window.grabWindow().save(str(run / "home.png"))
            key(Qt.Key_Escape)
            check(find("Ps2HomeMenu").isVisible(), "initial Escape cannot expose unchosen workspace")
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Maximized, "maximize from initial home")
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Windowed, "restore from initial home")
            window.resize(int(width), int(height))
            click("TitleBarButton:min")
            check(window.visibility() == QWindow.Minimized, "minimize from initial home")
            window.showNormal()
            QTest.qWait(100)
            drag = window.findChild(QObject, "TitleBarDragHandler")
            samples = []
            drag.activeChanged.connect(lambda: samples.append(drag.property("active")))
            start = QPoint(window.width() // 2, int(find("TitleBarButton:max").height() / 2))
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPoint(40, 0), 30)
            QTest.mouseMove(window, start + QPoint(70, 0), 30)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPoint(70, 0))
            drag.activeChanged.disconnect()
            check(True in samples, "menu permits existing title-bar system move")
            find("Ps2HomeMenu").forceActiveFocus()
            key(Qt.Key_Home)
            key(Qt.Key_Return)
            check(find("Ps2BrowserMenu").isVisible(), "Enter Browser")
            window.grabWindow().save(str(run / "browser.png"))
            key(Qt.Key_Escape)
            check(find("Ps2HomeMenu").isVisible(), "Browser Back returns to home")
            key(Qt.Key_End)
            key(Qt.Key_Return)
            check(controller.currentPage == "settings", "System Configuration uses actual settings")
            check(not dashboard.isVisible(), "selection enters actual workspace")
            window.grabWindow().save(str(run / "settings.png"))
            initial = dict(settings._data)
            for index, route in enumerate(("create", "outputs", "liveries", "community", "editor", "tools", "support", "help", "update", "settings")):
                click("Ps2DashboardLaunch")
                click("Ps2HomeBrowser")
                browser = find("Ps2BrowserMenu")
                browser.setProperty("currentIndex", index)
                QMetaObject.invokeMethod(browser, "forceActiveFocus")
                key(Qt.Key_Return)
                check(controller.currentPage == route, "browser routes to " + route)
                check(not dashboard.isVisible(), "route closes menu " + route)
            click("Ps2DashboardLaunch")
            click("Ps2HomeBrowser")
            key(Qt.Key_Home)
            key(Qt.Key_Right)
            check(find("Ps2BrowserMenu").property("currentIndex") == 1, "right moves between browser entries")
            key(Qt.Key_End)
            check(find("Ps2BrowserMenu").property("currentIndex") == 9, "End reaches final browser entry")
            key(Qt.Key_Escape)
            key(Qt.Key_Escape)
            check(not dashboard.isVisible(), "Back returns to prior workspace")
            check(find("Ps2DashboardLaunch").hasActiveFocus(), "focus restored to menu control")
            for name in ("Ps2DashboardEnter", "Ps2DashboardBack", "Ps2DashboardCredits"):
                check(find(name) is None, "menu footer removed: " + name)
            for theme in ("Night Blossom", "Command Prompt", "Original Xbox", "Original PS2"):
                settings.theme = theme
                QTest.qWait(200)
                check(settings.theme == theme, "theme changes to " + theme)
                check((find("Ps2Dashboard") is not None) == (theme == "Original PS2"), "PS2 menu scoped to its theme")
            check(all(settings._data.get(k) == v for k, v in initial.items() if k != "theme"), "unrelated settings preserved")
            from kfps_ui.settings_service import SettingsService
            check(SettingsService(module.AppPaths.discover().settings_file).theme == "Original PS2", "actual theme preferences reopen")
            settings.theme = "Night Blossom"
            QTest.qWait(200)
            check(find("ApplicationWorkspace").isVisible(), "theme switch removes open menu ownership")
            settings.theme = "Original PS2"
            QTest.qWait(200)
            window.resize(960, 600)
            QTest.qWait(200)
            window.grabWindow().save(str(run / "home-small.png"))
            click("Ps2HomeBrowser")
            key(Qt.Key_End)
            key(Qt.Key_Return)
            check(controller.currentPage == "settings", "compact browser scrolls to last entry")
            window.resize(int(width), int(height))
            click("Ps2DashboardLaunch")
            settings.reducedMotion = False
            settings.ambientMotion = True
            active(True)
            QTest.qWait(250)
            check(any(c.property("running") for c in clocks()), "clock runs under simulated foreground")
            window.grabWindow().save(str(run / "motion-0.png"))
            QTest.qWait(700)
            window.grabWindow().save(str(run / "motion-1.png"))
            from PIL import Image, ImageChops
            with Image.open(run / "motion-0.png") as a, Image.open(run / "motion-1.png") as b:
                check(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None, "clock changes rendered pixels")
            cpu_samples = []
            for ambient in (False, True):
                settings.ambientMotion = ambient
                QTest.qWait(200)
                cpu, wall = time.process_time(), time.monotonic()
                QTest.qWait(1000)
                cpu_samples.append({"ambient": ambient, "cpu_seconds": time.process_time() - cpu, "wall_seconds": time.monotonic() - wall})
            (run / "cpu-samples.json").write_text(json.dumps(cpu_samples, indent=2))
            settings.ambientMotion = False
            frozen("ambient off stops clock")
            settings.ambientMotion = True
            active(False)
            frozen("background stops clock")
            active(True)
            settings.reducedMotion = True
            frozen("reduced motion stops clock")
            settings.reducedMotion = False
            window.showMinimized()
            frozen("minimized stops clock")
            window.showNormal()
            QTest.qWait(150)
            active(True)
            click("Ps2HomeBrowser")
            frozen("covered home clock stops in Browser")
            key(Qt.Key_Escape)
            for attempt in range(3):
                key(Qt.Key_Escape)
                QTest.qWait(240)
                click("Ps2DashboardLaunch")
                QTest.qWait(20)
                key(Qt.Key_Escape)
                QTest.qWait(220)
                check(not find("Ps2Dashboard").isVisible(), "rapid entry/cancel settles " + str(attempt))
            settings.reducedMotion = True
            click("Ps2DashboardLaunch")
            check(not [m for m in warnings if any(x in m for x in ("ReferenceError", "TypeError", "Error:", "Cannot assign", "Unable to assign", "Binding loop", "Cannot open"))], "no QML errors")
            click("TitleBarButton:close")
            check(not window.isVisible(), "title close works with home menu open")
            app.exit(0)
        except Exception as error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
            app.exit(1)
        finally:
            (run / "results.json").write_text(json.dumps({"checks": results, "qml_messages": warnings}, indent=2), encoding="utf-8")
            print(json.dumps({"passed": sum(x.get("passed", False) for x in results), "results": str(run / "results.json"), "failures": [x for x in results if x.get("passed") is False or "error" in x], "qml_messages": warnings}, indent=2))
    QTimer.singleShot(1200, checks)


module.install_development_harness = install
sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--allow-source-download", "--demo", "--theme-preview", "Original PS2",
    "--width", width, "--height", height, "--page", "create"]
raise SystemExit(module.main())
