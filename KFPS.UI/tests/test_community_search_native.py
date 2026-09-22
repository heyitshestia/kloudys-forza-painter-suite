"""Exercise the real Community page with keyboard and input-method events."""
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]

def native():
    from PySide6.QtCore import QObject, Qt, QUrl, Signal
    from PySide6.QtGui import QFontDatabase, QInputMethodEvent
    from PySide6.QtQml import QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from kfps_ui.community_preview_service import CommunityPreviewService
    from kfps_ui.community_gallery_service import CommunityGalleryService
    from kfps_ui.theme_catalog import THEME_PRESETS

    APP = QApplication.instance() or QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf", "tahoma.ttf", "malgun.ttf"):
        font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))


    class LocalClient:
        token = ""

        def __init__(self):
            self.requests = []
            self.old_started = threading.Event()
            self.release_old = threading.Event()

        def json(self, path, **kwargs):
            query = parse_qs(urlparse(path).query).get("search", [""])[0]
            self.requests.append(query)
            if query == "old":
                self.old_started.set()
                if not self.release_old.wait(5):
                    raise TimeoutError("Test did not release delayed response")
            return {"items": [], "page": 1, "page_count": 1, "total": 99 if query == "old" else 0}


    class LocalCommunity(QObject):
        changed = Signal()
        catalogInvalidated = Signal()
        username = ""
        authenticated = False
        usernameRequired = False
        supporterAccess = False
        sessionUser = {}
        errorMessage = ""
        statusMessage = ""

        def __init__(self, root):
            super().__init__()
            self.paths = SimpleNamespace(runtime_root=Path(root))
            self.client = LocalClient()

        def sessionClient(self):
            return self.client


    class CommunitySearchTests(unittest.TestCase):
        live = False

        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.community = LocalCommunity(self.temp.name)
            if self.live:
                self.service = CommunityGalleryService(UI.parent, self.community, SimpleNamespace(communityLanguage="en"))
            else:
                self.service = CommunityPreviewService(UI.parent, self.temp.name)
            self.service.timer.stop()
            self.view = QQuickView()
            self.view.setResizeMode(QQuickView.SizeRootObjectToView)
            self.view.setFlags(Qt.Tool | Qt.WindowDoesNotAcceptFocus)
            self.view.resize(1400, 820)
            engine = self.view.engine()
            engine.addImportPath(str(UI / "qml"))
            context = engine.rootContext()
            context.setContextProperty("preview", self.service)
            context.setContextProperty("communityGalleryMode", self.live)
            context.setContextProperty("communityService", dict(authenticated=False, authenticationInProgress=False,
                usernameRequired=False, username="", githubUserCode="", supporterAccess=False,
                errorMessage="", statusMessage=""))
            context.setContextProperty("assetRoot", QUrl.fromLocalFile(str(UI / "assets")).toString())
            context.setContextProperty("screenshotMode", True)
            self.view.setSource(QUrl.fromLocalFile(str(UI / "qml/community-preview/CommunityPreview.qml")))
            self.assertIsNotNone(self.view.rootObject(), str(self.view.errors()))
            self.view.show()
            self.field = self.view.rootObject().findChild(QObject, "CommunitySearch")
            self.assertIsNotNone(self.field)
            self.field.forceActiveFocus()
            QTest.qWait(30)
            self.settle()
            self.community.client.requests.clear()

        def tearDown(self):
            self.community.client.release_old.set()
            self.view.close()
            self.view.setSource(QUrl())
            self.service.close()
            self.temp.cleanup()

        def settle(self):
            for _ in range(200):
                if not self.service.busy:
                    return
                QTest.qWait(10)
            self.fail("Gallery did not finish its local request")

        def expression(self, code, item=None):
            item = item or self.view.rootObject()
            expression = QQmlExpression(QQmlEngine.contextForObject(item), item, code)
            value, _ = expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            return value

        def type_text(self, text, delay=20):
            for char in text:
                QTest.keyClick(self.view, Qt.Key(ord(char.upper())))
                self.service.changed.emit()
                QTest.qWait(delay)

        def finish_search(self, expected):
            QTest.qWait(450)
            self.settle()
            self.assertEqual(self.field.property("text"), expected)
            self.assertEqual(self.service.filters["search"], expected)

        def test_background_notifications_do_not_erase_fast_typing(self):
            expected = ""
            for char in "createinsane":
                QTest.keyClick(self.view, Qt.Key(ord(char.upper())))
                expected += char
                self.service.changed.emit()
                QTest.qWait(20)
                self.assertEqual(self.field.property("text"), expected)
            self.finish_search(expected)
            if self.live:
                self.assertEqual(self.community.client.requests, [expected])

        def test_paused_and_slow_typing_survive_refreshes(self):
            self.type_text("crea")
            self.finish_search("crea")
            self.type_text("teinsane", delay=340)
            self.finish_search("createinsane")

        def test_backspace_middle_edit_selection_and_undo(self):
            self.type_text("createinsane")
            for _ in range(3):
                QTest.keyClick(self.view, Qt.Key_Backspace)
                self.service.changed.emit()
            self.finish_search("createins")
            QTest.keyClick(self.view, Qt.Key_Home)
            QTest.keyClick(self.view, Qt.Key_Right)
            self.type_text("x")
            self.finish_search("cxreateins")
            QTest.keyClick(self.view, Qt.Key_Z, Qt.ControlModifier)
            self.service.changed.emit()
            self.finish_search("createins")
            QTest.keyClick(self.view, Qt.Key_A, Qt.ControlModifier)
            self.type_text("logo")
            self.finish_search("logo")
            QTest.keyClick(self.view, Qt.Key_A, Qt.ControlModifier)
            QTest.keyClick(self.view, Qt.Key_Backspace)
            self.finish_search("")

        def test_paste_and_enter_search_once(self):
            clipboard = APP.clipboard()
            previous = clipboard.text()
            try:
                text = "vinyl " + "\ud55c\uae00" + " tag"
                clipboard.setText(text)
                QTest.keyClick(self.view, Qt.Key_V, Qt.ControlModifier)
                self.service.changed.emit()
                self.assertEqual(self.field.property("text"), text)
                QTest.keyClick(self.view, Qt.Key_Return)
                self.assertEqual(self.service.filters["search"], text)
                self.finish_search(text)
                if self.live:
                    self.assertEqual(self.community.client.requests, [text])
            finally:
                clipboard.setText(previous)

        def test_korean_preedit_waits_for_commit(self):
            self.type_text("tag")
            event = QInputMethodEvent("\ud55c", [])
            APP.sendEvent(self.field, event)
            self.assertTrue(self.field.property("inputMethodComposing"))
            for _ in range(5):
                self.service.changed.emit()
                QTest.qWait(90)
            self.assertEqual(self.service.filters["search"], "")
            self.assertEqual(self.field.property("text"), "tag")
            self.assertEqual(self.field.property("preeditText"), "\ud55c")
            commit = QInputMethodEvent()
            commit.setCommitString("\ud55c\uae00")
            APP.sendEvent(self.field, commit)
            self.finish_search("tag\ud55c\uae00")

        def test_cancelled_composition_does_not_submit_preedit(self):
            APP.sendEvent(self.field, QInputMethodEvent("\ud55c", []))
            self.service.changed.emit()
            QTest.qWait(400)
            APP.sendEvent(self.field, QInputMethodEvent())
            self.finish_search("")
            if self.live:
                self.assertEqual(self.community.client.requests, [])

        def test_explicit_reset_cancels_unsubmitted_draft(self):
            self.type_text("draft")
            self.assertEqual(self.service.filters["search"], "")
            self.service.searchReset.emit("")
            self.finish_search("")
            if self.live:
                self.assertEqual(self.community.client.requests, [])

        def test_backend_query_change_is_still_reflected(self):
            self.type_text("draft")
            self.service.filter("search", "replacement")
            self.finish_search("replacement")

        def test_successful_upload_or_creator_navigation_resets_pending_text(self):
            self.type_text("draft")
            if self.live:
                self.community._app_version = "test"
                self.service._pending = {"kind": "vinyl"}
                with patch.object(self.service, "_call") as call:
                    self.service.publish({})
                call.call_args.args[1]({"id": "local-test"})
            else:
                self.service.creator_value = "LocalArtist"
                self.service.browseCreator()
            self.finish_search("")

        def test_theme_changes_and_focus_loss_preserve_draft(self):
            for theme in THEME_PRESETS:
                with self.subTest(theme=theme.name):
                    self.expression("Theme.supporterUnlocked=true; Theme.themeName=" + repr(theme.name))
                    QTest.keyClick(self.view, Qt.Key_A, Qt.ControlModifier)
                    self.type_text("createinsane", delay=5)
                    self.field.setProperty("cursorPosition", 4)
                    self.service.changed.emit()
                    self.assertEqual(self.field.property("cursorPosition"), 4)
                    QTest.keyClick(self.view, Qt.Key_Tab)
                    self.service.changed.emit()
                    self.finish_search("createinsane")
                    evidence = os.environ.get("KFPS_SEARCH_EVIDENCE")
                    if evidence:
                        target = Path(evidence)
                        target.mkdir(parents=True, exist_ok=True)
                        image = self.view.grabWindow()
                        self.assertFalse(image.isNull())
                        self.assertGreaterEqual(image.width(), 1400)
                        self.assertGreaterEqual(image.height(), 820)
                        self.assertTrue(image.save(str(target / (str(self.live) + "-" + theme.qml_component + ".png"))))
                    self.field.forceActiveFocus()

        def test_reopening_page_restores_applied_query(self):
            self.type_text("saved")
            self.finish_search("saved")
            source = self.view.source()
            self.view.setSource(QUrl())
            self.view.setSource(source)
            self.field = self.view.rootObject().findChild(QObject, "CommunitySearch")
            self.assertEqual(self.field.property("text"), "saved")


    class LiveCommunitySearchTests(CommunitySearchTests):
        live = True

        def test_old_response_cannot_replace_new_query_or_results(self):
            self.service.filter("search", "old")
            self.assertTrue(self.community.client.old_started.wait(1))
            QTest.keyClick(self.view, Qt.Key_A, Qt.ControlModifier)
            self.type_text("new")
            QTest.keyClick(self.view, Qt.Key_Return)
            QTest.qWait(80)
            self.type_text("draft")
            self.community.client.release_old.set()
            QTest.qWait(80)
            self.assertEqual(self.field.property("text"), "newdraft")
            self.finish_search("newdraft")
            self.assertEqual(self.service.totalCount, 0)

    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(CommunitySearchTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(LiveCommunitySearchTests),
    ])
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


class CommunitySearchNativeTests(unittest.TestCase):
    def test_native_input_and_live_adapter_regressions(self):
        result = subprocess.run([sys.executable, '-B', __file__, '--native'],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONUTF8': '1'},
            capture_output=True, text=True, encoding='utf-8', timeout=240,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Ran 23 tests', result.stderr)
        print('PASS: 23 native Community input cases, both adapters and nine themes')


if __name__ == '__main__':
    if '--native' in sys.argv:
        sys.exit(0 if native() else 1)
    unittest.main()
