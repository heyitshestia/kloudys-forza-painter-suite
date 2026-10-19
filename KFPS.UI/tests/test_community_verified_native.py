"""Offscreen real Community service/gallery workflows against the loopback fake peer.

This is UI/client integration, not worker authorization qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

UI = Path(__file__).resolve().parents[1]
RUN = UI.parent / "runtime/community-tests/free-access-client-20261019"
sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(UI.parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")


def source_hashes():
    paths = list((UI / "src/kfps_ui").glob("community*.py"))
    paths += list((UI / "qml/community-preview").glob("*"))
    paths += [UI / "qml/pages/CommunityPage.qml", UI / "qml/components/CommunityArtworkCard.qml",
              UI.parent / "tools/community_worker/contracts/verified-access-contract.schema.json"]
    return {str(path.relative_to(UI.parent)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file()}


def native():
    from PySide6.QtCore import QObject, Qt, QUrl, QPoint, QPointF, qInstallMessageHandler
    from PySide6.QtGui import QColor, QFontDatabase
    from PySide6.QtQml import QQmlEngine, QQmlExpression, QQmlPropertyMap
    from PySide6.QtQuick import QQuickView
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    QQuickStyle.setStyle("Basic")
    app = QApplication.instance() or QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf", "tahoma.ttf", "malgun.ttf", "meiryo.ttc"):
        font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    from test_community_policy_service import PolicyServiceTests, settle
    from kfps_ui.theme_catalog import THEME_PRESETS

    class VerifiedUiTests(unittest.TestCase):
        def setUp(self):
            self.fixture = PolicyServiceTests("runTest")
            self.fixture.setUp()
            self.service = self.fixture.service
            from kfps_ui.community_validation import inspect_upload
            payload = json.loads(self.fixture.peer.raw)
            color = list(hashlib.sha256(self.id().encode()).digest()[:3]) + [255]
            payload["shapes"][0].update(color=color, data=[512, 512, 240, 130, 25])
            self.fixture.peer.raw = json.dumps(payload).encode()
            source = Path(self.fixture.temp.name) / "display-vinyl.json"
            source.write_bytes(self.fixture.peer.raw)
            inspected = inspect_upload(source, Path(self.fixture.temp.name) / "display-preview")
            self.fixture.peer.image = inspected.preview_bytes
            digest = hashlib.sha256(self.fixture.peer.image).hexdigest()
            for row in self.fixture.peer.records:
                row.update(preview_url=f"artworks/{row['id']}/preview", thumbnail_url=f"artworks/{row['id']}/thumbnail",
                           preview_sha256=digest, thumbnail_sha256=digest, shape_count=inspected.shape_count,
                           content_sha256=hashlib.sha256(self.fixture.peer.raw).hexdigest())
            self.gallery = self.fixture.make_gallery()
            self.messages = []
            self.old_handler = qInstallMessageHandler(lambda kind, context, message: self.messages.append(message))
            self.view = None
            self.open_view()

        def tearDown(self):
            self.close_view()
            qInstallMessageHandler(self.old_handler)
            self.fixture.tearDown()
            errors = [m for m in self.messages if any(term in m for term in (
                "ReferenceError", "TypeError", "Binding loop", "Cannot assign", "Unable to assign", "is not a type"))]
            self.assertEqual(errors, [])

        def open_view(self, retained=False):
            self.close_view()
            self.view = QQuickView()
            self.view.setResizeMode(QQuickView.SizeRootObjectToView)
            self.view.setFlags(Qt.Tool | Qt.WindowDoesNotAcceptFocus)
            self.view.setColor(QColor("#17191e"))
            self.view.resize(1400, 900)
            engine = self.view.engine()
            engine.addImportPath(str(UI / "qml"))
            if not retained:
                engine.addImageProvider("community-gallery", self.gallery.images)
            context = engine.rootContext()
            context.setContextProperty("preview", self.gallery)
            context.setContextProperty("communityService", self.service)
            context.setContextProperty("communityGalleryMode", True)
            context.setContextProperty("screenshotMode", True)
            context.setContextProperty("settings", {"communityLanguage": "en"})
            self.json_stub = QQmlPropertyMap()
            for key, value in {"currentSourceIndexing": False, "fileModel": [],
                               "searchQuery": "", "searchSummary": "", "sourceIndex": 0}.items():
                self.json_stub.insert(key, value)
            context.setContextProperty("jsonService", self.json_stub)
            context.setContextProperty("assetRoot", QUrl.fromLocalFile(str(UI / "assets")).toString())
            path = "pages/CommunityPage.qml" if retained else "community-preview/CommunityPreview.qml"
            self.view.setSource(QUrl.fromLocalFile(str(UI / "qml" / path)))
            self.assertIsNotNone(self.view.rootObject(), str(self.view.errors()))
            self.view.show()
            QTest.qWait(80)
            self.wait()

        def close_view(self):
            if self.view:
                self.view.close()
                self.view.setSource(QUrl())
                self.view.deleteLater()
                app.processEvents()
                self.view = None

        def wait(self):
            self.assertTrue(settle(lambda: not self.service.busy and not self.gallery.busy
                                   and not self.gallery._image_pending and not self.service._policy_timer.isActive()))
            QTest.qWait(40)

        def expression(self, source, item=None):
            item = item or self.view.rootObject()
            expr = QQmlExpression(QQmlEngine.contextForObject(item), item, source)
            value, _ = expr.evaluate()
            self.assertFalse(expr.hasError(), expr.error().toString())
            return value

        def find(self, name):
            direct = self.view.rootObject().findChild(QObject, name)
            if direct is not None:
                return direct
            pending, seen = [self.view.rootObject(), self.view.contentItem()], {}
            while pending:
                item = pending.pop()
                if id(item) in seen:
                    continue
                seen[id(item)] = item
                if item.objectName() == name:
                    return item
                pending.extend(item.children())
                if hasattr(item, "childItems"):
                    pending.extend(item.childItems())
            self.fail("Missing QML item: " + name)

        def click(self, name):
            item = self.find(name)
            self.assertTrue(item.property("enabled"), name)
            self.assertTrue(item.property("visible"), name)
            point = item.mapToScene(item.boundingRect().center())
            QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
            QTest.qWait(30)
            self.wait()

        def screenshot(self, name):
            image = self.view.grabWindow()
            self.assertFalse(image.isNull())
            colors = {image.pixel(x, y) for y in range(0, image.height(), 20) for x in range(0, image.width(), 20)}
            self.assertGreater(len(colors), 8)
            path = RUN / "screenshots" / (name + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(image.save(str(path)))
            reopened = type(image)(str(path))
            self.assertEqual(reopened.size(), image.size())

        def check_button_fit(self, name):
            item = self.find(name)
            self.assertTrue(self.expression("contentItem.implicitWidth <= availableWidth + 2", item), name)

        def test_claim_workflow_assertion_results_and_opaque_titles(self):
            self.assertTrue(settle(lambda: bool(self.gallery.images._images)),
                            (self.gallery.status, self.gallery._image_pending, self.messages[-3:]))
            self.assertFalse(any("restricted/preview" in path for _, path, _, _ in self.fixture.peer.requests))
            self.click("OwnClaimsView")
            self.click("SelectClaim:one")
            self.click("SelectClaim:two")
            self.assertEqual(self.service.claimSelection, ["one", "two"])
            self.fixture.peer.claim_outcomes["two"] = "claim_revision_changed"
            self.click("ReviewClaims")
            self.assertFalse(self.find("SubmitClaims").property("enabled"))
            self.click("ClaimAssertion")
            self.check_button_fit("SubmitClaims")
            self.screenshot("claims-en-review-1400")
            self.click("SubmitClaims")
            self.assertEqual([r["outcome"] for r in self.service.claimResults], ["accepted", "rejected"])
            self.assertEqual(self.service.claimResults[0]["title"], self.fixture.peer.records[0]["title"])
            self.assertEqual(self.service.verifiedCount, 9)
            self.assertTrue(self.find("CommunityClaimsDialog").property("visible"))
            self.screenshot("claims-en-results-1400")

        def test_claim_error_stays_visible_inside_dialog(self):
            self.click("OwnClaimsView")
            for ident in ("one", "two"):
                self.click("SelectClaim:" + ident)
            self.fixture.peer.bad_claim_response = True
            self.click("ReviewClaims")
            self.click("ClaimAssertion")
            self.click("SubmitClaims")
            self.assertEqual(self.service.claimError, "invalid_claim_response")
            self.assertTrue(self.find("ClaimRequestError").property("visible"))
            self.fixture.refresh()
            self.assertTrue(self.find("ClaimRequestError").property("visible"))

        def test_server_progress_grant_and_suspension_states(self):
            for count, reason, expected in ((0, None, False), (9, None, False), (10, "waiting_period", False),
                                             (10, None, True), (11, "account_suspended", False)):
                self.fixture.peer.count, self.fixture.peer.reason = count, reason
                self.fixture.refresh()
                self.wait()
                self.assertEqual(self.service.verifiedAccess, expected)
                text = self.expression("children[0].text", self.find("CommunityAccessStatus").parent())
                self.assertIn("Verified", text)
            self.fixture.peer.count, self.fixture.peer.reason = 0, None
            self.fixture.peer.grandfathered_at = "2026-10-01T00:00:00Z"
            self.fixture.refresh()
            self.wait()
            self.assertTrue(self.service.grandfatheredVerified)
            self.assertFalse(self.service.supporterAccess)
            self.assertIn("Existing supporter", self.find("CommunityAccessStatus").property("text"))
            self.assertFalse(self.find("VerifiedProgress").property("visible"))
            self.screenshot("permanent-grant-en-1400")

        def test_en_ko_themes_and_desktop_layout(self):
            self.click("OwnClaimsView")
            for language in ("en", "ko"):
                self.gallery.settings.communityLanguage = language
                self.gallery.changed.emit()
                for theme in THEME_PRESETS:
                    self.expression("Theme.supporterUnlocked=true; Theme.themeName=" + json.dumps(theme.name))
                    self.view.resize(1100, 800)
                    QTest.qWait(35)
                    self.check_button_fit("OpenUpload")
                    self.check_button_fit("ReviewClaims")
                self.expression("Theme.themeName='Carbon Dark'")
                QTest.qWait(40)
                self.screenshot("progress-" + language + "-1100")
                self.click("SelectClaim:one")
                self.click("ReviewClaims")
                self.check_button_fit("SubmitClaims")
                self.screenshot("claims-" + language + "-1100")
                self.expression("close()", self.find("CommunityClaimsDialog"))
                self.click("SelectClaim:one")

        def test_progress_uses_theme_tokens_including_custom_palette(self):
            self.click("OwnClaimsView")
            progress = self.find("VerifiedProgress")
            track = self.find("VerifiedProgressTrack")
            fill = self.find("VerifiedProgressFill")
            for theme in THEME_PRESETS:
                self.expression("Theme.supporterUnlocked=true; Theme.themeName=" + json.dumps(theme.name))
                QTest.qWait(25)
                self.assertTrue(self.expression("color.toString() === Theme.sliderTrack.toString()", track))
                self.assertTrue(self.expression("color.toString() === Theme.primary.toString()", fill))
                self.assertAlmostEqual(fill.width(), progress.property("position") * track.width(), delta=1)
            self.expression("""var custom = Object.assign({}, Theme.nightBlossom, {
                name: 'Synthetic custom palette', primary: '#21b79c', sliderTrack: '#57406e'
            }); Theme.palettes.push(custom); Theme.themeName = custom.name""")
            QTest.qWait(40)
            self.assertEqual(track.property("color"), QColor("#57406e"))
            self.assertEqual(fill.property("color"), QColor("#21b79c"))
            image = self.view.grabWindow()
            for item in (track, fill):
                x = item.width() * (0.95 if item is track else 0.5)
                point = item.mapToScene(QPointF(x, item.height() / 2))
                self.assertEqual(image.pixelColor(round(point.x()), round(point.y())), item.property("color"))
            self.screenshot("progress-custom-1400")
            self.expression("Theme.themeName='Night Blossom'; Theme.palettes.pop()")

        def test_upload_requires_authorship_but_allows_toolmade(self):
            from test_community_gallery import solid_png
            self.gallery._pending = {"kind": "vinyl", "title": "Opaque \u65e5\u672c\u8a9e.json", "payload": self.fixture.peer.raw,
                                     "preview": solid_png("#54bdce"), "photos": [], "sha256": hashlib.sha256(self.fixture.peer.raw).hexdigest()}
            self.gallery.changed.emit()
            self.click("OpenUpload")
            self.find("UploadClassification").setProperty("currentIndex", 1)
            self.find("UploadRights").setProperty("checked", True)
            self.assertFalse(self.find("PublishUpload").property("enabled"))
            self.find("UploadAuthorship").setProperty("currentIndex", 1)
            self.assertTrue(self.find("PublishUpload").property("enabled"))
            self.expression("clicked()", self.find("PublishUpload"))
            self.wait()
            body = next(body for method, path, _, body in reversed(self.fixture.peer.requests) if method == "POST" and path == "/v1/artworks")
            self.assertIn(b'"classification":"toolmade"', body.replace(b" ", b""))
            self.assertIn(b'"authorship":"own"', body.replace(b" ", b""))
            self.assertEqual(self.service.verifiedCount, 9)

        def test_retained_page_instantiates_with_real_policy_service(self):
            self.service.gallery_managed = False
            self.service.setScopeIndex(7)
            self.wait()
            self.open_view(retained=True)
            self.expression("activeTab=2")
            self.wait()
            self.screenshot("retained-profile-en-1400")
            self.expression("activeTab=0")
            self.wait()
            self.assertTrue(self.service.claimsEnabled)
            self.screenshot("retained-uploads-en-1400")

    before = source_hashes()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VerifiedUiTests))
    after = source_hashes()
    report = {"kind": "offscreen-client-fake-peer", "tests": result.testsRun, "success": result.wasSuccessful(),
              "source_unchanged": before == after, "source_before": before, "source_after": after,
              "external_services": False, "personal_sessions": False}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "verified-ui-evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if result.wasSuccessful() and before == after else 1


class NativeHarnessTests(unittest.TestCase):
    def test_offscreen_verified_workflows(self):
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
               "TEMP": str(RUN / "temp"), "TMP": str(RUN / "temp")}
        Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)
        result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--native"],
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    raise SystemExit(native()) if "--native" in sys.argv else unittest.main()
