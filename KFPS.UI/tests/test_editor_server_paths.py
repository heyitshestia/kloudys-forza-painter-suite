import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from test_editor_assets import SHAPE
from test_editor_diagnostics import wait_for
from test_fabric_editor_server import ROOT, RunningEditorServer, fabric_server as server, post_json


def get(instance, endpoint, **query):
    url = f"{instance}{endpoint}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={server.EDITOR_MUTATION_HEADER: instance.httpd.editor_session_token})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


class EditorServerPathsTests(unittest.TestCase):
    def setUp(self):
        # Browser IDs deliberately remain relative to the installation, including in isolation tests.
        run_root = ROOT / "runtime/test-runs/editor-modernization-2026-09-12/runs"
        run_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="server-paths-", dir=run_root)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.a = server.ServerPaths.for_runtime(ROOT, self.root / "a", exports=self.root / "a/exports")
        self.b = server.ServerPaths.for_runtime(ROOT, self.root / "b", exports=self.root / "b/exports")

    def test_production_locations_and_immutable_snapshot(self):
        self.assertEqual(server.ServerPaths.legacy(), server.ServerPaths.for_runtime(ROOT, ROOT / "runtime/fabric-editor"))
        with self.assertRaises(AttributeError):
            self.a.projects = self.b.projects
        with patch.object(server, "EDITOR_PROJECT_ROOT", self.a.projects), RunningEditorServer() as a:
            with patch.object(server, "EDITOR_PROJECT_ROOT", self.b.projects):
                self.assertEqual(self.a.projects, a.httpd.paths.projects)

    def test_same_names_receipts_and_exports_survive_independent_restart(self):
        saved = []
        with RunningEditorServer(paths=self.a) as a, RunningEditorServer(paths=self.b) as b:
            for index, instance in enumerate((a, b)):
                payload = {"shapes": [dict(SHAPE, color=[index, 20, 30, 255])]}
                request_id = str(uuid.uuid4())
                project = post_json(instance, server.PROJECT_SAVE_API, {"name": "Shared name", "payload": payload, "request_id": request_id})[1]
                export = post_json(instance, server.EDITOR_EXPORT_API, {"name": "Shared name", "payload": payload, "request_id": str(uuid.uuid4())})[1]
                self.assertEqual(payload["shapes"], get(instance, server.PROJECT_FILE_API, id=project["id"])["payload"]["shapes"])
                self.assertEqual(payload, get(instance, server.JSON_FILE_API, id=export["id"])["payload"])
                saved.append((project, export, request_id, payload))
            self.assertEqual(saved[0][0]["id"], saved[1][0]["id"])
            self.assertNotEqual(saved[0][0]["receipt"]["fingerprint"], saved[1][0]["receipt"]["fingerprint"])
            with self.assertRaises(urllib.error.HTTPError):
                get(a, server.JSON_FILE_API, id=saved[1][1]["id"])
        for paths, (project, export, request_id, payload) in zip((self.a, self.b), saved):
            with RunningEditorServer(paths=paths) as instance:
                self.assertEqual(1, get(instance, server.PROJECT_BROWSER_API)["total_entries"])
                self.assertEqual(payload["shapes"], get(instance, server.PROJECT_FILE_API, id=project["id"])["payload"]["shapes"])
                self.assertTrue(get(instance, server.PROJECT_RECEIPT_API, request_id=request_id)["current"])
                self.assertTrue(get(instance, server.PROJECT_RECEIPT_API, kind="export", request_id=export["receipt"]["request_id"])["current"])
                self.assertEqual(1, get(instance, server.JSON_BROWSER_API, source="editor")["total_entries"])
                self.assertTrue(paths.project_change.exists())
                self.assertTrue(paths.output_change.exists())

    def test_preferences_themes_favorites_and_confirmation_are_isolated(self):
        with RunningEditorServer(paths=self.a) as a, RunningEditorServer(paths=self.b) as b:
            for index, instance in enumerate((a, b)):
                post_json(instance, server.EDITOR_THEMES_API, {"name": "Same theme", "values": {"--panel": ["#101010", "#eeeeee"][index]}})
                post_json(instance, server.EDITOR_PREFS_API, {"settings": {"kloudyFabricFavorites": json.dumps([101 + index]), "kloudyFabricLanguage": ["en", "ko"][index]}})
            post_json(a, server.STARTUP_HELP_API, {})
            self.assertTrue(get(a, server.STARTUP_HELP_API)["confirmed"])
            self.assertFalse(get(b, server.STARTUP_HELP_API)["confirmed"])
        for index, paths in enumerate((self.a, self.b)):
            with RunningEditorServer(paths=paths) as instance:
                prefs = get(instance, server.EDITOR_PREFS_API)
                self.assertEqual(json.dumps([101 + index]), prefs["settings"]["kloudyFabricFavorites"])
                self.assertEqual(["en", "ko"][index], prefs["settings"]["kloudyFabricLanguage"])
                themes = get(instance, server.EDITOR_THEMES_API)["themes"]
                self.assertEqual(["#101010", "#eeeeee"][index], next(t for t in themes if t["id"] == prefs["theme"])["values"]["--panel"])

    def test_recovery_assets_and_diagnostics_are_isolated(self):
        entries = []
        writes = []
        with RunningEditorServer(paths=self.a) as a, RunningEditorServer(paths=self.b) as b:
            for index, instance in enumerate((a, b)):
                entry = post_json(instance, server.EDITOR_ASSETS_API, {"action": "save", "payload": {"format": server.EDITOR_ASSET_FORMAT, "name": "Asset", "shapes": [SHAPE]}})[1]["entry"]
                entries.append(entry)
                post_json(instance, server.EDITOR_AUTOSAVE_API, {"shapes": [dict(SHAPE, color=[index, 20, 30, 255])], "recovery_revision": 10 + index})
                logger = instance.httpd.diagnostics()
                writes.append((logger, logger.record("commit", commitId=100 + index)))
            with self.assertRaises(urllib.error.HTTPError):
                get(a, server.EDITOR_ASSETS_API, id=entries[1]["id"])
            for logger, serial in writes:
                wait_for(lambda: logger.status()["written"] >= serial)
            for index, instance in enumerate((a, b)):
                self.assertEqual([100 + index], [r["commitId"] for r in get(instance, server.EDITOR_DIAGNOSTICS_API)["recent"] if "commitId" in r])
        for index, paths in enumerate((self.a, self.b)):
            with RunningEditorServer(paths=paths) as instance:
                recovered = get(instance, server.EDITOR_AUTOSAVE_API)
                self.assertEqual(10 + index, recovered["payload"]["recovery_revision"])
                self.assertEqual(index, recovered["payload"]["shapes"][0]["color"][0])
                self.assertEqual([entries[index]], get(instance, server.EDITOR_ASSETS_API)["entries"])
            records = [json.loads(line) for line in (paths.server_marker.parent / "performance.jsonl").read_text().splitlines()]
            self.assertEqual([100 + index], [r["commitId"] for r in records if "commitId" in r])

    def test_diagnostics_isolation_waits_for_held_writers_in_both_orders(self):
        for order in ((0, 1), (1, 0)):
            with self.subTest(order=order):
                paths = [server.ServerPaths.for_runtime(ROOT, self.root / f"held-{order[0]}-{index}") for index in range(2)]
                with RunningEditorServer(paths=paths[order[0]]) as first, RunningEditorServer(paths=paths[order[1]]) as second:
                    instances = {order[0]: first, order[1]: second}
                    release = threading.Event()
                    entered = [threading.Event(), threading.Event()]
                    patches, writes = [], []
                    try:
                        for index in order:
                            logger = instances[index].httpd.diagnostics()
                            original = logger._write_batch

                            def held(records, original=original, index=index):
                                entered[index].set()
                                if not release.wait(10):
                                    raise AssertionError("Held diagnostic writer was not released")
                                return original(records)

                            replacement = patch.object(logger, "_write_batch", held)
                            replacement.start()
                            patches.append(replacement)
                            writes.append((logger, logger.record("commit", commitId=100 + index)))
                        for event in entered:
                            self.assertTrue(event.wait(3), "Writer did not reach the controlled barrier")
                        for instance in instances.values():
                            self.assertEqual([], [r for r in get(instance, server.EDITOR_DIAGNOSTICS_API)["recent"] if "commitId" in r])
                        release.set()
                        for logger, serial in writes:
                            wait_for(lambda: logger.status()["written"] >= serial)
                        for index, instance in instances.items():
                            self.assertEqual([100 + index], [r["commitId"] for r in get(instance, server.EDITOR_DIAGNOSTICS_API)["recent"] if "commitId" in r])
                    finally:
                        release.set()
                        for replacement in reversed(patches):
                            replacement.stop()

    def test_foreign_tokens_traversal_and_later_global_rebinding(self):
        with RunningEditorServer(paths=self.a) as a, RunningEditorServer(paths=self.b) as b:
            with self.assertRaises(urllib.error.HTTPError) as error:
                post_json(str(a), server.PROJECT_SAVE_API, {"name": "Forbidden", "payload": {"shapes": []}}, token=b.httpd.editor_session_token)
            self.assertEqual(403, error.exception.code)
            for instance in (a, b):
                with self.assertRaises(urllib.error.HTTPError):
                    get(instance, server.PROJECT_FILE_API, id="../../a/projects/hidden.fabric-project.json")
            with patch.object(server, "EDITOR_PROJECT_ROOT", self.b.projects), patch.object(server, "EDITOR_PREFS_MARKER", self.b.preferences):
                post_json(a, server.PROJECT_SAVE_API, {"name": "Owned by A", "payload": {"shapes": [SHAPE]}})
                post_json(a, server.EDITOR_PREFS_API, {"theme": "dark"})
                self.assertEqual(1, get(a, server.PROJECT_BROWSER_API)["total_entries"])
                self.assertEqual(0, get(b, server.PROJECT_BROWSER_API)["total_entries"])
                self.assertIsNone(get(b, server.EDITOR_PREFS_API)["theme"])

    def test_marker_cleanup_cannot_touch_another_runtime(self):
        server._write_server_marker(10001, "a", paths=self.a)
        server._write_server_marker(10002, "b", paths=self.b)
        server._remove_owned_server_marker(paths=self.a)
        self.assertFalse(self.a.server_marker.exists())
        self.assertEqual(10002, json.loads(self.b.server_marker.read_text())["port"])
        server._remove_owned_server_marker(paths=self.b)
        self.assertFalse(self.b.server_marker.exists())


if __name__ == "__main__":
    unittest.main()
