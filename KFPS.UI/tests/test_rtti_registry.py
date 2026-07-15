from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

import fh6_probe  # noqa: E402
from fh6_rtti_registry import (  # noqa: E402
    MAX_REGISTRY_BYTES,
    RegistryError,
    download_registry,
    empty_registry,
    load_registry_file,
    load_runtime_profiles,
    normalize_profile,
    normalize_registry,
    parse_registry_bytes,
    profile_from_calibration_result,
    publish_profile_to_github,
    refresh_registry_cache,
    registry_bytes,
    registry_with_profile,
    write_registry_file,
)


def valid_profile(**overrides):
    profile = {
        "game": "fh6",
        "module_size": 0x0C000000,
        "descriptor_offset": 0x09000000,
        "vtable_offsets": [0x06000000],
        "update_code": "12345678901234",
        "base_class_count": 4,
        "game_build": "9.9.9.9",
        "created_utc": "2026-07-15T00:00:00Z",
        "calibrator_version": "2.0.0",
        "evidence": {
            "workflow": "six_step_template_calibration",
            "confidence": "high",
            "scan_count": 6,
            "distinct_counts": [3000, 2997, 2994, 2991, 2988, 2985],
        },
    }
    profile.update(overrides)
    return profile


def complete_calibration_result():
    module_base = 0x140000000
    return {
        "format": "kfps_clivery_rtti_calibration_v1",
        "pid": 12345,
        "process": {"name": "forzahorizon6.exe", "exe": "C:\\Games\\Forza Horizon 6\\forzahorizon6.exe"},
        "module": {
            "name": "forzahorizon6.exe",
            "path": "C:\\Program Files\\WindowsApps\\Microsoft.ForteBaseGame_9.9.9.9_x64__test\\forzahorizon6.exe",
            "base": hex(module_base),
            "size": 0x0C000000,
        },
        "rtti": {
            "descriptor_offset": 0x09000000,
            "descriptor_address": hex(module_base + 0x09000000),
            "vtables": [hex(module_base + 0x06000000)],
            "type_name": "12345678901234    ",
            "hierarchy_update_code": "12345678901234    ",
            "base_class_count": 4,
            "confidence": "high",
        },
        "lock_summary": {
            "scans": 6,
            "distinct_counts": [2985, 2988, 2991, 2994, 2997, 3000],
            "count_changes": 5,
            "sources": ["live_group_candidate"],
        },
        "workflow": {
            "name": "six_step_template_calibration",
            "target_counts": [3000, 2997, 2994, 2991, 2988, 2985],
            "completed_step": 6,
            "required_scans": 3,
        },
        "created_utc": "2026-07-15T00:00:00Z",
        "calibrator_version": "2.0.0",
    }


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.data


class FakeGhRunner:
    def __init__(self, existing):
        self.commands = []
        self.inputs = []
        self.existing = normalize_registry(existing)

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        self.inputs.append(kwargs.get("input"))
        if command[1:3] == ["auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="authenticated", stderr="")
        if command[1] == "api" and "--method" not in command:
            content = base64.b64encode(registry_bytes(self.existing)).decode("ascii")
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"sha": "old-sha", "content": content}),
                stderr="",
            )
        if command[1] == "api" and "--method" in command:
            payload = json.loads(kwargs["input"])
            self.published = parse_registry_bytes(base64.b64decode(payload["content"]))
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"commit": {"html_url": "https://github.test/commit/1"}}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")


class ConflictOnceGhRunner(FakeGhRunner):
    def __init__(self, existing):
        super().__init__(existing)
        self.put_attempts = 0

    def __call__(self, command, **kwargs):
        if command[1] == "api" and "--method" in command:
            self.commands.append(list(command))
            self.inputs.append(kwargs.get("input"))
            self.put_attempts += 1
            if self.put_attempts == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="gh: Conflict (HTTP 409)")
        return super().__call__(command, **kwargs)


