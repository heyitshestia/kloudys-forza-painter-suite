"""Real QML visibility lifecycle against the local gallery scheduling fixture."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(UI.parent)]


def native():
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from kfps_ui.community_gallery_service import CommunityGalleryService
    from kfps_ui.community_preview_service import CommunityPreviewService
    from test_community_gallery_scheduling import LocalCommunity, record, stamp

    class VisibleCommunity(LocalCommunity):
        supporterAccess = verifiedAccess = grandfatheredVerified = claimsBusy = False
        verifiedCount = 0
        verifiedRequired = 10
        requiredAccountAgeDays = 14
        connectedAt = eligibleAfter = claimError = ""
        verifiedReason = "policy_legacy"
        claimSelection = claimResults = claimEntries = []

    class VisibilityTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory(prefix="gallery-visibility-", dir=os.environ.get("KFPS_COMMUNITY_TEST_ROOT"))
            self.community = VisibleCommunity(self.temp.name)
            self.service = CommunityGalleryService(UI.parent, self.community, SimpleNamespace(communityLanguage="en"))
            self.service.timer.stop()
            self.view = None
            self.warnings = []
            self.settle()

        def tearDown(self):
            self.community.client.release_catalog.set()
            self.community.client.release_images.set()
            if self.view is not None:
                self.view.setSource(QUrl())
                self.view.close()
            self.service.close()
            app.processEvents()
            self.temp.cleanup()

        def settle(self):
            for _ in range(200):
                app.processEvents()
                if not self.service.busy:
                    return
                QTest.qWait(5)
            self.fail("Local gallery did not settle")

        def wait_for(self, predicate):
            for _ in range(400):
                app.processEvents()
                if predicate():
                    return
                QTest.qWait(5)
            self.fail("Native gallery condition did not settle")

        def open_page(self, live=True):
            self.view = QQuickView()
            self.view.setResizeMode(QQuickView.SizeRootObjectToView)
            self.view.resize(1100, 800)
            engine = self.view.engine()
            engine.addImportPath(str(UI / "qml"))
            engine.warnings.connect(lambda warnings: self.warnings.extend(str(item) for item in warnings))
            context = engine.rootContext()
            context.setContextProperty("preview", self.service)
            context.setContextProperty("communityGalleryMode", live)
            context.setContextProperty("communityService", dict(authenticated=False, authenticationInProgress=False,
                usernameRequired=False, username="", githubUserCode="", supporterAccess=False,
                errorMessage="", statusMessage=""))
            context.setContextProperty("assetRoot", QUrl.fromLocalFile(str(UI / "assets")).toString())
            context.setContextProperty("screenshotMode", True)
            if live:
                engine.addImageProvider("community-gallery", self.service.images)
            self.view.setSource(QUrl.fromLocalFile(str(UI / "qml/community-preview/CommunityPreview.qml")))
            self.assertIsNotNone(self.view.rootObject(), str(self.view.errors()))
            self.view.show()
            app.processEvents()
            self.settle()

        def test_hidden_page_catches_up_on_return_without_waiting_for_timer(self):
            with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
                self.community.client.items = [record(starts_at=stamp(900), ends_at=stamp(1010))]
                self.service.refresh()
                self.settle()
                self.open_page()
                self.assertTrue(self.service._view_active)
                self.community.client.calls.clear()
                self.community.refreshAccount.reset_mock()
                root = self.view.rootObject()
                root.setProperty("visible", False)
                self.assertFalse(self.service._view_active)
                now.return_value = 1011
                for _ in range(3):
                    self.service._tick()
                    app.processEvents()
                self.assertEqual(self.community.client.calls, [])
                self.community.refreshAccount.assert_not_called()
                self.community.client.release_catalog.clear()
                self.community.client.catalog_started.clear()
                root.setProperty("visible", True)
                self.assertTrue(self.service._view_active)
                self.assertTrue(self.community.client.catalog_started.wait(1))
                self.assertTrue(self.service._catalog_loading)
                self.assertFalse(self.service.timer.isActive())
                self.community.client.release_catalog.set()
                self.settle()
                self.assertEqual(self.service.selected["id"], "art")
                self.assertEqual(self.service.selected["state"], "expired")
                self.assertEqual(len(self.community.client.calls), 1)
                # One transition refresh plus the page's existing access refresh.
                self.assertEqual(self.community.refreshAccount.call_count, 2)

        def test_page_destruction_deactivates_and_recreation_reactivates(self):
            self.open_page()
            self.assertTrue(self.service._view_active)
            source = self.view.source()
            self.view.setSource(QUrl())
            self.assertFalse(self.service._view_active)
            self.view.setSource(source)
            self.assertIsNotNone(self.view.rootObject())
            self.assertTrue(self.service._view_active)

        def test_native_hide_pauses_image_demand_and_show_resumes_retained_rows(self):
            client = self.community.client
            client.items = [record(f"visible-{index}") for index in range(24)]
            self.service.refresh()
            self.settle()
            client.release_images.clear()
            self.open_page()
            self.wait_for(lambda: len(client.images) == 4 and bool(self.service._image_waiting))
            root = self.view.rootObject()
            root.setProperty("visible", False)
            self.assertFalse(self.service._view_active)
            client.release_images.set()
            self.wait_for(lambda: not self.service._image_jobs)
            self.assertEqual(len(client.images), 4)
            self.assertFalse(self.service._image_ready)
            self.assertEqual(self.service.images._bytes, 0)
            demand = set(self.service._image_waiting)
            self.assertGreater(len(demand), 4)
            root.setProperty("visible", True)
            self.wait_for(lambda: demand.issubset(self.service._image_ready))
            self.assertTrue(all(key in self.service.images._images for key in demand))
            self.assertEqual(len(self.service.rows), 24)
            self.assertEqual(self.service.selected["id"], "visible-0")

        def test_native_expiry_disables_actions_and_media_before_pending_reply(self):
            with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
                client = self.community.client
                client.items = [record(starts_at=stamp(900), ends_at=stamp(1010),
                                       preview_url="previews/art", photo_urls=["photos/art"])]
                self.service.refresh()
                self.settle()
                self.open_page()
                root = self.view.rootObject()
                upvote = root.findChild(QObject, "Upvote")
                favorite = root.findChild(QObject, "Favorite")
                media = root.findChild(QObject, "MediaDialog")
                self.assertTrue(upvote.property("enabled"))
                self.assertTrue(favorite.property("enabled"))
                self.assertTrue(self.service.selected["photoUrls"])
                client.release_catalog.clear()
                client.catalog_started.clear()
                self.service.refresh()
                self.assertTrue(client.catalog_started.wait(1))
                now.return_value = 1011
                self.service._tick()
                app.processEvents()
                self.assertTrue(self.service._catalog_loading)
                self.assertEqual(self.service.selected["state"], "expired")
                self.assertFalse(upvote.property("enabled"))
                self.assertFalse(favorite.property("enabled"))
                self.assertFalse(self.service.selected["canViewMedia"])
                self.assertEqual(self.service.selected["photoUrls"], [])
                self.assertNotIn("/preview/", self.service.selected["previewUrl"])
                photos = media.property("photos")
                if hasattr(photos, "toVariant"):
                    photos = photos.toVariant()
                self.assertEqual(photos, [self.service.selected["previewUrl"]])
                client.release_catalog.set()
                self.settle()

        def test_preview_fixture_without_hook_is_guarded(self):
            self.service.close()
            self.service = CommunityPreviewService(UI.parent, self.temp.name)
            self.service.timer.stop()
            self.open_page(live=False)
            self.view.rootObject().setProperty("visible", False)
            self.view.rootObject().setProperty("visible", True)
            self.view.engine().rootContext().setContextProperty("communityGalleryMode", True)
            self.view.rootObject().setProperty("visible", False)
            self.view.setSource(QUrl())
            self.assertFalse(any("setViewActive" in warning for warning in self.warnings), self.warnings)

    return unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VisibilityTests)).wasSuccessful()


class GalleryVisibilityNativeTests(unittest.TestCase):
    def test_native_hidden_return_and_destruction(self):
        result = subprocess.run([sys.executable, "-I", "-B", __file__, "--native"],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
            capture_output=True, text=True, encoding="utf-8", timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 5 tests", result.stderr)
        print("PASS: 5 real-QML Community visibility, image scheduling and pending-expiry cases")


if __name__ == "__main__":
    if "--native" in sys.argv:
        raise SystemExit(0 if native() else 1)
    unittest.main()
