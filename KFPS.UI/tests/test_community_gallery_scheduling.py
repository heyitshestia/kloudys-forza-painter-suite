"""Local-only regressions for timed releases and obsolete gallery requests."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
from threading import Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]
from PySide6.QtCore import QCoreApplication, QObject, Signal
from kfps_ui.community_client import CommunityApiError
from kfps_ui.community_gallery_service import CommunityGalleryService
from test_community_gallery import solid_png

APP = QCoreApplication.instance() or QCoreApplication([])


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def record(ident="art", **extra):
    return dict(id=ident, kind="vinyl", title=ident, status="published",
                creator={"username": "Owner"}, thumbnail_url=f"images/{ident}", **extra)


class LocalClient:
    token = "account-a"

    def __init__(self):
        self.items = []
        self.calls, self.images = [], []
        self.lock = Lock()
        self.release_images, self.image_started = Event(), Event()
        self.release_images.set()
        self.release_catalog, self.catalog_started = Event(), Event()
        self.release_catalog.set()
        self.release_action, self.action_started = Event(), Event()
        self.release_action.set()
        self.image_error = self.catalog_error = None
        self.png = solid_png("blue")

    def json(self, path, method="GET", payload=None, **kwargs):
        with self.lock:
            self.calls.append((path, method))
        if method == "POST":
            self.action_started.set()
            if not self.release_action.wait(5):
                raise TimeoutError("Local action watchdog")
            return {"vote": 1, "vote_score": 1}
        if path.startswith("creators/"):
            return {"creator": {"username": path.split("/")[-1]}}
        if path == "profile/ignored":
            return {"items": []}
        self.catalog_started.set()
        if not self.release_catalog.wait(5):
            raise TimeoutError("Local catalog watchdog")
        if self.catalog_error:
            raise self.catalog_error
        return {"items": [dict(item) for item in self.items], "page": 1,
                "page_count": 1, "total": len(self.items)}

    def binary(self, path, **kwargs):
        with self.lock:
            self.images.append(path)
        self.image_started.set()
        if not self.release_images.wait(5):
            raise TimeoutError("Local image watchdog")
        if self.image_error:
            raise self.image_error
        return self.png, {}


class LocalCommunity(QObject):
    changed = Signal()
    catalogInvalidated = Signal()
    username = "Owner"
    authenticated = True
    usernameRequired = False
    policyMode = "legacy_supporter"
    policyReady = True
    restrictedAccess = False
    claimsEnabled = True
    claimsView = True
    _app_version = "test"
    sessionUser = {}
    errorMessage = statusMessage = ""

    def __init__(self, root):
        super().__init__()
        self.paths = SimpleNamespace(runtime_root=Path(root))
        self.client = LocalClient()
        self.refreshAccount = Mock()
        self.refreshSupporterEntitlement = Mock()
        self.acceptGalleryDownload = Mock()
        self.download_started, self.release_download = Event(), Event()
        self.release_download.set()

    def sessionClient(self):
        return self.client

    def accessSnapshot(self):
        return (self.client.token, self.username, self.policyMode, self.restrictedAccess)

    def setClaimsView(self, enabled):
        self.claimsView = enabled

    def downloadGalleryVinyl(self, item, client):
        self.download_started.set()
        if not self.release_download.wait(5):
            raise TimeoutError("Local download watchdog")
        return {"path": "synthetic-only", "title": item["title"]}


class GallerySchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gallery-r5r7-", dir=os.environ.get("KFPS_GALLERY_TEST_ROOT"))
        self.community = LocalCommunity(self.temp.name)
        self.client = self.community.client
        self.service = CommunityGalleryService(UI.parent, self.community, SimpleNamespace(communityLanguage="en"))
        self.service.timer.stop()
        # Keep direct service tests equivalent to an attached visible QML page.
        self.service.setViewActive(True)
        self.settle()
        self.client.calls.clear()

    def tearDown(self):
        self.client.release_images.set()
        self.client.release_catalog.set()
        self.client.release_action.set()
        self.community.release_download.set()
        self.service.close()
        APP.processEvents()
        self.temp.cleanup()

    def wait_for(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            APP.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail("Local gallery operation did not settle")

    def settle(self):
        self.wait_for(lambda: not self.service.busy and not self.service._catalog_loading
                      and not self.service._creator_loading)

    def load(self, items):
        self.client.items = items
        self.service.refresh()
        self.settle()
        self.client.calls.clear()

    def catalog_calls(self):
        return [path for path, method in self.client.calls if path.startswith("artworks?")]

    def request_images(self, count=24):
        for index in range(count):
            item = record(f"old-{index}")
            self.service._records[item["id"]] = item
            url = self.service._image_url(item, "thumbnail", item["thumbnail_url"])
            self.service._request_image(url.split("image://community-gallery/", 1)[1].split("?", 1)[0])

    def test_repeated_expired_claim_history_does_not_refresh_or_clear_selection(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=2000):
            self.load([record(starts_at=stamp(1000), ends_at=stamp(1500))])
            selected = self.service.selected
            for _ in range(5):
                self.service._tick()
                self.settle()
            self.assertEqual(self.catalog_calls(), [])
            self.community.refreshAccount.assert_not_called()
            self.assertEqual(self.service.selected, selected)
            self.assertEqual([row["id"] for row in self.service.rows], ["art"])

    def test_upcoming_owner_preview_keeps_server_granted_access(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000):
            self.load([record(starts_at=stamp(1010), ends_at=stamp(1020), preview_url="preview/art")])
            self.assertEqual(self.service.selected["state"], "upcoming")
            self.assertTrue(self.service.selected["canViewMedia"])
            self.assertIn("/preview/", self.service.selected["previewUrl"])

    def test_hidden_view_defers_expiry_and_show_catches_up_immediately_once(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(900), ends_at=stamp(1010))])
            self.service.setViewActive(False)
            now.return_value = 1011
            for _ in range(4):
                self.service._tick()
                self.settle()
            self.assertEqual(self.catalog_calls(), [])
            self.community.refreshAccount.assert_not_called()
            self.service.setViewActive(True)
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.assertEqual(self.service.selected["state"], "expired")
            self.assertEqual(self.service.selected["id"], "art")
            self.service.setViewActive(True)
            self.service._tick()
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)

    def test_hidden_renderer_expires_even_while_catalog_request_is_slow(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(900), ends_at=stamp(1010))])
            renderer = Mock()
            self.service._render_session, self.service._render_id = renderer, "art"
            self.service.setViewActive(False)
            self.client.release_catalog.clear()
            self.client.catalog_started.clear()
            self.service.refresh()
            self.assertTrue(self.client.catalog_started.wait(1))
            now.return_value = 1011
            for _ in range(3):
                self.service._tick()
            renderer.close.assert_called_once()
            self.assertIsNone(self.service._render_session)
            self.assertEqual(len(self.catalog_calls()), 1)
            self.community.refreshAccount.assert_not_called()
            self.client.release_catalog.set()
            self.settle()
            self.service.setViewActive(True)
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 2)

    def test_hiding_page_does_not_cancel_explicit_download_or_upload(self):
        self.load([record()])
        self.community.release_download.clear()
        self.service.download()
        self.assertTrue(self.community.download_started.wait(1))
        self.service.setViewActive(False)
        self.community.release_download.set()
        self.settle()
        self.community.acceptGalleryDownload.assert_called_once()
        self.service._pending = {"kind": "vinyl", "payload": b'{"shapes": []}', "preview": self.client.png}
        self.client.release_action.clear()
        self.service.publish({"title": "local", "rights": True})
        self.assertTrue(self.client.action_started.wait(1))
        self.service.setViewActive(False)
        self.client.release_action.set()
        self.settle()
        self.assertIsNone(self.service._pending)

    def test_hidden_late_render_result_cannot_open_after_expiry(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            item = record(starts_at=stamp(900), ends_at=stamp(1010))
            item["kind"] = "livery"
            self.load([item])
            self.client.release_action.clear()
            def fetch(*args):
                self.client.action_started.set()
                if not self.client.release_action.wait(5):
                    raise TimeoutError("Local render watchdog")
                return b"synthetic render result"
            with patch.object(self.service, "_livery_payload", side_effect=fetch), \
                    patch("kfps_ui.community_preview_livery.PreviewLiverySession") as renderer:
                self.service.openRender()
                self.assertTrue(self.client.action_started.wait(1))
                self.service.setViewActive(False)
                now.return_value = 1011
                self.service._tick()
                self.client.release_action.set()
                self.settle()
                renderer.assert_not_called()

    def test_upcoming_and_expiry_each_refresh_once_and_retain_claim_history(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(1010), ends_at=stamp(1020))])
            for seconds, expected, state in ((1010, 1, "available"), (1015, 1, "available"),
                                              (1020, 2, "expired"), (1030, 2, "expired")):
                now.return_value = seconds
                for _ in range(3):
                    self.service._tick()
                    self.settle()
                self.assertEqual(len(self.catalog_calls()), expected)
                self.assertEqual(self.service.selected["id"], "art")
                self.assertEqual(self.service.rows[0]["state"], state)
            self.assertEqual(self.community.refreshAccount.call_count, 2)

    def test_failed_expiry_refresh_is_not_retried_every_tick_and_history_is_retained(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(900), ends_at=stamp(1010))])
            self.client.catalog_error = OSError("offline fixture")
            now.return_value = 1011
            for _ in range(4):
                self.service._tick()
                self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.assertEqual(self.service.selected["id"], "art")
            self.assertEqual(self.service.rows[0]["state"], "expired")
            self.assertFalse(self.service.selected["downloadable"])

    def test_slow_transition_refresh_cannot_repeat_or_erase_history(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(900), ends_at=stamp(1010))])
            self.client.release_catalog.clear()
            self.client.catalog_started.clear()
            now.return_value = 1011
            self.service._tick()
            self.assertTrue(self.client.catalog_started.wait(1))
            for _ in range(3):
                self.service._tick()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.assertEqual(self.service.rows[0]["id"], "art")
            self.client.release_catalog.set()
            self.settle()
            self.service._tick()
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)

    def test_image_completion_cannot_hide_upcoming_transition_from_timer(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(1010), ends_at=stamp(1020))])
            now.return_value = 1011
            self.service._update_views("art")
            self.assertEqual(self.service.rows[0]["state"], "available")
            self.service._tick()
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.community.refreshAccount.assert_called_once()

    def test_transition_during_catalog_request_is_observed_once_after_result(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(1010), ends_at=stamp(1020))])
            self.client.release_catalog.clear()
            self.client.catalog_started.clear()
            self.service.refresh()
            self.assertTrue(self.client.catalog_started.wait(1))
            now.return_value = 1011
            self.service._tick()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.client.release_catalog.set()
            self.settle()
            for _ in range(3):
                self.service._tick()
                self.settle()
            self.assertEqual(len(self.catalog_calls()), 2)
            self.community.refreshAccount.assert_called_once()

    def test_expiry_is_enforced_before_pending_catalog_or_creator_reply(self):
        for owner in ("catalog", "creator"):
            for failed in (False, True):
                with self.subTest(owner=owner, failed=failed), patch(
                        "kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
                    self.client.catalog_error = None
                    self.service._creator_name = ""
                    self.load([record(f"{owner}-{failed}", starts_at=stamp(900), ends_at=stamp(1010),
                                      preview_url="previews/art", photo_urls=["photos/art"])])
                    self.community.refreshAccount.reset_mock()
                    self.client.release_catalog.clear()
                    self.client.catalog_started.clear()
                    if owner == "catalog":
                        self.service.refresh()
                    else:
                        self.service.viewCreator("Owner")
                    self.assertTrue(self.client.catalog_started.wait(1))
                    notices = Mock()
                    self.service.changed.connect(notices)
                    now.return_value = 1011
                    for _ in range(3):
                        self.service._tick()
                    for row in (self.service.rows[0], self.service.selected):
                        self.assertEqual(row["state"], "expired")
                        self.assertFalse(row["canViewMedia"])
                        self.assertFalse(row["canInteract"])
                        self.assertFalse(row["downloadable"])
                        self.assertEqual(row["photoUrls"], [])
                    self.assertNotIn("/preview/", self.service.selected["previewUrl"])
                    self.assertGreater(notices.call_count, 0)
                    self.service.changed.disconnect(notices)
                    self.service.vote(1)
                    self.service.report("expired")
                    self.assertFalse(any(method == "POST" for _, method in self.client.calls))
                    self.assertEqual(len(self.catalog_calls()), 1)
                    self.community.refreshAccount.assert_not_called()
                    self.client.catalog_error = OSError("held reply failed") if failed else None
                    self.client.release_catalog.set()
                    self.settle()
                    self.community.refreshAccount.assert_called_once()
                    expected = 2 if owner == "catalog" else 3
                    self.assertEqual(len(self.catalog_calls()), expected)
                    for _ in range(3):
                        self.service._tick()
                        self.settle()
                    self.assertEqual(len(self.catalog_calls()), expected)

    def test_pending_start_and_end_coalesce_and_hidden_completion_waits_for_show(self):
        with patch("kfps_ui.community_gallery_service.time.time", return_value=1000) as now:
            self.load([record(starts_at=stamp(1010), ends_at=stamp(1020))])
            self.client.release_catalog.clear()
            self.client.catalog_started.clear()
            self.service.refresh()
            self.assertTrue(self.client.catalog_started.wait(1))
            for seconds, state in ((1011, "available"), (1021, "expired")):
                now.return_value = seconds
                self.service._tick()
                self.assertEqual(self.service.selected["state"], state)
                self.assertEqual(len(self.catalog_calls()), 1)
            self.service.setViewActive(False)
            self.client.release_catalog.set()
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 1)
            self.community.refreshAccount.assert_not_called()
            self.service.setViewActive(True)
            self.settle()
            self.assertEqual(len(self.catalog_calls()), 2)
            self.community.refreshAccount.assert_called_once()

    def test_hidden_images_pause_running_results_stale_and_demand_resumes(self):
        self.client.release_images.clear()
        self.request_images(24)
        self.wait_for(lambda: len(self.client.images) == 4)
        self.service.setViewActive(False)
        self.request_images(25)
        self.client.release_images.set()
        self.wait_for(lambda: not self.service._image_jobs)
        self.assertEqual(len(self.client.images), 4)
        self.assertFalse(self.service._image_ready)
        self.assertEqual(self.service.images._bytes, 0)
        self.assertEqual(len(self.service._image_waiting), 25)
        self.service.setViewActive(True)
        self.wait_for(lambda: len(self.service._image_ready) == 25)
        self.assertEqual(len(self.client.images), 29)
        self.assertFalse(self.service._image_pending)

    def test_rapid_hide_show_rejects_prior_visibility_results_before_retry(self):
        self.client.release_images.clear()
        self.request_images(4)
        self.wait_for(lambda: len(self.client.images) == 4)
        futures = [job[0] for job in self.service._image_jobs.values()]
        self.service.setViewActive(False)
        self.client.release_images.set()
        for future in futures:
            future.result(timeout=1)
        self.client.release_images.clear()
        self.service.setViewActive(True)
        self.wait_for(lambda: len(self.client.images) == 8)
        self.assertFalse(self.service._image_ready)
        self.assertEqual(len(self.service._image_jobs), 4)
        self.client.release_images.set()
        self.wait_for(lambda: len(self.service._image_ready) == 4)

    def test_hide_cancels_queued_image_futures_and_hidden_errors_have_no_effect(self):
        self.service._image_executor.shutdown(wait=True)
        self.service._image_executor = ThreadPoolExecutor(max_workers=1)
        self.client.release_images.clear()
        self.client.image_error = CommunityApiError(401, "hidden", "Hidden image failure")
        self.request_images(24)
        self.assertTrue(self.client.image_started.wait(1))
        futures = [job[0] for job in self.service._image_jobs.values()]
        self.service.setViewActive(False)
        self.assertEqual(sum(future.cancelled() for future in futures), 3)
        self.client.release_images.set()
        self.wait_for(lambda: not self.service._image_jobs)
        self.assertEqual(len(self.client.images), 1)
        self.community.refreshAccount.assert_not_called()
        self.assertFalse(self.service.hasError)
        self.client.image_error = None
        self.service.setViewActive(True)
        self.wait_for(lambda: len(self.service._image_ready) == 24)

    def test_hidden_navigation_discards_old_demand_but_keeps_explicit_vote(self):
        self.load([record()])
        self.client.release_images.clear()
        self.request_images(24)
        self.wait_for(lambda: len(self.client.images) == 4)
        self.client.release_action.clear()
        self.service.vote(1)
        self.assertTrue(self.client.action_started.wait(1))
        self.service.setViewActive(False)
        self.service.filter("search", "new-hidden-view")
        self.wait_for(lambda: not self.service._catalog_loading)
        self.client.release_action.set()
        self.client.release_images.set()
        self.settle()
        self.wait_for(lambda: not self.service._image_jobs)
        self.assertEqual(self.service.selected["vote"], 1)
        key = self.service.rows[0]["previewUrl"].split("image://community-gallery/", 1)[1].split("?", 1)[0]
        self.service._request_image(key)
        self.assertEqual(len(self.client.images), 4)
        self.assertEqual(list(self.service._image_waiting), [key])
        self.service.setViewActive(True)
        self.wait_for(lambda: key in self.service._image_ready)
        self.assertEqual(len(self.client.images), 5)
        self.assertEqual(set(self.service._image_ready), {key})

    def test_slow_images_do_not_block_filter_or_vote_and_old_results_are_ignored(self):
        self.load([record()])
        self.client.release_images.clear()
        self.request_images()
        self.assertTrue(self.client.image_started.wait(1))
        self.service.filter("search", "new search")
        self.service.vote(1)
        self.assertTrue(self.client.action_started.wait(.5), "Vote waited behind speculative images")
        self.settle()
        self.assertIn("search=new+search", self.catalog_calls()[-1])
        self.assertLessEqual(len(self.client.images), 4)
        self.client.release_images.set()
        self.wait_for(lambda: not self.service._image_pending)
        for _ in range(10):
            APP.processEvents()
            time.sleep(.005)
        self.assertLessEqual(len(self.client.images), 4)
        self.assertFalse(any("old-" in key for key in self.service._image_ready))

    def test_current_image_backlog_drains_without_dropping_requested_images(self):
        self.request_images(24)
        self.wait_for(lambda: len(self.service._image_ready) == 24)
        self.assertEqual(len(self.client.images), 24)
        self.assertFalse(self.service._image_pending)

    def test_queued_image_futures_are_cancelled_and_running_future_stays_tracked(self):
        self.service._image_executor.shutdown(wait=True)
        self.service._image_executor = ThreadPoolExecutor(max_workers=1)
        self.client.release_images.clear()
        self.request_images(24)
        self.assertTrue(self.client.image_started.wait(1))
        futures = [job[0] for job in self.service._image_jobs.values()]
        self.assertEqual(len(futures), 4)
        self.assertEqual(len(self.service._image_waiting), 20)
        self.service.filter("search", "cancel obsolete")
        self.assertEqual(sum(future.cancelled() for future in futures), 3)
        self.assertEqual(sum(future.running() for future in futures), 1)
        self.assertEqual(len(self.service._image_jobs), 4)
        self.assertFalse(self.service._image_waiting)
        self.settle()
        self.assertEqual(len(self.service._image_jobs), 1)
        self.client.release_images.set()
        self.wait_for(lambda: not self.service._image_jobs)
        self.assertEqual(len(self.client.images), 1)

    def test_current_image_failure_releases_capacity_and_explicit_retry_works(self):
        self.client.image_error = OSError("offline image fixture")
        self.request_images(1)
        self.wait_for(lambda: not self.service._image_pending)
        self.assertFalse(self.service._image_jobs)
        self.assertFalse(self.service._image_ready)
        self.client.image_error = None
        self.service._request_image(next(iter(self.service._image_sources)))
        self.wait_for(lambda: len(self.service._image_ready) == 1)
        self.assertEqual(len(self.client.images), 2)

    def test_rapid_filters_cancel_queued_catalogs_without_cancelling_user_action(self):
        self.load([record()])
        self.client.release_catalog.clear()
        for index in range(4):
            self.service.filter("search", f"running-{index}")
            self.wait_for(lambda: len(self.catalog_calls()) == index + 1)
        self.service.vote(1)
        for index in range(12):
            self.service.filter("search", f"queued-{index}")
        self.assertEqual(len(self.catalog_calls()), 4)
        self.client.release_catalog.set()
        self.settle()
        self.assertEqual(len(self.catalog_calls()), 5)
        self.assertIn("search=queued-11", self.catalog_calls()[-1])
        self.assertTrue(self.client.action_started.is_set())
        self.assertEqual(sum(method == "POST" for _, method in self.client.calls), 1)

    def test_obsolete_image_failures_do_not_refresh_new_account_or_view(self):
        self.client.release_images.clear()
        self.client.image_error = CommunityApiError(401, "old", "Obsolete failure")
        self.request_images()
        self.assertTrue(self.client.image_started.wait(1))
        self.service.filter("search", "new")
        self.settle()
        self.client.release_images.set()
        for _ in range(30):
            APP.processEvents()
            time.sleep(.005)
        self.community.refreshAccount.assert_not_called()
        self.assertFalse(self.service.hasError)

    def test_account_switch_drops_old_images_but_new_images_can_load(self):
        self.client.release_images.clear()
        self.request_images()
        self.assertTrue(self.client.image_started.wait(1))
        self.client.token = "account-b"
        self.community.username = "Other"
        self.community.changed.emit()
        self.settle()
        self.client.release_images.set()
        self.load([record("new-account")])
        key = self.service.rows[0]["previewUrl"].split("image://community-gallery/", 1)[1].split("?", 1)[0]
        self.service._request_image(key)
        self.wait_for(lambda: key in self.service._image_ready)
        self.assertEqual(set(self.service._image_ready), {key})

    def test_logout_ignores_active_download_callback_without_cancelling_its_work(self):
        self.load([record()])
        self.community.release_download.clear()
        self.service.download()
        self.assertTrue(self.community.download_started.wait(1))
        self.client.token = ""
        self.community.username = ""
        self.community.authenticated = False
        self.community.changed.emit()
        self.community.release_download.set()
        self.settle()
        self.community.acceptGalleryDownload.assert_not_called()
        self.assertFalse(self.service.authenticated)

    def test_selection_change_rejects_old_preview_but_retains_catalog_images(self):
        self.load([record("first", preview_url="previews/first"), record("second", preview_url="previews/second")])
        thumbnail = self.service.rows[0]["previewUrl"].split("image://community-gallery/", 1)[1].split("?", 1)[0]
        preview = self.service.selected["previewUrl"].split("image://community-gallery/", 1)[1].split("?", 1)[0]
        self.client.release_images.clear()
        self.service._request_image(preview)
        self.service._request_image(thumbnail)
        self.assertTrue(self.client.image_started.wait(1))
        self.service.select("second")
        self.client.release_images.set()
        self.wait_for(lambda: not self.service._image_jobs)
        self.assertNotIn(preview, self.service._image_ready)
        self.assertIn(thumbnail, self.service._image_ready)
        self.assertEqual(self.service.selected["id"], "second")

    def test_filter_does_not_cancel_active_download(self):
        self.load([record()])
        self.community.release_download.clear()
        self.service.download()
        self.assertTrue(self.community.download_started.wait(1))
        self.service.filter("search", "during download")
        self.community.release_download.set()
        self.settle()
        self.community.acceptGalleryDownload.assert_called_once()

    def test_filter_does_not_cancel_active_upload(self):
        self.service._pending = {"kind": "vinyl", "payload": b'{"shapes": []}', "preview": self.client.png}
        self.client.release_action.clear()
        self.service.publish({"title": "local", "rights": True})
        self.assertTrue(self.client.action_started.wait(1))
        self.service.filter("search", "during upload")
        self.client.release_action.set()
        self.settle()
        self.assertIsNone(self.service._pending)
        self.assertEqual(self.service.scope, "My uploads")

    def test_creator_navigation_discards_obsolete_creator_images(self):
        self.client.items = [record("first")]
        self.service.viewCreator("First")
        self.settle()
        key = self.service._creator_rows[0]["previewUrl"].split("image://community-gallery/", 1)[1].split("?", 1)[0]
        self.client.release_images.clear()
        self.service._request_image(key)
        self.assertTrue(self.client.image_started.wait(1))
        self.client.items = [record("second")]
        self.service.viewCreator("Second")
        self.settle()
        self.client.release_images.set()
        for _ in range(20):
            APP.processEvents()
            time.sleep(.005)
        self.assertNotIn(key, self.service._image_ready)
        self.assertEqual(self.service.creatorProfile["username"], "Second")

    def test_close_cancels_queued_images_and_is_idempotent(self):
        self.client.release_images.clear()
        self.request_images()
        self.assertTrue(self.client.image_started.wait(1))
        self.client.release_images.set()
        self.service.close()
        self.service.close()
        APP.processEvents()
        self.assertLessEqual(len(self.client.images), 4)
        self.assertFalse(self.service._image_pending)
        self.assertFalse(self.service.busy)
        self.assertFalse(self.service.timer.isActive())


if __name__ == "__main__":
    unittest.main()
