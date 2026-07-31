from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
SYNC_ROOT = ROOT / "tools" / "fh6_rtti_sync"
for path in (ROOT, SYNC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fh6_rtti_registry import (  # noqa: E402
    RegistryError,
    empty_registry,
    load_registry_file,
    registry_with_profile,
    write_registry_file,
)
from sync_registry import SyncError, build_synced_registry, sync_registry  # noqa: E402


def profile(build: str, code: str, descriptor_offset: int) -> dict:
    return {
        "game": "fh6",
        "module_size": 0x0C000000,
        "descriptor_offset": descriptor_offset,
        "vtable_offsets": [0x06000000],
        "update_code": code,
        "base_class_count": 4,
        "game_build": build,
        "created_utc": "2026-07-31T00:00:00Z",
        "calibrator_version": "3.0.0",
        "evidence": {
            "workflow": "six_step_template_calibration",
            "confidence": "high",
            "scan_count": 6,
            "distinct_counts": [3000, 2997, 2994, 2991, 2988, 2985],
        },
    }


def registry(updated_utc: str, *profiles: dict) -> dict:
    value = empty_registry()
    for item in reversed(profiles):
        value = registry_with_profile(value, item)
    value["updated_utc"] = updated_utc
    return value


class RttiSyncTests(unittest.TestCase):
    def test_new_relay_profile_is_first_and_local_fallback_is_preserved(self):
        old = profile("1.0.0.0", "11111111111111", 0x09000000)
        new = profile("2.0.0.0", "22222222222222", 0x09100000)
        merged, changed = build_synced_registry(
            registry("2026-07-30T00:00:00Z", old),
            registry("2026-07-31T00:00:00Z", new),
        )
        self.assertTrue(changed)
        self.assertEqual([item["game_build"] for item in merged["profiles"]], ["2.0.0.0", "1.0.0.0"])

    def test_same_profiles_are_a_noop_even_if_relay_timestamp_changed(self):
        item = profile("2.0.0.0", "22222222222222", 0x09100000)
        local = registry("2026-07-30T00:00:00Z", item)
        relay = registry("2026-07-31T00:00:00Z", item)
        merged, changed = build_synced_registry(local, relay)
        self.assertFalse(changed)
        self.assertEqual(merged["updated_utc"], local["updated_utc"])

    def test_stale_relay_with_different_profiles_is_rejected(self):
        old = profile("1.0.0.0", "11111111111111", 0x09000000)
        new = profile("2.0.0.0", "22222222222222", 0x09100000)
        with self.assertRaisesRegex(SyncError, "older"):
            build_synced_registry(
                registry("2026-07-31T00:00:00Z", new),
                registry("2026-07-30T00:00:00Z", old),
            )

    def test_empty_relay_is_rejected(self):
        local = registry("2026-07-30T00:00:00Z", profile("1.0.0.0", "11111111111111", 0x09000000))
        remote = empty_registry()
        remote["updated_utc"] = "2026-07-31T00:00:00Z"
        with self.assertRaisesRegex(SyncError, "empty"):
            build_synced_registry(local, remote)

    def test_download_failure_does_not_touch_target(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "RTTI.dat"
            local = registry("2026-07-30T00:00:00Z", profile("1.0.0.0", "11111111111111", 0x09000000))
            write_registry_file(target, local)
            before = target.read_bytes()
            with self.assertRaises(SyncError):
                sync_registry(
                    "https://relay.test/RTTI.dat",
                    target,
                    downloader=lambda _url: (_ for _ in ()).throw(RegistryError("bad relay")),
                )
            self.assertEqual(target.read_bytes(), before)

    def test_dry_run_reports_change_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "RTTI.dat"
            old = profile("1.0.0.0", "11111111111111", 0x09000000)
            new = profile("2.0.0.0", "22222222222222", 0x09100000)
            write_registry_file(target, registry("2026-07-30T00:00:00Z", old))
            before = target.read_bytes()
            result = sync_registry(
                "https://relay.test/RTTI.dat",
                target,
                dry_run=True,
                downloader=lambda _url: registry("2026-07-31T00:00:00Z", new),
            )
            self.assertTrue(result["changed"])
            self.assertTrue(result["target_untouched"])
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(load_registry_file(target)["profiles"][0]["game_build"], "1.0.0.0")


if __name__ == "__main__":
    unittest.main()
