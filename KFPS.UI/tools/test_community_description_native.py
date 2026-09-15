"""Check real Community description layout with isolated data and no network."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "windows" if "--native-window" in sys.argv else "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"

from PySide6.QtCore import QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient
from kfps_ui.full_livery_service import FullLiveryService
import app as application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--theme", default="Windows 94")
    parser.add_argument("--native-window", action="store_true")
    parser.add_argument("--baseline", action="store_true", help="Record the existing clipping without requiring a pass")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {"theme": args.theme, "cases": [], "errors": [], "qml_errors": [], "screenshots": []}

    def messages(kind, context, message):
        if any(term in message for term in ("ReferenceError", "TypeError", "Cannot assign", "Binding loop")):
            result["qml_errors"].append(message)

    with tempfile.TemporaryDirectory(prefix="kfps-description-layout-") as temporary:
        isolated = Path(temporary)
        shutil.copy2(ROOT / "VERSION", isolated / "VERSION")
        paths = AppPaths(isolated, UI, UI / "qml", UI / "assets", isolated / "runtime", Path(sys.executable))

        def install(app, window, controller, community, settings, jsons, app_args):
            if args.native_window:
                window.setFlag(Qt.WindowDoesNotAcceptFocus, True)
                window.show()
                window.lower()

            def items():
                pending = [window.contentItem()]
                while pending:
                    item = pending.pop()
                    yield item
                    pending.extend(item.childItems())

            def evaluate(item, expression):
                expr = QQmlExpression(QQmlEngine.contextForObject(item), item, expression)
                value, _ = expr.evaluate()
                assert not expr.hasError(), expr.error().toString()
                return value.toVariant() if hasattr(value, "toVariant") else value

            def scroll_for(text):
                item = text.parentItem()
                while item:
                    if "ScrollView" in item.metaObject().className():
                        return item
                    item = item.parentItem()
                raise AssertionError("Description is not in a scroll view")

            def capture(name):
                target = out / f"{name}.png"
                assert window.grabWindow().save(str(target))
                result["screenshots"].append(target.name)

            def steps():
                try:
                    controller.navigate("community")
                    yield 800
                    page = next(item for item in items() if item.objectName() == "CommunityPage")
                    community._selected_index = 0
                    sample = {
                        "id": "local-description-test", "title": "Community description test",
                        "creatorName": "LayoutTest", "shapeCount": 87, "usesMasks": True,
                        "classificationLabel": "Handmade", "category": "Motorsport",
                        "schemaLabel": "KFPS-compatible JSON", "schemaKnown": True,
                        "license": "kfps-community-share-v1", "gamesText": "FM8",
                        "tagsText": "Bathurst, V8 Supercars, 2006, Holden, HRT",
                        "statusLabel": "Published", "downloads": 1, "favorites": 0,
                    }
                    descriptions = {
                        "long-english": "The side details from a racing livery. Masking used, including a gradient layer to approximate the original shading. " * 5,
                        "korean": "\uc774 \ub3c4\uc548\uc740 \ub9c8\uc2a4\ud06c\uc640 \uadf8\ub77c\ub370\uc774\uc158\uc744 \uc0ac\uc6a9\ud569\ub2c8\ub2e4. \uac00\uc838\uc624\uae30 \uc804\uc5d0 \uc124\uba85\uc744 \ub05d\uae4c\uc9c0 \ud655\uc778\ud574 \uc8fc\uc138\uc694. " * 8,
                        "unbroken": "W" * 600,
                        "paragraphs": "First paragraph.\n\n" + "More details to read. " * 100 + "\nLast line.",
                        "literal-markup": "<b>Keep this literal</b> <img src='missing-local-test-image.png'> " * 10,
                        "short": "A short description.",
                        "empty": "",
                    }
                    sizes = ((960, 600), (1440, 900), (1920, 1080))
                    for width, height in sizes:
                        window.resize(width, height)
                        yield 250
                        for name, description in descriptions.items():
                            community._selected = {**sample, "description": description}
                            community._rows = [community._selected]
                            community.changed.emit()
                            yield 120
                            for view in ("detail", "inspector"):
                                if view == "inspector":
                                    evaluate(page, "artworkInspector.open()")
                                    yield 160
                                expected_text = description or "No description was provided."
                                descriptions_found = [item for item in items() if item.isVisible()
                                                      and item.property("text") == expected_text]
                                assert descriptions_found, (name, view, "description missing")
                                # The inspector is reparented into the top-level overlay.
                                text = descriptions_found[0] if view == "detail" else next(
                                    item for item in descriptions_found
                                    if item not in detail_items)
                                if view == "detail":
                                    detail_items = descriptions_found
                                scroll = scroll_for(text)
                                if not args.baseline:
                                    position = scroll.mapToScene(QPointF(0, scroll.height() / 2))
                                    if not 0 <= position.y() < window.height():
                                        owner = "browseScroll" if view == "detail" else "inspectorBodyScroll"
                                        evaluate(page, f"{owner}.contentItem.contentY = Math.max(0, {owner}.contentHeight - {owner}.availableHeight)")
                                        yield 120
                                evaluate(scroll, "contentItem.contentY = 0")
                                yield 60
                                metrics = evaluate(scroll, "({width:width, available:availableWidth, content:contentWidth, contentHeight:contentHeight, height:availableHeight})")
                                next_items = [item for item in text.parentItem().childItems()
                                              if item.isVisible() and str(item.property("text") or "").startswith("Tags:")]
                                assert len(next_items) == 1
                                tags = next_items[0]
                                fits = text.width() <= metrics["available"] + 1 and float(text.property("contentWidth")) <= text.width() + 1
                                ordered = tags.y() >= text.y() + text.height() - 1
                                record = {"size": [window.width(), window.height()], "case": name, "view": view,
                                          "scroll": metrics, "text_width": text.width(), "text_height": text.height(),
                                          "lines": text.property("lineCount"), "fits": fits, "following_text_below": ordered}
                                result["cases"].append(record)
                                if name in ("long-english", "korean") and width == 1440:
                                    capture(f"{name}-{view}")
                                if not args.baseline:
                                    assert fits and ordered, record
                                    assert abs(metrics["content"] - metrics["available"]) <= 1, record
                                    if name not in ("short", "empty"):
                                        assert text.property("lineCount") > 1, record
                                    if name == "literal-markup":
                                        assert evaluate(text, "textFormat === Text.PlainText")
                                    if name == "paragraphs" and metrics["contentHeight"] > metrics["height"]:
                                        pos = scroll.mapToScene(QPointF(scroll.width() / 2, scroll.height() / 2))
                                        for _ in range(5):
                                            QGuiApplication.sendEvent(window, QWheelEvent(
                                                pos, QPointF(window.mapToGlobal(pos.toPoint())), QPointF(0, 0).toPoint(),
                                                QPointF(0, -120).toPoint(), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
                                            yield 45
                                        record["wheel_content_y"] = evaluate(scroll, "contentItem.contentY")
                                        assert record["wheel_content_y"] > 0, record
                                        evaluate(scroll, "contentItem.contentY = Math.max(0, contentHeight - availableHeight)")
                                        yield 60
                                        tag_position = tags.mapToScene(QPointF())
                                        bottom = scroll.mapToScene(QPointF(0, scroll.height())).y()
                                        assert tag_position.y() < bottom, record
                                if view == "inspector":
                                    evaluate(page, "artworkInspector.close()")
                                    yield 80
                            if not args.baseline:
                                evaluate(page, "browseScroll.contentItem.contentY = 0")
                    result["passed"] = not args.baseline or all(case["fits"] for case in result["cases"])
                except Exception:
                    result["errors"].append(traceback.format_exc())
                    capture("failure")
                finally:
                    app.exit(int(bool(result["errors"] or result["qml_errors"])))

            iterator = steps()

            def advance():
                try:
                    delay = next(iterator)
                except StopIteration:
                    return
                QTimer.singleShot(delay, advance)

            QTimer.singleShot(700, advance)

        sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", args.theme,
                    "--screenshot", str(out / "capture-mode.png"), "--skip-startup-index",
                    "--skip-startup-thumbnails", "--width", "1440", "--height", "900"]
        previous = qInstallMessageHandler(messages)
        try:
            with patch.object(AppPaths, "discover", return_value=paths), \
                    patch.object(FullLiveryService, "scanSaves"), \
                    patch.object(FullLiveryService, "refreshPackages"), \
                    patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
                    patch.object(CommunityApiClient, "json", side_effect=AssertionError("Unexpected network request")), \
                    patch.object(application, "install_development_harness", side_effect=install):
                code = application.main()
        finally:
            qInstallMessageHandler(previous)
    (out / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({"cases": len(result["cases"]), "errors": result["errors"],
                      "qml_errors": result["qml_errors"], "clipped": sum(not c["fits"] for c in result["cases"])}, indent=2))
    return code or int(bool(result["errors"] or result["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
