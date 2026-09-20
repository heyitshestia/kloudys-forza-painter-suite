from __future__ import annotations

import json
import traceback
import time
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QPointF, Qt, QEvent, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlEngine, QQmlExpression

QML_ERRORS = []


def run_theme_checks(app, window, service, state, errors):
    """Exercise every registered theme without a nested QTest event loop."""
    from kfps_ui.theme_catalog import THEME_PRESETS

    engine = QQmlEngine.contextForObject(window).engine()
    result = {"passed": False, "qml_errors": errors, "screenshots": [], "cases": []}
    engine.incubationController().incubateFor(100)
    cases = [(preset.name, width, height, language) for preset in THEME_PRESETS
             for width, height, language in ((1760, 1040, "en"), (1280, 800, "en"), (1000, 660, "ko"))]
    case_index = 0
    ready_deadline = 0.0

    def find(name):
        queue = [window.contentItem()]
        while queue:
            item = queue.pop()
            if item.objectName() == name:
                return item
            queue.extend(item.childItems())
        raise AssertionError("Missing control: " + name)

    def evaluate(code, item=None):
        page = item if item is not None else find("CommunityPreviewPage")
        expression = QQmlExpression(QQmlEngine.contextForObject(page), page, code)
        value, _ = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value

    def finish(failure=""):
        result["passed"] = not failure and not errors
        if failure:
            result["failure"] = failure
        (state / "theme-checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        app.exit(0 if result["passed"] else 1)

    def capture():
        incubation = engine.incubationController()
        if incubation.incubatingObjectCount() and time.monotonic() < ready_deadline:
            incubation.incubateFor(100)
            QTimer.singleShot(100, capture)
            return
        name, width, height, language = cases[case_index]
        entry = {"theme": name, "viewport": [width, height], "language": language, "issues": []}
        try:
            assert evaluate("Theme.activeThemeName") == name, "Theme fell back to a different palette"
            assert not incubation.incubatingObjectCount(), "Theme controls did not finish loading"
            page = find("CommunityPreviewPage")
            gallery = find("CommunityGallery")
            entry.update(columns=gallery.property("columns"), gallery_width=round(gallery.width(), 1),
                         gallery_top=round(gallery.mapToScene(QPointF(0, 0)).y(), 1))
            if width == 1280 and entry["columns"] != 3:
                entry["issues"].append("Expected three gallery columns at medium size")
            if gallery.height() < 200 or gallery.width() < 200:
                entry["issues"].append("Gallery has insufficient usable space")
            for control_name in ("CommunitySearch", "OpenUpload", "BackToKfps", "Download", "Favorite",
                                 "Scope:Featured", "Scope:Browse", "Scope:Timed Releases", "Scope:Livery", "Scope:Favorites", "Scope:Following"):
                control = find(control_name)
                assert control.isVisible(), "Hidden control: " + control_name
                point = control.mapToScene(QPointF(0, 0))
                if (control.width() <= 0 or control.height() <= 0 or point.x() < 0 or point.y() < 0
                        or point.x() + control.width() > window.width() + 1
                        or point.y() + control.height() > window.height() + 1):
                    entry["issues"].append(control_name + " is outside the window")
            assert find("InspectorBody").width() <= find("InspectorScroll").property("availableWidth") + 1, "Inspector content is clipped horizontally"
            filters = find("GalleryFilters")
            assert filters.property("columns") == gallery.property("columns")
            expected_width = gallery.property("columns") * gallery.property("cellWidth") - evaluate("Theme.px(10)")
            assert abs(filters.width() - expected_width) < 1, "Filters and artwork tracks differ"
            assert abs(filters.mapToScene(QPointF(0, 0)).x() - gallery.mapToScene(QPointF(0, 0)).x()) < 1
            assert find("Upvote").property("crispText") and find("Download").property("crispText")
            assert abs(find("Download").width() - find("Favorite").width()) < 1, "Unequal artwork actions"
            assert abs(find("Download").width() + find("Favorite").width() + 8 - find("Download").parentItem().width()) <= 1, "Artwork actions don't fill the inspector"
            label = "contentItem.children.filter(function(c) { return c.font !== undefined && c.text === text })[0]"
            assert evaluate(label + ".font.family === Theme.fontFamily", find("Scope:Browse")), "Theme font was replaced"
            assert evaluate(label + ".font.pixelSize >= 12", find("Scope:Browse")), "Unreadable button text size"
            assert find("Scope:Browse").height() >= 36
            assert evaluate("contentItem.renderType === 2", find("InspectorCreator"))
            assert evaluate("contentItem.renderType === 2", find("KindFilter"))
            if name == "Command Prompt":
                for control_name in ("Upvote", "Downvote", "Favorite"):
                    assert find(control_name).property("text"), control_name + " has a blank terminal label"
            if not evaluate("Theme.classicMode || Theme.controlSurfaceComponentFile.length > 0"):
                def luminance(color):
                    channels = (color.redF(), color.greenF(), color.blueF())
                    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
                    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
                foreground = luminance(find("Scope:Featured").property("effectiveLabelColor"))
                background = luminance(evaluate("Theme.navActiveMiddle"))
                entry["selected_text_contrast"] = round((max(foreground, background) + .05) / (min(foreground, background) + .05), 2)
                assert entry["selected_text_contrast"] >= 4.5, "Selected tab text has low contrast"
            assert page.isVisible() and window.isVisible()
            slug = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
            path = state / f"{slug}-{width}-{language}.png"
            image = window.grabWindow()
            assert image.save(str(path)), "Could not capture " + name
            if name == "Command Prompt" and width == 1760:
                # White text on black: unequal RGB channels expose colored font fringes.
                pixels = [image.pixelColor(x, y) for y in range(350, 420) for x in range(205, 410)]
                entry["colored_text_pixels"] = sum(max(p.red(), p.green(), p.blue()) - min(p.red(), p.green(), p.blue()) > 2 for p in pixels)
                assert entry["colored_text_pixels"] == 0, "Colored fringes remain in terminal gallery text"
            result["screenshots"].append(str(path))
        except Exception:
            entry["issues"].append(traceback.format_exc())
        result["cases"].append(entry)
        try:
            click("Scope:Browse")
            QTimer.singleShot(200, lambda: check_controls(entry))
        except Exception:
            entry["issues"].append(traceback.format_exc())
            complete_case(entry)

    def click(name):
        control = find(name)
        assert control.isVisible() and control.isEnabled(), "Inactive control: " + name
        point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point, 0)

    def check_controls(entry):
        try:
            assert service.scope == "Browse", "Browse button did not change the view"
            if entry["viewport"][0] == 1760:
                click("InspectorCreator")
                QTimer.singleShot(300, lambda: check_profile(entry))
            elif entry["viewport"][0] == 1280:
                click("OpenUpload")
                QTimer.singleShot(400, lambda: check_dialog(entry))
            else:
                complete_case(entry)
        except Exception:
            entry["issues"].append(traceback.format_exc())
            complete_case(entry)

    def check_profile(entry):
        try:
            assert evaluate("creatorDialog.visible"), "Creator profile did not open"
            assert evaluate("creatorDialog.standardButton(Dialog.Close).text.length > 0"), "Profile close button has no label"
            assert 0 <= evaluate("creatorDialog.x") and evaluate("creatorDialog.x + creatorDialog.width") <= window.width()
            assert 0 <= evaluate("creatorDialog.y") and evaluate("creatorDialog.y + creatorDialog.height") <= window.height()
            slug = "".join(c.lower() if c.isalnum() else "-" for c in entry["theme"]).strip("-")
            path = state / (slug + "-profile-default.png")
            assert window.grabWindow().save(str(path))
            result["screenshots"].append(str(path))
        except Exception:
            entry["issues"].append(traceback.format_exc())
        finally:
            evaluate("creatorDialog.close()")
        check_ordinary_page(entry, 0)

    def check_ordinary_page(entry, index):
        pages = ("create", "settings")
        if index == len(pages):
            evaluate('appController.navigate("community")')
            QTimer.singleShot(250, lambda: complete_case(entry))
            return
        evaluate("appController.navigate(" + json.dumps(pages[index]) + ")")
        def capture_page():
            try:
                engine.incubationController().incubateFor(100)
                slug = "".join(c.lower() if c.isalnum() else "-" for c in entry["theme"]).strip("-")
                path = state / (slug + "-" + pages[index] + "-default.png")
                assert window.grabWindow().save(str(path))
                result["screenshots"].append(str(path))
            except Exception:
                entry["issues"].append(traceback.format_exc())
            check_ordinary_page(entry, index + 1)
        QTimer.singleShot(700, capture_page)

    def check_dialog(entry):
        try:
            # Dialog is a Popup QObject, not part of the visual childItems tree.
            assert evaluate("uploadDialog.visible"), "Upload dialog did not open"
            assert 0 <= evaluate("uploadDialog.x") and evaluate("uploadDialog.x + uploadDialog.width") <= window.width()
            assert 0 <= evaluate("uploadDialog.y") and evaluate("uploadDialog.y + uploadDialog.height") <= window.height()
            slug = "".join(c.lower() if c.isalnum() else "-" for c in entry["theme"]).strip("-")
            path = state / (slug + "-upload.png")
            assert window.grabWindow().save(str(path))
            result["screenshots"].append(str(path))
        except Exception:
            entry["issues"].append(traceback.format_exc())
        finally:
            evaluate("uploadDialog.close()")
        complete_case(entry)

    def complete_case(entry):
        nonlocal case_index
        service.filter("scope", "Featured")
        print(json.dumps(entry), flush=True)
        case_index += 1
        QTimer.singleShot(100, advance)

    def advance():
        nonlocal ready_deadline
        if case_index == len(cases):
            failures = [case for case in result["cases"] if case["issues"]]
            finish(f"{len(failures)} theme/layout cases need attention" if failures else "")
            return
        try:
            name, width, height, language = cases[case_index]
            service.setLanguage(language)
            window.resize(width, height)
            evaluate("settings.theme = " + json.dumps(name))
            ready_deadline = time.monotonic() + 15
            engine.incubationController().incubateFor(100)
            window.update()
            QTimer.singleShot(1600, capture)
        except Exception:
            finish(traceback.format_exc())

    QTimer.singleShot(1000, advance)

