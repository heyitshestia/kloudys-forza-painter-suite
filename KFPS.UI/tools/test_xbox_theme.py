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
motion_mode = os.environ.get("KFPS_TEST_XBOX_MOTION") == "1"
depth_mode = True
surface_mode = True
run_root = Path(os.environ.get("KFPS_XBOX_TEST_OUTPUT", str(ROOT / "runtime/test-runs/xbox-theme")))
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
settings_path.write_text(json.dumps({"theme": "Original Xbox", "reducedMotion": True, "ambientMotion": False,
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

        def click(item):
            check(item is not None, "control exists")
            point = item.mapToScene(item.boundingRect().center())
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
            QTest.qWait(180)

        try:
            settings.reducedMotion = True
            settings.ambientMotion = False
            check(find("XboxDashboardLaunch") is not None, "theme surface loaded")
            if surface_mode:
                dashboard = find("XboxDashboard")
                check(dashboard.parentItem().objectName() == "ApplicationBody", "menu is part of the application body, not a popup overlay")
                check(not find("ApplicationWorkspace").isVisible() and not find("ApplicationWorkspace").isEnabled(), "workspace cannot receive clicks or keyboard focus behind the menu")
                find("TitleBarButton:max").forceActiveFocus()
                backdrop_clocks = [i for i in items() if i.objectName() == "XboxMotionClock"
                                   and i.parentItem().objectName() == "XboxBackdrop"
                                   and not i.parentItem().property("dashboard")]
                check(backdrop_clocks and all(not c.property("requested") for c in backdrop_clocks), "covered workspace animation stays paused when focus leaves menu content")
                find("XboxDashboardMenu").forceActiveFocus()
                click(find("TitleBarButton:max"))
                check(window.visibility() == QWindow.Maximized, "title-bar Maximize works while initial menu is open")
                click(find("TitleBarButton:max"))
                check(window.visibility() == QWindow.Windowed, "title-bar Restore works while menu is open")
                window.resize(int(width), int(height))
                QTest.qWait(100)
                click(find("TitleBarButton:min"))
                check(window.visibility() == QWindow.Minimized, "title-bar Minimize works while menu is open")
                window.showNormal()
                QTest.qWait(150)
                check(find("XboxDashboardMenu").isVisible(), "menu survives minimize and restore")
                drag = window.findChild(QObject, "TitleBarDragHandler")
                drag_samples = []
                drag.activeChanged.connect(lambda: drag_samples.append(drag.property("active")))
                start = QPoint(window.width() // 2, int(find("TitleBarButton:max").height() // 2))
                QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
                QTest.mouseMove(window, start + QPoint(30, 0), 30)
                QTest.mouseMove(window, start + QPoint(65, 0), 30)
                QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPoint(65, 0))
                QTest.qWait(100)
                check(True in drag_samples, "title-bar drag reaches the existing system-move handler with menu open")
                drag.activeChanged.disconnect()
                QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, start)
                QTest.qWait(150)
                check(window.visibility() == QWindow.Maximized, "title-bar double-click maximizes with menu open")
                click(find("TitleBarButton:max"))
                window.resize(int(width), int(height))
                QTest.qWait(100)
            if depth_mode:
                check(find("XboxDashboardMenu") is not None and find("XboxDashboardMenu").isVisible(), "dashboard is the initial navigation screen")
                check(window.title() == "KFPS - Main Menu", "initial title identifies main menu")
                check(not find("SidebarNavigationList").isVisible(), "parallel sidebar navigation is hidden")
                QTest.keyClick(window, Qt.Key_Escape)
                QTest.qWait(100)
                check(find("XboxDashboardMenu").isVisible(), "initial dashboard cannot dismiss into an unchosen workspace")
                QTest.keyClick(window, Qt.Key_Home)
                QTest.keyClick(window, Qt.Key_Return)
                QTest.qWait(200)
                results.append({"startup_page": controller.currentPage, "focus": window.activeFocusItem().objectName() if window.activeFocusItem() else None})
                check(controller.currentPage == "create" and (find("XboxDashboardMenu") is None or not find("XboxDashboardMenu").isVisible()), "initial selection enters its workspace")
            initial_data = dict(settings._data)
            click(find("XboxDashboardLaunch"))
            menu = find("XboxDashboardMenu")
            check(menu is not None and menu.isVisible(), "dashboard opens from emblem")
            window.grabWindow().save(str(run / "dashboard.png"))
            QTest.keyClick(window, Qt.Key_End)
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(250)
            check(controller.currentPage == "settings", "keyboard End/Enter navigates to settings")
            check(not menu.isVisible(), "navigation closes dashboard")
            click(find("XboxDashboardLaunch"))
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(100)
            check(not menu.isVisible(), "Escape returns to current page")
            if surface_mode:
                check(find("ApplicationWorkspace").isVisible() and find("ApplicationWorkspace").isEnabled(), "workspace input restored after closing the menu")
                check(find("XboxDashboardLaunch").hasActiveFocus(), "Back restores focus to the menu launcher")
            click(find("XboxDashboardLaunch"))
            QTest.keyClick(window, Qt.Key_Home)
            QTest.qWait(100)
            click(find("XboxDashboardRoute:create"))
            check(controller.currentPage == "create", "mouse navigation opens Create")
            window.grabWindow().save(str(run / "create.png"))
            if depth_mode:
                for index, route in enumerate(("create", "outputs", "liveries", "community", "editor", "tools", "support", "help", "update", "settings")):
                    click(find("XboxDashboardLaunch"))
                    QTest.keyClick(window, Qt.Key_Home)
                    for _ in range(index):
                        QTest.keyClick(window, Qt.Key_Down)
                    QTest.keyClick(window, Qt.Key_Return)
                    QTest.qWait(200)
                    check(controller.currentPage == route, f"main menu enters {route} through keyboard input")
                    check(not find("SidebarNavigationList").isVisible(), f"{route} keeps menu as primary navigation")
                click(find("XboxDashboardLaunch"))
                click(find("XboxDashboardCredits"))
                check(controller.currentPage == "credits", "Credits remains reachable through the main menu")
                click(find("XboxDashboardLaunch"))
                click(find("XboxDashboardClose"))
                check(controller.currentPage == "credits", "Back returns without changing the current workspace")
            for route in ("outputs", "liveries", "community", "editor", "tools", "help", "settings"):
                controller.navigate(route)
                QTest.qWait(180)
                check(controller.currentPage == route, f"existing route {route}")
            for theme in ("Night Blossom", "Command Prompt", "Original Xbox"):
                settings.theme = theme
                QTest.qWait(150)
                check(settings.theme == theme, f"theme switch {theme}")
                check((find("XboxDashboardLaunch") is not None) == (theme == "Original Xbox"), "theme-specific surface unloads cleanly")
                if depth_mode:
                    check(find("SidebarNavigationList").isVisible() == (theme != "Original Xbox"), "other themes retain normal sidebar navigation")
            preserved = {key: value for key, value in initial_data.items() if key != "theme"}
            check(all(settings._data.get(key) == value for key, value in preserved.items()), "unrelated settings preserved")
            from kfps_ui.settings_service import SettingsService
            check(SettingsService(module.AppPaths.discover().settings_file).theme == "Original Xbox", "actual preference reopened")
            click(find("XboxDashboardLaunch"))
            settings.theme = "Night Blossom"
            QTest.qWait(150)
            check(find("XboxDashboardMenu") is None, "open dashboard is removed when changing theme")
            if surface_mode:
                check(find("ApplicationWorkspace").isVisible() and find("ApplicationWorkspace").isEnabled(), "theme switch removes menu ownership of the workspace")
            settings.theme = "Original Xbox"
            QTest.qWait(150)
            click(find("XboxDashboardLaunch"))
            window.resize(960, 600)
            QTest.qWait(150)
            menu = find("XboxDashboardMenu")
            check(menu is not None and menu.width() > 200 and menu.height() > 100, "dashboard resizes while open")
            click(find("XboxDashboardClose"))
            check(not menu.isVisible(), "Back closes resized dashboard")
            if motion_mode:
                window.resize(int(width), int(height))
                settings.reducedMotion = False
                settings.ambientMotion = True
                QTest.qWait(250)
                def clocks():
                    return [i for i in items() if i.objectName() == "XboxMotionClock"]
                def simulate_focus(active):
                    # Only the offscreen clock input is simulated, never OS activation.
                    for clock in clocks():
                        clock.setProperty("applicationActive", active)
                def frozen(name):
                    before = [c.property("seconds") for c in clocks()]
                    QTest.qWait(350)
                    check(before == [c.property("seconds") for c in clocks()], name)

                target = find("XboxDashboardLaunch")
                dashboard = window.findChild(QObject, "XboxDashboard")
                reveal_samples = []
                if dashboard is not None:
                    dashboard.revealChanged.connect(lambda: reveal_samples.append(dashboard.property("reveal")))
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target.mapToScene(target.boundingRect().center()).toPoint())
                QTest.qWait(70)
                entry_sample = find("XboxDashboardRoute:settings")
                reveal = entry_sample.property("reveal") if entry_sample else None
                (run / "entry-progress.json").write_text(json.dumps({"reveal_after_70ms": reveal}))
                window.grabWindow().save(str(run / "entry-070.png"))
                QTest.qWait(520)
                if dashboard is not None:
                    dashboard.revealChanged.disconnect()
                (run / "entry-progress.json").write_text(json.dumps({"reveal_after_70ms": reveal, "samples": reveal_samples}))
                check(any(0 < value < 1 for value in reveal_samples), "menu entry has an intermediate animated state")
                simulate_focus(True)
                QTest.qWait(100)
                check(any(c.property("running") for c in clocks()), "ambient clock active in simulated foreground")
                if depth_mode:
                    check(find("XboxRearOrbits") is not None and find("XboxReactorCurrent") is not None, "front and rear orbital surfaces exist")
                window.grabWindow().save(str(run / "moving-0.png"))
                QTest.qWait(1100)
                window.grabWindow().save(str(run / "moving-1.png"))
                from PIL import Image, ImageChops
                with Image.open(run / "moving-0.png") as a, Image.open(run / "moving-1.png") as b:
                    check(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None, "rendered motion changes pixels")
                    region = (20, 90, int(width) - 40, 200)
                    check(ImageChops.difference(a.convert("RGB").crop(region), b.convert("RGB").crop(region)).getbbox() is not None, "wire grid changes outside the emblem")
                measurements = []
                for ambient in (False, True, False, True):
                    settings.ambientMotion = ambient
                    QTest.qWait(250)
                    cpu, wall = time.process_time(), time.monotonic()
                    QTest.qWait(1800)
                    measurements.append({"ambient": ambient, "cpu_seconds": time.process_time() - cpu,
                                         "wall_seconds": time.monotonic() - wall})
                (run / "cpu-samples.json").write_text(json.dumps(measurements, indent=2))
                settings.ambientMotion = False
                frozen("Ambient Motion off stops all theme clocks")
                settings.ambientMotion = True
                settings.reducedMotion = True
                frozen("Reduced Motion stops all theme clocks")
                settings.reducedMotion = False
                simulate_focus(False)
                frozen("inactive window stops all theme clocks")
                simulate_focus(True)
                window.hide()
                frozen("hidden window stops all theme clocks")
                window.show()
                QTest.qWait(100)
                simulate_focus(True)
                QTest.qWait(150)
                check(any(c.property("running") for c in clocks()), "ambient resumes after window returns")
                # Keep a short actual-window frame sequence for the visual review.
                for frame in range(24):
                    QTest.qWait(80)
                    window.grabWindow().save(str(run / f"frame-{frame:02d}.png"))
                preview = run / "preview-frames"
                preview.mkdir(exist_ok=True)
                QTest.keyClick(window, Qt.Key_Escape)
                QTest.qWait(500)
                target = find("XboxDashboardLaunch")
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target.mapToScene(target.boundingRect().center()).toPoint())
                for frame in range(64):
                    if frame == 8:
                        simulate_focus(True)
                        QTest.keyClick(window, Qt.Key_Home)
                    if frame in (18, 28, 38, 48):
                        QTest.keyClick(window, Qt.Key_Down)
                    QTest.qWait(80)
                    window.grabWindow().save(str(preview / f"{frame:03d}.png"))
                QTest.keyClick(window, Qt.Key_End)
                QTest.keyClick(window, Qt.Key_Return)
                QTest.qWait(550)
                check(controller.currentPage == "settings", "navigation works while ambient animation runs")
                check(find("XboxDashboardMenu") is None or not find("XboxDashboardMenu").isVisible(), "animated navigation closes dashboard")
                transition = find("XboxPageTransition")
                check(transition is not None, "page transition is loaded")
                transition.setProperty("applicationActive", True)
                controller.navigate("outputs")
                QTest.qWait(30)
                check(transition.property("progress") < 1, "page transition starts on a real route change")
                QTest.qWait(600)
                check(transition.property("progress") == 1, "page transition settles without input blocking")
                controller.navigate("create")
                QTest.qWait(30)
                settings.reducedMotion = True
                check(transition.property("progress") == 1, "Reduced Motion cancels an in-flight page transition")
                settings.reducedMotion = False
                for attempt in range(3):
                    target = find("XboxDashboardLaunch")
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target.mapToScene(target.boundingRect().center()).toPoint())
                    QTest.qWait(40)
                    closing_start = time.monotonic()
                    QTest.keyClick(window, Qt.Key_Escape)
                    while time.monotonic() - closing_start < 0.7 and find("XboxDashboardMenu") is not None and find("XboxDashboardMenu").isVisible():
                        QTest.qWait(20)
                    results.append({"escape_close_ms": round((time.monotonic() - closing_start) * 1000)})
                    check(find("XboxDashboardMenu") is None or not find("XboxDashboardMenu").isVisible(), f"Escape interrupts entry {attempt}")
                click(find("XboxDashboardLaunch"))
                settings.theme = "Night Blossom"
                QTest.qWait(100)
                check(not clocks(), "theme exit destroys all animation clocks")
                settings.theme = "Original Xbox"
                settings.reducedMotion = True
                QTest.qWait(100)
                click(find("XboxDashboardLaunch"))
                check(find("XboxDashboardMenu").isVisible(), "reduced-motion dashboard opens immediately")
                click(find("XboxDashboardClose"))
            if surface_mode:
                settings.reducedMotion = False
                click(find("XboxDashboardLaunch"))
                QTest.qWait(500)
                QTest.keyClick(window, Qt.Key_Escape)
                context = QQmlEngine.contextForObject(window)
                component = QQmlComponent(context.engine())
                component.setData(b'''import QtQuick 6.7
import QtQuick.Controls 6.7
Popup { width: 320; height: 100; modal: true; focus: true
    contentItem: TextField { objectName: "WindowControlDialogInput"; focus: true }
}''', QUrl())
                dialog = component.create(context)
                check(dialog is not None, "modal dialog fixture loads in the actual application")
                dialog.setParent(window)
                dialog.setProperty("parent", window.contentItem())
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(50)
                dialog_input = dialog.findChild(QQuickItem, "WindowControlDialogInput")
                dialog_input.forceActiveFocus()
                QTest.qWait(500)
                check(window.activeFocusItem() == dialog_input, "closing menu does not steal focus from a newly opened modal dialog")
                QMetaObject.invokeMethod(dialog, "close")
                dialog.deleteLater()
                QTest.qWait(100)
            check(not [w for w in warnings if any(x in w for x in ("ReferenceError", "TypeError", "Error:", "Cannot assign", "Unable to assign", "Binding loop", "Cannot open"))], "no QML errors")
            if surface_mode:
                settings.reducedMotion = True
                click(find("XboxDashboardLaunch"))
                check(find("XboxDashboardMenu").isVisible(), "menu open for real window-close check")
                click(find("TitleBarButton:close"))
                check(not window.isVisible(), "title-bar Close closes the actual application window with menu open")
            app.exit(0)
        except Exception as error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
            app.exit(1)
        finally:
            (run / "results.json").write_text(json.dumps({"checks": results, "qml_messages": warnings}, indent=2), encoding="utf-8")
            print(json.dumps({"results": str(run / "results.json"), "checks": results, "warnings": warnings}, indent=2))

    QTimer.singleShot(1200, checks)


module.install_development_harness = install
sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--allow-source-download", "--demo", "--theme-preview", "Original Xbox",
    "--width", width, "--height", height, "--page", "create"]
raise SystemExit(module.main())
