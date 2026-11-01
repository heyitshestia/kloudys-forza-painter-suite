"""Exercise 2049 in the real app with an isolated profile and no desktop input."""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--width", type=int, default=1600)
parser.add_argument("--height", type=int, default=1000)
parser.add_argument("--scale", type=float, default=1)
parser.add_argument("--rhi", action="store_true")
parser.add_argument("--threaded-smoke", action="store_true", help="Use queued real-loop native steps instead of nested QTest waits")
args = parser.parse_args()
if args.threaded_smoke and not args.rhi:
    parser.error("--threaded-smoke requires --rhi")
run = args.output.resolve()
profile = run / "profile"
profile.mkdir(parents=True, exist_ok=True)
os.environ.update(
    QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_SCALE_FACTOR=str(args.scale),
    KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1", KFPS_SKIP_STARTUP_INDEX="1",
    KFPS_SKIP_STARTUP_THUMBNAILS="1", KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
    APPDATA=str(profile / "roaming"), LOCALAPPDATA=str(profile / "local"),
    QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
)
os.environ.pop("QSG_RHI_BACKEND", None)
if args.rhi:
    os.environ.update(QT_QPA_PLATFORM="windows", QT_QUICK_BACKEND="rhi", KFPS_QML_GRAPHICS="d3d11", QSG_RHI_PREFER_SOFTWARE_RENDERER="1", QSG_RENDER_LOOP="threaded" if args.threaded_smoke else "basic")
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI"), str(ROOT / "KFPS.UI/src")]
from PySide6.QtCore import QEvent, QMetaObject, QObject, QPoint, QSize, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QResizeEvent, QWindow
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from PIL import Image, ImageChops
from PIL.ImageQt import fromqimage

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location("archive_test_app", ROOT / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
paths = module.AppPaths.discover()
sample = profile / "app"
sample.mkdir(exist_ok=True)
shutil.copy2(ROOT / "VERSION", sample / "VERSION")
module.AppPaths.discover = classmethod(lambda cls: replace(paths, app_root=sample, runtime_root=profile / "runtime"))
settings_path = profile / "runtime/qml-shell-settings.json"
settings_path.parent.mkdir(exist_ok=True)
settings_path.write_text(json.dumps({
    "theme": "2049", "reducedMotion": True, "ambientMotion": False,
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True,
}), encoding="utf-8")
protected = [ROOT / "VERSION", ROOT / "runtime/qml-shell-settings.json", *list((ROOT / "settings").glob("*.json"))]
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in protected}
before = hashes()


def fatal_qml_messages():
    return [m for m in messages if any(s in m for s in (
        "ReferenceError", "TypeError", "SyntaxError", "Unexpected token",
        "Expected token", "Cannot assign", "Unable to assign", "Binding loop", "is not a type",
    )) or ("Cannot open" in m and "/themes/nightcity/" not in m)]


