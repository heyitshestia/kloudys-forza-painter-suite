from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent
SRC = UI_ROOT / "src"
ROOT = UI_ROOT.parent
for item in (str(SRC), str(ROOT)):
    if item not in sys.path:
        sys.path.insert(0, item)

from PySide6.QtCore import QCoreApplication, QPointF, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow, QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from kfps_ui.app_controller import AppController
from kfps_ui.app_paths import AppPaths
from kfps_ui.announcement_service import AnnouncementService
from kfps_ui.changelog_service import ChangelogService
from kfps_ui.cgroup_library_service import CGroupLibraryService
from kfps_ui.desktop_service import DesktopService
from kfps_ui.editor_service import EditorService
from kfps_ui.generation_service import GenerationService
from kfps_ui.help_service import HelpService
from kfps_ui.json_service import JsonService
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
    return parser.parse_args()


def main():
    args = parse_args()
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

    logs = LogService()
    desktop = DesktopService(paths, logs)
    version = VersionService(paths.app_root / "VERSION", demo=args.demo)
    announcements = AnnouncementService(demo=args.demo)
    runtime = RuntimeService(demo=args.demo)
    preview = PreviewService(paths)
    source = SourceImageService(paths, desktop, logs)
    jsons = JsonService(paths, preview, desktop, logs, demo=args.demo)
    supporter = SupporterService(paths.app_root)
    if is_supporter_theme(settings.theme) and not supporter.unlocked:
        settings.theme = DEFAULT_THEME
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
