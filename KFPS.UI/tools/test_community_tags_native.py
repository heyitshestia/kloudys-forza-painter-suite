"""Exercise the actual Community page offline with an isolated native app profile."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
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

from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QKeyEvent, QInputMethodEvent, QWheelEvent
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient
from kfps_ui.community_validation import inspect_upload
from kfps_ui.full_livery_service import FullLiveryService
import app as application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--theme", default="Night Blossom")
    parser.add_argument("--native-window", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = {"cases": [], "errors": [], "qml_errors": [], "screenshots": [], "requests": []}

    def messages(kind, context, message):
        if "CommunityTagPicker.qml" in message:
            results["qml_errors"].append(message)
            return
        if any(token in message for token in (
            "ReferenceError", "TypeError", "Cannot assign", "Binding loop", "is not a type", "unavailable",
        )):
            results["qml_errors"].append(message)

    with tempfile.TemporaryDirectory(prefix="kfps-community-tags-") as temporary:
        isolated = Path(temporary)
        shutil.copy2(ROOT / "VERSION", isolated / "VERSION")
        paths = AppPaths(isolated, UI, UI / "qml", UI / "assets", isolated / "runtime", Path(sys.executable))
        fixture = isolated / "tag-test.json"
        fixture.write_text(json.dumps({"shapes": [
            {"type": 16, "color": [225, 130, 70, 255], "data": [512, 512, 300, 120, 0]},
            {"type": 16, "color": [20, 220, 180, 255], "data": [420, 440, 80, 160, 340]},
        ]}), encoding="utf-8")

        def install(app, window, controller, community, settings, jsons, app_args):
            if args.native_window:
                window.setFlag(Qt.WindowDoesNotAcceptFocus, True)
                window.show()
                window.lower()
            def items():
                pending = [window.contentItem()]
                found = []
                while pending:
                    item = pending.pop()
                    found.append(item)
                    pending.extend(item.childItems())
                return found

            def find(name):
                item = None
                for _ in range(30):
                    item = next((i for i in items() if i.objectName() == name), None)
                    if item is not None:
                        break
                    window.requestUpdate()
                    window.grabWindow()
                    QTest.qWait(50)
                assert item is not None, "Missing native item: " + name
                return item

            def evaluate(item, expression):
                context_item = find(item.objectName() + ":search") if item.objectName() in {
                    "CommunityUploadTags", "CommunityEditTags",
                } else item
                expr = QQmlExpression(QQmlEngine.contextForObject(context_item), item, expression)
                value, undefined = expr.evaluate()
                assert not expr.hasError(), expr.error().toString()
                return value.toVariant() if hasattr(value, "toVariant") else value

            def click(item):
                window.requestUpdate()
                window.grabWindow()
                QTest.qWait(120)
                if isinstance(item, str):
                    item = find(item)
                assert item.isEnabled() and item.isVisible(), "Disabled or hidden: " + item.objectName()
                pos = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
                assert 0 <= pos.x() < window.width() and 0 <= pos.y() < window.height(), item.objectName()
                QTest.mouseMove(window, pos.toPoint())
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y())))

            def enter(item, value, *, commit=True, ime=False):
                click(item)
                QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
                QTest.keyClick(window, Qt.Key_Backspace)
                if ime:
                    event = QInputMethodEvent()
                    event.setCommitString(value)
                    QGuiApplication.sendEvent(window.focusObject(), event)
                else:
                    for char in value:
                        QGuiApplication.sendEvent(window, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, char))
                        QGuiApplication.sendEvent(window, QKeyEvent(QEvent.KeyRelease, 0, Qt.NoModifier, char))
                if commit:
                    QTest.keyClick(window, Qt.Key_Return)

            def capture(name):
                QTest.mouseMove(window, QPoint(3, 3))
                target = out / (name + ".png")
                assert window.grabWindow().save(str(target))
                results["screenshots"].append(target.name)

            def api(endpoint, method="GET", payload=None, **kwargs):
                results["requests"].append({"endpoint": endpoint, "method": method, "tags": (payload or {}).get("tags")})
                return {}

            def steps():
                try:
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(CommunityApiClient, "json", side_effect=api))
                        stack.enter_context(patch.object(community, "_submit", side_effect=lambda operation, fn: fn()))
                        controller.navigate("community")
                        yield 600
                        page = find("CommunityPage")
                        page.setProperty("activeTab", 1)
                        community._upload_inspection = inspect_upload(fixture, paths.runtime_root)
                        community.changed.emit()
                        yield 400
                        picker = find("CommunityUploadTags")
                        prefix = picker.objectName()
                        search = prefix + ":search"
                        evaluate(page, "uploadScroll.contentItem.contentY = Math.max(0, uploadTags.y - 60)")
                        yield 250
                        click(search)
                        yield 200
                        assert evaluate(picker, "options.visible")
                        assert find(prefix + ":choices").property("count") == len(community.suggestedTags)
                        click(prefix + ":expand")
                        yield 100
                        assert not evaluate(picker, "options.visible")
                        click(prefix + ":expand")
                        yield 100
                        assert evaluate(picker, "options.visible")
                        QTest.keyClick(window, Qt.Key_Tab)
                        yield 100
                        assert not evaluate(picker, "options.visible")
                        click(search)
                        yield 100
                        click(prefix + ":choice:anime")
                        yield 200
                        assert picker.property("text") == "anime"
                        assert find(prefix + ":chip:anime").mapToScene(QPointF()).y() < find(search).mapToScene(QPointF()).y()
                        capture("upload-tag-bank")
                        results["cases"].append("Click opens a scrollable bank; selected tag locks into a removable chip above the input")

                        choices = find(prefix + ":choices")
                        for _ in range(30):
                            pos = choices.mapToScene(QPointF(choices.width() / 2, choices.height() / 2))
                            QTest.mouseMove(window, pos.toPoint())
                            QGuiApplication.sendEvent(window, QWheelEvent(pos, QPointF(window.mapToGlobal(pos.toPoint())),
                                QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
                            yield 35
                        yield 1000
                        assert float(choices.property("contentY")) > 100
                        assert not choices.property("moving")
                        click(prefix + ":choice:track")
                        yield 150
                        assert picker.property("text") == "anime, track"
                        QTest.keyClick(window, Qt.Key_Escape)
                        click(prefix + ":remove:track")
                        yield 150
                        results["cases"].append("Mouse wheel reaches the end of the tag bank; selecting the final suggestion and removing it works")

                        enter(search, "race day")
                        yield 150
                        assert picker.property("text") == "anime, race day"
                        enter(search, "ANIME")
                        yield 100
                        assert picker.property("text") == "anime, race day"
                        enter(search, "\ud55c\uad6d\uc5b4", ime=True)
                        yield 150
                        assert picker.property("text") == "anime, race day, \ud55c\uad6d\uc5b4"
                        results["cases"].append("Custom Enter entry, case-insensitive deduplication and Korean IME commit")

                        enter(search, "ret", commit=False)
                        yield 120
                        assert evaluate(picker, "choices.map(function(row) { return row.tag })") == ["retro", "ret"]
                        QTest.keyClick(window, Qt.Key_Down)
                        QTest.keyClick(window, Qt.Key_Return)
                        yield 150
                        assert "retro" in picker.property("text") and ", ret," not in picker.property("text")
                        enter(search, "custom phrase", commit=False)
                        yield 80
                        click(prefix + ":choice:custom phrase")
                        yield 100
                        assert "custom phrase" in picker.property("text")
                        QTest.keyClick(window, Qt.Key_Escape)
                        yield 80
                        assert not evaluate(picker, "options.visible")
                        click(prefix + ":remove:race day")
                        yield 120
                        assert "race day" not in picker.property("text")
                        results["cases"].append("Filtered keyboard choice, custom dropdown choice, Escape and individual X removal")

                        before = picker.property("text")
                        for invalid in ("a" * 25, "#bad", "valid, bad/tag"):
                            enter(search, invalid)
                            yield 100
                            assert picker.property("text") == before
                            assert picker.property("errorText")
                            assert find(search).property("text") == invalid
                        capture("invalid-tag-feedback")
                        results["cases"].append("Overlong and invalid tags report errors; failed multi-tag additions are atomic")

                        enter(search, "", commit=False)
                        clipboard = QGuiApplication.clipboard()
                        original_clipboard = clipboard.text()
                        try:
                            clipboard.setText("racing, patterns, logos, drift, space, track")
                            QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier)
                            QTest.keyClick(window, Qt.Key_Return)
                        finally:
                            clipboard.setText(original_clipboard)
                        yield 150
                        assert len(picker.property("text").split(", ")) == 10
                        enter(search, "eleventh")
                        yield 100
                        assert len(picker.property("text").split(", ")) == 10 and picker.property("errorText")
                        enter(search, "ANIME")
                        yield 100
                        assert not picker.property("errorText")
                        assert not find(prefix + ":choice:abstract").isEnabled()
                        capture("ten-tags")
                        click(prefix + ":remove:anime")
                        yield 100
                        enter(search, "replacement")
                        yield 100
                        assert len(picker.property("text").split(", ")) == 10
                        results["cases"].append("Ten-tag limit, duplicate at capacity, disabled new suggestions, removal and replacement")

                        evaluate(picker, 'reset("")')
                        yield 150
                        enter(search, "pending", commit=False)
                        evaluate(page, 'resetMetadataForNewUpload("C:/test/another.json")')
                        yield 120
                        assert picker.property("text") == "" and find(search).property("text") == ""
                        assert not evaluate(picker, "options.visible")
                        results["cases"].append("Changing upload resets pending text even when no tags were committed")

                        enter(search, "#invalid", commit=False)
                        evaluate(page, 'uploadTitle.text = "Native tag test"; uploadCategory.currentIndex = 1; '
                                       'uploadClassification = "handmade"; rightsConfirmation.checked = true; '
                                       'compatibilityConfirmation.checked = true; '
                                       'uploadScroll.contentItem.contentY = uploadScroll.contentItem.contentHeight - uploadScroll.contentItem.height')
                        yield 150
                        request_count = len(results["requests"])
                        click("PrimaryButton:Upload Artwork")
                        yield 150
                        assert len(results["requests"]) == request_count and picker.property("errorText")
                        assert find(search).mapToScene(QPointF()).y() < window.height()
                        results["cases"].append("Invalid pending upload tag blocks the network request and brings the input back into view")

                        enter(search, "anime, racing")
                        yield 100
                        enter(search, "last tag", commit=False)
                        evaluate(page, 'uploadTitle.text = "Native tag test"; uploadCategory.currentIndex = 1; '
                                       'uploadClassification = "handmade"; rightsConfirmation.checked = true; '
                                       'compatibilityConfirmation.checked = true; '
                                       'uploadScroll.contentItem.contentY = uploadScroll.contentItem.contentHeight - uploadScroll.contentItem.height')
                        yield 250
                        click("PrimaryButton:Upload Artwork")
                        yield 150
                        assert results["requests"][-1]["tags"] == ["anime", "racing", "last tag"]
                        assert results["requests"][-1]["method"] == "POST"
                        results["cases"].append("Real Upload Artwork click includes pending custom text in the unchanged API tag array; request intercepted locally")

                        community._scope = "mine"
                        community._selected = {"id": "local-only", "title": "Local tag test", "creatorName": community.username,
                                               "tagsText": "anime, custom saved", "category": "Characters", "classification": "handmade"}
                        community.changed.emit()
                        evaluate(page, "editTagsDialog.open()")
                        yield 250
                        edit = find("CommunityEditTags")
                        edit_search = "CommunityEditTags:search"
                        assert edit.property("text") == "anime, custom saved"
                        click("CommunityEditTags:remove:anime")
                        enter(edit_search, "retro", commit=False)
                        click("PrimaryButton:Save Tags")
                        yield 150
                        assert results["requests"][-1]["method"] == "PATCH"
                        assert results["requests"][-1]["tags"] == ["custom saved", "retro"]
                        evaluate(page, "editTagsDialog.open()")
                        yield 150
                        enter(edit_search, "#invalid", commit=False)
                        count = len(results["requests"])
                        click("PrimaryButton:Save Tags")
                        yield 100
                        assert evaluate(page, "editTagsDialog.visible") and len(results["requests"]) == count
                        QTest.keyClick(window, Qt.Key_Escape)
                        yield 150
                        assert evaluate(page, "editTagsDialog.visible") and not evaluate(edit, "options.visible")
                        click("GhostButton:Cancel")
                        yield 150
                        evaluate(page, "editTagsDialog.open()")
                        yield 150
                        assert edit.property("text") == "anime, custom saved" and find(edit_search).property("text") == ""
                        capture("edit-tags")
                        results["cases"].append("Edit tags loads existing custom tags; Save includes pending entry; invalid Save stays open; Cancel/reopen discards edits")

                        evaluate(page, "editTagsDialog.close(); prepareRevision()")
                        yield 150
                        assert picker.property("text") == "anime, custom saved"
                        evaluate(page, 'revisionNote.text = "Synthetic revision test"; rightsConfirmation.checked = true; '
                                       'compatibilityConfirmation.checked = true; '
                                       'uploadScroll.contentItem.contentY = Math.max(0, uploadTags.y - 60)')
                        yield 150
                        enter(search, "revision tag", commit=False)
                        evaluate(page, 'uploadScroll.contentItem.contentY = uploadScroll.contentItem.contentHeight - uploadScroll.contentItem.height')
                        yield 150
                        click("PrimaryButton:Submit Revision")
                        yield 150
                        assert results["requests"][-1]["endpoint"] == "artworks/local-only/revisions"
                        assert results["requests"][-1]["tags"] == ["anime", "custom saved", "revision tag"]
                        results["cases"].append("Revision restores saved tags and submits pending additions through the original revision API")

                        evaluate(page, "editTagsDialog.open()")
                        yield 150

                        for width, height in ((960, 600), (1920, 1080)):
                            window.resize(width, height)
                            yield 250
                            long_tags = ["W" * 23 + str(i) for i in range(9)] + ["\ud55c" * 24]
                            evaluate(edit, 'reset("' + ", ".join(long_tags) + '")')
                            yield 150
                            click(edit_search)
                            yield 150
                            capture(f"edit-tags-{width}x{height}")
                            bounds = evaluate(edit, "({y: options.contentItem.mapToItem(null, 0, 0).y, height: options.contentItem.height})")
                            assert bounds["y"] >= -1 and bounds["y"] + bounds["height"] <= window.height() + 1, bounds
                            assert find("PrimaryButton:Save Tags").mapToScene(QPointF()).y() < window.height()
                            QTest.keyClick(window, Qt.Key_Escape)
                            yield 100
                            capture(f"edit-tags-chips-{width}x{height}")
                        results["cases"].append("Ten longest tags and dropdown remain usable in compact and wide native windows")
                except Exception:
                    results["errors"].append(traceback.format_exc())
                    capture("failure")
                finally:
                    app.exit(int(bool(results["errors"] or results["qml_errors"])))

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
    (out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=True))
    return code or int(bool(results["errors"] or results["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
