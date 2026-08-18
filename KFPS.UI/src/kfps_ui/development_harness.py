from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtQuick import QQuickItem


INTERACTIVE_PREFIXES = (
    "PrimaryButton:", "GhostButton:", "NavButton:",
    "KfpsTextField:", "KfpsTextArea:", "KfpsComboBox",
    "KfpsCheckBox:", "KfpsSwitch:", "KfpsSlider",
    "HoverCard:", "QuickActionRow:", "RecentJsonRow:",
    "HelpCategory:", "HelpTopic:", "JsonTile:", "Fm8CreatorRow:",
    "CommunityDetailPreview", "AnnouncementTicker", "TitleBarButton:",
    "SupporterPromo", "KfpsLinkText:",
)

AUDIT_PAGES = (
    "create", "outputs", "liveries", "community", "editor", "tools",
    "support", "help", "update", "settings", "images", "reports", "credits",
)


class DevelopmentHarness:
    """Owns opt-in screenshot, layout, motion, and interaction capture flows."""

    def __init__(self, app, window, controller, community, settings, args):
        self.app = app
        self.window = window
        self.controller = controller
        self.community = community
        self.settings = settings
        self.args = args
        self._motion_index = 0
        self._motion_started = 0.0
        self._audit_index = 0

    def install(self) -> None:
        self._configure_community_test_state()
        if self.args.motion_capture_dir:
            self._start_motion_capture(Path(self.args.motion_capture_dir))
        elif self.args.interaction_capture_dir:
            target = Path(self.args.interaction_capture_dir)
            target.mkdir(parents=True, exist_ok=True)
            QTimer.singleShot(900, lambda: self._capture_interactions(target))
        elif self.args.layout_report_dir or self.args.screenshot_dir:
            report_dir = Path(self.args.layout_report_dir) if self.args.layout_report_dir else None
            screenshot_dir = Path(self.args.screenshot_dir) if self.args.screenshot_dir else None
            for target in (report_dir, screenshot_dir):
                if target:
                    target.mkdir(parents=True, exist_ok=True)
            QTimer.singleShot(700, lambda: self._audit_next_page(report_dir, screenshot_dir))
        elif self.args.screenshot or self.args.layout_report:
            screenshot = Path(self.args.screenshot) if self.args.screenshot else None
            if screenshot:
                screenshot.parent.mkdir(parents=True, exist_ok=True)
            delay = 1700 if screenshot else 650
            QTimer.singleShot(delay, lambda: self._capture_single(screenshot, self.args.layout_report))

    def _configure_community_test_state(self) -> None:
        args = self.args
        if args.page != "community" or not (args.community_tab or args.community_scope or args.community_overlay):
            return
        active_tab = {"browse": 0, "upload": 1, "profile": 2}.get(args.community_tab, 0)
        scope = {
            "featured": 0, "browse": 1, "handmade": 2, "toolmade": 3,
            "supporters": 4, "favorites": 5, "following": 6, "mine": 7,
        }.get(args.community_scope)

        def select(attempt=0):
            page = self.window.findChild(QQuickItem, "CommunityPage")
            if page is not None:
                page.setProperty("activeTab", active_tab)
                if scope is not None:
                    self.community.setScopeIndex(scope)
                if args.community_overlay:
                    page.setProperty("testOverlay", args.community_overlay)
            elif attempt < 20:
                QTimer.singleShot(50, lambda: select(attempt + 1))

        QTimer.singleShot(50, select)

    def _visual_items(self) -> list[QQuickItem]:
        stack = [self.window.contentItem()]
        seen: set[int] = set()
        items: list[QQuickItem] = []
        while stack:
            item = stack.pop()
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(item)
            stack.extend(item.childItems())
        return items

    def _visible_interactive_items(self) -> list[QQuickItem]:
        return [
            item for item in self._visual_items()
            if (item.objectName() or "").startswith(INTERACTIVE_PREFIXES)
            and item.isVisible()
            and item.opacity() > 0.01
        ]

    @staticmethod
    def _qml_property(item: QQuickItem, name: str, default=None):
        if item.metaObject().indexOfProperty(name) < 0:
            return default
        value = item.property(name)
        return default if value is None else value

    @staticmethod
    def _interaction_state(item: QQuickItem, names: tuple[str, ...]) -> tuple[bool, bool]:
        for name in names:
            if item.metaObject().indexOfProperty(name) >= 0:
                return True, bool(item.property(name))
        return False, False

    @staticmethod
    def _scene_rect(item: QQuickItem) -> QRectF:
        point = item.mapToScene(QPointF(0, 0))
        return QRectF(float(point.x()), float(point.y()), float(item.width()), float(item.height()))

    def _clipped_by_item_ancestor(self, item: QQuickItem) -> bool:
        bounds = self._scene_rect(item)
        ancestor = item.parentItem()
        while ancestor is not None:
            if ancestor.clip() and not self._scene_rect(ancestor).contains(bounds):
                return True
            ancestor = ancestor.parentItem()
        return False

    def write_layout_report(self, target_path: str | Path) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        controls = []
        for item in self._visible_interactive_items():
            point = item.mapToScene(QPointF(0, 0))
            x, y = float(point.x()), float(point.y())
            width, height = float(item.width()), float(item.height())
            controls.append({
                "name": item.objectName() or "",
                "class": item.metaObject().className(),
                "x": round(x, 2), "y": round(y, 2),
                "width": round(width, 2), "height": round(height, 2),
                "enabled": bool(item.isEnabled()),
                "intersectsWindow": bool(
                    x + width > 0 and y + height > 0
                    and x < self.window.width() and y < self.window.height()
                ),
                "fullyInsideWindow": bool(
                    x >= -0.5 and y >= -0.5
                    and x + width <= self.window.width() + 0.5
                    and y + height <= self.window.height() + 0.5
                ),
                "clippedByAncestor": self._clipped_by_item_ancestor(item),
            })

        text_items = []
        for item in self._visual_items():
            if not item.isVisible() or item.opacity() <= 0.01:
                continue
            text = self._qml_property(item, "text")
            painted_width = self._qml_property(item, "paintedWidth")
            painted_height = self._qml_property(item, "paintedHeight")
            if text is None or not str(text).strip() or painted_width is None or painted_height is None:
                continue
            point = item.mapToScene(QPointF(0, 0))
            width, height = float(item.width()), float(item.height())
            text_items.append({
                "text": str(text)[:240],
                "class": item.metaObject().className(),
                "x": round(float(point.x()), 2), "y": round(float(point.y()), 2),
                "width": round(width, 2), "height": round(height, 2),
                "paintedWidth": round(float(painted_width), 2),
                "paintedHeight": round(float(painted_height), 2),
                "truncated": bool(self._qml_property(item, "truncated", False)),
                "overflowsOwnBounds": bool(
                    float(painted_width) > width + 1.0 or float(painted_height) > height + 1.0
                ),
            })

        payload = {
            "page": self.controller.currentPage,
            "window": {"width": self.window.width(), "height": self.window.height()},
            "devicePixelRatio": round(float(self.window.devicePixelRatio()), 3),
            "theme": self.settings.theme,
            "controls": controls,
            "textItems": text_items,
            "zeroSize": [item["name"] for item in controls if item["width"] < 1 or item["height"] < 1],
            "tooSmall": [item["name"] for item in controls if item["width"] < 18 or item["height"] < 18],
            "textOverflow": [item["text"] for item in text_items if item["overflowsOwnBounds"]],
            "truncatedText": [item["text"] for item in text_items if item["truncated"]],
        }
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _grab_window(self):
        if hasattr(self.window, "grabWindow"):
            return self.window.grabWindow()
        return self.app.primaryScreen().grabWindow(int(self.window.winId()))

    def _start_motion_capture(self, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        self._motion_index = 0
        self._motion_started = time.monotonic()
        QTimer.singleShot(700, lambda: self._capture_motion_frame(target))

    def _capture_motion_frame(self, target: Path) -> None:
        frame_times = (700, 1050, 1450, 1950, 3450, 3650, 3950, 4400)
        scheduled_ms = frame_times[self._motion_index]
        elapsed_ms = round((time.monotonic() - self._motion_started) * 1000)
        self._grab_window().save(str(target / f"frame-{self._motion_index:02d}-{scheduled_ms:04d}ms.png"))
        self._motion_index += 1
        if self._motion_index >= len(frame_times):
            metadata = {
                "page": self.controller.currentPage,
                "window": {"width": self.window.width(), "height": self.window.height()},
                "devicePixelRatio": round(float(self.window.devicePixelRatio()), 3),
                "theme": self.settings.theme,
                "scheduledMs": list(frame_times),
                "lastElapsedMs": elapsed_ms,
            }
            (target / "motion.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            QTimer.singleShot(50, self.app.quit)
            return
        delay = frame_times[self._motion_index] - scheduled_ms
        QTimer.singleShot(delay, lambda: self._capture_motion_frame(target))

    def _save_crop(self, target: Path, logical_rect: QRect) -> None:
        image = self.window.grabWindow()
        scale_x = image.width() / max(1, self.window.width())
        scale_y = image.height() / max(1, self.window.height())
        pixel_rect = QRect(
            round(logical_rect.x() * scale_x), round(logical_rect.y() * scale_y),
            max(1, round(logical_rect.width() * scale_x)),
            max(1, round(logical_rect.height() * scale_y)),
        )
        image.copy(pixel_rect).save(str(target))

    def _capture_interactions(self, target: Path) -> None:
        from PySide6.QtTest import QTest

        controls = sorted(
            self._visible_interactive_items(),
            key=lambda item: (
                round(float(item.mapToScene(QPointF(0, 0)).y()), 2),
                round(float(item.mapToScene(QPointF(0, 0)).x()), 2),
                item.objectName() or "",
            ),
        )
        outside = QPoint(max(2, self.window.width() // 2), 3)
        manifest = {
            "page": self.controller.currentPage,
            "window": {"width": self.window.width(), "height": self.window.height()},
            "devicePixelRatio": round(float(self.window.devicePixelRatio()), 3),
            "theme": self.settings.theme,
            "controls": [],
        }
        QTest.mouseMove(self.window, outside)
        QTest.qWait(120)
        for index, item in enumerate(controls):
            name = item.objectName() or f"control-{index + 1}"
            point = item.mapToScene(QPointF(0, 0))
            x, y = round(float(point.x())), round(float(point.y()))
            width, height = max(1, round(float(item.width()))), max(1, round(float(item.height())))
            fully_inside = (
                x >= 0 and y >= 0 and x + width <= self.window.width()
                and y + height <= self.window.height()
            )
            safe_name = "-".join(
                part for part in "".join(
                    character if character.isalnum() else " " for character in name
                ).split() if part
            )[:80] or f"control-{index + 1}"
            control_dir = target / f"{index + 1:03d}-{safe_name}"
            control_dir.mkdir(parents=True, exist_ok=True)
            padding = 14
            crop_x, crop_y = max(0, x - padding), max(0, y - padding)
            crop_right = min(self.window.width(), x + width + padding)
            crop_bottom = min(self.window.height(), y + height + padding)
            crop_rect = QRect(crop_x, crop_y, crop_right - crop_x, crop_bottom - crop_y)
            record = {
                "name": name,
                "class": item.metaObject().className(),
                "folder": control_dir.name,
                "enabled": bool(item.isEnabled()),
                "auditAllowOutsideFeedback": bool(self._qml_property(item, "auditAllowOutsideFeedback", False)),
                "fullyInsideWindow": fully_inside,
                "bounds": {"x": x, "y": y, "width": width, "height": height},
                "crop": {
                    "x": crop_x, "y": crop_y, "width": crop_rect.width(), "height": crop_rect.height(),
                    "controlX": x - crop_x, "controlY": y - crop_y,
                },
                "states": [],
            }
            manifest["controls"].append(record)
            if not fully_inside:
                continue
            QTest.mouseMove(self.window, outside)
            self.window.contentItem().forceActiveFocus(Qt.OtherFocusReason)
            QTest.qWait(140)
            self._save_crop(control_dir / "idle.png", crop_rect)
            record["states"].append("idle")
            center = QPoint(x + width // 2, y + height // 2)
            QTest.mouseMove(self.window, center)
            QTest.qWait(90)
            self._save_crop(control_dir / "hover-early.png", crop_rect)
            record["states"].append("hover-early")
            QTest.qWait(190)
            self._save_crop(control_dir / "hover.png", crop_rect)
            record["states"].append("hover")
            available, reached = self._interaction_state(item, ("hovered", "containsMouse"))
            record["hoverStateAvailable"], record["hoverReached"] = available, reached
            if item.isEnabled() and not name.startswith("TitleBarButton:"):
                QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, center)
                QTest.qWait(90)
                available, reached = self._interaction_state(item, ("down", "pressed"))
                record["pressStateAvailable"], record["pressReached"] = available, reached
                self._save_crop(control_dir / "pressed.png", crop_rect)
                record["states"].append("pressed")
                QTest.mouseMove(self.window, outside)
                QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, outside)
                QTest.qWait(110)
            else:
                QTest.mouseMove(self.window, outside)
                QTest.qWait(80)
            if item.isEnabled() and int(self._qml_property(item, "focusPolicy", 0) or 0):
                item.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(130)
                self._save_crop(control_dir / "focus.png", crop_rect)
                record["states"].append("focus")
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        QTimer.singleShot(50, self.app.quit)

    def _audit_next_page(self, report_dir: Path | None, screenshot_dir: Path | None) -> None:
        if self._audit_index >= len(AUDIT_PAGES):
            QTimer.singleShot(50, self.app.quit)
            return
        page = AUDIT_PAGES[self._audit_index]
        self.controller.navigate(page)

        def save_current_page():
            if screenshot_dir:
                self._grab_window().save(str(screenshot_dir / f"{page}.png"))
            if report_dir:
                self.write_layout_report(report_dir / f"{page}.json")
            self._audit_index += 1
            QTimer.singleShot(110, lambda: self._audit_next_page(report_dir, screenshot_dir))

        QTimer.singleShot(620 if screenshot_dir else 360, save_current_page)

    def _capture_single(self, screenshot: Path | None, report: str | None) -> None:
        try:
            if screenshot:
                self._grab_window().save(str(screenshot))
            if report:
                self.write_layout_report(report)
        finally:
            QTimer.singleShot(50, self.app.quit)


def install_development_harness(app, window, controller, community, settings, args) -> DevelopmentHarness:
    harness = DevelopmentHarness(app, window, controller, community, settings, args)
    harness.install()
    return harness
