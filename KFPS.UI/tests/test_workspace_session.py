"""Session metadata and retained-host integration; all windows stay offscreen."""
import json
import hashlib
import os
from contextlib import ExitStack
from pathlib import Path
import sys
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from _test_evidence import evidence_directory

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.environ.get("KFPS_SESSION_STUDIO_PROBE") == "1":
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --use-gl=angle --use-angle=swiftshader-webgl --enable-unsafe-swiftshader"

from PySide6.QtCore import QCoreApplication, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from shiboken6 import delete, isValid

from kfps_ui.app_controller import AppController
from kfps_ui.workspace_controller import WorkspaceController
from kfps_ui.workspace_host import WorkspaceWindow
from kfps_ui.workspace_session import (
    MAX_BYTES, SessionStore, STUDIO_SNAPSHOT, WorkspaceSession, reference, validate_manifest,
)


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
CAR = {"car_id": 123, "model_code": "Fixture_Car"}
PROJECT = "a" * 32


def manifest(enabled=False):
    return {"version": 1, "reopen": enabled, "page": "outputs", "surfaces": {
        "Editor": {"project": "Saved.fabric-project.json", "dirty": False},
        "Studio": {"car": dict(CAR), "project": PROJECT, "dirty": False},
    }}


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = SessionStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_off_and_exact_atomic_round_trip(self):
        self.assertFalse(self.store.read()["reopen"])
        self.assertFalse(self.store.path.exists())
        value = manifest(True)
        self.store.write(value)
        self.assertEqual(SessionStore(self.root).read(), value)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])
        self.assertNotIn("http", self.store.path.read_text())

    def test_schema_rejects_sources_urls_secrets_traversal_and_invalid_types(self):
        cases = [dict(manifest(), version=True), dict(manifest(), reopen="yes"),
                 dict(manifest(), page="liveries"), dict(manifest(), token="secret"),
                 dict(manifest(), page=[]),
                 dict(manifest(), surfaces={"Source abcdef12": {}})]
        for bad in ("../Saved.fabric-project.json", "C:/Saved.fabric-project.json",
                    "https://host/Saved.fabric-project.json", "a\\Saved.fabric-project.json",
                    "a//Saved.fabric-project.json", "./Saved.fabric-project.json"):
            cases.append(dict(manifest(), surfaces={"Editor": {"project": bad}}))
        cases.extend(dict(manifest(), surfaces={"Studio": value}) for value in (
            {"car": CAR, "project": "http://127.0.0.1/token/"},
            {"car": CAR, "returnUrl": "secret"}, {"car": dict(CAR, car_id=True)},
            {"car": dict(CAR, model_code="../car")}, {"car": CAR, "dirty": 1}))
        cases.extend(dict(manifest(), surfaces={"Editor": {"project": value}}) for value in (None, False, 0, []))
        for case in cases:
            with self.subTest(case=case), self.assertRaises((ValueError, TypeError)):
                validate_manifest(case)

    def test_corrupt_oversized_and_duplicate_fields_rejected(self):
        self.store.path.parent.mkdir(parents=True)
        for body in (b"{", b"x" * (MAX_BYTES + 1), b'{"version":1,"version":1}'):
            self.store.path.write_bytes(body)
            with self.assertRaises(ValueError):
                self.store.read()

    def test_failed_replace_keeps_original_and_cleans_temporary(self):
        self.store.write(manifest())
        before = self.store.path.read_bytes()
        with patch("kfps_ui.workspace_session.os.replace", side_effect=PermissionError), self.assertRaises(PermissionError):
            self.store.write(manifest(True))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_under_limit_deeply_nested_corruption_is_normalized_and_preserved(self):
        body = b"[" * 3000 + b"]" * 3000
        self.assertLess(len(body), MAX_BYTES)
        self.store.path.parent.mkdir(parents=True)
        self.store.path.write_bytes(body)
        with self.assertRaisesRegex(ValueError, "nested too deeply"):
            self.store.read()
        self.assertEqual(self.store.path.read_bytes(), body)

    def test_hardlinked_manifest_is_never_read_or_overwritten(self):
        self.store.write(manifest())
        other = self.root / "other.json"
        os.link(self.store.path, other)
        before = other.read_bytes()
        with self.assertRaises(ValueError):
            self.store.read()
        with self.assertRaises(ValueError):
            self.store.write(manifest(True))
        self.assertEqual(other.read_bytes(), before)

    def test_missing_project_never_falls_back_to_a_different_file(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.store.editor_path("Saved.fabric-project.json")
        folder = self.root / "runtime/fabric-editor/projects"
        folder.mkdir(parents=True)
        path = folder / "Saved.fabric-project.json"
        path.write_text("{}")
        self.assertEqual(self.store.editor_path(path.name), path)

    def test_explicit_runtime_root_isolates_manifest_and_editor_paths(self):
        runtime = self.root / "isolated/profile"
        store = SessionStore(self.root, runtime)
        store.write(manifest())
        self.assertEqual(store.path, runtime / "workspace/session.json")
        self.assertFalse((self.root / "runtime").exists())
        path = runtime / "fabric-editor/projects/Saved.fabric-project.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
        self.assertEqual(store.editor_path(path.name), path)


class Page(QObject):
    titleChanged = Signal(str)
    loadFinished = Signal(bool)
    loadStarted = Signal()
    urlChanged = Signal(QUrl)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.current_url = QUrl("http://127.0.0.1:12345/" + "a" * 43 + "/")

    def runJavaScript(self, script, callback=None):
        self.calls.append((script, callback))

    def title(self):
        return "Fixture"

    def url(self):
        return self.current_url

    def navigate(self, url):
        self.loadStarted.emit()
        self.current_url = QUrl(url)
        self.urlChanged.emit(self.current_url)
        self.loadFinished.emit(True)


class Owner(QObject):
    def __init__(self):
        super().__init__()
        self.page = Page()
        self.page.setParent(self)

    def shutdown(self):
        return True


class SessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = SessionStore(self.root)
        self.main = QWindow()
        self.shell = WorkspaceWindow(self.main, offscreen=True)
        self.service = Mock()
        self.app = AppController()
        self.controller = WorkspaceController(self.shell,
            SimpleNamespace(app_root=self.root, runtime_root=self.root / "runtime"),
            self.service, SimpleNamespace())
        self.owners = []

    def tearDown(self):
        self.controller.close()
        self.shell.shutdown()
        delete(self.shell)
        delete(self.main)
        delete(self.app)
        for owner in self.owners:
            delete(owner)
        self.temp.cleanup()

    def configure(self, enabled=False):
        self.store.write(manifest(enabled))
        self.controller.configure_session(None, self.app)
        return self.controller.session

    def owner(self, name):
        owner = Owner()
        self.owners.append(owner)
        self.shell.install_surface(name, QWidget(), owner)
        self.shell.show_surface(name, background=True)
        self.shell.show()
        return owner

    def test_qobject_contract_and_default_off_no_launch_or_page_navigation(self):
        session = self.configure()
        self.assertIsInstance(self.controller.property("session"), QObject)
        self.assertFalse(session.property("restoreEnabled"))
        self.assertTrue(session.property("previousAvailable"))
        self.assertEqual(self.app.currentPage, "create")
        self.assertEqual(self.shell._selected, "KFPS")
        self.assertEqual(session.staged, {})
        self.service.activate.assert_not_called()
        self.service.launchLiveryStudio.assert_not_called()
        self.service._launch.assert_not_called()
        session.setProperty("restoreEnabled", True)
        self.assertTrue(SessionStore(self.root).read()["reopen"])
        self.controller.configure_session(None, self.app)
        self.assertIs(self.controller.session, session)

    def test_existing_customizations_and_projects_survive_session_opt_in_and_restart(self):
        from kfps_ui.settings_service import SettingsService
        runtime = self.root / "runtime"
        existing = {
            "qml-shell-settings.json": {"theme": "Night City 2077", "editorUseChrome": True,
                "liveryUseChrome": True, "editorGraphics": "d3d11", "reducedMotion": True,
                "windowGeometry": {"x": 40, "y": 70, "width": 1600, "height": 900, "maximized": False}},
            "fabric-editor/preferences.json": {"theme": "custom-fixture", "settings": {
                "kloudyFabricFavorites": "[1048677,1048678]", "kloudyFabricLanguage": "ja",
                "kloudyFabricShortcuts": '{"undo":"Ctrl+Alt+Z"}'}},
            "fabric-editor/themes/custom-fixture.json": {"name": "Custom fixture", "base": "blackout",
                "values": {"--text": "#eeeeee"}},
            "fabric-editor/projects/Saved.fabric-project.json": {"objects": [], "name": "Saved"},
            "fabric-editor/recovery/retained.json": {"objects": [], "name": "Unsaved"},
        }
        original = {}
        for relative, payload in existing.items():
            path = runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            original[path] = path.read_bytes()
        settings = SettingsService(runtime / "qml-shell-settings.json")
        self.controller.configure_session(settings, self.app)
        session = self.controller.session
        self.assertFalse(session.restoreEnabled)
        self.assertEqual(settings.theme, "Night City 2077")
        self.assertTrue(settings.editorUseChrome and settings.liveryUseChrome)
        session.set_enabled(True)
        session.set_enabled(False)
        session.set_enabled(True)
        self.controller.close()
        self.assertTrue(SessionStore(self.root).read()["reopen"])
        restored = SettingsService(runtime / "qml-shell-settings.json")
        self.assertEqual(restored._data, settings._data)
        for path, body in original.items():
            self.assertEqual(path.read_bytes(), body, str(path.relative_to(runtime)))
        self.service.activate.assert_not_called()
        self.service.launchLiveryStudio.assert_not_called()
        self.service._launch.assert_not_called()
        settings.deleteLater()
        restored.deleteLater()

    def test_opt_in_and_manual_reopen_only_stage_placeholders(self):
        session = self.configure(True)
        self.assertEqual(set(session.staged), {"Editor", "Studio"})
        self.assertEqual(self.shell.owners, {})
        self.assertIn("Previous session", self.shell.surfaces["Editor"].text())
        self.assertEqual(self.shell._selected, "KFPS")
        self.service.launchLiveryStudio.assert_not_called()
        session.restoreEnabled = False
        self.assertEqual(session.staged, {})
        self.assertTrue(session.restorePrevious())
        self.assertFalse(session.restoreEnabled)

    def test_activation_uses_existing_editor_launch_only_when_selected(self):
        session = self.configure(True)
        path = self.root / "runtime/fabric-editor/projects/Saved.fabric-project.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
        self.shell.show_surface("Editor", background=True)
        self.service._launch.assert_called_once_with(str(path), "activate")
        self.service.launchLiveryStudio.assert_not_called()
        self.assertNotIn("Editor", session.staged)

    def test_missing_reference_is_reported_without_launch(self):
        session = self.configure(True)
        self.shell.show_surface("Editor", background=True)
        self.service._launch.assert_not_called()
        self.assertIn("missing", session.status)

    def test_newer_or_dirty_recovery_is_not_overridden_by_saved_project(self):
        session = self.configure()
        path = self.root / "runtime/fabric-editor/projects/Saved.fabric-project.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
        os.utime(path, ns=(1, 1))
        recovery = path.parent.parent / "autosave.json"
        recovery.write_text("{}")
        value = manifest()["surfaces"]["Editor"]
        self.assertEqual(session.editor_request(value), {"mode": "activate", "project": ""})
        self.assertIn("Newer", session.status)
        recovery.unlink()
        self.assertEqual(session.editor_request(dict(value, dirty=True))["project"], "")

    def test_explicit_open_overrides_staged_restore_and_keeps_live_owner(self):
        session = self.configure(True)
        session.explicit_open("Editor")
        self.assertNotIn("Editor", session.staged)
        owner = self.owner("Studio")
        self.assertFalse(session.restorePrevious() and "Studio" in session.staged)
        self.assertIs(self.shell.owners["Studio"], owner)
        self.assertFalse(any("?.restore(" in code for code, _ in owner.page.calls))

    def test_stale_callbacks_cannot_replace_current_reference_or_write_after_close(self):
        session = self.configure()
        owner = self.owner("Editor")
        marker = session.inflight["Editor"]
        session.explicit_open("Editor")
        session.accept("Editor", owner, marker, json.dumps({"project": "Old.fabric-project.json"}))
        self.assertNotEqual(session.current["Editor"].get("project"), "Old.fabric-project.json")
        session.capture()
        marker = session.inflight["Editor"]
        session.close()
        before = self.store.path.read_bytes()
        session.accept("Editor", owner, marker, json.dumps({"project": "Old.fabric-project.json"}))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_snapshot_records_only_allowlisted_metadata(self):
        session = self.configure()
        owner = self.owner("Editor")
        session.accept("Editor", owner, session.inflight["Editor"], json.dumps({"project": "New.fabric-project.json", "dirty": True}))
        self.assertEqual(self.store.read()["surfaces"]["Editor"], {"project": "New.fabric-project.json", "dirty": True})
        session.capture()
        session.accept("Editor", owner, session.inflight["Editor"], json.dumps({"project": "Bad.fabric-project.json", "secret": "token"}))
        self.assertNotIn("secret", self.store.path.read_text())

    def test_corrupt_manifest_preserved_until_explicit_preference_change(self):
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_bytes(b"broken")
        self.controller.configure_session(None, self.app)
        session = self.controller.session
        self.assertFalse(session.previousAvailable)
        session.persist()
        self.assertEqual(self.store.path.read_bytes(), b"broken")
        session.restoreEnabled = True
        self.assertTrue(self.store.read()["reopen"])

    def test_failed_preference_save_does_not_claim_enabled(self):
        session = self.configure()
        with patch.object(session.store, "write", side_effect=PermissionError):
            session.restoreEnabled = True
        self.assertFalse(session.restoreEnabled)
        self.assertIn("could not be saved", session.status)

    def test_deeply_nested_manifest_does_not_abort_startup_or_overwrite_evidence(self):
        body = b"[" * 3000 + b"]" * 3000
        self.assertLess(len(body), MAX_BYTES)
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_bytes(body)
        self.controller.configure_session(None, self.app)
        session = self.controller.session
        self.assertFalse(session.restoreEnabled)
        self.assertFalse(session.previousAvailable)
        self.assertTrue(session.blocked)
        self.assertIn("could not be read", session.status)
        session.capture()
        session.persist()
        session.restorePrevious()
        self.assertEqual(self.store.path.read_bytes(), body)
        session.restoreEnabled = True
        self.assertTrue(self.store.read()["reopen"])
        self.assertFalse(session.blocked)

    def test_retiring_tab_drops_reference_but_whole_close_preserves_it(self):
        session = self.configure()
        session.retired("Editor", True)
        self.assertIn("Editor", self.store.read()["surfaces"])
        session.retired("Editor", False)
        self.assertNotIn("Editor", self.store.read()["surfaces"])

    def studio_reply(self, session, owner, result=None, item=None):
        session.accept("Studio", owner, session.inflight["Studio"], json.dumps({
            "ready": True, "reference": item or manifest()["surfaces"]["Studio"], "restore": result}))

    def test_direct_bridge_dispatches_once_and_reads_authoritative_outcome(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner)
        restores = lambda: [code for code, _ in owner.page.calls if "?.restore(" in code]
        self.assertEqual(len(restores()), 1)
        self.assertIn(nonce, restores()[0])
        session.capture()
        self.studio_reply(session, owner, {"requestId": nonce, "state": "pending"})
        self.assertEqual(len(restores()), 1)
        session.capture()
        self.studio_reply(session, owner, {"requestId": nonce, "state": "restored"})
        self.assertNotIn("Studio", session.loading)
        self.assertIn("reopened", session.status)
        self.assertEqual(self.store.read()["surfaces"]["Studio"]["project"], PROJECT)
        self.assertEqual(session.timer.interval(), 30000)

    def test_explicit_open_cancels_matching_operation_and_ignores_late_result(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner)
        session.capture()
        marker = session.inflight["Studio"]
        session.explicit_open("Studio")
        self.assertIn('cancelRestore("' + nonce + '")', owner.page.calls[-1][0])
        session.accept("Studio", owner, marker, json.dumps({"ready": True, "reference": {
            "car": CAR, "project": "b" * 32, "dirty": False},
            "restore": {"requestId": nonce, "state": "restored"}}))
        self.assertEqual(session.current["Studio"]["project"], PROJECT)

    def test_package_request_cancels_delayed_studio_restore_before_launch(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner)
        session.capture()
        marker = session.inflight["Studio"]
        failures = []

        def request():
            try:
                self.controller.prepare_studio({"layout": {"format": "kfps-livery-layout-v1"}})
            except RuntimeError as error:
                failures.append(str(error))

        with patch("kfps_ui.workspace_controller._studio_module_path", side_effect=RuntimeError("launch boundary")):
            worker = threading.Thread(target=request)
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            APP.processEvents()
        self.assertEqual(failures, ["launch boundary"])
        self.assertTrue(any('cancelRestore("' + nonce + '")' in code for code, _ in owner.page.calls))
        self.assertNotIn("Studio", session.loading)
        session.accept("Studio", owner, marker, json.dumps({"ready": True, "reference": {
            "car": CAR, "project": "b" * 32, "dirty": False},
            "restore": {"requestId": nonce, "state": "restored"}}))
        self.assertEqual(session.current["Studio"]["project"], PROJECT)

    def test_blank_studio_launch_does_not_cancel_staged_restore(self):
        session = self.configure(True)
        with patch("kfps_ui.workspace_controller._studio_module_path", side_effect=RuntimeError("launch boundary")):
            with self.assertRaisesRegex(RuntimeError, "launch boundary"):
                self.controller.prepare_studio({})
        APP.processEvents()
        self.assertIn("Studio", session.staged)

    def test_no_inactive_poll_and_no_periodic_capture_when_off(self):
        session = self.configure()
        editor = self.owner("Editor")
        studio = self.owner("Studio")
        self.assertFalse(session.timer.isActive())
        session.inflight.clear()
        before = len(editor.page.calls)
        session.capture()
        self.assertEqual(len(editor.page.calls), before)
        self.assertEqual(studio.page.calls[-1][0], STUDIO_SNAPSHOT)
        session.restoreEnabled = True
        self.assertTrue(session.timer.isActive())
        self.assertEqual(session.timer.interval(), 30000)
        self.shell.hide()
        self.assertFalse(session.timer.isActive())
        self.shell.show()
        self.assertTrue(session.timer.isActive())
        self.shell.show_surface("KFPS", background=True)
        self.assertFalse(session.timer.isActive())
        counts = [len(owner.page.calls) for owner in (editor, studio)]
        session.capture()
        self.assertEqual(counts, [len(owner.page.calls) for owner in (editor, studio)])

    def test_native_cancel_allows_committed_car_navigation_without_restore_replay(self):
        session = self.configure()
        session.restorePrevious()
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner, item={"car": {"car_id": 456, "model_code": "Default_Car"}, "dirty": False})
        session.capture()
        stale = session.inflight["Studio"]
        self.controller.discardSessionRestore("Studio")
        self.assertIn('cancelRestore("' + nonce + '")', owner.page.calls[-1][0])
        self.assertFalse(session.timer.isActive())
        session.accept("Studio", owner, stale, json.dumps({"ready": True,
            "reference": manifest()["surfaces"]["Studio"],
            "restore": {"requestId": nonce, "state": "pending"}}))
        owner.page.navigate("http://127.0.0.1:12345/" + "b" * 43 + "/")
        self.studio_reply(session, owner, item={"car": CAR, "dirty": False})
        self.assertIs(self.shell.owners["Studio"], owner)
        self.assertEqual(sum("?.restore(" in code for code, _ in owner.page.calls), 1)
        self.assertEqual(session.current["Studio"], {"car": CAR, "dirty": False})
        for state in (session.loading, session.nonces, session.navigation, session.dispatched,
                      session.continuing, session.navigating, session.reloading):
            self.assertNotIn("Studio", state)
        self.assertFalse(session.timer.isActive())
        self.assertNotIn("http", self.store.path.read_text())

    def test_private_source_is_never_snapshotted_or_persisted(self):
        session = self.configure(True)
        source = self.owner("Source abcdef12")
        session.capture()
        session.capture("Source abcdef12")
        session.capture_close()
        self.assertEqual(source.page.calls, [])
        self.assertFalse(session.timer.isActive())
        self.assertNotIn("Source", self.store.path.read_text())

    def test_background_install_does_not_probe_or_restore_until_selected(self):
        session = self.configure(True)
        session.take("Studio")
        owner = Owner()
        self.owners.append(owner)
        self.shell.install_surface("Studio", QWidget(), owner)
        self.assertEqual(self.shell._selected, "KFPS")
        self.assertEqual(owner.page.calls, [])
        self.assertFalse(session.timer.isActive())
        self.shell.show_surface("Studio", background=True)
        self.assertEqual(owner.page.calls[-1][0], STUDIO_SNAPSHOT)

    def test_close_preparation_reads_metadata_without_starting_pending_restore(self):
        session = self.configure(True)
        session.take("Studio")
        owner = self.owner("Studio")
        self.shell._closing = True
        self.studio_reply(session, owner)
        self.assertFalse(any("?.restore(" in code for code, _ in owner.page.calls))
        self.assertFalse(session.timer.isActive())
        self.shell._closing = False

    def test_car_navigation_reissues_once_after_matching_ready_snapshot(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner, item={"car": {"car_id": 456, "model_code": "Default_Car"}, "dirty": False})
        restores = lambda: [code for code, _ in owner.page.calls if "?.restore(" in code]
        self.assertEqual(len(restores()), 1)
        session.capture()
        stale = session.inflight["Studio"]
        owner.page.navigate("http://127.0.0.1:12345/" + "b" * 43 + "/")
        session.accept("Studio", owner, stale, json.dumps({"ready": True, "reference": manifest()["surfaces"]["Studio"]}))
        self.assertEqual(len(restores()), 1)
        self.studio_reply(session, owner, item={"car": CAR, "dirty": False})
        self.assertEqual(len(restores()), 2)
        self.assertTrue(all(nonce in code for code in restores()))
        session.capture()
        self.studio_reply(session, owner, {"requestId": nonce, "state": "restored"})
        self.assertIn("reopened", session.status)
        self.assertNotIn("http", self.store.path.read_text())

    def test_car_navigation_rejects_wrong_origin_unexpected_path_and_second_transition(self):
        for target in ("http://127.0.0.1:45678/" + "b" * 43 + "/", "https://example.com/",
                       "http://127.0.0.1:12345/other/", "http://127.0.0.1:12345/" + "b" * 43 + "/?token=x"):
            with self.subTest(target=target):
                session = self.controller.session or self.configure(True)
                session.staged["Studio"] = dict(manifest()["surfaces"]["Studio"])
                session.take("Studio")
                owner = self.shell.owners.get("Studio") or self.owner("Studio")
                owner.page.current_url = QUrl("http://127.0.0.1:12345/" + "a" * 43 + "/")
                session.capture()
                self.studio_reply(session, owner)
                owner.page.navigate(target)
                self.assertNotIn("Studio", session.loading)
                self.assertIn("unexpectedly", session.status)
        session.staged["Studio"] = dict(manifest()["surfaces"]["Studio"])
        session.take("Studio")
        owner.page.current_url = QUrl("http://127.0.0.1:12345/" + "a" * 43 + "/")
        session.capture()
        self.studio_reply(session, owner)
        owner.page.navigate("http://127.0.0.1:12345/" + "b" * 43 + "/")
        self.studio_reply(session, owner)
        owner.page.navigate("http://127.0.0.1:12345/" + "c" * 43 + "/")
        self.assertNotIn("Studio", session.loading)

    def test_same_page_reload_and_wrong_car_after_navigation_never_replay(self):
        session = self.configure(True)
        session.take("Studio")
        owner = self.owner("Studio")
        self.studio_reply(session, owner)
        owner.page.navigate(owner.page.url().toString())
        self.assertNotIn("Studio", session.loading)
        session.staged["Studio"] = dict(manifest()["surfaces"]["Studio"])
        session.take("Studio")
        session.capture()
        self.studio_reply(session, owner)
        count = sum("?.restore(" in code for code, _ in owner.page.calls)
        owner.page.navigate("http://127.0.0.1:12345/" + "b" * 43 + "/")
        self.studio_reply(session, owner, item={"car": {"car_id": 789, "model_code": "Wrong_Car"}, "dirty": False})
        self.assertNotIn("Studio", session.loading)
        self.assertEqual(sum("?.restore(" in code for code, _ in owner.page.calls), count)

    def test_bridge_unavailable_is_bounded_and_never_drives_dom_or_fetch(self):
        session = self.configure(True)
        session.take("Studio")
        owner = self.owner("Studio")
        for _ in range(31):
            if "Studio" in session.inflight:
                session.accept("Studio", owner, session.inflight["Studio"], "null")
            session.capture()
        self.assertNotIn("Studio", session.loading)
        self.assertIn("did not finish", session.status)
        scripts = "\n".join(code for code, _ in owner.page.calls)
        for forbidden in ("fetch", "querySelector", ".click(", "__kfpsWorkspaceSession"):
            self.assertNotIn(forbidden, scripts)

    def test_failed_restore_preserves_previous_reference_and_reports_recovery(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner, {"requestId": nonce, "state": "missing"},
                          {"car": CAR, "dirty": False})
        self.assertNotIn("Studio", session.loading)
        self.assertIn("missing", session.status)
        self.assertEqual(session.current["Studio"]["project"], PROJECT)

    def test_restored_outcome_must_confirm_exact_reference(self):
        session = self.configure(True)
        session.take("Studio")
        nonce = session.nonces["Studio"]
        owner = self.owner("Studio")
        self.studio_reply(session, owner, {"requestId": nonce, "state": "restored"},
                          {"car": CAR, "project": "b" * 32, "dirty": False})
        self.assertNotIn("Studio", session.loading)
        self.assertIn("did not confirm", session.status)
        self.assertEqual(session.current["Studio"]["project"], PROJECT)

    def test_restart_reloads_preference_and_lazy_references_without_launch(self):
        session = self.configure()
        session.restoreEnabled = True
        owner = self.owner("Editor")
        session.accept("Editor", owner, session.inflight["Editor"], json.dumps({
            "project": "Restart.fabric-project.json", "dirty": True}))
        self.controller.close()
        second_shell = WorkspaceWindow(QWindow(), offscreen=True)
        second = WorkspaceController(second_shell, self.controller.paths, Mock(), SimpleNamespace())
        try:
            second.configure_session(None, self.app)
            self.assertTrue(second.session.restoreEnabled)
            self.assertEqual(second.session.staged["Editor"], {"project": "Restart.fabric-project.json", "dirty": True})
            self.assertEqual(second_shell.owners, {})
            self.assertEqual(second_shell._selected, "KFPS")
            second.service._launch.assert_not_called()
            second.service.launchLiveryStudio.assert_not_called()
            self.assertFalse(second.session.timer.isActive())
        finally:
            second.close()
            second_shell.shutdown()
            main = second_shell.main_window
            delete(second_shell)
            delete(main)


