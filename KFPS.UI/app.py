from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent
SRC = UI_ROOT / "src"
ROOT = UI_ROOT.parent
for item in (str(SRC), str(ROOT)):
    if item not in sys.path:
        sys.path.insert(0, item)

from PySide6.QtCore import QCoreApplication, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow, QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from kfps_ui.app_controller import AppController
from kfps_ui.app_paths import AppPaths
from kfps_ui.announcement_service import AnnouncementService
from kfps_ui.changelog_service import ChangelogService
from kfps_ui.cgroup_library_service import CGroupLibraryService
from kfps_ui.desktop_service import DesktopService
from kfps_ui.editor_service import EditorService
from kfps_ui.generation_service import GenerationService
from kfps_ui.help_service import HelpService
from kfps_ui.json_service import JsonService, build_startup_json_index_cache
from kfps_ui.json_thumbnail_worker import worker_command, worker_environment
from kfps_ui.log_service import LogService
from kfps_ui.preview_service import PreviewService
from kfps_ui.report_service import ReportService
from kfps_ui.runtime_service import RuntimeService
from kfps_ui.settings_service import SettingsService
from kfps_ui.source_image_service import SourceImageService
from kfps_ui.supporter_service import SupporterService
from kfps_ui.theme_catalog import DEFAULT_THEME, is_supporter_theme
from kfps_ui.transfer_service import TransferService
from kfps_ui.update_service import UpdateService
from kfps_ui.version_service import VersionService


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot")
    parser.add_argument("--layout-report")
    parser.add_argument("--layout-report-dir")
    parser.add_argument("--screenshot-dir")
    parser.add_argument("--page", default="create")
    parser.add_argument("--width", type=int, default=1760)
    parser.add_argument("--height", type=int, default=1040)
    parser.add_argument("--ui-scale", type=float)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--allow-unsupported-python", action="store_true")
    parser.add_argument("--skip-startup-index", action="store_true")
    parser.add_argument("--skip-startup-thumbnails", action="store_true")
    parser.add_argument("--thumbnail-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-app-root", help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-ui-root", help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-runtime-root", help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-cache-file", help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-max-seconds", type=float, default=0.0, help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-max-items", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--thumbnail-worker-preferred-source", help=argparse.SUPPRESS)
    return parser.parse_args()


def _startup_thumbnail_seconds() -> float:
    raw = os.environ.get("KFPS_STARTUP_THUMBNAIL_SECONDS", "5")
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        seconds = 5.0
    return max(0.0, min(300.0, seconds))


