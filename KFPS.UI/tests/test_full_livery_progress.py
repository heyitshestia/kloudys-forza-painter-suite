from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]
from kfps_ui.experimental.full_livery import worker_main
from kfps_ui.experimental.full_livery.protocol import write_json_atomic


class WorkerProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = self.root / "request.json"
        self.result = self.root / "result.json"
        write_json_atomic(self.request, dict(protocol=1, request_id="progress-test", operation="prepare-mesh",
            session_dir=str(self.root), paths={}, payload={}))

    def tearDown(self):
        self.temp.cleanup()

    def test_progress_write_failure_is_diagnostic_not_render_failure(self):
        def writer(path, value):
            if Path(path).name == "progress.json":
                raise PermissionError("simulated Windows sharing violation")
            write_json_atomic(path, value)
        def execute(request, cancel, *, progress):
            progress("Preparing texture")
            return {"mesh": "completed"}
        with patch.object(worker_main, "execute_operation", side_effect=execute), patch.object(worker_main, "write_json_atomic", side_effect=writer):
            self.assertEqual(worker_main.run_request(self.request, self.result), 0)
        self.assertTrue(json.loads(self.result.read_text())["ok"])
        events = [json.loads(line) for line in (self.root / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(e["event"] == "progress_update_failed" and e["error_type"] == "PermissionError" for e in events))

    @unittest.skipUnless(os.name == "nt", "Windows file sharing semantics")
    def test_windows_reader_lock_does_not_abort_and_later_progress_recovers(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        progress_path = self.root / "progress.json"
        write_json_atomic(progress_path, {"message": "old"})
        def execute(request, cancel, *, progress):
            # Permit reads/writes, but not replacement while the reader is open.
            handle = kernel.CreateFileW(str(progress_path), 0x80000000, 3, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            try:
                progress("While reader is open")
                self.assertEqual(json.loads(progress_path.read_text())["message"], "old")
            finally:
                kernel.CloseHandle(handle)
            progress("Recovered")
            return {"mesh": "completed"}
        with patch.object(worker_main, "execute_operation", side_effect=execute):
            self.assertEqual(worker_main.run_request(self.request, self.result), 0)
        self.assertEqual(json.loads(progress_path.read_text())["message"], "Recovered")
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_result_write_failure_still_fails_operation(self):
        attempted = False
        def writer(path, value):
            nonlocal attempted
            if Path(path) == self.result and not attempted:
                attempted = True
                raise PermissionError("result write denied")
            write_json_atomic(path, value)
        with patch.object(worker_main, "execute_operation", return_value={"mesh": "completed"}), patch.object(worker_main, "write_json_atomic", side_effect=writer):
            self.assertEqual(worker_main.run_request(self.request, self.result), 2)
        result = json.loads(self.result.read_text())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "result write denied")


if __name__ == "__main__":
    unittest.main()
