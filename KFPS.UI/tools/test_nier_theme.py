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
motion_mode = os.environ.get("KFPS_TEST_NIER_MOTION") == "1"
depth_mode = True
surface_mode = True
run_root = Path(os.environ.get("KFPS_NIER_TEST_OUTPUT", str(ROOT / "runtime/test-runs/nier-theme")))
run = run_root / f"interaction-{width}x{height}-{os.environ.get('QT_SCALE_FACTOR', '1')}"
profile = run / "profile"
profile.mkdir(parents=True, exist_ok=True)
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", KFPS_QML_GRAPHICS="software",
    QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
    KFPS_ACTIVITY_DISABLED="1", KFPS_SKIP_STARTUP_INDEX="1", KFPS_SKIP_STARTUP_THUMBNAILS="1", KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
os.environ.pop("QSG_RHI_BACKEND", None)
if os.environ.get("KFPS_TEST_RHI") == "1":
    os.environ.pop("QT_QUICK_BACKEND", None)
    os.environ.update(KFPS_QML_GRAPHICS="d3d11", QSG_RHI_PREFER_SOFTWARE_RENDERER="1")
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
settings_path.write_text(json.dumps({"theme": "NieR Automata", "reducedMotion": True, "ambientMotion": False,
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
            return next((i for i in items() if i.objectName() == name), None)
        def click(name):
            item = find(name)
            check(item is not None and item.isVisible(), "reachable " + name)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, item.mapToScene(item.boundingRect().center()).toPoint())
            QTest.qWait(100)
        def key(value):
            QTest.keyClick(window, value)
            QTest.qWait(60)
        try:
            dashboard = find("NierDashboard")
            check(dashboard is not None, "NieR dashboard loaded")
            check(dashboard.parentItem().objectName() == "ApplicationBody", "dashboard owns body, not overlay")
            check(not find("ApplicationWorkspace").isVisible(), "workspace hidden behind dashboard")
            window.grabWindow().save(str(run / "home.png"))
            key(Qt.Key_Escape)
            check(dashboard.isVisible(), "initial Escape cannot reveal unchosen workspace")
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Maximized, "maximize while menu open")
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Windowed, "restore while menu open")
            window.resize(int(width), int(height))
            click("TitleBarButton:min")
            check(window.visibility() == QWindow.Minimized, "minimize while menu open")
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
            check(True in samples, "menu preserves native system move")
            for category, routes in enumerate((("create","editor","tools"),("outputs","liveries","community"),("settings","help","support","update","credits"))):
                for route in routes:
                    if not dashboard.isVisible():
                        click("NierDashboardLaunch")
                    click("NierCategory:" + str(category))
                    click("NierDashboardRoute:" + route)
                    check(controller.currentPage == route, "real page " + route)
                    check(not dashboard.isVisible(), "menu closes for " + route)
            window.grabWindow().save(str(run / "workspace.png"))
            click("NierDashboardLaunch")
            dashboard.forceActiveFocus()
            key(Qt.Key_Left)
            check(dashboard.property("category") == 1, "keyboard category navigation")
            key(Qt.Key_End)
            check(dashboard.property("selectedIndex") == 2, "End selects last row")
            key(Qt.Key_Home)
            key(Qt.Key_Down)
            key(Qt.Key_Return)
            check(controller.currentPage == "liveries", "keyboard invokes selected page")
            click("NierDashboardLaunch")
            key(Qt.Key_Escape)
            check(not dashboard.isVisible(), "Escape returns to workspace")
            check(find("NierDashboardLaunch").hasActiveFocus(), "menu focus restored")
            for theme in ("Night Blossom", "Command Prompt", "Original Xbox", "Original PS2", "NieR Automata"):
                settings.theme = theme
                QTest.qWait(200)
                check(settings.theme == theme, "existing theme works: " + theme)
            dashboard = find("NierDashboard")
            for size in ((960,600),(1280,720),(1760,1040)):
                window.resize(*size)
                QTest.qWait(150)
                check(find("NierCategory:2").mapToScene(find("NierCategory:2").boundingRect().bottomRight()).x() <= window.width(), "category fits " + str(size))
                window.grabWindow().save(str(run / ("menu-%sx%s.png" % size)))
            window.resize(int(width), int(height))
            settings.reducedMotion = False
            settings.theme = "Night Blossom"
            QTest.qWait(100)
            settings.theme = "NieR Automata"
            QTest.qWait(40)
            reveal = find("NierWindowReveal")
            check(reveal is not None and not reveal.isEnabled(), "window reveal never captures input")
            check(reveal.property("progress") < 1, "window reveal is animated, not a static screenshot")
            window.grabWindow().save(str(run / "reveal-early.png"))
            QTest.qWait(250)
            window.grabWindow().save(str(run / "reveal-mid.png"))
            QTest.qWait(500)
            check(reveal.property("progress") == 1, "bounded reveal completes")
            window.grabWindow().save(str(run / "reveal-complete.png"))
            from PIL import Image, ImageChops
            with Image.open(run / "reveal-early.png") as early, Image.open(run / "reveal-complete.png") as complete:
                check(ImageChops.difference(early.convert("RGB"), complete.convert("RGB")).getbbox() is not None, "triangle reveal changes rendered pixels")
            for index in range(3):
                settings.theme = "Original PS2"
                QTest.qWait(40)
                settings.theme = "NieR Automata"
                QTest.qWait(40)
                settings.reducedMotion = True
                QTest.qWait(40)
                check(find("NierWindowReveal").property("progress") == 1, "reduced motion interrupts reveal " + str(index))
                settings.reducedMotion = False
            settings.reducedMotion = True
            QTest.qWait(100)
            settings.save()
            check(json.loads(settings_path.read_text())["theme"] == "NieR Automata", "native theme persisted")
            check(not [m for m in warnings if any(x in m for x in ("ReferenceError", "TypeError", "Error:", "Cannot assign", "Unable to assign", "Binding loop", "Cannot open"))], "no QML errors")
            click("TitleBarButton:close")
            check(not window.isVisible(), "close works from menu")
            app.exit(0)
        except Exception as error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
            app.exit(1)
        finally:
            (run / "results.json").write_text(json.dumps({"checks": results, "graphics_api": str(window.rendererInterface().graphicsApi()), "qml_messages": warnings}, indent=2), encoding="utf-8")
            print(json.dumps({"passed": sum(x.get("passed", False) for x in results), "failures": [x for x in results if x.get("passed") is False or "error" in x], "qml_message_count": len(warnings)}, indent=2))
    QTimer.singleShot(1200, checks)

module.install_development_harness = install
sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--allow-source-download", "--demo", "--theme-preview", "NieR Automata",
    "--width", width, "--height", height, "--page", "create"]
raise SystemExit(module.main())
