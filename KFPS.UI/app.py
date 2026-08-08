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

from PySide6.QtCore import QCoreApplication, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow, QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle
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
    if not os.environ.get("KFPS_QML_GRAPHICS"):
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
    QCoreApplication.setOrganizationName("Kloudy")
    QCoreApplication.setApplicationName("KFPS")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QQuickStyle.setStyle("Basic")
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
    generation = GenerationService(paths, logs)
    transfer = TransferService(paths, logs, jsons)
    editor = EditorService(paths, preview, desktop, logs)
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
        window.setPersistentGraphics(True)
        window.setPersistentSceneGraph(True)
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
    if args.page == "community" and (args.community_tab or args.community_scope or args.community_overlay):
        community_tab = {"browse": 0, "upload": 1, "profile": 2}.get(args.community_tab, 0)
        community_scope = {
            "featured": 0, "browse": 1, "handmade": 2, "toolmade": 3, "supporters": 4,
            "favorites": 5, "following": 6, "mine": 7,
        }.get(args.community_scope)

        def select_community_tab(attempt=0):
            page = window.findChild(QQuickItem, "CommunityPage")
            if page is not None:
                page.setProperty("activeTab", community_tab)
                if community_scope is not None:
                    community.setScopeIndex(community_scope)
                if args.community_overlay:
                    page.setProperty("testOverlay", args.community_overlay)
            elif attempt < 20:
                QTimer.singleShot(50, lambda: select_community_tab(attempt + 1))

        QTimer.singleShot(50, select_community_tab)

    interactive_prefixes = (
        "PrimaryButton:", "GhostButton:", "NavButton:",
        "KfpsTextField:", "KfpsTextArea:", "KfpsComboBox",
        "KfpsCheckBox:", "KfpsSwitch:", "KfpsSlider",
        "HoverCard:", "QuickActionRow:", "RecentJsonRow:",
        "HelpCategory:", "HelpTopic:", "JsonTile:", "Fm8CreatorRow:",
        "CommunityDetailPreview", "AnnouncementTicker", "TitleBarButton:",
        "SupporterPromo", "KfpsLinkText:",
    )

    def visual_items() -> list[QQuickItem]:
        root_item = window.contentItem()
        stack = [root_item]
        seen = set()
        items = []
        while stack:
            obj = stack.pop()
            identity = id(obj)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(obj)
            stack.extend(obj.childItems())
        return items

    def visible_interactive_items() -> list[QQuickItem]:
        items = []
        for obj in visual_items():
            name = obj.objectName() or ""
            if not name.startswith(interactive_prefixes):
                continue
            if not obj.isVisible() or obj.opacity() <= 0.01:
                continue
            items.append(obj)
        return items

    def qml_property(obj: QQuickItem, name: str, default=None):
        if obj.metaObject().indexOfProperty(name) < 0:
            return default
        value = obj.property(name)
        return default if value is None else value

    def interaction_state(obj: QQuickItem, names: tuple[str, ...]) -> tuple[bool, bool]:
        for name in names:
            if obj.metaObject().indexOfProperty(name) >= 0:
                return True, bool(obj.property(name))
        return False, False

    def scene_rect(obj: QQuickItem) -> QRectF:
        point = obj.mapToScene(QPointF(0, 0))
        return QRectF(float(point.x()), float(point.y()), float(obj.width()), float(obj.height()))

    def clipped_by_item_ancestor(obj: QQuickItem) -> bool:
        bounds = scene_rect(obj)
        ancestor = obj.parentItem()
        while ancestor is not None:
            if ancestor.clip():
                ancestor_bounds = scene_rect(ancestor)
                if not ancestor_bounds.contains(bounds):
                    return True
            ancestor = ancestor.parentItem()
        return False

    def write_layout_report(target_path: str) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        controls = []
        for obj in visible_interactive_items():
            name = obj.objectName() or ""
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
                "clippedByAncestor": clipped_by_item_ancestor(obj),
            })

        text_items = []
        for obj in visual_items():
            if not obj.isVisible() or obj.opacity() <= 0.01:
                continue
            text = qml_property(obj, "text")
            if text is None or not str(text).strip():
                continue
            painted_width = qml_property(obj, "paintedWidth")
            painted_height = qml_property(obj, "paintedHeight")
            if painted_width is None or painted_height is None:
                continue
            point = obj.mapToScene(QPointF(0, 0))
            width = float(obj.width())
            height = float(obj.height())
            text_items.append({
                "text": str(text)[:240],
                "class": obj.metaObject().className(),
                "x": round(float(point.x()), 2),
                "y": round(float(point.y()), 2),
                "width": round(width, 2),
                "height": round(height, 2),
                "paintedWidth": round(float(painted_width), 2),
                "paintedHeight": round(float(painted_height), 2),
                "truncated": bool(qml_property(obj, "truncated", False)),
                "overflowsOwnBounds": bool(
                    float(painted_width) > width + 1.0 or float(painted_height) > height + 1.0
                ),
            })
        payload = {
            "page": controller.currentPage,
            "window": {"width": window.width(), "height": window.height()},
            "devicePixelRatio": round(float(window.devicePixelRatio()), 3),
            "theme": settings.theme,
            "controls": controls,
            "textItems": text_items,
            "zeroSize": [item["name"] for item in controls if item["width"] < 1 or item["height"] < 1],
            "tooSmall": [item["name"] for item in controls if item["width"] < 18 or item["height"] < 18],
            "textOverflow": [item["text"] for item in text_items if item["overflowsOwnBounds"]],
            "truncatedText": [item["text"] for item in text_items if item["truncated"]],
        }
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.motion_capture_dir:
        motion_dir = Path(args.motion_capture_dir)
        motion_dir.mkdir(parents=True, exist_ok=True)
        frame_times = (700, 1050, 1450, 1950, 3450, 3650, 3950, 4400)
        motion_started = time.monotonic()
        motion_index = 0

        def capture_motion_frame():
            nonlocal motion_index
            scheduled_ms = frame_times[motion_index]
            elapsed_ms = round((time.monotonic() - motion_started) * 1000)
            image = window.grabWindow() if hasattr(window, "grabWindow") else app.primaryScreen().grabWindow(int(window.winId()))
            image.save(str(motion_dir / f"frame-{motion_index:02d}-{scheduled_ms:04d}ms.png"))
            motion_index += 1
            if motion_index >= len(frame_times):
                metadata = {
                    "page": controller.currentPage,
                    "window": {"width": window.width(), "height": window.height()},
                    "devicePixelRatio": round(float(window.devicePixelRatio()), 3),
                    "theme": settings.theme,
                    "scheduledMs": list(frame_times),
                    "lastElapsedMs": elapsed_ms,
                }
                (motion_dir / "motion.json").write_text(
                    json.dumps(metadata, indent=2), encoding="utf-8"
                )
                QTimer.singleShot(50, app.quit)
                return
            delay = frame_times[motion_index] - scheduled_ms
            QTimer.singleShot(delay, capture_motion_frame)

        QTimer.singleShot(frame_times[0], capture_motion_frame)
    elif args.interaction_capture_dir:
        interaction_dir = Path(args.interaction_capture_dir)
        interaction_dir.mkdir(parents=True, exist_ok=True)

        def capture_interactions():
            from PySide6.QtTest import QTest

            controls = sorted(
                visible_interactive_items(),
                key=lambda item: (
                    round(float(item.mapToScene(QPointF(0, 0)).y()), 2),
                    round(float(item.mapToScene(QPointF(0, 0)).x()), 2),
                    item.objectName() or "",
                ),
            )
            outside = QPoint(max(2, window.width() // 2), 3)
            manifest = {
                "page": controller.currentPage,
                "window": {"width": window.width(), "height": window.height()},
                "devicePixelRatio": round(float(window.devicePixelRatio()), 3),
                "theme": settings.theme,
                "controls": [],
            }

            def save_crop(path: Path, logical_rect: QRect) -> None:
                image = window.grabWindow()
                scale_x = image.width() / max(1, window.width())
                scale_y = image.height() / max(1, window.height())
                pixel_rect = QRect(
                    round(logical_rect.x() * scale_x),
                    round(logical_rect.y() * scale_y),
                    max(1, round(logical_rect.width() * scale_x)),
                    max(1, round(logical_rect.height() * scale_y)),
                )
                image.copy(pixel_rect).save(str(path))

            QTest.mouseMove(window, outside)
            QTest.qWait(120)
            for index, obj in enumerate(controls):
                name = obj.objectName() or f"control-{index + 1}"
                point = obj.mapToScene(QPointF(0, 0))
                x = round(float(point.x()))
                y = round(float(point.y()))
                width = max(1, round(float(obj.width())))
                height = max(1, round(float(obj.height())))
                fully_inside = (
                    x >= 0 and y >= 0 and x + width <= window.width() and y + height <= window.height()
                )
                safe_name = "-".join(
                    part for part in "".join(
                        character if character.isalnum() else " " for character in name
                    ).split() if part
                )[:80] or f"control-{index + 1}"
                control_dir = interaction_dir / f"{index + 1:03d}-{safe_name}"
                control_dir.mkdir(parents=True, exist_ok=True)
                padding = 14
                crop_x = max(0, x - padding)
                crop_y = max(0, y - padding)
                crop_right = min(window.width(), x + width + padding)
                crop_bottom = min(window.height(), y + height + padding)
                crop_rect = QRect(crop_x, crop_y, crop_right - crop_x, crop_bottom - crop_y)
                record = {
                    "name": name,
                    "class": obj.metaObject().className(),
                    "folder": control_dir.name,
                    "enabled": bool(obj.isEnabled()),
                    "auditAllowOutsideFeedback": bool(
                        qml_property(obj, "auditAllowOutsideFeedback", False)
                    ),
                    "fullyInsideWindow": fully_inside,
                    "bounds": {"x": x, "y": y, "width": width, "height": height},
                    "crop": {
                        "x": crop_x, "y": crop_y,
                        "width": crop_rect.width(), "height": crop_rect.height(),
                        "controlX": x - crop_x, "controlY": y - crop_y,
                    },
                    "states": [],
                }
                manifest["controls"].append(record)
                if not fully_inside:
                    continue

                QTest.mouseMove(window, outside)
                window.contentItem().forceActiveFocus(Qt.OtherFocusReason)
                QTest.qWait(140)
                idle_path = control_dir / "idle.png"
                save_crop(idle_path, crop_rect)
                record["states"].append("idle")

                center = QPoint(x + width // 2, y + height // 2)
                QTest.mouseMove(window, center)
                QTest.qWait(90)
                save_crop(control_dir / "hover-early.png", crop_rect)
                record["states"].append("hover-early")
                QTest.qWait(190)
                save_crop(control_dir / "hover.png", crop_rect)
                record["states"].append("hover")
                hover_available, hover_reached = interaction_state(
                    obj, ("hovered", "containsMouse")
                )
                record["hoverStateAvailable"] = hover_available
                record["hoverReached"] = hover_reached

                press_safe = not name.startswith("TitleBarButton:")
                if bool(obj.isEnabled()) and press_safe:
                    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, center)
                    QTest.qWait(90)
                    press_available, press_reached = interaction_state(
                        obj, ("down", "pressed")
                    )
                    record["pressStateAvailable"] = press_available
                    record["pressReached"] = press_reached
                    save_crop(control_dir / "pressed.png", crop_rect)
                    record["states"].append("pressed")
                    QTest.mouseMove(window, outside)
                    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, outside)
                    QTest.qWait(110)
                else:
                    QTest.mouseMove(window, outside)
                    QTest.qWait(80)

                focus_policy = int(qml_property(obj, "focusPolicy", 0) or 0)
                if bool(obj.isEnabled()) and focus_policy:
                    obj.forceActiveFocus(Qt.TabFocusReason)
                    QTest.qWait(130)
                    save_crop(control_dir / "focus.png", crop_rect)
                    record["states"].append("focus")

            (interaction_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            QTimer.singleShot(50, app.quit)

        QTimer.singleShot(900, capture_interactions)
    elif args.layout_report_dir or args.screenshot_dir:
        report_dir = Path(args.layout_report_dir) if args.layout_report_dir else None
        screenshot_dir = Path(args.screenshot_dir) if args.screenshot_dir else None
        if report_dir:
            report_dir.mkdir(parents=True, exist_ok=True)
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
        audit_pages = [
            "create", "outputs", "community", "editor", "tools", "support", "help",
            "update", "settings", "images", "reports", "credits",
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
    app.aboutToQuit.connect(community.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