def install(app, window, controller, community, settings, jsons, app_args):
    if args.rhi:
        foreground_handle = ctypes.windll.user32.GetForegroundWindow
        foreground_handle.restype = ctypes.c_void_p
    if args.threaded_smoke:
        steps = [("2049", page) for page in ("create", "outputs", "liveries", "community", "editor", "tools", "support", "help", "update", "settings")]
        steps += [("Night Blossom", "settings"), ("2049", "settings"), ("2049", "create")]
        results = []
        idle = {}
        def finish(error=None):
            if error is None and fatal_qml_messages():
                error = AssertionError(fatal_qml_messages())
            report = {"steps": results, "error": repr(error) if error else None, "messages": sorted(set(messages)), "protected_unchanged": hashes() == before, "graphics_api": str(window.rendererInterface().graphicsApi()), "render_loop": "threaded", "idle": idle}
            (run / "threaded-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            window.close()
            app.exit(1 if error or not report["protected_unchanged"] else 0)
        def step(index):
            if index == len(steps):
                def sample():
                    frames = [0]
                    def frame_swapped():
                        frames[0] += 1
                    window.frameSwapped.connect(frame_swapped)
                    cpu, wall = time.process_time(), time.perf_counter()
                    def sampled():
                        window.frameSwapped.disconnect(frame_swapped)
                        idle.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall, frames=frames[0])
                        idle["running_animations"] = []
                        for obj in window.findChildren(QObject):
                            if "Animation" not in obj.metaObject().className() or not obj.property("running"):
                                continue
                            parents, owner = [], obj.parent()
                            while owner is not None and len(parents) < 6:
                                parents.append(owner.metaObject().className() + ":" + owner.objectName())
                                owner = owner.parent()
                            target = obj.property("target")
                            idle["running_animations"].append({"type": obj.metaObject().className(), "name": obj.objectName(), "parents": parents, "target": target.objectName() if isinstance(target, QObject) else str(target), "property": obj.property("property"), "duration": obj.property("duration"), "loops": obj.property("loops")})
                        finish(AssertionError("Inactive window keeps rendering") if frames[0] > 2 or idle["running_animations"] else None)
                    QTimer.singleShot(2000, sampled)
                QTimer.singleShot(4000, sample)
                return
            theme, page = steps[index]
            (run / "progress.txt").write_text(f"threaded {index}: {theme} / {page}", encoding="utf-8")
            settings.theme = theme
            controller.navigate(page)
            started = time.perf_counter()
            def capture_step():
                try:
                    assert settings.theme == theme and controller.currentPage == page
                    assert not fatal_qml_messages(), fatal_qml_messages()
                    host = window.findChild(QObject, "CachedPageHost")
                    if host.property("item") is None:
                        assert time.perf_counter() - started < 10, f"Page not ready: {page}"
                        QTimer.singleShot(100, capture_step)
                        return
                    if theme == "2049" and page == "create":
                        stack = [window.contentItem()]
                        visible_names = set()
                        while stack:
                            item = stack.pop()
                            if item.isVisible():
                                visible_names.add(item.objectName())
                            stack.extend(item.childItems())
                        assert {"ArchiveWorkbench", "ArchiveSourceBay", "ArchiveResultBay"} <= visible_names
                    assert foreground_handle() != int(window.winId()) and not window.isActive()
                    frame = window.grabWindow()
                    target = run / f"threaded-{index:02d}-{page}.png"
                    assert not frame.isNull() and frame.save(str(target))
                    with Image.open(target) as image:
                        assert any(hi - lo > 50 for lo, hi in image.convert("RGB").getextrema())
                    results.append({"theme": theme, "page": page, "passed": True, "settle_seconds": time.perf_counter() - started})
                    QTimer.singleShot(50, lambda: step(index + 1))
                except Exception as error:
                    finish(error)
            QTimer.singleShot(1200, capture_step)
        QTimer.singleShot(1500, lambda: step(0))
        return
    cold_routes = []
    def checks():
        results = []
        measurements = {"cold_routes": cold_routes}
        def check(condition, name):
            (run / "progress.txt").write_text(name, encoding="utf-8")
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
            matches = [i for i in items() if i.objectName() == name]
            return next((i for i in matches if i.isVisible()), matches[0] if matches else None)
        def page_ready():
            host = find("CachedPageHost")
            started = time.perf_counter()
            deadline = started + 4
            while host.property("item") is None and time.perf_counter() < deadline:
                window.grabWindow()
                QTest.qWait(40)
            measurements.setdefault("page_readiness", []).append({
                "page": controller.currentPage,
                "wait_seconds": time.perf_counter() - started,
                "host_page": host.property("currentPage"),
                "ready": host.property("item") is not None,
            })
            check(host.property("item") is not None, "page content ready " + controller.currentPage)
        def click(name):
            window.grabWindow()
            QTest.qWait(50)
            window.grabWindow()
            item = find(name)
            check(item is not None and item.isVisible() and item.isEnabled(), "reachable " + name)
            ancestor = item.parentItem()
            while ancestor is not None:
                if ancestor.property("contentY") is not None and ancestor.property("contentHeight") is not None:
                    point = item.mapToItem(ancestor, item.boundingRect().center())
                    offset = max(0, min(float(ancestor.property("contentHeight")) - ancestor.height(), float(ancestor.property("contentY")) + point.y() - ancestor.height() / 2))
                    ancestor.setProperty("contentY", offset)
                    QTest.qWait(40)
                ancestor = ancestor.parentItem()
            point = item.mapToScene(item.boundingRect().center()).toPoint()
            check(0 <= point.x() < window.width() and 0 <= point.y() < window.height(), "onscreen target " + name)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(500)
            if name.startswith("NavButton:"):
                page_ready()
        def capture(name):
            window.grabWindow()
            QTest.qWait(50)
            frame = window.grabWindow()
            check(not frame.isNull() and frame.save(str(run / (name + ".png"))), "capture " + name)
            if args.rhi:
                check(foreground_handle() != int(window.winId()) and not window.isActive(), "background native capture " + name)
            with Image.open(run / (name + ".png")) as image:
                check(any(hi - lo > 50 for lo, hi in image.convert("RGB").getextrema()), "nonblank " + name)
            active_nav = find("NavButton:" + controller.currentPage.title())
            if active_nav is not None:
                check(active_nav.property("selected"), "instrument route selected " + name)
                point = active_nav.mapToScene(active_nav.boundingRect().bottomLeft())
                point.setX(point.x() + active_nav.width() / 2)
                point.setY(point.y() - 3)
                pixel = frame.pixelColor(round(point.x() * frame.width() / window.width()), round(point.y() * frame.height() / window.height()))
                check(pixel.red() > 115 and pixel.green() > 135, "selected navigation pixels " + name)
        try:
            window.resize(args.width, args.height)
            window.grabWindow()
            QTest.qWait(80)
            content = window.contentItem()
            if args.rhi and (content.width() != window.width() or content.height() != window.height()):
                # An unexposed Win32 test window can miss WM_SIZE. Exercise the
                # normal Qt resize handler without moving it onto the desktop.
                app.sendEvent(window, QResizeEvent(window.size(), QSize(int(content.width()), int(content.height()))))
                window.grabWindow()
                QTest.qWait(80)
                measurements["off_desktop_resize_event_injected"] = True
            check(content.width() == window.width() and content.height() == window.height(), "scene matches native window dimensions")
            window.setProperty("liveryWipNoticeAcknowledged", True)
            check(find("ArchiveBackdrop") is not None, "2049 loaded")
            check(find("ApplicationWorkspace").isVisible(), "normal workspace immediately available")
            check(find("ArchiveConsole") is not None, "instrument console loaded")
            check(find("ArchiveWorkbench") is not None, "new create workbench loaded")
            check(find("ArchiveSourceBay").isVisible() and find("ArchiveResultBay").isVisible(), "dual viewing bays available")
            foreground = find("ArchiveForeground")
            check(not foreground.property("motionAllowed"), "initial reduced motion")
            capture("create")
            context = QQmlEngine.contextForObject(window)
            source = context.contextProperty("sourceService")
            generation = context.contextProperty("generationService")
            session = find("CachedPageHost").property("item")
            layer_field = find("ArchiveLayers")
            layer_field.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
            for digit in "1375":
                QTest.keyClick(window, Qt.Key(ord(digit)))
            QTest.keyClick(window, Qt.Key_Tab)
            QTest.qWait(100)
            check(session.property("templateLayers") == "1375", "instrument edits authoritative shape budget")
            check(session.property("checkpointValues") == "500,1000,1250,1375", "instrument computes checkpoints through shared logic")
            settings.theme = "Night Blossom"
            QTest.qWait(200)
            check(session.property("templateLayers") == "1375", "budget preserved when leaving instrument theme")
            settings.theme = "2049"
            QTest.qWait(200)
            check(find("ArchiveLayers").property("text") == "1375", "budget restored in instrument controls")
            launches = []
            original_start = generation._start_single
            generation._start_single = lambda *values: launches.append(values)
            click("ArchiveGenerate")
            check(not launches and not generation.running, "empty source safely rejected")
            # Test through the real source service and queue entry point; stop at
            # the process boundary so no GPU generator is launched by UI tests.
            fixture = run / "calibration-source.png"
            from PIL import ImageDraw
            fixture_image = Image.new("RGBA", (480, 480), (0, 0, 0, 0))
            draw = ImageDraw.Draw(fixture_image)
            draw.rounded_rectangle((60, 60, 420, 420), radius=70, fill=(30, 130, 220, 255))
            draw.ellipse((135, 135, 345, 345), fill=(250, 230, 90, 255))
            draw.polygon(((240, 170), (300, 290), (180, 290)), fill=(210, 40, 80, 255))
            fixture_image.save(fixture)
            source.setPath(str(fixture))
            QTest.qWait(250)
            click("ArchiveGenerate")
            check(len(launches) == 1 and launches[0][2] == "1375", "real queue receives edited budget")
            check(launches[0][3] == "500,1000,1250,1375", "real queue receives edited checkpoints")
            check(Path(launches[0][0]) == fixture, "real queue receives chosen source")
            generation._start_single = original_start
            capture("source-loaded")
            artwork = find("ArchiveArtworkSource")
            scroll_view = find("ArchiveWorkbenchScroll")
            scroll_view.property("contentItem").setProperty("contentY", 0)
            window.grabWindow()
            QTest.qWait(40)
            point = artwork.mapToScene(artwork.boundingRect().center())
            shot = window.grabWindow()
            pixel = shot.pixelColor(round(point.x() * shot.width() / window.width()), round(point.y() * shot.height() / window.height()))
            check(abs(pixel.red() - 210) < 5 and abs(pixel.green() - 40) < 5 and abs(pixel.blue() - 80) < 5, "artwork colours remain unfiltered")
            check(not find("ArchiveStopSafe").isEnabled() and not find("ArchiveStopNow").isEnabled(), "idle stop controls disabled")
            simulated_run = profile / "simulated-run"
            simulated_run.mkdir(exist_ok=True)
            old_status = generation._status
            generation._running = True
            generation._run_dir = str(simulated_run)
            generation.changed.emit()
            QTest.qWait(80)
            check(not find("ArchiveGenerate").isEnabled() and find("ArchiveStopNow").isEnabled(), "running controls reflect real service state")
            click("ArchiveStopSafe")
            check((simulated_run / ".v2-stop").read_text().strip() == "stop", "safe stop uses existing service marker")
            generation._running = False
            generation._run_dir = ""
            generation._status = old_status
            generation.changed.emit()
            settings.manualOverrides = True
            click("ArchiveOpenOverrides")
            check(window.findChild(QObject, "ArchiveOverrides").property("visible"), "manual override dialog opens")
            close = find("ArchiveOverridesClose")
            seed_input = find("ArchiveOverride:seedValue")
            check(close.mapToScene(close.boundingRect().topLeft()).y() >= seed_input.mapToScene(seed_input.boundingRect().bottomLeft()).y(), "dialog footer clears all inputs")
            seed_input.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
            QTest.keyClick(window, Qt.Key_4)
            QTest.keyClick(window, Qt.Key_2)
            QTest.keyClick(window, Qt.Key_Tab)
            check(session.property("seedValue") == "42", "manual seed updates authoritative form")
            capture("overrides")
            click("ArchiveOverridesClose")
            QTest.qWait(100)
            check(not window.findChild(QObject, "ArchiveOverrides").property("visible"), "manual override dialog closes")
            for label in ("Detail", "Luma", "Repair", "2x"):
                option = find("KfpsCheckBox:" + label)
                option.forceActiveFocus()
                QTest.keyClick(window, Qt.Key_Space)
                QTest.qWait(30)
                check(option.property("checked"), "instrument option toggles " + label)
            generation._start_single = lambda *values: launches.append(values)
            try:
                click("ArchiveGenerate")
                check(len(launches) == 2 and all(launches[-1][4:9]), "all option flags reach real queue")
                check(launches[-1][12] == 42 and launches[-1][9] == session.property("maxResolution"), "manual values reach real queue")
            finally:
                generation._start_single = original_start
            click("ArchiveSourceReport")
            check(window.findChild(QObject, "ArchiveSourceReportDialog").property("visible"), "full source report accessible")
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(100)
            for label, page in (("Outputs", "outputs"), ("Liveries", "liveries"), ("Community", "community"), ("Editor", "editor"), ("Tools", "tools"), ("Support", "support"), ("Help", "help"), ("Update", "update"), ("Settings", "settings"), ("Create", "create")):
                click("NavButton:" + label)
                check(controller.currentPage == page, "real route " + page)
                button = find("NavButton:" + label)
                descendants = list(button.childItems())
                labels = []
                while descendants:
                    child = descendants.pop()
                    if child.isVisible() and child.property("text") == label and child.property("truncated") is not None:
                        labels.append(child)
                    descendants.extend(child.childItems())
                check(bool(labels) and all(not child.property("truncated") for child in labels), "navigation label fits " + label)
                if page in ("outputs", "liveries", "community", "help", "settings"):
                    capture(page)
            click("NavButton:Settings")
            QTest.qWait(500)
            combo = next((i for i in items() if i.objectName() == "KfpsComboBox" and i.property("currentText") == "2049"), None)
            check(combo is not None, "settings lists new theme")
            combo.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            QTest.qWait(80)
            capture("theme-menu")
            QTest.keyClick(window, Qt.Key_Home)
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(400)
            check(settings.theme == "Night Blossom", "keyboard selects existing theme")
            combo.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            QTest.keyClick(window, Qt.Key_Home)
            for _ in range(context.contextProperty("supporterService").availableThemes.index("2049")):
                QTest.keyClick(window, Qt.Key_Down)
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(400)
            check(settings.theme == "2049", "keyboard selects 2049")
            for name, preference in (("Reduce nonessential motion", "reducedMotion"), ("Ambient background motion", "ambientMotion")):
                toggle = find("KfpsSwitch:" + name)
                check(toggle is not None and toggle.isEnabled(), "motion control available " + preference)
                previous = getattr(settings, preference)
                toggle.forceActiveFocus()
                QTest.keyClick(window, Qt.Key_Space)
                QTest.qWait(80)
                check(getattr(settings, preference) != previous, "keyboard toggles " + preference)
            from kfps_ui.theme_catalog import THEME_PRESETS
            for preset in THEME_PRESETS:
                settings.theme = preset.name
                QTest.qWait(200)
                check(settings.theme == preset.name, "switch " + preset.name)
                check((find("ArchiveBackdrop") is not None) == (preset.name == "2049"), "theme unload/reload " + preset.name)
                wrapper = find("ThemedPageTransition")
                check(wrapper.property("contentOffsetX") == 0 and wrapper.property("contentOffsetY") == 0, "no offset after switching " + preset.name)
            settings.theme = "2049"
            QTest.qWait(200)
            check(find("ArchiveBackdrop") is not None, "2049 restored after catalog traversal")
            check(find("ApplicationWorkspace").isVisible(), "switch back releases previous dashboard")
            capture("settings-return")
            # Only the offscreen platform receives simulated activation.
            settings.reducedMotion = False
            settings.ambientMotion = True
            foreground = find("ArchiveForeground")
            backdrop = find("ArchiveBackdrop")
            if args.rhi:
                check("Direct3D11" in str(window.rendererInterface().graphicsApi()), "native D3D11 active")
                check(not window.isActive(), "native test does not take focus")
                check(not foreground.property("motionAllowed"), "native inactive animation stopped")
                check(not backdrop.property("motionAllowed"), "native inactive analog stopped")
                check(not window.findChild(QObject, "ArchiveAnalogSweepAnimation").property("running"), "native sweep animation stopped")
                check(not window.findChild(QObject, "ArchiveAnalogTrackingAnimation").property("running"), "native tracking animation stopped")
            else:
                settings.theme = "Night Blossom"
                QTest.qWait(150)
                window.requestActivate()
                QTest.qWait(120)
                check(window.isActive(), "offscreen window activated for motion")
                ticker = find("AnnouncementTicker")
                scroll = window.findChild(QObject, "TickerScrollAnimation")
                restart = window.findChild(QObject, "TickerRestartTimer")
                check(scroll is not None and restart is not None, "ticker animation found")
                check(scroll.property("running"), "active ticker scrolls")
                # Reproduce the delayed-restart race, then stop it through each real control.
                for preference in ("reducedMotion", "paused", "visible"):
                    QMetaObject.invokeMethod(ticker, "restartScroll")
                    check(restart.property("running"), "ticker restart queued " + preference)
                    if preference == "reducedMotion":
                        settings.reducedMotion = True
                    else:
                        ticker.setProperty(preference, preference != "visible")
                    QTest.qWait(120)
                    check(not restart.property("running") and not scroll.property("running"), "ticker pending restart cancelled " + preference)
                    if preference == "reducedMotion":
                        settings.reducedMotion = False
                    else:
                        ticker.setProperty(preference, preference == "visible")
                    deadline = time.perf_counter() + 2
                    while not scroll.property("running") and time.perf_counter() < deadline:
                        QTest.qWait(25)
                    check(ticker.property("motionAllowed") and scroll.property("running"), "ticker resumes " + preference)
                settings.theme = "2049"
                QTest.qWait(120)
                foreground = find("ArchiveForeground")
                backdrop = find("ArchiveBackdrop")
                check(foreground.property("motionAllowed"), "active ambient permitted")
                check(backdrop.property("motionAllowed"), "active analog permitted")
                first = foreground.property("scanPosition")
                sweep_first = backdrop.property("sweepPosition")
                QTest.qWait(180)
                check(first != foreground.property("scanPosition"), "edge reader moves")
                check(sweep_first != backdrop.property("sweepPosition"), "background scan moves")
                settings.ambientMotion = False
                stopped = foreground.property("scanPosition")
                stopped_sweep = backdrop.property("sweepPosition")
                QTest.qWait(120)
                check(stopped == foreground.property("scanPosition"), "ambient preference stops clock")
                check(stopped_sweep == backdrop.property("sweepPosition"), "ambient preference stops scan")
                check(not window.findChild(QObject, "ArchiveAnalogTrackingAnimation").property("running"), "ambient preference stops tracking")
                settings.ambientMotion = True
                controller.navigate("create")
                preview_live_status = settings.liveStatusVisible
                settings.liveStatusVisible = False
                QTest.mouseMove(window, QPoint(1, 1))
                QTest.qWait(2300)
                frames, positions, drift = [], [], []
                artwork = find("ArchiveArtworkSource")
                find("ArchiveWorkbenchScroll").property("contentItem").setProperty("contentY", 0)
                for _ in range(40):
                    shot = window.grabWindow()
                    point = artwork.mapToScene(artwork.boundingRect().center())
                    pixel = shot.pixelColor(round(point.x() * shot.width() / window.width()), round(point.y() * shot.height() / window.height()))
                    check(abs(pixel.red() - 210) < 5 and abs(pixel.green() - 40) < 5 and abs(pixel.blue() - 80) < 5, "active analog leaves artwork unchanged")
                    frame = fromqimage(shot).convert("RGB")
                    frame.thumbnail((1100, 700), Image.Resampling.LANCZOS)
                    frames.append(frame)
                    positions.append(backdrop.property("sweepPosition"))
                    drift.append(backdrop.property("trackingOffset"))
                    QTest.qWait(140)
                frames[0].save(run / "analog-idle.gif", save_all=True, append_images=frames[1:], duration=140, loop=0, optimize=False)
                check(max(positions) - min(positions) > 0.15, "scan crosses the background")
                check(max(abs(value) for value in drift) > 0.1, "raster registration drifts")
                check(ImageChops.difference(frames[0], frames[-1]).getbbox() is not None, "analog motion changes rendered pixels")
                measurements["analog_motion"] = {"sampled_frames": len(frames), "sweep_range": [min(positions), max(positions)], "tracking_range": [min(drift), max(drift)]}
                capture("analog-active")
                settings.liveStatusVisible = preview_live_status
                transition = find("ArchivePageTransition")
                controller.navigate("outputs")
                QTest.qWait(30)
                check(transition.property("progress") < 1, "record transition begins")
                check(transition.property("contentOffsetX") > 0, "actual content plate travels")
                capture("motion-early")
                frames = []
                for _ in range(16):
                    frame = fromqimage(window.grabWindow()).convert("RGB")
                    frame.thumbnail((1100, 700), Image.Resampling.LANCZOS)
                    frames.append(frame)
                    QTest.qWait(35)
                frames[0].save(run / "plate-motion.gif", save_all=True, append_images=frames[1:] + [frames[-1]], duration=[55] * 16 + [1100], loop=0, optimize=False)
                QTest.qWait(650)
                check(transition.property("progress") == 1, "transition completes")
                check(transition.property("contentOffsetX") == 0 and transition.property("contentOffsetY") == 0, "plate aligns exactly after sliding")
                capture("motion-complete")
                with Image.open(run / "motion-early.png") as early, Image.open(run / "motion-complete.png") as late:
                    check(ImageChops.difference(early.convert("RGB"), late.convert("RGB")).getbbox() is not None, "motion changes actual pixels")
                controller.navigate("settings")
                settings.reducedMotion = True
                QTest.qWait(20)
                check(transition.property("progress") == 1, "reduced motion interrupts transition")
                check(transition.property("contentOffsetX") == 0, "reduced motion immediately aligns content")
                check(not foreground.property("motionAllowed"), "reduced motion stops ambient")
                check(not backdrop.property("motionAllowed"), "reduced motion stops analog")
                check(not window.findChild(QObject, "ArchiveAnalogSweepAnimation").property("running"), "reduced motion stops sweep animation")
                check(not window.findChild(QObject, "ArchiveAnalogTrackingAnimation").property("running"), "reduced motion stops tracking animation")
                settings.reducedMotion = False
                for page in ("outputs", "settings", "create", "settings"):
                    controller.navigate(page)
                    QTest.qWait(20)
                QTest.qWait(650)
                check(transition.property("progress") == 1, "rapid navigation settles cleanly")
                window.showMinimized()
                QTest.qWait(100)
                check(not foreground.property("motionAllowed"), "minimized clock stopped")
                check(not backdrop.property("motionAllowed"), "minimized analog stopped")
                check(not scroll.property("running"), "minimized ticker stopped")
                window.showNormal()
                other = QWindow()
                other.resize(16, 16)
                other.show()
                other.requestActivate()
                QTest.qWait(100)
                check(not foreground.property("motionAllowed"), "inactive clock stopped")
                check(not backdrop.property("motionAllowed"), "inactive analog stopped")
                check(not scroll.property("running") and not restart.property("running"), "inactive ticker stopped")
                frozen = foreground.property("scanPosition")
                QTest.qWait(120)
                check(frozen == foreground.property("scanPosition"), "inactive clock stays frozen")
                other.close()
            settings.reducedMotion = True
            controller.navigate("create")
            QTest.qWait(300)
            wall, cpu = time.perf_counter(), time.process_time()
            QTest.qWait(1500)
            measurements["idle_cpu_seconds"] = time.process_time() - cpu
            measurements["idle_wall_seconds"] = time.perf_counter() - wall
            settings.save()
            check(json.loads(settings_path.read_text())["theme"] == "2049", "theme persisted in isolated profile")
            check(hashes() == before, "personal settings and version unchanged")
            # These font/scroll messages already occur in the frozen baseline.
            fatal = fatal_qml_messages()
            check(not fatal, "no new QML errors")
            click("TitleBarButton:close")
            check(not window.isVisible(), "native close works")
            app.exit(0)
        except Exception as error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
            app.exit(1)
        finally:
            report = {"checks": results, "messages": sorted(set(messages)), "measurements": measurements, "protected_unchanged": hashes() == before, "graphics_api": str(window.rendererInterface().graphicsApi())}
            (run / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"passed": sum(r.get("passed", False) for r in results), "failures": [r for r in results if r.get("passed") is False or "error" in r], "messages": sorted(set(messages)), "measurements": measurements}, indent=2))
    # Cold asynchronous QML incubation needs the normal event loop. Nested
    # QTest waits can starve it in an unexposed window, so qualify cold loads
    # here before the keyboard/mouse checks exercise the retained pages.
    routes = ("outputs", "liveries", "community", "editor", "tools", "support", "help", "update", "settings", "create")
    def prepare_routes(index=0):
        if index == len(routes):
            QTimer.singleShot(100, checks)
            return
        page = routes[index]
        controller.navigate(page)
        started = time.perf_counter()
        def poll():
            host = window.findChild(QObject, "CachedPageHost")
            errors = fatal_qml_messages()
            if errors or time.perf_counter() - started >= 10:
                failure = {"page": page, "wait_seconds": time.perf_counter() - started, "errors": errors, "cold_routes": cold_routes}
                (run / "preflight-failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
                print(json.dumps(failure, indent=2))
                window.close()
                app.exit(1)
                return
            if host is not None and host.property("currentPage") == page and host.property("item") is not None:
                cold_routes.append({"page": page, "ready": True, "seconds": time.perf_counter() - started})
                QTimer.singleShot(0, lambda: prepare_routes(index + 1))
            else:
                QTimer.singleShot(50, poll)
        QTimer.singleShot(50, poll)
    QTimer.singleShot(1200, prepare_routes)


module.install_development_harness = install
sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--allow-source-download", "--demo", "--theme-preview", "2049", "--width", str(args.width), "--height", str(args.height), "--page", "create"]
if args.rhi:
    sys.argv.append("--community-preview-background")
def timeout():
    (run / "timeout.txt").write_text("Test exceeded 180 seconds.\n" + "\n".join(messages[-100:]), encoding="utf-8")
    os._exit(124)
watchdog = threading.Timer(180, timeout)
watchdog.daemon = True
watchdog.start()
raise SystemExit(module.main())
