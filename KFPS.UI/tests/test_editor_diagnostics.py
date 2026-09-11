import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools/fabric-editor", ROOT / "KFPS.UI/src"):
    sys.path.insert(0, str(entry))
from tools.fabric_editor_diagnostics import EditorDiagnostics, clean_packet, read_support_diagnostics
from kfps_ui.support_report import build_support_report
from test_fabric_editor_server import RunningEditorServer, post_json, fabric_server


def packet(seq=1, **changes):
    return {"schema": 1, "page": "a" * 32, "seq": seq, "state": {"layers": 355, "referenceWidth": 1216},
            "metrics": {"frameMax": 523, "gaps500": 1}, "events": [{"kind": "frame-stall", "duration": 523}], **changes}


def wait_for(test, timeout=5):
    end = time.monotonic() + timeout
    while not test():
        if time.monotonic() >= end:
            raise AssertionError("Timed out waiting for diagnostic writer")
        time.sleep(.02)


class EditorDiagnosticTests(unittest.TestCase):
    def test_memory_probe_failure_does_not_stop_diagnostic_writes(self):
        import psutil
        with tempfile.TemporaryDirectory() as folder:
            logger = EditorDiagnostics(ROOT, Path(folder))
            try:
                with patch.object(psutil, "Process", side_effect=psutil.AccessDenied()):
                    serial = logger.accept(packet())
                    wait_for(lambda: logger.status()["written"] == serial)
                self.assertEqual(logger.status()["error"], "")
            finally:
                logger.close()

    def test_strict_fields_exclude_artwork_secrets_and_invalid_numbers(self):
        result = clean_packet(packet(state={"name": "PRIVATE", "data_url": "PRIVATE", "shapeType": float("nan"), "layers": 3,
                                           "renderer": "PRIVATE", "visible": "PRIVATE"},
                                     events=[{"kind": "js-error", "message": "PRIVATE", "error": "TypeError", "source": "C:/PRIVATE", "line": 7}]))
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(result["state"], {"layers": 3})
        self.assertEqual(result["events"][0], {"kind": "js-error", "error": "TypeError", "line": 7})
        for bad in (None, {}, packet(page="private-project"), packet(seq=True), packet(events=[{}] * 49)):
            with self.assertRaises(ValueError):
                clean_packet(bad)

    def test_writer_restart_rotation_and_actual_support_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "runtime/fabric-editor"
            logger = EditorDiagnostics(ROOT, runtime, max_log_bytes=1300)
            try:
                logger.record("native-start", source="native")
                for i in range(1, 25):
                    serial = logger.accept(packet(i))
                    wait_for(lambda: logger.status()["written"] >= serial)
                logger.record("renderer-stopped", code=42, source="native")
            finally:
                logger.close()
            snapshot = json.loads((runtime / "diagnostics.json").read_text())
            self.assertEqual(snapshot["logging"]["error"], "")
            self.assertTrue((runtime / "performance.1.jsonl").exists())
            self.assertEqual(len(list(runtime.glob("performance*.jsonl"))), 3)
            report = build_support_report(root, {"page": "editor", "version": "3.1.76"}, since=time.time(), collect=lambda: {})
            editor = report["technical"]["editor"]
            self.assertEqual(editor["page"]["state"]["layers"], 355)
            self.assertEqual(editor["page"]["metrics"]["gaps500"], 1)
            self.assertTrue(any(e.get("kind") == "renderer-stopped" for e in editor["recent"]))
            self.assertIn("editor.js", editor["installed_assets"])
            before = (runtime / "performance.jsonl").read_text()
            second = EditorDiagnostics(ROOT, runtime)
            second.record("native-start")
            second.close()
            self.assertNotEqual(logger.session, second.session)
            self.assertIn(before, (runtime / "performance.jsonl").read_text())

    def test_slow_writer_does_not_block_producer_and_queue_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = EditorDiagnostics(ROOT, Path(folder))
            entered, release = threading.Event(), threading.Event()
            original = logger._write_batch
            def slow(records):
                entered.set()
                release.wait(5)
                original(records)
            logger._write_batch = slow
            try:
                logger.record("native-start")
                self.assertTrue(entered.wait(3))
                start = time.monotonic()
                for _ in range(400):
                    logger.record("console-warning", source="editor.js", message="PRIVATE")
                self.assertLess(time.monotonic() - start, .25)
                self.assertLessEqual(logger.status()["queue"], 128)
                self.assertGreater(logger.status()["dropped"], 0)
            finally:
                release.set()
                logger.close()

    def test_failed_disk_write_surfaces_and_can_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = EditorDiagnostics(ROOT, Path(folder))
            try:
                with patch.object(logger, "_write_batch", side_effect=PermissionError("PRIVATE")):
                    logger.accept(packet())
                    wait_for(lambda: logger.status()["error"] == "PermissionError")
                    self.assertEqual(logger.status()["written"], 0)
                serial = logger.accept(packet(2))
                wait_for(lambda: logger.status()["written"] == serial)
                self.assertEqual(logger.status()["error"], "")
                self.assertNotIn("PRIVATE", (Path(folder) / "diagnostics.json").read_text())
            finally:
                logger.close()

    def test_http_requires_session_bounds_input_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(fabric_server, "EDITOR_SERVER_MARKER", Path(folder) / "server.json"), RunningEditorServer() as server:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post_json(server, fabric_server.EDITOR_DIAGNOSTICS_API, packet(), token=False)
                self.assertEqual(error.exception.code, 403)
                _, result = post_json(server, fabric_server.EDITOR_DIAGNOSTICS_API, packet())
                serial = result["accepted"]
                wait_for(lambda: server.httpd.diagnostics().status()["written"] >= serial)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(f"{server}{fabric_server.EDITOR_DIAGNOSTICS_API}")
                self.assertEqual(error.exception.code, 403)
                request = urllib.request.Request(f"{server}{fabric_server.EDITOR_DIAGNOSTICS_API}", headers={fabric_server.EDITOR_MUTATION_HEADER: server.httpd.editor_session_token})
                with urllib.request.urlopen(request) as response:
                    saved = json.load(response)
                self.assertEqual(saved["page"]["state"]["layers"], 355)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post_json(server, fabric_server.EDITOR_DIAGNOSTICS_API, packet(extra="x" * 30000))
                self.assertEqual(error.exception.code, 400)

    def test_out_of_order_samples_and_corrupt_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "runtime/fabric-editor"
            logger = EditorDiagnostics(ROOT, runtime)
            logger.accept(packet(20))
            logger.accept(packet(2))
            logger.close()
            self.assertEqual(read_support_diagnostics(root)["page"]["seq"], 20)
            (runtime / "diagnostics.json").write_text('{"broken":')
            self.assertIn("unavailable", read_support_diagnostics(root))
            (runtime / "diagnostics.json").write_text(json.dumps({"schema":"kfps-editor-diagnostics/1", "updated":float("nan")}))
            self.assertIn("unavailable", read_support_diagnostics(root))


if __name__ == "__main__":
    unittest.main()