class EditorSessionProbeTests(unittest.TestCase):
    """Real local server, page, project receipts and retained close owner."""

    def wait(self, predicate, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail("Offscreen session probe timed out")

    def js(self, owner, expression):
        values = []
        owner.page.runJavaScript("JSON.stringify((" + expression + "))", values.append)
        self.wait(lambda: bool(values), 10)
        return json.loads(values[0]) if values[0] else None

    def async_js(self, owner, body):
        owner.page.runJavaScript("window.__sessionProbe=null;(async()=>{" + body +
            "})().then(value=>window.__sessionProbe={value},error=>window.__sessionProbe={error:String(error)});")
        self.wait(lambda: self.js(owner, "window.__sessionProbe") is not None)
        result = self.js(owner, "window.__sessionProbe")
        self.assertNotIn("error", result)
        return result.get("value")

    def test_real_editor_dirty_cancel_clean_shutdown_and_lazy_restart(self):
        from kfps_editor.host import EditorDesktop
        from tools.kfps_update_status import VersionService
        root = Path(__file__).resolve().parents[2]
        h = SessionIntegrationTests("runTest")
        h.setUp()
        created = []
        second, second_shell = None, None

        def make_owner(_app_root, runtime, **kwargs):
            owner = EditorDesktop(root, runtime, export_root=h.root / "exports", **kwargs)
            owner.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            owner.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            owner._message_box = lambda *_: QMessageBox.StandardButton.Cancel
            created.append(owner)
            return owner

        runtime = SimpleNamespace(baseline={"status": "development"}, borrow_guard=lambda: SimpleNamespace(Close=lambda: None))
        h.controller.runtime = runtime
        try:
            with patch("kfps_editor.host.EditorDesktop", side_effect=make_owner), \
                 patch("kfps_ui.workspace_controller.editor_is_open", return_value=False), \
                 patch("tools.kfps_update_status.VersionService", side_effect=lambda *a, **kw: VersionService(*a, **dict(kw, demo=True))):
                session = h.configure()
                session.restoreEnabled = True
                self.assertTrue(h.controller.open_editor({"mode": "new", "project": ""}))
                owner = h.shell.owners["Editor"]
                h.shell.show()
                self.wait(lambda: owner._ready or owner._failed)
                self.assertFalse(owner._failed, owner.error_label.text())
                saved = self.async_js(owner, "await continueEditorStartup();"
                    "document.querySelectorAll('dialog[open]').forEach(d=>d.close());"
                    "await writeStartupHelpConfirmed();"
                    "await loadPayload({shapes:Array.from({length:12},(_,i)=>({type:1048677,color:[70+i*10,160,190,255],data:[i*45-250,0,.2,.2,0,0,0]}))});"
                    "currentProjectName='Session probe';await saveProject();"
                    "return {count:vinylObjects().length,dirty:isDocumentDirty(),id:editorProjects.association?.target_id};")
                self.assertEqual(saved["count"], 12)
                self.assertFalse(saved["dirty"])
                self.assertEqual(saved["id"], "Session probe.fabric-project.json")
                session.capture("Editor")
                self.wait(lambda: session.current.get("Editor", {}).get("project") == saved["id"])
                self.async_js(owner, "selectObjects([vinylObjects()[0]],'test');"
                    "document.getElementById('xInput').value='123';document.getElementById('applyFields').click();return isDocumentDirty();")
                self.assertTrue(self.js(owner, "isDocumentDirty()"))
                identity = self.js(owner, "documentIdentity")
                self.assertTrue(h.shell.close_surface("Editor"))
                self.wait(lambda: not h.shell._closing)
                self.assertIs(h.shell.owners["Editor"], owner)
                self.assertTrue(session.timer.isActive())
                self.assertEqual(self.js(owner, "documentIdentity"), identity)
                self.assertEqual(self.js(owner, "vinylObjects().length"), 12)
                self.wait(lambda: session.current["Editor"]["dirty"])
                self.async_js(owner, "await saveProject();return isDocumentDirty();")
                self.assertFalse(self.js(owner, "isDocumentDirty()"))
                session.capture("Editor")
                self.wait(lambda: not session.current["Editor"]["dirty"])
                h.shell.close()
                self.wait(lambda: h.shell._approved)
                h.controller.close()
                persisted = h.store.read()
                self.assertEqual(persisted["surfaces"]["Editor"], {"project": saved["id"], "dirty": False})
                # A clean close may write an autosave newer than the project. The
                # existing recovery-aware launcher must still reopen that artwork.
                second_shell = WorkspaceWindow(QWindow(), offscreen=True)
                service = Mock()
                second = WorkspaceController(second_shell, h.controller.paths, service, runtime)
                service._launch.side_effect = lambda path, mode: second.open_editor({"mode": mode,
                    "project": Path(path).relative_to(h.root / "runtime/fabric-editor/projects").as_posix() if path else ""})
                second.configure_session(None, h.app)
                self.assertEqual(second_shell.owners, {})
                self.assertEqual(second_shell._selected, "KFPS")
                service._launch.assert_not_called()
                second_shell.show_surface("Editor", background=True)
                second_shell.show()
                reopened = second_shell.owners["Editor"]
                self.wait(lambda: reopened._ready or reopened._failed)
                self.assertFalse(reopened._failed, reopened.error_label.text())
                self.wait(lambda: self.js(reopened, "vinylObjects().length") == 12)
                self.assertEqual(service._launch.call_count, 1)
                self.assertEqual(self.js(reopened, "vinylObjects()[0].left"), 123)
                self.assertTrue(all(owner.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen) for owner in created if isValid(owner)))
                print("Session probe: saved 12 shapes; dirty close cancelled; identity retained; clean close persisted; lazy restart reopened exact artwork.")
        finally:
            if second is not None:
                second.close()
            if second_shell is not None:
                second_shell.shutdown()
                main = second_shell.main_window
                delete(second_shell)
                delete(main)
            h.tearDown()
            QCoreApplication.processEvents()


