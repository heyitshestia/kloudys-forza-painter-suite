import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_fabric_editor_server import RunningEditorServer, fabric_server, post_json
from tools.fabric_editor_recovery import RecoveryStore


class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.marker = Path(self.temporary.name) / "autosave.json"
        self.store = RecoveryStore(self.marker,
                                   lambda path, data: fabric_server._write_json_atomic(path, data, compact=True),
                                   1024 * 1024)

    def reference(self, text="original pixels"):
        source = {"data_url": text, "svg_text": None}
        body = json.dumps(source, separators=(",", ":")).encode()
        identity = hashlib.sha256(body).hexdigest()
        self.store.put_reference(body, identity)
        return {"sha256": identity, "size": len(body)}, source

    def payload(self, revision, reference=None):
        result = {"shapes": [{"data": [revision]}], "recovery_revision": revision}
        if reference:
            result.update(editor_source_overlay={"data_url": None, "svg_text": None, "transform": {"left": revision}},
                          editor_recovery_reference=reference)
        return result

    def test_sidecar_roundtrip_and_compact_snapshot(self):
        reference, source = self.reference()
        payload = self.payload(10, reference)
        self.store.write(payload)
        self.assertEqual(payload, self.store.read(materialize=False)[0])
        restored, fallback, error = self.store.read()
        self.assertFalse(fallback)
        self.assertFalse(error)
        self.assertEqual(source["data_url"], restored["editor_source_overlay"]["data_url"])
        self.assertNotIn("editor_recovery_reference", restored)
        self.assertLess(self.marker.stat().st_size, 500)

    def test_repeated_checkpoints_do_not_reread_verified_reference(self):
        reference, _ = self.reference("x" * 100000)
        self.store.write(self.payload(1, reference))
        with patch.object(self.store, "reference_bytes", side_effect=AssertionError("Repeated reference read")):
            for revision in range(2, 12):
                self.store.write(self.payload(revision, reference))
        self.assertEqual(11, self.store.revision())

    def test_corrupt_current_checkpoint_recovers_previous(self):
        self.store.write(self.payload(1))
        self.store.write(self.payload(2))
        self.marker.write_text("{interrupted")
        recovered, fallback, error = self.store.read()
        self.assertEqual(1, recovered["recovery_revision"])
        self.assertTrue(fallback)
        self.assertTrue(error)
        self.assertEqual(2, self.store.revision())

    def test_head_survives_corrupt_reference_without_loading_image(self):
        reference, _ = self.reference("reference pixels")
        self.store.write(self.payload(10, reference))
        self.store.write({"action": "clear", "shapes": [], "recovery_revision": 20})
        self.store.write(self.payload(30, reference))
        with patch.object(self.store, "reference_bytes", side_effect=AssertionError("Head decoded a reference")):
            self.assertEqual({"recovery_revision": 30, "clearedRevision": 20}, self.store.head())
        self.marker.write_text("{interrupted")
        self.assertEqual({"recovery_revision": 30, "clearedRevision": 20}, self.store.head())

    def test_corrupt_reference_falls_back_to_different_previous_reference(self):
        first, source = self.reference("first image")
        self.store.write(self.payload(1, first))
        second, _ = self.reference("second image")
        self.store.write(self.payload(2, second))
        self.store.reference_path(second["sha256"]).write_text("broken")
        recovered, fallback, error = self.store.read()
        self.assertTrue(fallback)
        self.assertTrue(error)
        self.assertEqual(source["data_url"], recovered["editor_source_overlay"]["data_url"])

    def test_acknowledged_clear_never_resurrects_previous_checkpoint(self):
        self.store.write(self.payload(1))
        self.store.write({"shapes": [], "action": "clear", "recovery_revision": 2})
        self.marker.write_text("broken")
        self.assertEqual("clear", self.store.read()[0]["action"])
        self.store.previous.unlink()
        self.assertEqual(2, self.store.read()[0]["recovery_revision"])

    def test_failed_replace_preserves_last_complete_checkpoint(self):
        self.store.write(self.payload(1))
        original = self.marker.read_bytes()
        replace = fabric_server.os.replace
        def fail_new_head(source, destination):
            if Path(destination) == self.marker:
                raise OSError("Injected disk failure")
            return replace(source, destination)
        with patch("os.replace", side_effect=fail_new_head):
            with self.assertRaises(OSError):
                self.store.write(self.payload(2))
        self.assertEqual(original, self.marker.read_bytes())
        self.assertEqual(1, self.store.revision())
        self.store.write(self.payload(2))
        self.assertEqual(2, self.store.read()[0]["recovery_revision"])

    def test_restart_removes_only_owned_abandoned_temporary_files(self):
        self.store.write(self.payload(1))
        self.store.references.mkdir(exist_ok=True)
        abandoned = [self.marker.parent / ".autosave.json.123.456.tmp",
                     self.marker.parent / ".autosave.revision.json.123.456.tmp",
                     self.marker.parent / "autosave.previous.tmp",
                     self.store.references / ("a" * 64 + ".tmp")]
        preserved = [self.marker.parent / "unrelated.tmp",
                     self.marker.parent / ".autosave.json.not-a-process.tmp",
                     self.store.references / "unrelated.tmp"]
        for path in abandoned + preserved:
            path.write_bytes(b"interrupted")
        directory = self.store.references / ("b" * 64 + ".tmp")
        directory.mkdir()
        restarted = RecoveryStore(self.marker, self.store.write_json, self.store.max_bytes)
        self.assertTrue(all(not path.exists() for path in abandoned))
        self.assertTrue(all(path.read_bytes() == b"interrupted" for path in preserved))
        self.assertTrue(directory.is_dir())
        self.assertEqual(1, restarted.read()[0]["recovery_revision"])

    def test_restart_does_not_follow_reference_directory_link(self):
        self.store.references.mkdir()
        temporary = self.store.references / ("a" * 64 + ".tmp")
        temporary.write_bytes(b"not ours")
        original = Path.is_junction
        with patch.object(Path, "is_junction", lambda path: path == self.store.references or original(path)):
            RecoveryStore(self.marker, self.store.write_json, self.store.max_bytes)
        self.assertEqual(b"not ours", temporary.read_bytes())

    def test_committed_head_ack_retry_preserves_previous_generation(self):
        with patch.object(fabric_server, "EDITOR_AUTOSAVE_MARKER", self.marker), RunningEditorServer() as server:
            store = server.httpd.store_autosave
            self.assertTrue(store(self.payload(1))["applied"])
            original = fabric_server._write_json_atomic
            def fail_watermark(path, payload, **options):
                if path == self.store.watermark:
                    raise OSError("Injected acknowledgement failure")
                return original(path, payload, **options)
            with patch.object(fabric_server, "_write_json_atomic", side_effect=fail_watermark):
                with self.assertRaises(OSError):
                    store(self.payload(2))
            self.assertEqual(2, json.loads(self.marker.read_text())["recovery_revision"])
            self.assertEqual(1, json.loads(self.store.previous.read_text())["recovery_revision"])
            result = store(self.payload(2))
            self.assertTrue(result["applied"])
            self.assertTrue(result["duplicate"])
            self.assertEqual(1, json.loads(self.store.previous.read_text())["recovery_revision"])

    def test_orphan_references_are_bounded_and_previous_remains_readable(self):
        reference, _ = self.reference("keep previous")
        self.store.write(self.payload(1, reference))
        current, _ = self.reference("keep current")
        self.store.write(self.payload(2, current))
        for n in range(10):
            self.reference(str(n))
        self.assertLessEqual(len(list(self.store.references.glob("*.json"))), 4)
        self.assertTrue(self.store.reference_path(reference["sha256"]).exists())
        self.assertTrue(self.store.reference_path(current["sha256"]).exists())

    def test_reference_identity_content_and_combined_size_are_checked(self):
        with self.assertRaises(ValueError):
            self.store.put_reference(b'{}', "0" * 64)
        with self.assertRaises(ValueError):
            self.store.reference_path("../outside")
        reference, _ = self.reference("x" * 900)
        self.store.max_bytes = 1000
        with self.assertRaises(ValueError):
            self.store.write(self.payload(1, reference))
        self.assertFalse(self.marker.exists())

    def test_http_compact_and_legacy_read_share_exact_data(self):
        import urllib.request
        with patch.object(fabric_server, "EDITOR_AUTOSAVE_MARKER", self.marker), RunningEditorServer() as server:
            body = b'{"data_url":"original","svg_text":null}'
            identity = hashlib.sha256(body).hexdigest()
            request = urllib.request.Request(
                f"{server}{fabric_server.EDITOR_RECOVERY_REFERENCE_API}?sha256={identity}",
                data=body, headers={fabric_server.EDITOR_MUTATION_HEADER: server.httpd.editor_session_token}, method="POST")
            with urllib.request.urlopen(request) as response:
                self.assertTrue(json.load(response)["ok"])
            payload = self.payload(3, {"sha256": identity, "size": len(body)})
            self.assertTrue(post_json(server, fabric_server.EDITOR_AUTOSAVE_API, payload)[1]["applied"])
            with urllib.request.urlopen(f"{server}{fabric_server.EDITOR_AUTOSAVE_API}?compact=1") as response:
                self.assertEqual(payload, json.load(response)["payload"])
            with urllib.request.urlopen(f"{server}{fabric_server.EDITOR_AUTOSAVE_API}") as response:
                self.assertEqual("original", json.load(response)["payload"]["editor_source_overlay"]["data_url"])


if __name__ == "__main__":
    unittest.main()
