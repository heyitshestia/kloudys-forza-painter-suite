from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CALIBRATOR = ROOT / "tools" / "fh6_rtti_calibrator"
sys.path.insert(0, str(CALIBRATOR))
sys.path.insert(0, str(ROOT))

from rtti_relay_client import (  # noqa: E402
    PlaintextTestProtector,
    RelayError,
    RelayStateStore,
    _request_json,
    ensure_enrolled,
    publish_profile_to_relay,
)


def valid_profile():
    return {
        "game": "fh6",
        "module_size": 187904000,
        "descriptor_offset": 173585832,
        "vtable_offsets": [116506584],
        "update_code": "82282983460368",
        "base_class_count": 4,
        "game_build": "3.398.92.0",
        "created_utc": "2026-07-15T12:33:37Z",
        "calibrator_version": "3.0.0",
        "evidence": {
            "workflow": "six_step_template_calibration",
            "confidence": "high",
            "scan_count": 6,
            "distinct_counts": [3000, 2997, 2994, 2991, 2988, 2985],
        },
    }


class RelayClientTests(unittest.TestCase):
    def test_credential_requests_do_not_follow_redirects(self):
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/credential-capture")
                self.end_headers()

            def log_message(self, _format, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(RelayError, "HTTP 302"):
                _request_json(f"http://127.0.0.1:{server.server_port}", "/v1/health")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_enrollment_is_stored_and_plaintext_code_is_scrubbed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            enrollment = root / "rtti-enrollment.json"
            enrollment.write_text(json.dumps({
                "endpoint": "https://relay.test",
                "enrollment_code": "a" * 43,
            }), encoding="utf-8")
            store = RelayStateStore(root / "state", PlaintextTestProtector())
            calls = []

            def request(endpoint, path, **kwargs):
                calls.append((endpoint, path, kwargs))
                return {"helper_id": "helper-1", "credential": "b" * 64}

            first = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            second = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            self.assertEqual(first["credential"], "b" * 64)
            self.assertEqual(second["device_id"], first["device_id"])
            self.assertEqual(len(calls), 1)
            self.assertNotIn("enrollment_code", enrollment.read_text(encoding="utf-8"))
            self.assertTrue(store.path.read_bytes().startswith(b"KFPS-RTTI-TEST\0"))

    def test_publish_sends_only_normalized_profile_and_device_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            enrollment = root / "rtti-enrollment.json"
            enrollment.write_text(json.dumps({
                "endpoint": "https://relay.test",
                "enrollment_code": "c" * 43,
            }), encoding="utf-8")
            store = RelayStateStore(root / "state", PlaintextTestProtector())
            sent = []

            def request(endpoint, path, **kwargs):
                if path == "/v1/enroll":
                    return {"helper_id": "helper-2", "credential": "d" * 64}
                sent.append(kwargs)
                profile = kwargs["body"]["profile"]
                return {"accepted": True, "profile_id": profile["profile_id"], "updated_utc": "now"}

            raw = valid_profile()
            raw["pid"] = 1234
            raw["path"] = "C:\\private\\forzahorizon6.exe"
            result = publish_profile_to_relay(
                raw,
                relay_url="https://relay.test",
                enrollment_file=enrollment,
                store=store,
                requester=request,
            )
            self.assertTrue(result["published"])
            profile = sent[0]["body"]["profile"]
            self.assertNotIn("pid", profile)
            self.assertNotIn("path", profile)
            self.assertEqual(sent[0]["credential"], "d" * 64)

    def test_new_enrollment_file_replaces_an_invalidated_protected_credential(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            enrollment = root / "rtti-enrollment.json"
            store = RelayStateStore(root / "state", PlaintextTestProtector())
            responses = iter((
                {"helper_id": "helper-old", "credential": "e" * 64},
                {"helper_id": "helper-new", "credential": "f" * 64},
            ))

            def request(_endpoint, path, **_kwargs):
                self.assertEqual(path, "/v1/enroll")
                return next(responses)

            enrollment.write_text(json.dumps({
                "endpoint": "https://relay.test", "enrollment_code": "g" * 43,
            }), encoding="utf-8")
            first = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            enrollment.write_text(json.dumps({
                "endpoint": "https://relay.test", "enrollment_code": "h" * 43,
            }), encoding="utf-8")
            second = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            self.assertEqual(first["credential"], "e" * 64)
            self.assertEqual(second["credential"], "f" * 64)
            self.assertEqual(second["helper_id"], "helper-new")
            self.assertEqual(first["device_id"], second["device_id"])

    def test_reusable_auto_enrollment_registers_once_and_remains_in_the_base_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            enrollment = root / "rtti-enrollment.json"
            enrollment.write_text(json.dumps({
                "endpoint": "https://relay.test", "auto_enrollment_code": "i" * 64,
            }), encoding="utf-8")
            store = RelayStateStore(root / "state", PlaintextTestProtector())
            calls = []

            def request(_endpoint, path, **kwargs):
                calls.append((path, kwargs))
                return {"helper_id": "auto-helper", "credential": "j" * 64, "auto_enrolled": True}

            first = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            second = ensure_enrolled(
                relay_url="https://relay.test", enrollment_file=enrollment, store=store, requester=request
            )
            self.assertEqual(first["credential"], second["credential"])
            self.assertEqual(len(calls), 1)
            self.assertIn("auto_enrollment_code", calls[0][1]["body"])
            self.assertIn("auto_enrollment_code", enrollment.read_text(encoding="utf-8"))

    def test_incomplete_profile_never_contacts_the_relay(self):
        profile = valid_profile()
        profile["evidence"]["distinct_counts"] = [3000, 2997]
        with self.assertRaises(RelayError):
            publish_profile_to_relay(
                profile,
                relay_url="https://relay.test",
                dry_run=True,
                requester=lambda *_args, **_kwargs: self.fail("network should not be called"),
            )


if __name__ == "__main__":
    unittest.main()
