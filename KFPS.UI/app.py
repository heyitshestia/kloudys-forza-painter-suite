from __future__ import annotations

import argparse
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

from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from fh6_rtti_registry import refresh_runtime_registry
from kfps_ui.app_controller import AppController
from kfps_ui.app_paths import AppPaths
from kfps_ui.backup_service import BackupService
from kfps_ui.announcement_service import AnnouncementService
from kfps_ui.changelog_service import ChangelogService
from kfps_ui.cgroup_library_service import CGroupLibraryService
from kfps_ui.community_service import CommunityService
from kfps_ui.desktop_service import DesktopService
from kfps_ui.development_harness import install_development_harness
from kfps_ui.editor_service import EditorService
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.generation_service import GenerationService
from kfps_ui.help_service import HelpService
from kfps_ui.json_service import JsonService, build_startup_json_index_cache
from kfps_ui.json_thumbnail_worker import worker_command, worker_environment
from kfps_ui.log_service import LogService
from kfps_ui.preview_service import PreviewService
from kfps_ui.report_service import ReportService
from kfps_ui.renderer_policy import apply_renderer_policy, select_renderer_policy
from kfps_ui.runtime_service import RuntimeService
from kfps_ui.settings_service import SettingsService
from kfps_ui.source_download_guard import SourceDownloadGuardStatus, evaluate_source_download_guard
from kfps_ui.source_image_service import SourceImageService
from kfps_ui.supporter_service import SupporterService
from kfps_ui.theme_catalog import (
    DEFAULT_THEME,
    KNOWN_THEME_NAMES,
    is_supporter_theme,
    normalize_theme,
)
from kfps_ui.transfer_service import TransferService
from kfps_ui.update_service import UpdateService
from kfps_ui.version_service import VersionService
from kfps_ui.window_geometry import ScreenRect, calculate_window_placement


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot")
    parser.add_argument("--layout-report")
    parser.add_argument("--layout-report-dir")
    parser.add_argument("--screenshot-dir")
    parser.add_argument("--interaction-capture-dir", help=argparse.SUPPRESS)
    parser.add_argument("--motion-capture-dir", help=argparse.SUPPRESS)
    parser.add_argument("--motion-preview", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--page", default="create")
    parser.add_argument("--community-tab", choices=("browse", "upload", "profile"), help=argparse.SUPPRESS)
    parser.add_argument(
        "--community-scope",
        choices=("featured", "browse", "handmade", "toolmade", "supporters", "favorites", "following", "mine"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--community-overlay", choices=("login", "inspector", "supporter-unlock"), help=argparse.SUPPRESS)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--theme-preview", choices=sorted(KNOWN_THEME_NAMES), help=argparse.SUPPRESS)
    parser.add_argument("--terminal-green-text", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-unsupported-python", action="store_true")
    parser.add_argument("--allow-source-download", action="store_true", help=argparse.SUPPRESS)
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
    parser.add_argument("--thumbnail-worker-regenerate", action="store_true", help=argparse.SUPPRESS)
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
        progress("Saving the latest FH6 locator for offline use...", 1, 100)
        refresh_runtime_registry(paths.app_root)
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


def run_source_download_blocker(
    app: QApplication,
    paths: AppPaths,
    status: SourceDownloadGuardStatus,
    args,
    app_icon: QIcon,
) -> int:
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("assetRoot", QUrl.fromLocalFile(str(paths.asset_root.resolve())).toString())
    ctx.setContextProperty(
        "screenshotMode",
        bool(args.screenshot or args.screenshot_dir or args.interaction_capture_dir),
    )
    ctx.setContextProperty("sourceDownloadUrl", status.latest_release_url)
    ctx.setContextProperty("sourceDownloadReason", status.reason)
    ctx.setContextProperty("sourceDownloadDetails", status.details)
    ctx.setContextProperty("sourceDownloadOverrideHint", status.override_hint)

    qml = paths.qml_root / "SourceDownloadBlocker.qml"
    engine.addImportPath(str(paths.qml_root))
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        return 2

    window = engine.rootObjects()[0]
    if not app_icon.isNull() and hasattr(window, "setIcon"):
        window.setIcon(app_icon)
    window.setWidth(max(980, int(args.width or 1180)))
    window.setHeight(max(620, int(args.height or 720)))

    screenshot_target = None
    if args.screenshot:
        screenshot_target = Path(args.screenshot)
    elif args.screenshot_dir:
        screenshot_target = Path(args.screenshot_dir) / "wrong-download.png"
    if screenshot_target:
        screenshot_target.parent.mkdir(parents=True, exist_ok=True)

        def capture_blocker():
            try:
                image = window.grabWindow() if hasattr(window, "grabWindow") else app.primaryScreen().grabWindow(int(window.winId()))
                image.save(str(screenshot_target))
            finally:
                QTimer.singleShot(50, app.quit)

        def settle_blocker_capture():
            if hasattr(window, "grabWindow"):
                window.grabWindow()
            QTimer.singleShot(350, capture_blocker)

        QTimer.singleShot(5000, settle_blocker_capture)
    return app.exec()


def main():
    args = parse_args()
    if args.theme_preview and not args.demo:
        raise SystemExit("--theme-preview is available only with --demo.")
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
        if args.thumbnail_worker_regenerate:
            worker_args.append("--regenerate")
        return thumbnail_worker_main(worker_args)
    if sys.version_info[:2] != (3, 12) and not args.allow_unsupported_python:
        raise SystemExit("KFPS requires 64-bit Python 3.12. Use the bundled runtime.")
    renderer_policy = select_renderer_policy(os.environ)
    apply_renderer_policy(renderer_policy, os.environ)
    QCoreApplication.setOrganizationName("Kloudy")
    QCoreApplication.setApplicationName("KFPS")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QQuickStyle.setStyle("Basic")
    QtWebEngineQuick.initialize()
    app = QApplication(sys.argv[:1])
    app.setApplicationDisplayName("KFPS")

    paths = AppPaths.discover()
    icon_path = paths.asset_root / "kfps-logo.png"
    app_icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    source_guard = evaluate_source_download_guard(paths.app_root, allow=args.allow_source_download)
    if source_guard.blocked:
        return run_source_download_blocker(app, paths, source_guard, args, app_icon)
    settings = SettingsService(paths.settings_file)
    theme_preview = normalize_theme(args.theme_preview) if args.theme_preview else ""
    if theme_preview:
        settings._data["theme"] = theme_preview
    if args.terminal_green_text:
        settings._data["terminalGreenText"] = True
    if args.motion_capture_dir or args.motion_preview:
        settings._data["reducedMotion"] = False
        settings._data["ambientMotion"] = True
        settings._data["glassEffects"] = True
        settings._data["liveStatusVisible"] = True

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
    if renderer_policy.warning:
        logs.append(renderer_policy.warning, "warning")
    logs.append(
        f"QML renderer policy: {renderer_policy.name} ({renderer_policy.source})."
    )
    desktop = DesktopService(paths, logs)
    backup = BackupService(paths, settings, logs)
    version = VersionService(paths.app_root / "VERSION", demo=args.demo)
    announcements = AnnouncementService(demo=args.demo)
    runtime = RuntimeService(demo=args.demo)
    source = SourceImageService(paths, desktop, logs)
    jsons = JsonService(paths, preview, desktop, logs, demo=args.demo)
    community = CommunityService(
        paths, desktop, logs, jsons=jsons, app_version=version.localVersion, demo=args.demo,
    )
    supporter = SupporterService(paths.app_root)
    community.supporterEntitlementRequested.connect(supporter.requestCommunityEntitlement)
    supporter.communityEntitlementReady.connect(community.applySupporterEntitlement)
    community.supporterRepairRequested.connect(supporter.repairActivation)
    def sync_community_supporter_state():
        community.setLocalSupporterState(supporter.activationState, supporter.keyValid)
    supporter.changed.connect(sync_community_supporter_state)
    sync_community_supporter_state()
    def enforce_available_theme():
        if not theme_preview and is_supporter_theme(settings.theme) and not supporter.unlocked:
            settings.theme = DEFAULT_THEME

    enforce_available_theme()
    supporter.changed.connect(enforce_available_theme)
    cgroup_library = CGroupLibraryService(paths, preview, jsons, logs, supporter=supporter, demo=args.demo)
    full_livery = FullLiveryService(paths, logs, supporter=supporter, demo=args.demo)
    generation = GenerationService(paths, logs)
    generation.generatedOutputsChanged.connect(jsons.refreshGeneratedOutputs)
    transfer = TransferService(paths, logs, jsons)
    editor = EditorService(paths, preview, desktop, logs)
    editor.editorOutputsChanged.connect(jsons.refreshEditorOutputs)
    help_service = HelpService()
    reports = ReportService(paths, logs, version, settings)
    updates = UpdateService(paths, logs)
    controller = AppController()
    changelog = ChangelogService(paths.app_root / "CHANGELOG.md", auto_refresh=not args.demo)

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
        "backupService": backup,
        "sourceService": source,
        "jsonService": jsons,
        "communityService": community,
        "cgroupLibraryService": cgroup_library,
        "fullLiveryService": full_livery,
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
    ctx.setContextProperty(
        "screenshotMode",
        bool(args.screenshot or args.screenshot_dir or args.interaction_capture_dir),
    )
    ctx.setContextProperty("demoMode", args.demo)
    ctx.setContextProperty("themePreviewUnlocked", bool(theme_preview))

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
        window.setPersistentGraphics(renderer_policy.persistent_scene_graph)
        window.setPersistentSceneGraph(renderer_policy.persistent_scene_graph)
    except Exception:
        pass
    active_screen = QGuiApplication.screenAt(QCursor.pos()) or app.primaryScreen()
    ordered_screens = [active_screen] if active_screen is not None else []
    ordered_screens.extend(screen for screen in app.screens() if screen is not active_screen)
    screens = []
    for screen in ordered_screens:
        geometry = screen.availableGeometry()
        screens.append(ScreenRect(
            geometry.x(), geometry.y(), geometry.width(), geometry.height()
        ))
    placement = calculate_window_placement(
        screens,
        settings.window_geometry(),
        requested_width=args.width,
        requested_height=args.height,
    )
    window.setX(placement.x)
    window.setY(placement.y)
    window.setWidth(placement.width)
    window.setHeight(placement.height)

    persist_window_state = args.width is None and args.height is None and not args.demo
    normal_geometry = {
        "x": placement.x,
        "y": placement.y,
        "width": placement.width,
        "height": placement.height,
    }
    window_state = {"maximized": placement.maximized}

    def remember_normal_geometry(*_args):
        if window.visibility() != QWindow.Windowed:
            return
        normal_geometry.update({
            "x": int(window.x()),
            "y": int(window.y()),
            "width": int(window.width()),
            "height": int(window.height()),
        })

    def remember_window_state(visibility):
        if visibility == QWindow.Maximized:
            window_state["maximized"] = True
        elif visibility == QWindow.Windowed:
            window_state["maximized"] = False
            remember_normal_geometry()

    def save_window_state():
        settings.save_window_geometry(
            normal_geometry["x"],
            normal_geometry["y"],
            normal_geometry["width"],
            normal_geometry["height"],
            window_state["maximized"],
        )

    if persist_window_state:
        window.xChanged.connect(remember_normal_geometry)
        window.yChanged.connect(remember_normal_geometry)
        window.widthChanged.connect(remember_normal_geometry)
        window.heightChanged.connect(remember_normal_geometry)
        window.visibilityChanged.connect(remember_window_state)
        app.aboutToQuit.connect(save_window_state)

    controller.navigate(args.page)
    if placement.maximized and persist_window_state:
        window.showMaximized()
    else:
        window.show()
    development_harness = install_development_harness(
        app, window, controller, community, settings, args,
    )
    shutdown_order = [
        editor,
        transfer,
        generation,
        full_livery,
        cgroup_library,
        community,
        supporter,
        jsons,
        runtime,
        backup,
        changelog,
        announcements,
        version,
        logs,
    ]
    shutdown_started = False

    def shutdown_services():
        nonlocal shutdown_started
        if shutdown_started:
            return
        shutdown_started = True
        for service in shutdown_order:
            close = getattr(service, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    print(f"KFPS shutdown warning ({type(service).__name__}): {exc}", file=sys.stderr)

    app.aboutToQuit.connect(shutdown_services)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
