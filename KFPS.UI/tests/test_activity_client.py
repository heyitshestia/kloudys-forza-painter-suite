from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import gzip
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools.kfps_activity import (ActivityCounter, MAX_ATTEMPTS, MAX_STATE_BYTES,
    STATE_DIRECTORY, _locked, _protect, _send, activity_payload, period_starts)

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc).timestamp()


class ActivityClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="activity-client-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = NOW
        self.calls = []
        self.mode = "ok"
        self.guard = patch.dict(os.environ, {"KFPS_ACTIVITY_DISABLED": "0"})
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.counter = self.make()

    def transport(self, endpoint, payload):
        self.calls.append((endpoint, payload))
        if self.mode == "fail":
            raise TimeoutError("SECRET PATH TOKEN")
        if self.mode == "old":
            return 404, {}
        if self.mode == "large":
            return 200, {"raw": "secret"}
        return 200, {"ok": True, "day": payload["periods"]["day"]["start"]}

    def make(self):
        return ActivityCounter(self.root, clock=lambda: self.now, transport=self.transport)

    def test_daily_dedup_restart_and_distinct_period_tokens(self):
        self.assertEqual(self.counter.run_once(), "counted")
        self.assertEqual(self.counter.run_once(), "already_counted")
        self.assertEqual(self.make().run_once(), "already_counted")
        self.assertEqual(len(self.calls), 1)
        before = self.calls[0][1]["periods"]
        self.now += 86400
        self.assertEqual(self.make().run_once(), "counted")
        after = self.calls[-1][1]["periods"]
        self.assertNotEqual(before["day"]["token"], after["day"]["token"])
        self.assertEqual(before["week"]["token"], after["week"]["token"])
        self.assertEqual(before["month"]["token"], after["month"]["token"])
        self.now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc).timestamp()
        self.assertEqual(self.make().run_once(), "counted")
        for kind in ("day", "week", "month"):
            self.assertNotEqual(before[kind]["token"], self.calls[-1][1]["periods"][kind]["token"])

    def test_payload_is_small_allowlisted_and_not_machine_derived(self):
        self.counter.run_once()
        body = self.calls[0][1]
        self.assertLess(len(json.dumps(body).encode()), 768)
        self.assertEqual(set(body), {"v", "periods"})
        for item in body["periods"].values():
            self.assertEqual(set(item), {"start", "token"})
            self.assertRegex(item["token"], "^[0-9a-f]{64}$")
        private = json.loads((self.root / STATE_DIRECTORY / "state.json").read_text())
        self.assertNotIn(private["seed"], json.dumps(body))
        seed = _protect(bytes.fromhex(private["seed"]), decrypt=True)
        self.assertEqual(len(seed), 32)
        self.assertNotIn(seed.hex(), json.dumps(body))
        self.assertNotIn(str(self.root), json.dumps(body))
        other = self.root / "other"
        other.mkdir()
        ActivityCounter(other, clock=lambda: self.now, transport=self.transport).run_once()
        self.assertNotEqual(body, self.calls[-1][1])

    def test_opt_out_before_first_launch_never_generates_seed_or_calls(self):
        self.assertTrue(self.counter.set_enabled(False))
        self.assertFalse(self.make().enabled())
        self.assertEqual(self.make().run_once(), "disabled")
        self.assertEqual(self.calls, [])
        state = json.loads((self.root / STATE_DIRECTORY / "state.json").read_text())
        self.assertEqual(state, {"schema": 1, "enabled": False})
        self.assertTrue(self.counter.set_enabled(True))
        self.assertEqual(self.make().run_once(), "counted")
        self.assertTrue(self.counter.set_enabled(False))
        self.assertEqual(self.make().run_once(), "disabled")
        self.assertEqual(len(self.calls), 1)

    def test_test_disable_and_stop_are_inert(self):
        with patch.dict(os.environ, {"KFPS_ACTIVITY_DISABLED": "1"}):
            self.assertIs(self.counter.start(), self.counter)
            self.assertIsNone(self.counter._thread)
            self.assertFalse(self.counter.enabled())
            self.assertEqual(self.counter.run_once(), "disabled")
        self.assertFalse((self.root / "runtime").exists())
        self.counter.stop()
        self.counter.start()
        self.assertIsNone(self.counter._thread)
        self.assertEqual(self.counter.run_once(), "disabled")

    def test_bounded_backoff_survives_restart_and_recovers_tomorrow(self):
        self.mode = "fail"
        self.assertEqual(self.counter.run_once(), "network_unavailable")
        self.assertEqual(self.make().run_once(), "backoff")
        self.now += 301
        self.assertEqual(self.make().run_once(), "network_unavailable")
        self.now += 1801
        self.assertEqual(self.make().run_once(), "network_unavailable")
        self.now += 1801
        self.assertEqual(self.make().run_once(), "retry_limit")
        self.assertEqual(len(self.calls), MAX_ATTEMPTS)
        self.now += 86400
        self.mode = "ok"
        self.assertEqual(self.make().run_once(), "counted")

    def test_old_worker_does_not_loop_or_affect_features(self):
        self.mode = "old"
        self.assertEqual(self.counter.run_once(), "unsupported_server")
        self.assertEqual(self.make().run_once(), "retry_limit")
        self.assertTrue(self.counter.enabled())
        self.assertEqual(len(self.calls), 1)

    def test_wrong_clock_correction_is_bounded_and_retains_budget(self):
        self.now -= 100 * 86400
        def corrected(endpoint, payload):
            self.calls.append(payload)
            if payload["periods"]["day"]["start"] != "2026-10-19":
                return 409, {"error": "activity_period_changed", "day": "2026-10-19",
                             "utc": "2026-10-19T12:00:00.000Z"}
            return 200, {"ok": True, "day": "2026-10-19"}
        counter = ActivityCounter(self.root, clock=lambda: self.now, transport=corrected)
        self.assertEqual(counter.run_once(), "counted")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(counter.run_once(), "already_counted")
        state = json.loads((self.root / STATE_DIRECTORY / "state.json").read_text())
        self.assertEqual(state["attempts"], 2)

    def test_server_cannot_create_unlimited_clock_retries(self):
        def wrong(*_args):
            self.calls.append(1)
            return 409, {"error": "activity_period_changed", "day": "2026-10-20",
                         "utc": "2026-10-20T12:00:00.000Z"}
        counter = ActivityCounter(self.root, clock=lambda: self.now, transport=wrong)
        self.assertEqual(counter.run_once(), "server_unavailable")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(counter.run_once(), "backoff")

    def test_damaged_preferences_fail_closed_without_overwrite(self):
        self.assertTrue(self.counter.set_enabled(False))
        path = self.root / STATE_DIRECTORY / "state.json"
        for value in (b"not json", b"[]", b"x" * (MAX_STATE_BYTES + 1),
                      b'{"schema":1,"enabled":true,"path":"private"}',
                      b'{"schema":1,"enabled":true,"next_attempt":NaN}'):
            path.write_bytes(value)
            self.assertFalse(self.counter.enabled())
            self.assertEqual(self.counter.run_once(), "disabled")
            self.assertEqual(path.read_bytes(), value)
        self.assertEqual(self.calls, [])

    def test_interrupted_write_preserves_old_optout(self):
        self.assertTrue(self.counter.set_enabled(False))
        path = self.root / STATE_DIRECTORY / "state.json"
        before = path.read_bytes()
        with patch("tools.kfps_activity.os.replace", side_effect=OSError("denied")):
            self.assertFalse(self.counter.set_enabled(True))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_hardlinked_state_is_never_read_or_modified(self):
        self.counter.set_enabled(False)
        path = self.root / STATE_DIRECTORY / "state.json"
        outside = self.root / "personal.json"
        outside.write_text('{"schema":1,"enabled":true}')
        path.unlink()
        os.link(outside, path)
        before = outside.read_bytes()
        self.assertFalse(self.counter.enabled())
        self.assertFalse(self.counter.set_enabled(False))
        self.assertEqual(self.counter.run_once(), "disabled")
        self.assertEqual(outside.read_bytes(), before)

    def test_concurrent_hosts_share_one_success_and_one_seed(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _i: self.make().run_once(), range(36)))
        self.assertEqual(results.count("counted"), 1, (results, len(self.calls)))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.counter.run_once(), "already_counted")

    def test_process_lock_released_after_crash(self):
        # A separate hidden process takes the actual OS lock and exits without cleanup.
        self.counter.set_enabled(False)
        code = ("import sys,os;sys.path.insert(0,sys.argv[1]);"
                "from pathlib import Path;from tools.kfps_activity import _locked;"
                "guard=_locked(Path(sys.argv[2]));guard.__enter__();os._exit(0)")
        root = str(Path(__file__).resolve().parents[2])
        result = subprocess.run([sys.executable, "-c", code, root, str(self.counter.directory)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.counter.set_enabled(True))
        self.assertEqual(self.counter.run_once(), "counted")

    def test_running_request_does_not_get_overlapped_by_second_host(self):
        entered, proceed = threading.Event(), threading.Event()
        def slow(endpoint, payload):
            entered.set()
            proceed.wait(3)
            return self.transport(endpoint, payload)
        first = ActivityCounter(self.root, clock=lambda: self.now, transport=slow)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(first.run_once)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.make().run_once(), "disabled")
            self.assertFalse(self.make().set_enabled(False))
            proceed.set()
            self.assertEqual(pending.result(), "counted")
        self.assertTrue(self.make().set_enabled(False))
        self.assertEqual(len(self.calls), 1)

    def test_dates_and_endpoint_validation(self):
        self.assertEqual(period_starts("2027-01-01"),
            {"day": "2027-01-01", "week": "2026-12-28", "month": "2027-01-01"})
        self.assertEqual(period_starts("2028-02-29")["month"], "2028-02-01")
        for bad in ("2026-02-30", "2026-1-1", "bad"):
            with self.assertRaises(ValueError):
                period_starts(bad)
        for bad in ("http://not-secure.test", "https://user:pass@host.test", "https://host.test/a",
                    "https://host.test?key=secret", "https://host.test#data"):
            with self.assertRaises(ValueError):
                ActivityCounter(self.root, endpoint=bad)

    def test_transport_has_no_auth_cookies_or_redirect_following(self):
        class Response:
            code = 200
            def read(self, maximum):
                self.maximum = maximum
                return b'{"ok":true,"day":"2026-10-19"}'
            def __enter__(self): return self
            def __exit__(self, *_args): pass
        response = Response()
        with patch("tools.kfps_activity.build_opener") as make:
            make.return_value.open.return_value = response
            status, value = _send("https://counter.test", activity_payload(b"x" * 32, "2026-10-19"))
            self.assertEqual(status, 200)
            request = make.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://counter.test/v1/activity/ping")
            self.assertEqual(set(k.lower() for k in request.headers), {"content-type", "accept", "user-agent"})
            self.assertIsNone(make.call_args.args[0].redirect_request(None, None, None, None, None, None))
            self.assertEqual(make.return_value.open.call_args.kwargs["timeout"], 4)
        self.assertEqual(value, {"ok": True, "day": "2026-10-19"})

    def test_invalid_response_and_disk_failure_are_fail_open(self):
        self.mode = "large"
        self.assertEqual(self.counter.run_once(), "server_unavailable")
        self.assertTrue(self.counter.enabled())
        self.now += 301
        with patch("tools.kfps_activity.os.fsync", side_effect=OSError("disk full")):
            self.assertEqual(self.counter.run_once(), "storage_unavailable")
        self.assertEqual(len(self.calls), 1)

    def test_usage_status_is_read_only_allowlisted_and_seed_free(self):
        initial = self.counter.usage_status()
        self.assertEqual(initial["status"], "never_sent")
        self.assertFalse((self.root / "runtime").exists())
        self.counter.run_once()
        directory = self.root / STATE_DIRECTORY
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        self.now += 123
        with patch.object(self.counter, "transport", side_effect=AssertionError("Diagnostic network")), patch.object(
                self.counter, "_write", side_effect=AssertionError("Diagnostic write")):
            status = self.counter.usage_status()
        self.assertEqual(status, {"enabled": True, "status": "counted",
            "last_success_utc": "2026-10-19T12:00:00Z", "last_success_age_seconds": 123})
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})
        private = json.loads(before["state.json"])
        self.assertNotIn(private["seed"], json.dumps(status))
        for period in self.calls[0][1]["periods"].values():
            self.assertNotIn(period["token"], json.dumps(status))
        self.counter.set_enabled(False)
        self.assertFalse(self.counter.usage_status()["enabled"])

    def test_usage_status_damaged_missing_lock_and_failure_enum_are_safe(self):
        self.mode = "fail"
        self.counter.run_once()
        self.assertEqual(self.counter.usage_status()["status"], "network_unavailable")
        path = self.root / STATE_DIRECTORY / "state.json"
        path.write_text('{"schema":1,"enabled":true,"last_status":"secret/path"}')
        self.assertEqual(self.counter.usage_status()["status"], "state_unavailable")
        lock = path.parent / "state.lock"
        lock.unlink()
        self.counter.usage_status()
        self.assertFalse(lock.exists())

    def test_actual_report_collector_and_release_policy_exclude_private_state(self):
        import base64
        ui_source = str(Path(__file__).resolve().parents[1] / "src")
        with patch.object(sys, "path", [ui_source, *sys.path]):
            from kfps_ui.support_log_bundle import collect_retained_log_bundle, package_report
            from kfps_ui.support_logs import SOURCES
        release_source = str(Path(__file__).resolve().parents[2] / "tools" / "release")
        with patch.object(sys, "path", [release_source, *sys.path]):
            from tools.release.build_release_bundles import _is_forbidden
        from pathlib import PurePosixPath
        self.counter.run_once()
        private = self.root / STATE_DIRECTORY
        before = {path.name: path.read_bytes() for path in private.iterdir()}
        attachment = collect_retained_log_bundle(self.root)
        self.assertIsNotNone(attachment)
        package = json.loads(gzip.decompress(package_report({"activity": self.counter.usage_status()}, attachment)))
        log_json = gzip.decompress(base64.b64decode(package["logs_base64"])).decode("utf-8")
        private_state = json.loads(before["state.json"])
        self.assertNotIn(private_state["seed"], json.dumps(package))
        self.assertNotIn(private_state["seed"], log_json)
        self.assertNotIn("activity-private", log_json)
        for item in self.calls[0][1]["periods"].values():
            self.assertNotIn(item["token"], log_json)
        self.assertNotIn("activity-private", repr(SOURCES))
        self.assertEqual(before, {path.name: path.read_bytes() for path in private.iterdir()})
        self.assertTrue(_is_forbidden(PurePosixPath(STATE_DIRECTORY + "/state.json")))

    def test_concurrent_host_stress_twenty_independent_installations(self):
        for index in range(20):
            root = self.root / str(index)
            root.mkdir()
            before = len(self.calls)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _i: ActivityCounter(root, clock=lambda: self.now,
                    transport=self.transport).run_once(), range(24)))
            self.assertEqual(results.count("counted"), 1, (index, results))
            self.assertEqual(len(self.calls), before + 1)

    def test_background_thread_creation_and_start_fail_open_without_state_or_network(self):
        for target in ("tools.kfps_activity.threading.Thread", "tools.kfps_activity.threading.Thread.start"):
            with self.subTest(target=target), patch(target, side_effect=RuntimeError("cannot create thread")):
                self.assertIs(self.counter.start(), self.counter)
                self.assertIsNone(self.counter._thread)
                self.assertFalse((self.root / "runtime").exists())
                self.assertEqual(self.calls, [])
        self.counter.stop()
        self.assertIs(self.counter.start(), self.counter)


if __name__ == "__main__":
    unittest.main()