def _run_startup_thumbnail_worker(app: QApplication, paths: AppPaths, progress, max_seconds: float) -> int:
    cmd = worker_command(paths, cache_file=paths.runtime_root / "json-browser-index.v1.json", max_seconds=max_seconds, app_executable=sys.executable)
    kwargs = {
        "cwd": str(UI_ROOT),
        "env": worker_environment(paths),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    started = time.monotonic()
    proc = subprocess.Popen(cmd, **kwargs)
    progress("Rendering missing thumbnails in a separate room...", 5, 100)
    hard_limit = max_seconds + 12.0 if max_seconds > 0 else 0.0
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        if hard_limit and elapsed >= hard_limit:
            proc.kill()
            proc.communicate(timeout=2)
            progress("Thumbnail worker got stuck making tiny posters. Opening anyway.", 100, 100)
            return 0
        if max_seconds > 0:
            done = min(95, 5 + int((min(elapsed, max_seconds) / max_seconds) * 90.0))
        else:
            done = 50
        progress("Rendering missing thumbnails in a separate room...", done, 100)
        app.processEvents()
        time.sleep(0.05)
    stdout, stderr = proc.communicate(timeout=2)
    if proc.returncode != 0:
        progress("Thumbnail worker misplaced its notes. Opening with the cache we have.", 100, 100)
        return 0
    try:
        return max(0, int((stdout or "0").strip().splitlines()[-1]))
    except (IndexError, TypeError, ValueError):
        return 0


def run_startup_output_index(
    app: QApplication,
    paths: AppPaths,
    preview: PreviewService,
    show_splash: bool = True,
    warm_thumbnails: bool = False,
    thumbnail_seconds: float = 45.0,
) -> None:
    splash = None
    title = None
    detail = None
    bar = None
    splash_started = time.monotonic()
    bits = [
        "Counting rectangles with a clipboard held upside down.",
        "Asking the JSON pile to stand in one suspiciously straight line.",
        "Putting tiny name tags on vinyl files.",
        "Checking under the sofa for missing layer counts.",
        "Polishing the progress bar with a napkin.",
    ]

    if show_splash:
        splash = QWidget()
        splash.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        splash.setFixedSize(520, 220)
        splash.setStyleSheet("""
            QWidget {
                background: #190516;
                border: 3px solid #ff4bac;
                color: #ffd6ee;
                font-family: Segoe UI;
            }
            QLabel#Title {
                color: #ff5fba;
                font-size: 23px;
                font-weight: 800;
            }
            QLabel#Detail {
                color: #ffeaf6;
                font-size: 12px;
            }
            QLabel#Footnote {
                color: #c68aaa;
                font-size: 10px;
            }
            QProgressBar {
                border: 2px solid #713055;
                border-radius: 0px;
                background: #080208;
                color: #ffffff;
                text-align: center;
                height: 22px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background: #ff3da6;
            }
        """)
        layout = QVBoxLayout(splash)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("PLEASE STAND BY: THE JSONS ARE PUTTING ON SHOES")
        title.setObjectName("Title")
        title.setWordWrap(True)
        detail = QLabel(bits[0])
        detail.setObjectName("Detail")
        detail.setWordWrap(True)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(3)
        foot = QLabel("Crude loading rectangle v1. It has one job and a questionable attitude.")
        foot.setObjectName("Footnote")
        foot.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(bar)
        layout.addWidget(foot)
        splash.show()
        app.processEvents()

    def progress(message: str, done: int, total: int):
        if not splash:
            return
        pct = int(max(0, min(100, (float(done) / max(1, float(total))) * 100.0)))
        if detail:
            detail.setText(f"{message}\n{bits[done % len(bits)]}")
        if bar:
            bar.setValue(max(3, pct))
        app.processEvents()

    try:
        build_startup_json_index_cache(paths, preview=preview, progress=progress)
        progress("Output library has been bullied into a cache file.", 100, 100)
        if warm_thumbnails:
            count = _run_startup_thumbnail_worker(app, paths, progress, thumbnail_seconds)
            noun = "thumbnail" if count == 1 else "thumbnails"
            progress(f"Thumbnail cache warmed with {count} new {noun}.", 100, 100)
    except Exception:
        progress("Index preflight tripped over its own shoelaces. Opening anyway.", 100, 100)
    finally:
        if splash:
            while time.monotonic() - splash_started < 5.0:
                app.processEvents()
                time.sleep(0.05)
            splash.close()
            app.processEvents()


def main():
    args = parse_args()
    if args.thumbnail_worker:
        from kfps_ui.json_thumbnail_worker import main as thumbnail_worker_main
        worker_args = [
            "--app-root",
            str(args.thumbnail_worker_app_root or ""),
            "--ui-root",
            str(args.thumbnail_worker_ui_root or ""),
            "--runtime-root",
            str(args.thumbnail_worker_runtime_root or ""),
            "--max-seconds",
            str(args.thumbnail_worker_max_seconds or 0.0),
        ]
        if args.thumbnail_worker_cache_file:
            worker_args.extend(["--cache-file", str(args.thumbnail_worker_cache_file)])
        if args.thumbnail_worker_max_items:
            worker_args.extend(["--max-items", str(args.thumbnail_worker_max_items)])
        if args.thumbnail_worker_preferred_source is not None:
            worker_args.extend(["--preferred-source", str(args.thumbnail_worker_preferred_source)])
        return thumbnail_worker_main(worker_args)
    if sys.version_info[:2] != (3, 12) and not args.allow_unsupported_python:
        raise SystemExit("KFPS requires 64-bit Python 3.12. Use the bundled runtime.")
    if not os.environ.get("KFPS_QML_GRAPHICS"):
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
    QCoreApplication.setOrganizationName("Kloudy")
    QCoreApplication.setApplicationName("KFPS")
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv[:1])
    app.setApplicationDisplayName("KFPS")

    paths = AppPaths.discover()
    icon_path = paths.asset_root / "kfps-logo.png"
    app_icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    settings = SettingsService(paths.settings_file)
    if args.ui_scale is not None:
        settings._data["uiScale"] = max(0.80, min(1.35, float(args.ui_scale)))

    preview = PreviewService(paths)
    should_preindex = not args.skip_startup_index and not args.demo and os.environ.get("KFPS_SKIP_STARTUP_INDEX", "").strip() != "1"
    show_splash = should_preindex and not (args.screenshot or args.screenshot_dir or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen")
    should_warm_thumbnails = (
        show_splash
        and not args.skip_startup_thumbnails
        and os.environ.get("KFPS_SKIP_STARTUP_THUMBNAILS", "").strip() != "1"
    )
    if should_preindex:
        run_startup_output_index(
            app,
            paths,
            preview,
            show_splash=show_splash,
            warm_thumbnails=should_warm_thumbnails,
            thumbnail_seconds=_startup_thumbnail_seconds(),
        )

    logs = LogService()
    desktop = DesktopService(paths, logs)
    version = VersionService(paths.app_root / "VERSION", demo=args.demo)
    announcements = AnnouncementService(demo=args.demo)
    runtime = RuntimeService(demo=args.demo)
    source = SourceImageService(paths, desktop, logs)
    jsons = JsonService(paths, preview, desktop, logs, demo=args.demo)
    supporter = SupporterService(paths.app_root)
    def enforce_available_theme():
        if is_supporter_theme(settings.theme) and not supporter.unlocked:
            settings.theme = DEFAULT_THEME

    enforce_available_theme()
    supporter.changed.connect(enforce_available_theme)
    cgroup_library = CGroupLibraryService(paths, preview, jsons, logs, supporter=supporter, demo=args.demo)
    generation = GenerationService(paths, logs)
    transfer = TransferService(paths, logs, jsons)
    editor = EditorService(paths, preview, desktop, logs)
    help_service = HelpService()
    reports = ReportService(paths, logs, version, settings)
    updates = UpdateService(paths, logs)
    controller = AppController()
    changelog = ChangelogService(paths.app_root / "CHANGELOG.md")

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    objects = {
        "appController": controller,
        "settings": settings,
        "logs": logs,
        "versionService": version,
        "announcementService": announcements,
        "runtimeService": runtime,
        "desktop": desktop,
        "sourceService": source,
        "jsonService": jsons,
        "cgroupLibraryService": cgroup_library,
        "generationService": generation,
        "transferService": transfer,
        "editorService": editor,
        "helpService": help_service,
        "reportService": reports,
        "updateService": updates,
        "supporterService": supporter,
        "changelogService": changelog,
    }
    for name, obj in objects.items():
        ctx.setContextProperty(name, obj)
    ctx.setContextProperty("assetRoot", QUrl.fromLocalFile(str(paths.asset_root.resolve())).toString())
    ctx.setContextProperty("screenshotMode", bool(args.screenshot or args.screenshot_dir))
    ctx.setContextProperty("demoMode", args.demo)

    qml = paths.qml_root / "Main.qml"
    engine.addImportPath(str(paths.qml_root))
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        return 2
    window = engine.rootObjects()[0]
    if not app_icon.isNull() and hasattr(window, "setIcon"):
        window.setIcon(app_icon)
    try:
        # Keep the scene graph alive while minimized so long-running import/export
        # jobs can finish without the restored UI rebuilding under log updates.
        window.setPersistentGraphics(True)
        window.setPersistentSceneGraph(True)
    except Exception:
        pass
    window.setWidth(args.width)
    window.setHeight(args.height)
    controller.navigate(args.page)

    def write_layout_report(target_path: str) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        prefixes = (
            "PrimaryButton:", "GhostButton:", "NavButton:",
            "KfpsTextField:", "KfpsTextArea:", "KfpsComboBox",
            "KfpsCheckBox:", "KfpsSwitch:", "KfpsSlider",
        )
        controls = []
        for obj in window.findChildren(QQuickItem):
            name = obj.objectName() or ""
            if not name.startswith(prefixes) or not obj.isVisible() or obj.opacity() <= 0.01:
                continue
            point = obj.mapToScene(QPointF(0, 0))
            width = float(obj.width())
            height = float(obj.height())
            x = float(point.x())
            y = float(point.y())
            controls.append({
                "name": name,
                "class": obj.metaObject().className(),
                "x": round(x, 2),
                "y": round(y, 2),
                "width": round(width, 2),
                "height": round(height, 2),
                "enabled": bool(obj.isEnabled()),
                "intersectsWindow": bool(x + width > 0 and y + height > 0 and x < window.width() and y < window.height()),
                "fullyInsideWindow": bool(x >= -0.5 and y >= -0.5 and x + width <= window.width() + 0.5 and y + height <= window.height() + 0.5),
            })
        payload = {
            "page": controller.currentPage,
            "window": {"width": window.width(), "height": window.height()},
            "uiScale": settings.uiScale,
            "theme": settings.theme,
            "controls": controls,
            "zeroSize": [item["name"] for item in controls if item["width"] < 1 or item["height"] < 1],
            "tooSmall": [item["name"] for item in controls if item["width"] < 18 or item["height"] < 18],
        }
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.layout_report_dir or args.screenshot_dir:
        report_dir = Path(args.layout_report_dir) if args.layout_report_dir else None
        screenshot_dir = Path(args.screenshot_dir) if args.screenshot_dir else None
        if report_dir:
            report_dir.mkdir(parents=True, exist_ok=True)
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
        audit_pages = [
            "create", "outputs", "editor", "help", "settings",
            "tools", "images", "reports", "update",
        ]
        audit_index = 0

        def audit_next_page():
            nonlocal audit_index
            if audit_index >= len(audit_pages):
                QTimer.singleShot(50, app.quit)
                return
            page = audit_pages[audit_index]
            controller.navigate(page)

            def save_current_page():
                nonlocal audit_index
                if screenshot_dir:
                    image = window.grabWindow() if hasattr(window, "grabWindow") else app.primaryScreen().grabWindow(int(window.winId()))
                    image.save(str(screenshot_dir / f"{page}.png"))
                if report_dir:
                    write_layout_report(str(report_dir / f"{page}.json"))
                audit_index += 1
                QTimer.singleShot(110, audit_next_page)

            QTimer.singleShot(620 if screenshot_dir else 360, save_current_page)

        QTimer.singleShot(700, audit_next_page)
    elif args.screenshot or args.layout_report:
        screenshot_target = Path(args.screenshot) if args.screenshot else None
        if screenshot_target:
            screenshot_target.parent.mkdir(parents=True, exist_ok=True)

        def capture_and_report():
            try:
                if screenshot_target:
                    image = window.grabWindow() if hasattr(window, "grabWindow") else app.primaryScreen().grabWindow(int(window.winId()))
                    image.save(str(screenshot_target))
                if args.layout_report:
                    write_layout_report(args.layout_report)
            finally:
                QTimer.singleShot(50, app.quit)

        QTimer.singleShot(1700 if screenshot_target else 650, capture_and_report)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
