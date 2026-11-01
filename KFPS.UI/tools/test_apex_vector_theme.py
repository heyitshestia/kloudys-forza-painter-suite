"""Exercise the actual Qt app without desktop input, network or personal settings."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import zipfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--width", type=int, default=1760)
parser.add_argument("--height", type=int, default=1040)
parser.add_argument("--scale", type=float, default=1.0)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--rhi", action="store_true")
parser.add_argument("--regression-only", action="store_true")
parser.add_argument("--baseline", type=Path)
args = parser.parse_args()
run = args.output.resolve()
run.mkdir(parents=True, exist_ok=True)
profile = run / "profile"
profile.mkdir(exist_ok=True)
os.environ.update(
    QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
    QT_SCALE_FACTOR=str(args.scale),
    KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1",
    KFPS_SKIP_STARTUP_INDEX="1", KFPS_SKIP_STARTUP_THUMBNAILS="1",
    KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
    APPDATA=str(profile / "roaming"), LOCALAPPDATA=str(profile / "local"),
    QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
)
os.environ.pop("QSG_RHI_BACKEND", None)
if args.rhi:
    os.environ.update(QT_QPA_PLATFORM="windows", QT_QUICK_BACKEND="rhi", KFPS_QML_GRAPHICS="d3d11", QSG_RHI_PREFER_SOFTWARE_RENDERER="1")
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI"), str(ROOT / "KFPS.UI/src")]

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QEvent, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtGui import QWindow
from PIL import Image, ImageChops

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location("apex_test_app", ROOT / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if args.rhi:
    original_placement = module.calculate_window_placement
    module.calculate_window_placement = lambda *a, **k: replace(original_placement(*a, **k), x=-20000, y=-20000)
original = module.AppPaths.discover()
if args.baseline:
    if not args.regression_only:
        parser.error("--baseline requires --regression-only")
    baseline_qml = run / "baseline-qml"
    if not (run / "assets").is_dir():
        raise ValueError("Baseline snapshot needs an assets junction to KFPS.UI/assets beside baseline-qml")
    shutil.copytree(original.qml_root, baseline_qml, dirs_exist_ok=True)
    with zipfile.ZipFile(args.baseline) as archive:
        for name in archive.namelist():
            if name.startswith("KFPS.UI/qml/") and name.endswith(".qml"):
                target = (baseline_qml / name.removeprefix("KFPS.UI/qml/")).resolve()
                if not target.is_relative_to(baseline_qml):
                    raise ValueError("Unsafe baseline archive path")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    original = replace(original, qml_root=baseline_qml)
sample = profile / "app"
sample.mkdir(exist_ok=True)
shutil.copy2(ROOT / "VERSION", sample / "VERSION")
module.AppPaths.discover = classmethod(lambda cls: replace(original, app_root=sample, runtime_root=profile / "runtime"))
settings_path = profile / "runtime/qml-shell-settings.json"
settings_path.parent.mkdir(exist_ok=True)
settings_path.write_text(json.dumps({
    "theme": "Apex Vector", "reducedMotion": True, "ambientMotion": False,
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True,
}), encoding="utf-8")
protected = [ROOT / "VERSION", ROOT / "runtime/qml-shell-settings.json"]
protected.extend((ROOT / "settings").glob("*.json"))
def protected_hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in protected}
before = protected_hashes()


def install(app, window, controller, community, settings, jsons, app_args):
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
            # A native window outside the desktop is not continuously exposed.
            # Force its real layout/render pass before deriving hit coordinates.
            window.grabWindow()
            QTest.qWait(20)
            item = find(name)
            check(item is not None and item.isVisible() and item.isEnabled(), "reachable " + name)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, item.mapToScene(item.boundingRect().center()).toPoint())
            QTest.qWait(80)
        def key(value):
            QTest.keyClick(window, value)
            QTest.qWait(60)
        def capture(name):
            screenshot = window.grabWindow()
            check(not screenshot.isNull(), "nonempty image " + name)
            check(screenshot.save(str(run / (name + ".png"))), "capture " + name)
            with Image.open(run / (name + ".png")) as image:
                extrema = image.convert("RGB").getextrema()
                check(any(high - low > 50 for low, high in extrema), "nonblank pixels " + name)
        try:
            if args.rhi:
                check("Direct3D11" in str(window.rendererInterface().graphicsApi()), "D3D11 renderer actually active")
            # A production notice is unrelated to navigation and handled separately.
            window.setProperty("liveryWipNoticeAcknowledged", True)
            if args.regression_only:
                for page in ("create", "editor", "tools", "outputs", "liveries", "community", "settings", "help", "support", "update", "credits"):
                    controller.navigate(page)
                    QTest.qWait(200)
                    window.grabWindow()
                from kfps_ui.theme_catalog import THEME_PRESETS
                for preset in THEME_PRESETS:
                    settings.theme = preset.name
                    QTest.qWait(500)
                    capture("regression-" + preset.name.lower().replace(" ", "-"))
                check(protected_hashes() == before, "personal settings and version unchanged")
                window.close()
                app.exit(0)
                return
            dashboard = find("ApexDashboard")
            check(dashboard is not None and dashboard.isVisible(), "initial menu visible")
            check(dashboard.parentItem().objectName() == "ApplicationBody", "menu replaces body, not title bar")
            check(not find("ApplicationWorkspace").isVisible(), "workspace hidden while menu open")
            check(not find("ApexBackdrop").property("motionAllowed"), "reduced motion stops backdrop")
            capture("home")
            dashboard.forceActiveFocus()
            key(Qt.Key_Escape)
            check(dashboard.isVisible(), "Escape cannot reveal unchosen page")
            click("ApexRoute:create")
            check(not dashboard.isVisible() and controller.currentPage == "create", "initial Create closes menu without route change")
            capture("create")
            click("ApexDashboardLaunch")
            key(Qt.Key_Escape)
            check(not dashboard.isVisible(), "Escape resumes workspace")
            check(find("ApexDashboardLaunch").hasActiveFocus(), "return restores launcher focus")
            for category, routes in enumerate((("create", "editor", "tools"), ("outputs", "liveries", "community"), ("settings", "help", "support", "update", "credits"))):
                for route in routes:
                    click("ApexDashboardLaunch")
                    click("ApexCategory:" + str(category))
                    check(dashboard.property("category") == category, "category selected " + str(category))
                    item = find("ApexRoute:" + route)
                    check(item is not None, "route instantiated " + route)
                    point = item.mapToScene(item.boundingRect().bottomRight())
                    check(0 < point.x() <= window.width() and 0 < point.y() <= window.height(), "route fits " + route)
                    check(item.height() >= 24, "usable target " + route)
                    click("ApexRoute:" + route)
                    check(controller.currentPage == route and not dashboard.isVisible(), "actual page " + route)
                    if route in ("outputs", "settings", "liveries"):
                        capture(route)
            click("ApexDashboardLaunch")
            dashboard.forceActiveFocus()
            key(Qt.Key_Left)
            check(dashboard.property("category") == 1, "left changes category")
            key(Qt.Key_End)
            check(dashboard.property("selectedIndex") == 2, "End selects last entry")
            key(Qt.Key_Home)
            key(Qt.Key_Down)
            key(Qt.Key_Return)
            check(controller.currentPage == "liveries" and not dashboard.isVisible(), "keyboard routes to selected destination")
            click("ApexDashboardLaunch")
            click("ApexCategory:2")
            capture("system")
            if args.rhi:
                check(not window.isActive(), "native background window never takes focus")
                settings.reducedMotion = False
                settings.ambientMotion = True
                QTest.qWait(40)
                check(not find("ApexBackdrop").property("motionAllowed"), "native inactive backdrop stays stopped")
                check(protected_hashes() == before, "personal settings and version unchanged")
                click("TitleBarButton:close")
                check(not window.isVisible(), "close works from menu")
                app.exit(0)
                return
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Maximized, "maximize from menu")
            click("TitleBarButton:max")
            check(window.visibility() == QWindow.Windowed, "restore from menu")
            window.resize(args.width, args.height)
            click("TitleBarButton:min")
            check(window.visibility() == QWindow.Minimized, "minimize from menu")
            check(not find("ApexBackdrop").property("motionAllowed"), "minimized motion disabled")
            window.showNormal()
            QTest.qWait(100)
            drag = window.findChild(QObject, "TitleBarDragHandler")
            active = []
            callback = lambda: active.append(drag.property("active"))
            drag.activeChanged.connect(callback)
            start = QPoint(window.width() // 2, 12)
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPoint(50, 0), 30)
            QTest.mouseMove(window, start + QPoint(90, 0), 30)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPoint(90, 0))
            drag.activeChanged.disconnect(callback)
            check(True in active, "title retains native move handler")
            for theme in ("Night Blossom", "Command Prompt", "Windows 94", "Original Xbox", "Original PS2", "NieR Automata", "Apex Vector"):
                settings.theme = theme
                QTest.qWait(220)
                check(settings.theme == theme, "switch theme " + theme)
                check((find("ApexDashboard") is not None) == (theme == "Apex Vector"), "Apex lifecycle " + theme)
            dashboard = find("ApexDashboard")
            check(dashboard.isVisible(), "returning to Apex restores menu")
            settings.reducedMotion = False
            settings.ambientMotion = True
            # Synthetic activation is delivered only to the offscreen Qt window.
            app.sendEvent(window, QEvent(QEvent.WindowActivate))
            QTest.qWait(80)
            backdrop = find("ApexBackdrop")
            check(backdrop.property("motionAllowed"), "active menu permits ambient motion")
            drift = backdrop.property("drift")
            QTest.qWait(200)
            check(backdrop.property("drift") != drift, "ambient clock advances")
            inactive_target = QWindow()
            inactive_target.resize(16, 16)
            inactive_target.show()
            inactive_target.requestActivate()
            QTest.qWait(80)
            check(not backdrop.property("motionAllowed"), "inactive menu stops ambient motion")
            drift = backdrop.property("drift")
            QTest.qWait(100)
            check(backdrop.property("drift") == drift, "inactive clock is stationary")
            inactive_target.close()
            window.requestActivate()
            QTest.qWait(80)
            for frame in range(8):
                if frame in (0, 2, 4, 6):
                    click("ApexCategory:" + str((frame // 2) % 3))
                capture("animation-%02d" % frame)
                QTest.qWait(180)
            click("ApexCategory:1")
            check(dashboard.property("reveal") < 1, "category transition runs")
            capture("motion-early")
            QTest.qWait(400)
            check(dashboard.property("reveal") == 1, "transition completes")
            capture("motion-complete")
            with Image.open(run / "motion-early.png") as early, Image.open(run / "motion-complete.png") as late:
                check(ImageChops.difference(early.convert("RGB"), late.convert("RGB")).getbbox() is not None, "motion changes real pixels")
            click("ApexCategory:2")
            settings.reducedMotion = True
            QTest.qWait(60)
            check(dashboard.property("reveal") == 1, "reduced motion interrupts transition")
            settings.reducedMotion = False
            click("ApexRoute:settings")
            check(not find("ApexBackdrop").property("motionAllowed"), "ambient motion stops inside workspace")
            click("ApexDashboardLaunch")
            settings.save()
            check(json.loads(settings_path.read_text())["theme"] == "Apex Vector", "test theme persisted")
            fatal = [m for m in messages if any(token in m for token in ("ReferenceError", "TypeError", "Error:", "Cannot assign", "Unable to assign", "Binding loop", "Cannot open", "is not a type"))]
            check(not fatal, "no QML errors")
            check(protected_hashes() == before, "personal settings and version unchanged")
            click("TitleBarButton:close")
            check(not window.isVisible(), "close works from menu")
            app.exit(0)
        except Exception as error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
            app.exit(1)
        finally:
            (run / "results.json").write_text(json.dumps({"checks": results, "messages": messages, "protected_unchanged": protected_hashes() == before, "graphics_api": str(window.rendererInterface().graphicsApi())}, indent=2), encoding="utf-8")
            print(json.dumps({"passed": sum(r.get("passed", False) for r in results), "failures": [r for r in results if r.get("passed") is False or "error" in r], "unique_messages": sorted(set(messages))}, indent=2))
    QTimer.singleShot(1200, checks)

module.install_development_harness = install
sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--allow-source-download", "--demo", "--theme-preview", "Apex Vector", "--width", str(args.width), "--height", str(args.height), "--page", "create"]
if args.rhi:
    sys.argv.append("--community-preview-background")
def timeout():
    (run / "timeout.txt").write_text("Test exceeded 90 seconds.\n" + "\n".join(messages[-100:]), encoding="utf-8")
    os._exit(124)
watchdog = threading.Timer(90, timeout)
watchdog.daemon = True
watchdog.start()
raise SystemExit(module.main())
