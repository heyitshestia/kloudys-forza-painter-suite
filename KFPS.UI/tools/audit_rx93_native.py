"""Opt-in interaction/motion checks against the real isolated native shell."""
from __future__ import annotations

import json
import math
import os
import statistics
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QWindow
from kfps_ui.development_harness import DevelopmentHarness


def install_audit(app, window, controller, community, settings, jsons, args):
    harness = DevelopmentHarness(app, window, controller, community, settings, jsons, args)
    target = Path(os.environ["KFPS_RX93_AUDIT"])
    target.mkdir(parents=True, exist_ok=True)
    report = {"checks": [], "samples": [], "errors": []}

    def check(condition, name):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def control(name):
        window.grabWindow()  # Polish lazy page layouts before using their hit-test geometry.
        return next(item for item in harness._visual_items() if item.isVisible() and item.isEnabled()
                    and item.width() > 1 and item.height() > 1 and item.objectName() == name)

    def theme_combo():
        window.grabWindow()
        candidates = [item for item in harness._visual_items() if item.isVisible() and item.width() > 1
                      and item.objectName() == "KfpsComboBox"]
        report["combo_probe"] = [{"text": item.property("currentText"), "display": item.property("displayText"),
            "index": item.property("currentIndex"), "x": item.mapToScene(QPointF()).x(), "y": item.mapToScene(QPointF()).y(),
            "tooltip": item.property("toolTipText")} for item in candidates]
        report["settings_theme"] = settings.theme
        return next(item for item in candidates if "color and surface style" in str(item.property("toolTipText")))

    def page_ready():
        host = window.findChild(QQuickItem, "CachedPageHost")
        started = time.perf_counter()
        for _ in range(300):
            expression = QQmlExpression(QQmlEngine.contextForObject(host), host, "Number(currentLoader.status)")
            status, _ = expression.evaluate()
            if status == 1:
                report.setdefault("page_loads", []).append({"page": controller.currentPage, "wait_s": round(time.perf_counter() - started, 3)})
                window.grabWindow()
                yield 100
                return
            window.requestUpdate()
            yield 50
        raise AssertionError("Page loader did not become Ready: " + controller.currentPage + ", status=" + str(status))

    def click(item):
        p = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        point = QPoint(round(p.x()), round(p.y()))
        QTest.mouseMove(window, point)
        yield 100
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
        yield 80
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
        yield 350

    def motion_state():
        backdrop = next(item for item in harness._visual_items() if item.objectName() == "rx93Foreground")
        return {"allowed": backdrop.property("motionAllowed"), "illumination": backdrop.property("carriage")}

    def dismiss_notices():
        for _ in range(5):
            yield 600
            notices = [item for item in harness._visual_items() if item.isVisible() and item.objectName().endswith("WelcomeGotIt")]
            if not notices:
                continue
            name = notices[0].objectName()
            yield from click(notices[0])
            check(not notices[0].isVisible(), "Acknowledge first-run notice: " + name)

    def sample(theme, moving):
        settings.theme = theme
        settings.reducedMotion = not moving
        settings.ambientMotion = moving
        window.raise_()
        window.requestActivate()
        yield 800
        swaps = []
        def frame():
            swaps.append(time.perf_counter())
        window.frameSwapped.connect(frame)
        cpu = time.process_time()
        wall = time.perf_counter()
        yield 3000
        elapsed = time.perf_counter() - wall
        used = time.process_time() - cpu
        window.frameSwapped.disconnect(frame)
        intervals = [(b - a) * 1000 for a, b in zip(swaps, swaps[1:])]
        report["samples"].append({"theme": theme, "motion": moving, "elapsed_s": round(elapsed, 3),
            "window_active": window.isActive(),
            "cpu_s": round(used, 4), "cpu_percent_one_core": round(used / elapsed * 100, 2),
            "presented_frames": len(swaps), "median_present_interval_ms": round(statistics.median(intervals), 3) if intervals else None})

    def run():
        try:
            window.requestActivate()
            settings.liveStatusVisible = False
            yield 500
            yield from dismiss_notices()
            original_size = window.size()
            for name in ("min", "max", "close"):
                button = control("TitleBarButton:" + name)
                origin = button.mapToScene(QPointF())
                check(0 <= origin.y() <= 3 and button.height() == 30,
                      "Window control lies in upper strip: " + name)
            yield from click(control("TitleBarButton:max"))
            check(window.visibility() == QWindow.Maximized, "Title-bar maximize click")
            yield from click(control("TitleBarButton:max"))
            check(window.visibility() == QWindow.Windowed and window.size() == original_size,
                  "Title-bar restore click preserves window size")
            yield from click(control("TitleBarButton:min"))
            check(window.visibility() == QWindow.Minimized, "Title-bar minimize click")
            window.showNormal()
            window.requestActivate()
            yield 350
            for page, label in (("outputs", "Outputs"), ("liveries", "Liveries"), ("community", "Community"),
                                ("editor", "Editor"), ("tools", "Tools"), ("help", "Help"), ("update", "Update"), ("settings", "Settings")):
                yield from click(control("NavButton:" + label))
                yield from page_ready()
                check(controller.currentPage == page, "Mouse navigation: " + label)
            combo = theme_combo()
            yield from click(combo)
            window.grabWindow().save(str(target / "theme-dropdown.png"))
            QTest.keyClick(window, Qt.Key_Home)
            yield 120
            QTest.keyClick(window, Qt.Key_Return)
            yield 450
            check(settings.theme == "Night Blossom", "Theme dropdown selects previous theme")
            yield from click(theme_combo())
            QTest.keyClick(window, Qt.Key_End)
            yield 120
            QTest.keyClick(window, Qt.Key_Return)
            yield 450
            check(settings.theme == "RX-93 Psycho-Frame", "Theme dropdown restores RX-93")
            from kfps_ui.settings_service import SettingsService
            check(SettingsService(settings._path).theme == "RX-93 Psycho-Frame", "Theme preference survives a fresh settings instance")
            settings.reducedMotion = False
            settings.ambientMotion = True
            window.raise_()
            window.requestActivate()
            yield 800
            start = motion_state()
            window.grabWindow().save(str(target / "motion-start.png"))
            # The carriage deliberately rests for eight seconds. Observe movement
            # within a bound rather than assuming every 50 ms timer fires on time.
            observations = []
            for _ in range(80):
                yield 250
                end = motion_state()
                observations.append(end)
                if end["allowed"] and abs(end["illumination"] - start["illumination"]) > 0.005:
                    break
            report["motion_probe"] = {"start": start, "end": end, "observations": observations,
                                     "window_active": window.isActive()}
            window.grabWindow().save(str(target / "motion-end.png"))
            check(start["allowed"] and end["allowed"] and abs(end["illumination"] - start["illumination"]) > 0.005, "Ambient animation advances in active window")
            yield from click(control("KfpsSwitch:Reduce nonessential motion"))
            first = motion_state()
            yield 650
            second = motion_state()
            check(settings.reducedMotion and not second["allowed"] and first["illumination"] == second["illumination"], "Reduced-motion switch stops animation")
            yield from click(control("KfpsSwitch:Reduce nonessential motion"))
            yield from click(control("KfpsSwitch:Ambient background motion"))
            check(not settings.ambientMotion and not motion_state()["allowed"], "Ambient toggle stops animation")
            settings.ambientMotion = True
            window.showMinimized()
            yield 350
            check(not motion_state()["allowed"], "Minimized window stops theme animation")
            window.showNormal()
            window.requestActivate()
            yield 350
            check(motion_state()["allowed"], "Animation resumes after restoring the window")
            yield from click(control("NavButton:Create"))
            check(controller.currentPage == "create", "Create route still works after theme switches")
            box = control("KfpsCheckBox:Detail heatmap")
            initial = box.property("checked")
            box.forceActiveFocus(Qt.TabFocusReason)
            QTest.keyClick(window, Qt.Key_Space)
            check(box.property("checked") != initial, "Checkbox supports keyboard activation")
            for theme in ("RX-93 Psycho-Frame", "Night Blossom"):
                for moving in (True, False):
                    yield from sample(theme, moving)
            settings.theme = "RX-93 Psycho-Frame"
            settings.reducedMotion = False
            settings.ambientMotion = True
            yield 400
            QTest.mouseMove(window, QPoint(2, round(window.height() / 2)))
            window.grabWindow().save(str(target / "verified-native.png"))
            app.setQuitOnLastWindowClosed(False)
            yield from click(control("TitleBarButton:close"))
            check(not window.isVisible(), "Title-bar close click")
        except Exception:
            window.grabWindow().save(str(target / "failure.png"))
            report["failure_page"] = controller.currentPage
            report["window_active"] = window.isActive()
            report["errors"].append(traceback.format_exc())
        finally:
            (target / "native-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            app.exit(1 if report["errors"] else 0)

    steps = run()
    def advance():
        try:
            delay = next(steps)
        except StopIteration:
            return
        QTimer.singleShot(delay, advance)
    QTimer.singleShot(1200, advance)
    return harness


def install_capture(app, window, controller, community, settings, jsons, args):
    """Capture only fully instantiated pages, not transient empty async loaders."""
    from kfps_ui.development_harness import AUDIT_PAGES
    harness = DevelopmentHarness(app, window, controller, community, settings, jsons, args)
    target = Path(args.screenshot_dir or Path(args.screenshot).parent)
    target.mkdir(parents=True, exist_ok=True)
    pages = AUDIT_PAGES if args.screenshot_dir else (args.page or "create",)
    records = []

    def advance(index):
        if index == len(pages):
            (target / "capture-readiness.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            app.exit(0)
            return
        page = pages[index]
        controller.navigate(page)
        started = time.perf_counter()
        def wait_ready():
            host = window.findChild(QQuickItem, "CachedPageHost")
            expression = QQmlExpression(QQmlEngine.contextForObject(host), host, "Number(currentLoader.status)")
            status, _ = expression.evaluate()
            if status == 1:
                QTimer.singleShot(500, capture)
            elif time.perf_counter() - started < 30 and status != 3:
                window.requestUpdate()
                QTimer.singleShot(50, wait_ready)
            else:
                print("Capture failed: page not ready", page, status, flush=True)
                app.exit(1)
        def capture():
            QTest.mouseMove(window, QPoint(2, round(window.height() / 2)))
            assets = 0
            for item in harness._visual_items():
                if not item.isVisible():
                    continue
                kind = item.metaObject().className()
                source = str(item.property("source"))
                if "Image" in kind and "rx93-psycho-frame" in source:
                    expression = QQmlExpression(QQmlEngine.contextForObject(item), item, "Number(status)")
                    status, _ = expression.evaluate()
                    if status != 1 or not math.isfinite(item.width()) or not math.isfinite(item.height()):
                        print("Unrenderable theme asset", source, status, flush=True)
                        app.exit(1)
                        return
                    assets += 1
            path = target / (page + ".png") if args.screenshot_dir else Path(args.screenshot)
            if not window.grabWindow().save(str(path)):
                app.exit(1)
                return
            if args.layout_report_dir:
                harness.write_layout_report(Path(args.layout_report_dir) / (page + ".json"))
            if args.layout_report:
                harness.write_layout_report(args.layout_report)
            records.append({"page": page, "ready": True, "verified_theme_assets": assets, "elapsed_s": round(time.perf_counter() - started, 3)})
            QTimer.singleShot(50, lambda: advance(index + 1))
        QTimer.singleShot(50, wait_ready)
    QTimer.singleShot(700, lambda: advance(0))
    return harness
