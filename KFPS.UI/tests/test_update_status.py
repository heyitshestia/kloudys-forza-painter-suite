import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
from PySide6.QtCore import QCoreApplication
from tools.kfps_update_status import VersionService, is_remote_newer
from kfps_ui.version_service import VersionService as MainVersionService

APP = QCoreApplication.instance() or QCoreApplication([])


def channel(version="3.1.78"):
    return json.dumps({"schema": "kfps.update-channel.v1", "channel": "stable", "sequence": 1,
                       "manifest": {"url": f"https://example.invalid/kfps-update-{version}-s1.json"}}).encode()


class ChannelHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append((self.path, self.headers.get("Cache-Control")))
        time.sleep(self.server.delay)
        self.send_response(self.server.status)
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        try:
            self.wfile.write(self.server.body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class UpdateStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        version = Path(self.temp.name) / "VERSION"
        version.write_text("3.1.77", encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ChannelHandler)
        self.server.body, self.server.status, self.server.delay = channel(), 200, 0
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.service = VersionService(version, demo=True, blink=False)
        self.service.URL = f"http://127.0.0.1:{self.server.server_port}/channel.json"

    def tearDown(self):
        self.service.close()
        self.service.deleteLater()
        APP.processEvents()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def finish(self):
        end = time.monotonic() + 3
        while self.service.checking and time.monotonic() < end:
            APP.processEvents()
            time.sleep(0.005)
        self.assertFalse(self.service.checking, "The async update request did not finish")

    def refresh(self):
        self.service.checkNow()
        self.finish()

    def test_shared_identity_independent_transport_and_poll_cadence(self):
        self.assertIs(MainVersionService, VersionService)
        self.assertEqual(self.service._poll.interval(), 300000)
        self.assertFalse(self.service._blink_timer.isActive())
        self.assertEqual(self.service._initial_timer.interval(), 500)
        self.service.checkNow()
        self.service.checkNow()
        self.finish()
        self.assertEqual(len(self.server.requests), 1)
        self.assertIn("?cache=", self.server.requests[0][0])
        self.assertEqual(self.server.requests[0][1], "no-cache, no-store")
        self.assertEqual(self.service.snapshot(), {"localVersion": "3.1.77", "latestVersion": "3.1.78",
                                                  "available": True, "checked": True, "checking": False})

    def test_equal_older_and_newer_versions(self):
        for version, available in (("3.1.77", False), ("3.1.76", False), ("3.1.100", True), ("3.1.77.1", True)):
            with self.subTest(version=version):
                self.server.body = channel(version)
                self.refresh()
                self.assertTrue(self.service.checkSucceeded)
                self.assertEqual(self.service.updateAvailable, available)
        self.assertFalse(is_remote_newer("v3.1.77", "3.1.77.0"))

    def test_offline_and_invalid_responses_keep_last_confirmed_offer(self):
        self.refresh()
        for body, status in ((b"unavailable", 503), (b"bad JSON", 200), (b"{}", 200),
                             (channel().replace(b"stable", b"preview"), 200), (b"x" * 70000, 200)):
            with self.subTest(status=status, size=len(body)):
                self.server.body, self.server.status = body, status
                self.refresh()
                self.assertFalse(self.service.checkSucceeded)
                self.assertTrue(self.service.updateAvailable)
                self.assertEqual(self.service.latestVersion, "3.1.78")

    def test_deadline_and_close_cancel_work(self):
        self.server.delay = 0.25
        self.service._deadline.setInterval(30)
        self.refresh()
        self.assertFalse(self.service.checkSucceeded)
        self.service.checkNow()
        self.service.close()
        APP.processEvents()
        self.assertFalse(self.service._poll.isActive())
        self.assertFalse(self.service._deadline.isActive())
        requests = len(self.server.requests)
        self.service.checkNow()
        APP.processEvents()
        self.assertEqual(len(self.server.requests), requests)


if __name__ == "__main__":
    unittest.main()
