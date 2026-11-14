"""Failure and image-provider teardown coverage for the real native fixture."""
from __future__ import annotations

import faulthandler
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "tests"), str(UI / "src"), str(UI.parent)]


def native():
    from PySide6.QtCore import QCoreApplication, QEvent, QUrl, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtWidgets import QApplication
    import shiboken6
    import test_community_verified_native as verified
    from kfps_ui.community_gallery_images import GalleryImages

    app = QApplication.instance() or QApplication([])

    class SuiteCaptured(Exception):
        pass

    captured = []

    def capture(_runner, suite):
        captured.extend(suite)
        raise SuiteCaptured()

    with patch.object(unittest.TextTestRunner, "run", capture):
        try:
            verified.native()
        except SuiteCaptured:
            pass
    fixture_class = type(captured[0])
    method = captured[0]._testMethodName

    class LifecycleTests(unittest.TestCase):
        def setUp(self):
            self.case = fixture_class(method)
            self.previous_handler = qInstallMessageHandler(self.handler)
            self.addCleanup(qInstallMessageHandler, self.previous_handler)
            self.addCleanup(self.recover)

        @staticmethod
        def handler(kind, context, message):
            # Retain warnings in subprocess output, including expected offscreen GL.
            print(message, file=sys.stderr, flush=True)

        def recover(self):
            case = self.case
            if getattr(case, "view", None) is not None:
                case.close_view()
            fixture = getattr(case, "fixture", None)
            if fixture is not None:
                fixture.peer.release_session.set()
                gallery = getattr(fixture, "gallery", None)
                if gallery is not None:
                    gallery.close()
                fixture.service.close()
                fixture.peer.close()
                fixture.endpoint.stop()
                fixture.temp.cleanup()
                fixture.doCleanups()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

        def run_case(self):
            result = unittest.TestResult()
            self.case.run(result)
            return result

        def assert_released(self):
            fixture = self.case.fixture
            self.assertTrue(fixture.service._closed, "service survived failed setup")
            self.assertFalse(fixture.peer.thread.is_alive(), "fixture server survived")
            self.assertFalse(Path(fixture.temp.name).exists(), "fixture directory survived")
            executors = [fixture.service._executor]
            if getattr(fixture, "gallery", None) is not None:
                self.assertTrue(fixture.gallery._closed)
                executors += [fixture.gallery._executor, fixture.gallery._image_executor]
            self.assertFalse([t.name for pool in executors for t in pool._threads if t.is_alive()])
            self.assertEqual(len(QGuiApplication.allWindows()), 0)
            current = qInstallMessageHandler(self.handler)
            self.assertIs(current, self.handler, "native message handler was not restored")

        def test_bootstrap_assertion_releases_partial_fixture(self):
            with patch("test_community_policy_service.settle", return_value=False):
                result = self.run_case()
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.errors, [])
            self.assert_released()

        def test_preview_failure_releases_started_fixture(self):
            with patch("kfps_ui.community_validation.inspect_upload", side_effect=RuntimeError("injected preview failure")):
                result = self.run_case()
            self.assertEqual(len(result.errors), 1)
            self.assertIn("injected preview failure", result.errors[0][1])
            self.assert_released()

        def test_open_view_failure_releases_view_provider_and_handler(self):
            original = fixture_class.open_view
            views = []

            def fail_after_open(case, *args, **kwargs):
                original(case, *args, **kwargs)
                views.append(case.view)
                raise RuntimeError("injected view failure")

            with patch.object(fixture_class, "open_view", fail_after_open):
                result = self.run_case()
            self.assertEqual(len(result.errors), 1)
            self.assertIn("injected view failure", result.errors[0][1])
            self.assert_released()
            self.assertFalse(shiboken6.isValid(views[0]))

        def test_close_view_destroys_engine_before_return(self):
            def body():
                view = self.case.view
                engine = view.engine()
                self.case.close_view()
                self.assertFalse(shiboken6.isValid(view), "view destruction was deferred past cleanup")
                self.assertFalse(shiboken6.isValid(engine))

            setattr(self.case, method, body)
            result = self.run_case()
            self.assertEqual(result.errors + result.failures, [])
            self.assert_released()

        def test_cleanup_error_is_reported_without_skipping_other_resources(self):
            from kfps_ui.community_gallery_service import CommunityGalleryService
            original = CommunityGalleryService.close

            def fail_after_close(gallery):
                original(gallery)
                raise RuntimeError("injected cleanup failure")

            setattr(self.case, method, lambda: None)
            with patch.object(CommunityGalleryService, "close", fail_after_close):
                result = self.run_case()
            self.assertEqual(len(result.errors), 1)
            self.assertIn("injected cleanup failure", result.errors[0][1])
            self.assert_released()

        def test_close_with_inflight_async_image_provider(self):
            entered, release, finished = threading.Event(), threading.Event(), threading.Event()
            expired = []

            class HeldImages(GalleryImages):
                def requestImage(self, ident, size, requested_size):
                    if ident != "teardown-probe":
                        return super().requestImage(ident, size, requested_size)
                    entered.set()
                    if not release.wait(3):
                        expired.append(True)
                    try:
                        return super().requestImage(ident, size, requested_size)
                    finally:
                        finished.set()

            self.addCleanup(release.set)

            def body():
                view = self.case.view
                component = QQmlComponent(view.engine())
                component.setData(b'import QtQuick\nImage { asynchronous: true; cache: false; '
                                  b'source: "image://community-gallery/teardown-probe" }', QUrl())
                item = component.create(view.engine().rootContext())
                self.assertIsNotNone(item, str(component.errors()))
                item.setParent(view.contentItem())
                item.setParentItem(view.contentItem())
                self.assertTrue(entered.wait(1), "real QML did not request its provider")
                # The independent releaser lets actual engine teardown overlap the
                # provider callback without relying on main-thread event delivery.
                releaser = threading.Timer(0.05, release.set)
                releaser.start()
                try:
                    self.case.close_view()
                finally:
                    release.set()
                    releaser.join(1)
                self.assertTrue(finished.wait(1))
                self.assertEqual(expired, [], "provider barrier reached its fail-safe bound")
                self.assertFalse(shiboken6.isValid(view))

            setattr(self.case, method, body)
            with patch("kfps_ui.community_gallery_service.GalleryImages", HeldImages):
                result = self.run_case()
            self.assertEqual(result.errors + result.failures, [])
            self.assert_released()

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests)
    only = os.environ.get("KFPS_COMMUNITY_LIFECYCLE_CASE")
    if only:
        suite = unittest.TestSuite(test for test in suite if test._testMethodName == only)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


class NativeLifecycleHarnessTests(unittest.TestCase):
    def test_native_fixture_failure_and_provider_lifetimes(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        try:
            result = subprocess.run([sys.executable, "-I", "-B", __file__, "--native"], env=env,
                                    capture_output=True, text=True, encoding="utf-8", timeout=40,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            self.fail("Community lifecycle child timed out: " + repr((exc.stdout, exc.stderr)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    if "--native" in sys.argv:
        faulthandler.dump_traceback_later(10, repeat=True)
        raise SystemExit(native())
    unittest.main()