def run_checks(app, window, service, state, errors):
    result = {"checks": [], "qml_errors": errors, "screenshots": []}
    incubation = QQmlEngine.contextForObject(window).engine().incubationController()

    def finish(failure=""):
        result["passed"] = not failure and not errors
        if failure: result["failure"] = failure
        (state / "native-checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k != "screenshots"}, indent=2), flush=True)
        app.exit(0 if result["passed"] else 1)

    def settle():
        # A deliberately background window may not get frames to incubate QML.
        deadline = time.monotonic() + 30
        while incubation.incubatingObjectCount() and time.monotonic() < deadline:
            incubation.incubateFor(20)
            QTest.qWait(20)

    def items():
        queue = [window.contentItem()]
        while queue:
            item = queue.pop()
            yield item
            queue.extend(item.childItems())

    def find(name):
        item = next((i for i in items() if i.objectName() == name), None)
        assert item is not None, "Missing control: " + name
        return item

    def click(name):
        item = find(name)
        assert item.isVisible() and item.isEnabled(), "Inactive control: " + name
        ancestor = item.parentItem()
        while ancestor is not None:
            if ancestor.metaObject().indexOfProperty("contentY") >= 0:
                y = item.mapToItem(ancestor, QPointF(0, 0)).y()
                offset = min(0, y) + max(0, y + item.height() - ancestor.height())
                if offset:
                    ancestor.setProperty("contentY", ancestor.property("contentY") + offset)
                    QTest.qWait(100)
            ancestor = ancestor.parentItem()
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(160)

    def capture(name):
        print("Capture: " + name, flush=True)
        settle()
        QTest.mouseMove(window, QPointF(window.width() / 2, window.height() - 18).toPoint())
        QTest.qWait(350)
        target = state / (name + ".png")
        image = window.grabWindow()
        assert not image.isNull()
        assert image.save(str(target))
        result["screenshots"].append(str(target))

    def evaluate(item, code):
        expression = QQmlExpression(QQmlEngine.contextForObject(item), item, code)
        value, undefined = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value

    def await_upload():
        deadline = time.monotonic() + 30
        while service.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not service.busy and not service.hasError, service.status

    def type_text(text):
        for character in text:
            app.sendEvent(window, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, character))
            app.sendEvent(window, QKeyEvent(QEvent.KeyRelease, 0, Qt.NoModifier, character))

    try:
        assert service.rows
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            settle()
            candidates = [i for i in items() if i.objectName() == "CommunityGallery"]
            if candidates and candidates[0].width() > 0:
                break
            window.update()
            QTest.qWait(100)
        native_window_id = int(window.winId())
        assert find("CommunityPreviewPage").isVisible()
        assert find("CachedPageHost").isVisible()
        gallery = find("CommunityGallery")
        QTest.qWait(500)
        capture("gallery-desktop")
        assert evaluate(find("InspectorCreator"), "contentItem.renderType === 2")
        assert gallery.property("columns") == 3, ("Expected three columns at 1280", gallery.width())
        gallery_top = gallery.mapToScene(QPointF(0, 0)).y()
        assert gallery_top <= 280, ("Oversized Community header", gallery_top)
        assert gallery.height() >= gallery.property("cellHeight") * 2
        assert window.property("communityReviewPage") and window.property("headerHeight") == 40
        result["layout"] = {"viewport": [window.width(), window.height()],
                            "gallery_top": round(gallery_top, 1),
                            "gallery_height": round(gallery.height(), 1),
                            "row_height": round(gallery.property("cellHeight"), 1)}
        page = find("CommunityPreviewPage")
        creator = service.selected["creator"]
        click("CreatorLink:" + creator)
        assert evaluate(page, "creatorDialog.visible")
        assert service.creatorProfile["creator"] == creator
        assert find("CreatorGallery").property("columns") in (3, 4)
        capture("creator-profile")
        click("ProfileBrowse")
        assert not evaluate(page, "creatorDialog.visible")
        assert service.filters["creator"] == creator
        assert all(a["creator"] == creator for a in service.rows)
        click("ClearCreator")
        assert not service.filters["creator"]
        click("InspectorCreator")
        assert evaluate(page, "creatorDialog.visible")
        evaluate(page, "creatorDialog.close()")
        click("OwnProfile")
        assert service.creatorProfile["own"]
        click("ProfileEdit")
        assert evaluate(page, "profileDialog.visible")
        evaluate(page, "profileDialog.close()")
        service.setAccount("Moderator")
        assert not any(i.property("text") in ("Moderation", "Resolve reports", "Unfeature") for i in items())
        service.setAccount("Creator")
        result["checks"].append("Pointer clicks: gallery/inspector/account profiles, exact creator browse, clear filter and own profile edit; no moderation UI")
        click("Scope:Browse")
        assert service.scope == "Browse"
        item = next(a for a in service.rows if a["downloadable"] and not a["supporter"] and not a["ends"])
        service.select(item["id"])
        QTest.qWait(100)
        hit = find("ArtworkHit:" + item["id"])
        point = hit.mapToScene(QPointF(hit.width()/2, hit.height()/2)).toPoint()
        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(100)
        assert evaluate(page, "imageDialog.visible"), "Thumbnail double-click did not open the image"
        QTest.keyClick(window, Qt.Key_Escape)
        assert not evaluate(page, "imageDialog.visible")
        result["checks"].append("Gallery thumbnail double-click opens full image; Escape closes it")
        old = service.selected["vote"]
        if old: service.vote(old)
        click("Upvote")
        assert service.selected["vote"] == 1
        click("Downvote")
        assert service.selected["vote"] == -1
        click("Downvote")
        assert service.selected["vote"] == 0
        click("Favorite")
        if not service.selected["favorite"]: click("Favorite")
        assert service.selected["favorite"]
        click("Download")
        assert not service.hasError
        result["checks"].append("Actual Qt pointer clicks: browse, vote, change/remove vote, favorite, download")
        gallery = find("CommunityGallery")
        gallery.setProperty("contentY", 100)
        before_scroll = gallery.property("contentY")
        for vote in (1, -1, 1, 1):
            service.vote(vote)
        QTest.qWait(100)
        assert abs(gallery.property("contentY") - before_scroll) < 2
        result["checks"].append("Voting updates rows without resetting gallery scroll")
        service.setAccount("Visitor")
        QTest.qWait(100)
        assert not find("Download").isEnabled() and not find("Upvote").isEnabled()
        result["checks"].append("Visitor UI gates")
        service.setAccount("Member")
        gated = next(a for a in service.rows if a["supporter"])
        service.select(gated["id"])
        QTest.qWait(100)
        assert find("Download").isEnabled() and find("Download").property("text") == "Ko-Fi"
        with patch("webbrowser.open", return_value=True) as opened:
            click("Download")
            opened.assert_called_once_with("https://ko-fi.com/s/2d1507698d")
        assert abs(find("Download").width() - find("Favorite").width()) < 1
        service.setAccount("Supporter")
        assert not service.selected["locked"]
        result["checks"].append("Member/supporter entitlement states")
        service.setAccount("Moderator")
        service.filter("scope", "Featured")
        service.setLanguage("ko")
        capture("gallery-korean")
        window.resize(1050,740)
        capture("gallery-compact")
        window.resize(1000,660)
        capture("gallery-minimum")
        service.setLanguage("en")
        window.resize(1520,940)
        click("OpenUpload")
        capture("upload-dialog")
        payload = {"shapes":[{"type":16,"data":[512,512,217,119,31],"color":[41,211,100,255]}]}
        upload_path = state / "native-upload.json"
        upload_path.write_text(json.dumps(payload), encoding="utf-8")
        service.inspectPath(str(upload_path))
        await_upload()
        click("UploadTitle")
        type_text("Native scheduled upload")
        scroll = find("UploadScroll")
        evaluate(scroll, "contentItem.contentY = Math.max(0, contentItem.contentHeight - height)")
        QTest.qWait(200)
        click("TimedUpload")
        evaluate(find("UploadStarts"), 'setIso("2099-02-19T13:00:00+09:00")')
        evaluate(find("UploadEnds"), 'setIso("2099-02-19T16:00:00+09:00")')
        evaluate(scroll, "contentItem.contentY = Math.max(0, contentItem.contentHeight - height)")
        QTest.qWait(200)
        click("UploadRights")
        capture("scheduled-upload")
        click("PublishUpload")
        assert not service.hasError, service.status
        assert service.scope == "My uploads" and service.selected["state"] == "scheduled"
        assert service.selected["ends"] - service.selected["starts"] == 10800
        result["checks"].append("Actual upload form: validated JSON, title entry, timed release, rights confirmation, local publication")
        service.filter("scope", "Browse")
        search = find("CommunitySearch")
        click("CommunitySearch")
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        type_text("nothing-should-match-this")
        QTest.qWait(350)
        assert not service.rows
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(window, Qt.Key_Backspace)
        QTest.qWait(350)
        assert service.rows
        result["checks"].append("Search input and empty-results recovery")
        QTest.keyClick(window, Qt.Key_Escape)
        service.filter("kind","livery")
        assert service.rows and all(a["kind"] == "livery" for a in service.rows)
        capture("livery-filter")
        result["checks"].append("Korean, compact/wide layout, upload dialog, livery filter")
        service.filter("kind", "All")
        service.filter("scope", "Featured")
        evaluate(find("CommunityPreviewPage"), 'settings.theme = "Windows 94"')
        capture("gallery-classic")
        result["checks"].append("Shared KFPS theme setting updates the embedded page and real title bar")
        # The compact layout fits the original small catalog at larger sizes.
        # Seed actual local catalog rows and a long description to exercise overflow.
        picture = service.store.preview(service.rows[0]["id"], "Moderator", service.now())
        stress_ids = []
        for index in range(24):
            stress_ids.append(service.store.add({
                "title": "Layout stress sample " + str(index + 1), "kind": "vinyl",
                "sample": True, "game": "FH6", "creator": "LayoutTest",
                "description": "A longer artwork description that must wrap inside the inspector. " * 30,
            }, None, picture, "Moderator", seed=True))
        service.filter("scope", "Browse")
        service.select(stress_ids[0])
        for width, height in ((1520, 940), (1000, 660)):
            window.resize(width, height)
            QTest.qWait(250)
            gallery = find("CommunityGallery")
            inspector = find("InspectorScroll")
            body = find("InspectorBody")
            for bar_name, content in (("GalleryScrollBar", gallery), ("InspectorScrollBar", body)):
                bar = find(bar_name)
                left = bar.mapToScene(QPointF(0, 0))
                content_right = content.mapToScene(QPointF(content.width(), 0)).x()
                assert left.x() - content_right >= 7, (bar_name, "overlaps content")
                assert abs(bar.height() - bar.parentItem().height()) < 1, bar_name
                assert abs(bar.x() + bar.width() - bar.parentItem().width()) < 1, bar_name
                arrows = {}
                queue = list(bar.childItems())
                while queue:
                    child = queue.pop()
                    queue.extend(child.childItems())
                    if child.property("text") in ("\u25b2", "\u25bc"):
                        arrows[child.property("text")] = child.parentItem()
                assert len(arrows) == 2, bar_name
                for symbol, arrow in arrows.items():
                    point = arrow.mapToScene(QPointF(0, 0))
                    assert abs(point.x() - left.x()) < 1, (bar_name, "arrow x")
                    assert abs(arrow.width() - bar.width()) < 1, (bar_name, "arrow width")
                    expected_y = left.y() if symbol == "\u25b2" else left.y() + bar.height() - arrow.height()
                    assert abs(point.y() - expected_y) < 1, (bar_name, "arrow y")
                if bar_name == "GalleryScrollBar":
                    gallery.setProperty("contentY", 0)
                else:
                    evaluate(inspector, "contentItem.contentY = 0")
                QTest.qWait(100)
                assert bar.property("size") < 1, (bar_name, "test needs overflowing content")
                for symbol in ("\u25bc", "\u25b2"):
                    arrow = arrows[symbol]
                    point = arrow.mapToScene(QPointF(arrow.width()/2, arrow.height()/2)).toPoint()
                    before = bar.property("position")
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
                    QTest.qWait(120)
                    after = bar.property("position")
                    assert after > before if symbol == "\u25bc" else after < before, (bar_name, "arrow click")
                thumb = bar.property("contentItem")
                start = thumb.mapToScene(QPointF(thumb.width()/2, thumb.height()/2)).toPoint()
                end = start + QPointF(0, 45).toPoint()
                before = bar.property("position")
                QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
                QTest.mouseMove(window, end, 30)
                QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
                QTest.qWait(120)
                assert bar.property("position") > before, (bar_name, "thumb drag")
            capture("scrollbars-classic-" + str(width))
        result["checks"].append("Windows 94 scrollbars: separate gutters, full-height tracks, aligned arrows, arrow clicks and thumb drags at desktop/minimum sizes")
        result["checks"].append("Readable aligned filters: gallery starts within 280px, two full rows visible at 1280x800; long descriptions and a 30+ item catalog still scroll")
        window.resize(1280, 800)
        service.setLanguage("en")
        service.filter("scope", "Featured")
        service.select(service.rows[0]["id"])
        gallery.setProperty("contentY", 0)
        evaluate(find("InspectorScroll"), "contentItem.contentY = 0")
        QTest.qWait(200)
        assert gallery.property("columns") == 3
        capture("integrated-windows94-medium-english")
        evaluate(find("CommunityPreviewPage"), 'settings.theme = "Night Blossom"')
        capture("integrated-night-blossom-medium-english")
        service.setLanguage("ko")
        capture("back-button-korean")
        back = find("BackToKfps")
        point = back.mapToScene(QPointF(0, back.height()))
        assert point.y() <= window.height()
        previous = service.selected["id"]
        page = find("CommunityPreviewPage")
        click("BackToKfps")
        assert window.isVisible() and not page.isVisible()
        assert evaluate(page, "appController.currentPage") == "create"
        assert not window.property("communityReviewPage") and window.property("headerHeight") == 96
        evaluate(page, 'appController.navigate("settings")')
        QTest.qWait(300)
        assert evaluate(page, "appController.currentPage") == "settings"
        evaluate(page, 'appController.navigate("community")')
        QTest.qWait(300)
        assert page.isVisible() and service.selected["id"] == previous
        assert window.property("headerHeight") == 40
        assert int(window.winId()) == native_window_id
        result["checks"].append("Embedded in real KFPS: three columns at 1280x800; Back/Create/Settings/Community navigation stays in one window and retains selection")
        service.setLanguage("en")
        service.setAccount("Creator")
        service.filter("kind", "All")
        service.filter("search", "")
        click("Scope:Timed Releases")
        assert all(row["ends"] is not None and row["state"] == "available" for row in service.rows)
        timed_ids = {row["id"] for row in service.rows}
        click("Scope:Browse")
        assert timed_ids <= {row["id"] for row in service.rows}
        result["checks"].append("Timed tab filters active releases without removing them from Browse")

        # A large creator catalog exercises real delegate reuse and lazy decoding.
        import uuid
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage
        thumb = QImage.fromData(picture).scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        thumb.save(buffer, "PNG")
        small_picture = bytes(buffer.data())
        creator_ids = [uuid.uuid4().hex for _ in range(600)]
        meta = {"title": "Catalog scrolling", "kind": "vinyl", "creator": "GalleryStress", "game": "FH6", "description": "", "tags": [], "sample": True}
        with service.store.db:
            service.store.db.executemany("INSERT INTO artwork VALUES (?,?,?,?,?,?,?,?,?)", (
                (ident, json.dumps(dict(meta, title=f"Catalog {index+1:03d}")), None, small_picture, "", service.now()-index,
                 None, None, "published") for index, ident in enumerate(creator_ids)))
        window.resize(1760, 1040)
        opened = time.perf_counter()
        service.viewCreator("GalleryStress")
        evaluate(page, "creatorDialog.open()")
        QTest.qWait(200)
        first_ready = time.perf_counter() - opened
        creator_grid = find("CreatorGallery")
        assert creator_grid.property("columns") == 4
        assert service.creatorProfile["artworkCount"] == 600
        assert service.creator_model.rowCount() < 600
        captures = []
        timings = []
        started = time.monotonic()
        while service.creatorHasMore:
            assert time.monotonic() - started < 45, "Creator paging stopped progressing"
            before = time.perf_counter()
            creator_grid.setProperty("contentY", max(0, creator_grid.property("contentHeight") - creator_grid.height()))
            QTest.qWait(45)
            timings.append(time.perf_counter() - before)
            captures.append(sum(i.objectName().startswith("CreatorArtwork:") for i in items()))
        creator_grid.setProperty("contentY", max(0, creator_grid.property("contentHeight") - creator_grid.height()))
        QTest.qWait(200)
        assert service.creator_model.rowCount() == 600
        assert max(captures) < 80, ("Creator delegates not bounded", max(captures))
        last_thumb = find("CreatorThumbnail:" + creator_ids[-1])
        assert evaluate(last_thumb, "status === Image.Ready"), "Last thumbnail did not render"
        capture("creator-catalog-last-page")
        click("CreatorArtwork:" + creator_ids[-1])
        assert evaluate(page, "imageDialog.visible") and service.selected["id"] == creator_ids[-1]
        QTest.keyClick(window, Qt.Key_Escape)
        assert evaluate(page, "creatorDialog.visible"), "Image close lost the creator profile"
        evaluate(page, "creatorDialog.close()")
        result["creator_gallery"] = {"artworks": 600, "max_live_delegates": max(captures),
            "first_ready_including_200ms_wait": round(first_ready, 3),
            "max_page_step_including_45ms_wait": round(max(timings), 3)}
        result["checks"].append("600-artwork creator profile: four columns, bounded lazy thumbnails, scrolling through final page, image open and Escape back to profile")
        with service.store.db:
            service.store.db.executemany("DELETE FROM artwork WHERE id=?", ((ident,) for ident in creator_ids))
        service.creator_value = ""
        service.creator_model.replace([])
        service.refresh()
        import os
        real_package = os.environ.get("KFPS_COMMUNITY_TEST_LIVERY")
        if real_package:
            import hashlib
            import subprocess
            source = Path(real_package)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            service.inspectPath(str(source)); await_upload()
            photo_paths = [str(service.repo / "docs/screenshots/showcase/livery-preview.png")] * 3
            service.inspectPhotos(photo_paths); await_upload()
            click("OpenUpload")
            capture("livery-three-photo-upload")
            evaluate(page, "uploadDialog.close()")
            service.publish({"title": "Community 3D qualification", "rights": True, "compatibility": True})
            assert not service.hasError, service.status
            assert len(service.selected["photoUrls"]) == 4
            assert service.selected['photoUrls'][0] == service.selected['previewUrl']
            QTest.qWait(500)
            assert not evaluate(page, "uploadDialog.visible")
            evaluate(find("InspectorScroll"), "contentItem.contentY = 0")
            QTest.qWait(200)
            click("LiveryPhoto:1")
            capture("livery-photo-click")
            assert evaluate(page, "imageDialog.photoIndex") == 1, (evaluate(page, "imageDialog.visible"), evaluate(page, "imageDialog.photoIndex"))
            window.resize(1760, 1040)
            capture("livery-photo-default")
            click("OpenLiveryRender")
            progress = {"deadline": time.monotonic() + 120, "process": None, "log": None}

            def poll_render():
                try:
                    viewer = service.liveryViewer
                    assert viewer, service.status
                    (state / "render-progress.json").write_text(json.dumps({"status": viewer.status, "summary": viewer.summary, "ready": viewer.viewerReady, "url": viewer.viewerUrl}))
                    window.update()
                    incubation.incubateFor(20)
                    assert time.monotonic() < progress["deadline"], viewer.summary
                    if progress["process"] is None:
                        if not viewer.viewerReady:
                            QTimer.singleShot(100, poll_render)
                            return
                        capture("livery-render-default")
                        config = {"port": int(os.environ["QTWEBENGINE_REMOTE_DEBUGGING"].split(":")[-1]), "url": viewer.viewerUrl, "output": str(state)}
                        config_path = state / "render-test-config.json"
                        config_path.write_text(json.dumps(config))
                        progress["log"] = (state / "render-playwright.log").open("w", encoding="utf-8")
                        progress["process"] = subprocess.Popen([os.environ["KFPS_TEST_NODE"], str(service.repo / "KFPS.UI/tools/test_community_preview_render.cjs"), str(config_path)], stdout=progress["log"], stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
                        progress["deadline"] = time.monotonic() + 90
                    process = progress["process"]
                    if process.poll() is None:
                        QTimer.singleShot(100, poll_render)
                        return
                    progress["log"].close()
                    assert process.returncode == 0, (state / "render-playwright.log").read_text()
                    render_folder = Path(service._render_session.temporary.name)
                    click("CloseLiveryRender")
                    QTest.qWait(500)
                    assert service.liveryViewer is None and not render_folder.exists()
                    assert not evaluate(page, "renderDialog.visible")
                    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
                    result["checks"].append("Real livery: three-photo upload, second-photo click, 3D pipeline, orbit/pan/zoom, nonblank desktop/narrow canvas, X close and scratch cleanup; original unchanged")
                    finish()
                except Exception:
                    process = progress["process"]
                    if process and process.poll() is None: process.kill(); process.wait()
                    if progress["log"]: progress["log"].close()
                    finish(traceback.format_exc())
            QTimer.singleShot(100, poll_render)
            return
        assert not errors, "QML errors: " + repr(errors)
        result["passed"] = True
    except Exception:
        result["passed"] = False
        result["failure"] = traceback.format_exc()
        print(result["failure"], flush=True)
    finish(result.get("failure", ""))