@unittest.skipUnless(os.environ.get("KFPS_SESSION_STUDIO_PROBE") == "1", "Opt-in real Studio probe requires prepared car assets")
class StudioSessionProbeTests(unittest.TestCase):
    wait = EditorSessionProbeTests.wait
    js = EditorSessionProbeTests.js
    async_js = EditorSessionProbeTests.async_js

    def test_real_managed_project_lazy_restart_cancel_and_recovery(self):
        self.run_probe(cross_car=False)

    def test_different_default_car_prepares_navigates_and_reopens_exact_project(self):
        self.run_probe(cross_car=True)

    def test_different_default_car_dirty_hint_offers_recovery_on_fresh_page(self):
        self.run_probe(cross_car=True, dirty_hint=True)

    def test_native_cancel_after_car_commit_keeps_new_page_usable_without_replay(self):
        self.run_probe(cross_car=True, commit_cancel=True)

    def run_probe(self, *, cross_car, dirty_hint=False, commit_cancel=False):
        root = Path(__file__).resolve().parents[2]
        lab = root / "tools/livery-studio"
        car = (evidence_directory("fixtures/studio-car", "KFPS_TEST_PREPARED_CAR")
               if "KFPS_TEST_PREPARED_CAR" in os.environ else lab / "runs/workspace-qualification/car")
        self.assertTrue((car / "prepared.json").is_file(), "Prepared car fixture is required")
        with patch.object(sys, "path", [str(lab / "src"), str(lab / "src/kfps_livery_lab"), *sys.path]):
            from kfps_livery_lab import server, source_editor, confirmation_preferences, language_preferences, preview_preferences, theme_context, car_workspace
            from studio_host import StudioHost
        h = SessionIntegrationTests("runTest")
        h.setUp()
        backend = second = second_shell = None
        release = threading.Event()
        committed = threading.Event()
        patches = ExitStack()
        runtime = SimpleNamespace(graphics=SimpleNamespace(backend="opengl"))
        h.controller.runtime = runtime

        def install(controller):
            pending = {"result": {"url": backend.url}, "done": threading.Event(), "error": ""}
            controller._install_studio(pending)
            self.assertIn("Studio", controller.shell.owners, pending["error"])
            return controller.shell.owners["Studio"]

        try:
            isolated_lab = h.root / "studio-lab"
            for module in (server, confirmation_preferences, language_preferences, preview_preferences, theme_context, car_workspace):
                patches.enter_context(patch.object(module, "LAB_ROOT", isolated_lab))
            patches.enter_context(patch.object(source_editor, "LAB", isolated_lab))
            patches.enter_context(patch.object(server, "ThemeContext", side_effect=lambda _workspace, host_root:
                theme_context.ThemeContext(isolated_lab / "runs/theme", host_root)))
            backend = server.LiveryLabServer(json.loads((car / "prepared.json").read_text()), car, h.root,
                session_data_root=isolated_lab / "runs/session", web_root=lab / "src/web")
            backend.session_workspace = isolated_lab / "runs/workspace"
            backend.session_workspace.mkdir(parents=True)
            # Serve real read-only assets while every mutable service root stays
            # inside the probe's isolated profile, including managed project files.
            vendor = root / "tools/livery-inspector/vendor"
            for name in server.VENDOR_FILES:
                backend.static["vendor/" + name] = (vendor / name, vendor)
            for name in ("release-announcement.js", "release-announcement.css", "activity-client.js"):
                backend.static[name] = (root / "KFPS.Editor/web" / name, root / "KFPS.Editor/web")
            backend.start()
            with patch("kfps_ui.workspace_controller._studio_module_path", side_effect=lambda _root, name: lab / "src/kfps_livery_lab" / name):
                h.controller.configure_session(None, h.app)
                session = h.controller.session
                owner = install(h.controller)
                self.assertIsInstance(owner, StudioHost)
                h.shell.show()
                self.wait(lambda: owner.ready or owner.stopped)
                self.assertTrue(owner.ready)
                self.wait(lambda: self.js(owner, "window.kfpsWorkspaceSession?.snapshot().ready") is True)
                document = self.js(owner, "window.__liveryLab.getProject()")
                document["vinyls"] = [{"id": "session-vinyl", "name": "Session probe",
                    "shapes": [{"type": 1048677, "data": [i * 10, 0, .2, .2, 0, 0, 0],
                                "color": [20, 160, 210, 255]} for i in range(12)]}]
                document["placements"] = [{"id": "session-placement", "vinylId": "session-vinyl", "section": "Left",
                    "visible": True, "x": 123, "y": 15, "scaleX": 1, "scaleY": 1, "rotation": 0, "opacity": 1}]
                saved = backend.projects.save(document["vehicle"], {"name": "Session probe", "project": document})
                ref = {"project": saved["entry"]["id"], "car": document["vehicle"], "dirty": False}
                self.assertEqual(len(ref["project"]), 32)
                self.async_js(owner, "return await window.kfpsWorkspaceSession.restore(" + json.dumps(ref) + ",'prime');")
                self.assertEqual(self.js(owner, "kfpsWorkspaceSession.snapshot().restore.state"), "restored")
                self.assertEqual(self.js(owner, "kfpsWorkspaceSession.snapshot().reference.project"), ref["project"])
                expected = self.js(owner, "window.__liveryLab.getProject()")
                self.assertEqual(len(expected["vinyls"][0]["shapes"]), 12)
                self.assertEqual(expected["placements"][0]["x"], 123)
                session.restoreEnabled = True
                session.capture("Studio")
                self.wait(lambda: session.current.get("Studio", {}).get("project") == ref["project"])
                owner.test_control = lambda: {"confirm": False}
                self.js(owner, "(()=>{document.getElementById('duplicate').click();return true;})()")
                self.wait(lambda: self.js(owner, "kfpsWorkspaceSession.snapshot().reference.dirty") is True)
                h.shell.close_surface("Studio")
                self.wait(lambda: not h.shell._closing)
                self.assertIs(h.shell.owners["Studio"], owner)
                self.assertEqual(len(self.js(owner, "__liveryLab.getProject().placements")), 2)
                self.js(owner, "(()=>{document.getElementById('undo').click();return true;})()")
                self.wait(lambda: self.js(owner, "kfpsWorkspaceSession.snapshot().reference.dirty") is False)
                session.capture("Studio")
                self.wait(lambda: not session.current["Studio"]["dirty"])
                h.shell.close()
                self.wait(lambda: h.shell._approved)
                h.controller.close()
                self.assertEqual(h.store.read()["surfaces"]["Studio"], ref)
                if dirty_hint:
                    previous = h.store.read()
                    previous["surfaces"]["Studio"]["dirty"] = True
                    h.store.write(previous)
                if cross_car:
                    prepared = json.loads((car / "prepared.json").read_text())
                    target = prepared["editor_config"]["vehicle"]
                    default = {"car_id": 1, "model_code": "Fixture_Default", "archive_name": "Fixture_Default.zip"}
                    backend.prepared = json.loads(json.dumps(prepared))
                    backend.prepared["editor_config"]["vehicle"] = dict(default)
                    backend.prepared["manifest"]["vehicle"] = dict(default)
                    catalogue_root = h.root / "catalogue"
                    catalogue_root.mkdir()
                    archive = catalogue_root / target["archive_name"]
                    archive.write_bytes(b"prepared-car-session-test")
                    prepared["signature"]["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                    rows = {identifier: {"id": identifier, "name": vehicle["model_code"],
                            "model_code": vehicle["model_code"], "archive": vehicle["archive_name"],
                            "car_id": vehicle["car_id"], "_path": archive,
                            "_size": archive.stat().st_size, "_mtime": archive.stat().st_mtime_ns}
                            for identifier, vehicle in (("a" * 32, target), ("b" * 32, default))}
                    patches.enter_context(patch.object(car_workspace, "catalogue", return_value=rows))
                    manager = car_workspace.CarWorkspace(backend.session_workspace, h.root, catalogue_root)
                    backend.car_workspace = manager
                    def prepare_fixture(record):
                        for source, _mime in car_workspace.prepared_assets(prepared, car).values():
                            destination = record["root"] / source.relative_to(car)
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(source, destination)
                        (record["root"] / "prepared.json").write_text(json.dumps(prepared))
                        return car_workspace.validate_prepared(record["root"], record["car"])
                    patches.enter_context(patch.object(manager, "_prepare", side_effect=prepare_fixture))
                    if commit_cancel:
                        original_commit = manager.commit
                        def delayed_commit(*args):
                            result = original_commit(*args)
                            committed.set()
                            if not release.wait(15):
                                raise RuntimeError("Probe did not release committed car response")
                            return result
                        patches.enter_context(patch.object(manager, "commit", side_effect=delayed_commit))
                        project_reads = patches.enter_context(patch.object(backend.projects, "open", wraps=backend.projects.open))
                second_shell = WorkspaceWindow(QWindow(), offscreen=True)
                service = Mock()
                second = WorkspaceController(second_shell, h.controller.paths, service, runtime)
                service.launchLiveryStudio.side_effect = lambda: install(second)
                second.configure_session(None, h.app)
                self.assertEqual(second_shell.owners, {})
                self.assertEqual(second_shell._selected, "KFPS")
                service.launchLiveryStudio.assert_not_called()
                second_shell.show()
                second_shell.show_surface("Studio", background=True)
                reopened = second_shell.owners["Studio"]
                initial_url = backend.url
                transitions = []
                reopened.page.urlChanged.connect(lambda url: transitions.append(url.toString()))
                if commit_cancel:
                    self.wait(committed.is_set)
                    self.assertNotEqual(backend.url, initial_url)
                    self.assertEqual(reopened.page.url().toString(), initial_url)
                    nonce = second.session.nonces["Studio"]
                    self.assertIs(self.js(reopened, "kfpsWorkspaceSession.cancelRestore(" + json.dumps(nonce) + ")"), False)
                    second.discardSessionRestore("Studio")
                    self.assertNotIn("Studio", second.session.loading)
                    self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().restore.state"), "pending")
                    release.set()
                    self.wait(lambda: reopened.page.url().toString() == backend.url)
                    self.wait(lambda: self.js(reopened, "window.kfpsWorkspaceSession?.snapshot().ready") is True)
                    self.assertIsNone(self.js(reopened, "kfpsWorkspaceSession.snapshot().restore"))
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject().vinyls"), [])
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject().placements"), [])
                    self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().reference.car"), ref["car"])
                    self.assertEqual(len({url for url in transitions if url != initial_url}), 1)
                    project_reads.assert_not_called()
                    self.assertIs(second_shell.owners["Studio"], reopened)
                    self.assertFalse(reopened.stopped)
                    self.assertEqual(next(iter(manager.records.values()))["status"], "committed")
                    outcome = self.async_js(reopened, "return await kfpsWorkspaceSession.restore(" + json.dumps(ref) + ",'explicit-after-cancel');")
                    self.assertEqual(outcome["state"], "restored")
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject()"), expected)
                    self.assertEqual(project_reads.call_count, 1)
                    self.assertNotIn(backend.token, h.store.path.read_text())
                    print("Studio commit-boundary probe: cancellation refused after real token rotation; native continuation dropped; one valid navigation; zero automatic project reads; explicit reopen retained all 12 shapes and placement.")
                    return
                self.wait(lambda: "Studio" not in second.session.loading)
                service.launchLiveryStudio.assert_called_once()
                if cross_car:
                    self.assertNotEqual(reopened.page.url().toString(), initial_url)
                    self.assertEqual(len(manager.records), 1)
                    self.assertEqual(next(iter(manager.records.values()))["status"], "committed")
                    self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().reference.car"), ref["car"])
                    self.assertEqual(len({url for url in transitions if url != initial_url}), 1)
                if dirty_hint:
                    self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().restore.state"), "recovery")
                    self.assertTrue(self.js(reopened, "document.querySelector('[data-recovery=dialog]').open"))
                    self.assertFalse(self.js(reopened, "kfpsWorkspaceSession.snapshot().reference.project"))
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject().placements"), [])
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject().vinyls"), [])
                    self.assertNotIn(backend.token, h.store.path.read_text())
                    self.assertNotIn("http", h.store.path.read_text())
                    print("Studio session probe: cross-car dirty hint navigated once, offered fresh-page Recovery, and applied neither the saved project nor recovery content.")
                    return
                self.assertIn("reopened", second.session.status)
                self.assertEqual(self.js(reopened, "__liveryLab.getProject()"), expected)
                self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().reference.project"), ref["project"])
                self.assertFalse(self.js(reopened, "document.getElementById('openLayoutProject').open"))

                entered = threading.Event()
                original_open = backend.projects.open
                def delayed_open(*args):
                    entered.set()
                    if not release.wait(10):
                        raise RuntimeError("Probe did not release managed load")
                    return original_open(*args)
                with patch.object(backend.projects, "open", side_effect=delayed_open):
                    second.session.staged["Studio"] = dict(ref)
                    second.session.take("Studio")
                    nonce = second.session.nonces["Studio"]
                    second.session.capture("Studio")
                    self.wait(entered.is_set)
                    second.discardSessionRestore("Studio")
                    self.wait(lambda: self.js(reopened, "kfpsWorkspaceSession.snapshot().restore.state") == "cancelled")
                    release.set()
                    self.wait(lambda: self.js(reopened, "kfpsWorkspaceCommands.activity().running") is False)
                self.assertEqual(self.js(reopened, "kfpsWorkspaceSession.snapshot().restore.requestId"), nonce)
                self.assertEqual(self.js(reopened, "__liveryLab.getProject()"), expected)
                for suffix, changed, state in (
                    ("wrong-car", dict(ref, car={"car_id": 999999, "model_code": "Missing_Car"}), "missing" if cross_car else "failed"),
                    ("missing", dict(ref, project="0" * 32), "missing"),
                    ("car-only", dict(ref, project=""), "restored"),
                    ("recovery", dict(ref, dirty=True), "recovery"),
                ):
                    result = self.async_js(reopened, "return await kfpsWorkspaceSession.restore(" + json.dumps(changed) + "," + json.dumps(suffix) + ");")
                    self.assertEqual(result["state"], state)
                    self.assertEqual(self.js(reopened, "__liveryLab.getProject()"), expected)
                self.assertTrue(self.js(reopened, "document.querySelector('[data-recovery=dialog]').open"))
                self.assertNotIn(backend.token, h.store.path.read_text())
                self.assertNotIn("http", h.store.path.read_text())
                print("Studio session probe (cross_car=" + str(cross_car) + "): real 32hex managed receipt; 12 shapes and placement reopened on lazy restart; dirty close cancelled; delayed native cancellation preserved artwork; wrong car/missing project rejected; Recovery offered without applying.")
        finally:
            release.set()
            if second is not None:
                second.close()
            if second_shell is not None:
                second_shell.shutdown()
                main = second_shell.main_window
                delete(second_shell)
                delete(main)
            if backend is not None:
                backend.close()
            try:
                h.tearDown()
            finally:
                patches.close()
                QCoreApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