class RttiRegistryTests(unittest.TestCase):
    def test_calibrator_and_runtime_share_the_exact_registry_implementation(self):
        runtime_module = ROOT / "fh6_rtti_registry.py"
        calibrator_module = ROOT / "tools" / "fh6_rtti_calibrator" / "fh6_rtti_registry.py"
        self.assertEqual(runtime_module.read_bytes(), calibrator_module.read_bytes())

    def test_profile_identity_is_recomputed_and_offsets_must_be_module_relative(self):
        profile = normalize_profile({**valid_profile(), "profile_id": "untrusted"})
        self.assertTrue(profile["profile_id"].startswith("fh6-"))
        self.assertNotEqual(profile["profile_id"], "untrusted")
        with self.assertRaises(RegistryError):
            normalize_profile(valid_profile(descriptor_offset=0x0C000000))
        with self.assertRaises(RegistryError):
            normalize_profile(valid_profile(vtable_offsets=[0x140000000]))

    def test_calibration_result_is_sanitized_and_requires_all_six_steps(self):
        result = complete_calibration_result()
        profile = profile_from_calibration_result(result)
        encoded = json.dumps(profile)
        self.assertEqual(profile["game_build"], "9.9.9.9")
        self.assertEqual(profile["vtable_offsets"], [0x06000000])
        self.assertNotIn('"pid"', encoded)
        self.assertNotIn('"process"', encoded)
        self.assertNotIn('"path"', encoded)
        self.assertNotIn("Program Files", encoded)
        self.assertNotIn(hex(0x140000000), encoded)

        result["workflow"]["completed_step"] = 5
        result["lock_summary"]["distinct_counts"].remove(2985)
        with self.assertRaises(RegistryError):
            profile_from_calibration_result(result)

    def test_registry_merge_keeps_other_builds_and_deduplicates_current_build(self):
        first = normalize_profile(valid_profile())
        second = normalize_profile(
            valid_profile(
                descriptor_offset=0x09100000,
                update_code="22345678901234",
                game_build="10.0.0.0",
            )
        )
        registry = registry_with_profile(registry_with_profile(empty_registry(), first), second)
        self.assertEqual([item["profile_id"] for item in registry["profiles"]], [second["profile_id"], first["profile_id"]])
        registry = registry_with_profile(registry, second)
        self.assertEqual(len(registry["profiles"]), 2)

    def test_invalid_remote_download_does_not_replace_a_good_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "RTTI.dat"
            good = registry_with_profile(empty_registry(), valid_profile())
            write_registry_file(cache, good)
            before = cache.read_bytes()

            status = refresh_registry_cache(
                cache,
                remote_url="https://example.test/RTTI.dat",
                now=1000,
                downloader=lambda _url: (_ for _ in ()).throw(RegistryError("bad remote")),
            )
            self.assertEqual(status["result"], "error")
            self.assertEqual(cache.read_bytes(), before)
            self.assertEqual(load_registry_file(cache)["profiles"][0]["profile_id"], normalize_profile(valid_profile())["profile_id"])

    def test_offline_runtime_load_uses_cached_then_built_in_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cached = normalize_profile(valid_profile(update_code="32345678901234"))
            cache_path = root / "runtime" / "fh6-rtti" / "RTTI.dat"
            write_registry_file(cache_path, registry_with_profile(empty_registry(), cached))
            fallback = valid_profile(update_code="42345678901234")

            profiles, status = load_runtime_profiles(
                root,
                fallback,
                refresh=True,
                remote_url="https://offline.test/RTTI.dat",
                downloader=lambda _url: (_ for _ in ()).throw(OSError("offline")),
                now=2000,
            )
            self.assertEqual(status["refresh"]["result"], "error")
            self.assertEqual(profiles[0]["_registry_source"], "remote_cache")
            self.assertEqual(profiles[-1]["_registry_source"], "built_in")

    def test_refresh_throttle_avoids_repeated_network_attempts(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "RTTI.dat"
            registry = registry_with_profile(empty_registry(), valid_profile())

            def downloader(_url):
                calls.append(1)
                return registry

            first = refresh_registry_cache(cache, now=3000, downloader=downloader)
            second = refresh_registry_cache(cache, now=3001, downloader=downloader)
            self.assertTrue(first["updated"])
            self.assertEqual(second["result"], "throttled")
            self.assertEqual(len(calls), 1)

    def test_unwritable_cache_never_breaks_locator_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            blocked = Path(temp) / "blocked"
            blocked.write_text("not a directory", encoding="ascii")
            status = refresh_registry_cache(
                blocked / "RTTI.dat",
                now=3500,
                downloader=lambda _url: registry_with_profile(empty_registry(), valid_profile()),
            )
            self.assertEqual(status["result"], "error")
            self.assertFalse(status["updated"])

    def test_download_requires_https_and_enforces_size_limit(self):
        with self.assertRaises(RegistryError):
            download_registry("http://example.test/RTTI.dat")
        with self.assertRaises(RegistryError):
            parse_registry_bytes(b"x" * (MAX_REGISTRY_BYTES + 1))

        registry = registry_with_profile(empty_registry(), valid_profile())
        loaded = download_registry(
            "https://example.test/RTTI.dat",
            opener=lambda _request, timeout: FakeResponse(registry_bytes(registry)),
        )
        self.assertEqual(len(loaded["profiles"]), 1)

    def test_github_publication_merges_registry_without_embedding_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / "gh.exe"
            gh.write_bytes(b"")
            old_profile = normalize_profile(valid_profile(update_code="52345678901234"))
            new_profile = normalize_profile(valid_profile(update_code="62345678901234"))
            runner = FakeGhRunner(registry_with_profile(empty_registry(), old_profile))

            result = publish_profile_to_github(
                new_profile,
                gh_executable=str(gh),
                runner=runner,
            )
            self.assertTrue(result["published"])
            self.assertEqual(runner.published["profiles"][0]["profile_id"], new_profile["profile_id"])
            self.assertEqual(len(runner.published["profiles"]), 2)
            command_text = json.dumps(runner.commands)
            input_text = json.dumps(runner.inputs)
            self.assertNotIn("token", command_text.lower())
            self.assertNotIn("authorization", input_text.lower())

    def test_github_publication_refetches_after_concurrent_update_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / "gh.exe"
            gh.write_bytes(b"")
            runner = ConflictOnceGhRunner(registry_with_profile(empty_registry(), valid_profile()))
            result = publish_profile_to_github(
                valid_profile(update_code="92345678901234"),
                gh_executable=str(gh),
                runner=runner,
            )
            self.assertTrue(result["published"])
            self.assertEqual(runner.put_attempts, 2)
            get_calls = [command for command in runner.commands if command[1] == "api" and "--method" not in command]
            self.assertEqual(len(get_calls), 2)

    def test_probe_skips_stale_profile_and_uses_verified_profile(self):
        module_base = 0x140000000
        stale = normalize_profile(valid_profile(update_code="72345678901234"))
        current = normalize_profile(
            valid_profile(
                descriptor_offset=0x09100000,
                vtable_offsets=[0x06100000],
                update_code="82345678901234",
            )
        )
        stale["_registry_source"] = "remote_cache"
        current["_registry_source"] = "packaged"

        def fake_read(_pid, address, size):
            if address == module_base + current["descriptor_offset"] + 0x10:
                return current["update_code"].encode("ascii")[:size]
            return b"x" * size

        with patch.object(fh6_probe, "get_base_address", return_value=module_base), patch.object(
            fh6_probe, "read_process_memory", side_effect=fake_read
        ):
            located = fh6_probe.locate_calibrated_clivery_group_rtti(
                99,
                SimpleNamespace(key="fh6"),
                [stale, current],
            )
        self.assertEqual(located["profile_id"], current["profile_id"])
        self.assertEqual(located["vtables"], [module_base + 0x06100000])

    def test_environment_can_disable_network_refresh(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"KFPS_DISABLE_RTTI_UPDATE": "1"}):
            profiles, status = load_runtime_profiles(Path(temp), valid_profile(), refresh=True)
            self.assertEqual(status["refresh"]["result"], "disabled")
            self.assertEqual(len(profiles), 1)


if __name__ == "__main__":
    unittest.main()
