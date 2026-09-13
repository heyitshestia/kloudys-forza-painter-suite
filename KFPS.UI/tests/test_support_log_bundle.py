import base64
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT)]
from kfps_ui import support_log_bundle as bundle
from kfps_ui.support_report import save_handoff


class FullEditorLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime/fabric-editor"
        self.runtime.mkdir(parents=True)

    def record(self, serial=1):
        return {"schema": "kfps-editor-diagnostics/1", "session": "a"*32,
                "utc": "2026-09-13T12:00:00+00:00", "serial": serial,
                "kind": "commit", "action": "move", "commitId": serial, "inputId": serial}

    def unpack(self):
        metadata, blob = bundle.collect_editor_log_bundle(self.root)
        return metadata, json.loads(gzip.decompress(blob))

    def test_full_retained_rotations_no_tail_limit_and_privacy(self):
        for name in bundle.NAMES:
            text = "\n".join(json.dumps({**self.record(i), "message": "PRIVATE_ARTWORK"}) for i in range(1, 5001)) if name.startswith("performance") else "GPU startup\nAuthorization: PRIVATE_TOKEN\nC:\\Users\\PRIVATE_USER\\drawing.png\nuser@private.example\n"
            (self.runtime / name).write_text(text+"\n", encoding="utf-8")
        (self.runtime / "autosave.json").write_text("PRIVATE_PROJECT")
        metadata, data = self.unpack()
        self.assertEqual(metadata["files"], 6)
        self.assertFalse(metadata["warnings"])
        for file in data["files"][:3]:
            events = [json.loads(line) for line in file["text"].splitlines()]
            self.assertEqual(len(events), 5000)
            self.assertEqual(events[0]["commitId"], 1)
            self.assertEqual(events[-1]["commitId"], 5000)
        self.assertNotIn("PRIVATE", json.dumps(data))
        self.assertNotIn("private.example", json.dumps(data))

    def test_partial_and_unknown_records_are_visible_omissions(self):
        (self.runtime / "performance.jsonl").write_text(json.dumps(self.record())+'\n{"kind":', encoding="utf-8")
        metadata, data = self.unpack()
        self.assertEqual(len(data["files"][0]["text"].splitlines()), 1)
        self.assertEqual(data["files"][0]["omitted_lines"], 1)
        self.assertTrue(metadata["warnings"])

    def test_oversized_and_linked_files_fail_without_reading_arbitrary_data(self):
        target = self.runtime / "desktop.log"
        target.write_text("outside private data")
        os.link(target, self.root / "other.log")
        metadata, data = self.unpack()
        self.assertFalse(data["files"])
        self.assertTrue(metadata["warnings"])
        target.unlink()
        target.write_bytes(b"large"*100)
        with patch.object(bundle, "MAX_FILE_BYTES", 10):
            metadata, data = self.unpack()
        self.assertFalse(data["files"])
        self.assertTrue(metadata["warnings"])

    def test_live_appending_file_is_copied_at_collection_time(self):
        path = self.runtime / "performance.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(self.record())+"\n"); stream.flush()
            metadata, data = self.unpack()
            self.assertEqual(json.loads(data["files"][0]["text"])["commitId"], 1)
            stream.write(json.dumps(self.record(2))+"\n"); stream.flush()
        self.assertFalse(metadata["warnings"])

    def test_handoff_keeps_full_archive_separate_and_legacy_unchanged(self):
        (self.runtime / "performance.jsonl").write_text(json.dumps(self.record())+"\n", encoding="utf-8")
        attachment = bundle.collect_editor_log_bundle(self.root)
        report = {"schema": "kfps-support-report/1", "id": "b11fcf72-ba45-42a5-bc97-0990135f8038", "description": "test", "private_logs": attachment[0]}
        path, handoff = save_handoff(self.root, report, log_attachment=attachment)
        package = json.loads(gzip.decompress((path.parent / "report.kfps-report.json.gz").read_bytes()))
        self.assertEqual(package["report"], report)
        self.assertEqual(base64.b64decode(package["logs_base64"]), attachment[1])
        self.assertIn("#bundle=", handoff.read_text())
        self.assertNotIn("fetch(", handoff.read_text())
        del report["private_logs"]
        _, handoff = save_handoff(self.root, report)
        self.assertIn("#draft=", handoff.read_text())

    def test_missing_logs_do_not_add_empty_attachment(self):
        self.assertIsNone(bundle.collect_editor_log_bundle(self.root))

    def test_all_retained_worker_logs_include_old_runs_and_complete_lines(self):
        examples = [
            "runtime/qml-transfer-logs/transfer-20260801-120000.log",
            "runtime/qml-transfer-logs/transfer-20260913-120000.log",
            "runtime/qml-generation-logs/generation-20260913-120000.log",
            "imgs/generated/private-art-name/reports/example.v2.worker.log",
            "runtime/upscaler/runs/20260913-120000/native.log",
            "runtime/background-remover/runs/20260913-120000/worker.log",
            "runtime/experiments/full-livery/sessions/20260913-120000/stdout.log",
            "runtime/experiments/full-livery/sessions/20260913-120000/stderr.log",
            "runtime/experiments/full-livery/sessions/viewer-20260913-120000/stdout.log",
        ]
        expected = "\n".join(f"worker event {i}" for i in range(4000)) + "\n"
        for relative in examples:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected + "token=PRIVATE_TOKEN\n", encoding="utf-8")
            os.utime(path, (1, 1))
        (self.root / "runtime/qml-transfer-logs/project.json").write_text("PRIVATE_PROJECT")
        metadata, blob = bundle.collect_retained_log_bundle(self.root)
        data = json.loads(gzip.decompress(blob))
        self.assertEqual(metadata["schema"], bundle.APP_SCHEMA)
        self.assertEqual(metadata["files"], len(examples))
        self.assertFalse(metadata["warnings"])
        self.assertTrue(all(file["text"].startswith(expected) for file in data["files"]))
        self.assertTrue(any(file["name"].startswith("livery-worker-stderr-") for file in data["files"]))
        self.assertNotIn("PRIVATE", json.dumps(data))
        self.assertNotIn("private-art-name", json.dumps(data))

    def test_retained_worker_discovery_refuses_hardlinks_with_visible_warning(self):
        folder = self.root / "runtime/qml-transfer-logs"
        folder.mkdir(parents=True)
        original = self.root / "private.txt"
        original.write_text("PRIVATE")
        os.link(original, folder / "transfer-20260913-120000.log")
        metadata, blob = bundle.collect_retained_log_bundle(self.root)
        self.assertFalse(json.loads(gzip.decompress(blob))["files"])
        self.assertTrue(metadata["warnings"])

    def test_large_bundle_uses_visible_file_fallback_without_truncation(self):
        report = {"id": "b11fcf72-ba45-42a5-bc97-0990135f8038", "schema": "kfps-support-report/1"}
        package = b"oversized-test-package" * 40000
        with patch.object(bundle, "package_report", return_value=package):
            path, handoff = save_handoff(self.root, report, log_attachment=({}, b"test"))
        self.assertEqual((path.parent / "report.kfps-report.json.gz").read_bytes(), package)
        self.assertIn("#draft=", handoff.read_text())
        self.assertNotIn("#bundle=", handoff.read_text())


if __name__ == "__main__": unittest.main()
