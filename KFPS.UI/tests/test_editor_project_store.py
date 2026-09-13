import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_fabric_editor_server import fabric_server, RunningEditorServer, post_json
from tools.fabric_editor_projects import ProjectStore, ProjectSaveError


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "projects"
        self.store = ProjectStore(self.root, fabric_server._write_json_atomic, 1024 * 1024)
        self.target = "Fixture.fabric-project.json"

    def save(self, number, **kwargs):
        return self.store.save(self.target, {"shapes": [{"type": number}]},
                               request_id=f"{number:032x}", **kwargs)

    def test_exact_reopen_receipt_duplicate_and_conflict(self):
        first = self.save(1)["receipt"]
        self.assertEqual({"shapes": [{"type": 1}]}, self.store.read(self.target)["payload"])
        self.assertEqual(first, self.save(1)["receipt"])
        with self.assertRaises(ProjectSaveError) as conflict:
            self.save(2)
        self.assertEqual("project_exists", conflict.exception.code)
        second = self.save(2, expected=first["fingerprint"])["receipt"]
        self.assertFalse(self.store.verify(self.target, first["fingerprint"]))
        self.assertTrue(self.store.verify(self.target, second["fingerprint"]))
        self.assertFalse(self.store.outcome(first["request_id"])["current"])
        with self.assertRaises(ProjectSaveError) as conflict:
            self.save(3, expected=first["fingerprint"])
        self.assertEqual("project_conflict", conflict.exception.code)
        (self.root / self.target).unlink()
        with self.assertRaises(ProjectSaveError):
            self.save(3, expected=second["fingerprint"])

    def test_read_admission_exact_multibyte_and_oversized_file(self):
        self.root.mkdir()
        target = self.root / self.target
        body = json.dumps({"shapes": [], "name": "\ud55c\uad6d"}, ensure_ascii=False).encode("utf-8")
        target.write_bytes(body)
        self.store.max_bytes = len(body)
        self.assertEqual("\ud55c\uad6d", self.store.read(self.target)["payload"]["name"])
        self.store.max_bytes -= 1
        with self.assertRaises(ProjectSaveError) as failure:
            self.store.read(self.target)
        self.assertEqual("input_too_large", failure.exception.code)
        self.assertEqual(body, target.read_bytes())

    def test_lost_commit_receipt_is_reconciled_after_restart_without_rewrite(self):
        original = self.store.write_json
        def fail_completion(path, payload):
            if payload.get("write_stage") == "committed":
                raise OSError("Injected journal acknowledgment failure")
            original(path, payload)
        with patch.object(self.store, "write_json", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.save(1)
        restored = ProjectStore(self.root, original, 1024 * 1024)
        receipt = restored.outcome(f"{1:032x}")
        self.assertEqual("committed", receipt["status"])
        self.assertEqual(1, restored.read(self.target)["payload"]["shapes"][0]["type"])

    def test_failed_replace_preserves_original_and_reports_unknown_not_success(self):
        first = self.save(1)["receipt"]
        original = __import__("os").replace
        def fail_target(source, target):
            if Path(target).name == self.target:
                raise OSError("Injected target failure")
            original(source, target)
        with patch("tools.fabric_editor_projects.os.replace", side_effect=fail_target):
            with self.assertRaises(OSError):
                self.save(2, expected=first["fingerprint"])
        self.assertTrue(self.store.verify(self.target, first["fingerprint"]))
        self.assertEqual("unknown", self.store.outcome(f"{2:032x}")["status"])
        self.assertEqual([], list(self.root.glob("*.tmp")))

    def test_concurrent_writers_only_one_can_replace_expected_revision(self):
        first = self.save(1)["receipt"]
        def attempt(number):
            try:
                return self.save(number, expected=first["fingerprint"])["ok"]
            except ProjectSaveError:
                return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual([False, True], sorted(pool.map(attempt, [2, 3])))

    def test_receipts_bounded_and_no_artwork_or_paths_in_journal(self):
        previous = None
        for number in range(1, 133):
            previous = self.save(number, expected=previous)["receipt"]["fingerprint"]
        files = list(self.store.receipts.glob("*.json"))
        self.assertEqual(128, len(files))
        for file in files:
            receipt = json.loads(file.read_text())
            self.assertEqual({"request_id", "target_id", "fingerprint", "bytes", "write_stage"}, set(receipt))

    def test_size_and_path_validation_leave_original_unchanged(self):
        first = self.save(1)["receipt"]
        self.store.max_bytes = 10
        with self.assertRaises(ProjectSaveError):
            self.save(2, expected=first["fingerprint"])
        self.store.max_bytes = 1024 * 1024
        self.assertTrue(self.store.verify(self.target, first["fingerprint"]))
        with self.assertRaises(ValueError):
            self.store.save("../outside.json", {}, request_id="a" * 32)

    def test_http_save_read_and_receipt_match(self):
        import urllib.request
        with patch.object(fabric_server, "EDITOR_PROJECT_ROOT", self.root), \
             patch.object(fabric_server, "EDITOR_PROJECT_CHANGE_MARKER", self.root.parent / "changed.json"), \
             RunningEditorServer() as url:
            _, result = post_json(url, fabric_server.PROJECT_SAVE_API,
                                  {"name": "Fixture", "payload": {"shapes": []}, "request_id": "a" * 32})
            with urllib.request.urlopen(f"{url}{fabric_server.PROJECT_RECEIPT_API}?request_id={'a' * 32}") as response:
                self.assertEqual(result["receipt"], json.load(response)["receipt"])
            with urllib.request.urlopen(f"{url}{fabric_server.PROJECT_FILE_API}?id={self.target}") as response:
                self.assertEqual(result["receipt"]["fingerprint"], json.load(response)["receipt"]["fingerprint"])
