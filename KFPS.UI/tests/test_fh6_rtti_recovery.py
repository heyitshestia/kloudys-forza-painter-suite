from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_probe  # noqa: E402
from game_adapters import get_adapter  # noqa: E402
from fh6_rtti_registry import (  # noqa: E402
    empty_registry,
    normalize_profile,
    refresh_runtime_registry,
    registry_with_profile,
)
from live_memory_locator.cache import LocatorCache  # noqa: E402
from live_memory_locator.contracts import LocatorRequest  # noqa: E402
from live_memory_locator.engine import LiveMemoryLocatorEngine  # noqa: E402
from live_memory_locator.fh6_recovery import (  # noqa: E402
    _derive_profile_from_group,
    load_local_profiles,
    local_registry_path,
    merge_local_profiles,
    persist_local_profile,
    recover_local_profile,
)


def recovery_profile(update_code: str = "12345678901234") -> dict:
    return normalize_profile(
        {
            "game": "fh6",
            "module_size": 0x0C000000,
            "descriptor_offset": 0x09000000,
            "vtable_offsets": [0x06000000],
            "update_code": update_code,
            "base_class_count": 1,
            "game_build": "test",
            "created_utc": "2026-08-29T00:00:00Z",
            "calibrator_version": "organic-test",
            "evidence": {
                "workflow": "organic_live_transfer_recovery",
                "confidence": "high",
                "scan_count": 1,
                "distinct_counts": [8],
            },
        }
    )


def initial_no_profile_payload() -> dict:
    return {
        "game": "fh6",
        "layer_count": 8,
        "no_match": True,
        "profile_recovery_required": True,
        "failure_reason": "local recovery required",
        "locator_diagnostics": {"rtti_profile": {"matched": False}},
    }


def located_payload(profile_id: str) -> dict:
    return {
        "game": "fh6",
        "layer_count": 8,
        "group_address": 0x270010000,
        "count_address": 0x27001005A,
        "table_pointer_field": 0x270010078,
        "table_address": 0x270020000,
        "locator": "rtti_allocator_exact",
        "validated_entries": 8,
        "vector_count": 8,
        "capacity_count": 8,
        "import_group_address": 0x270010000,
        "import_count_address": 0x27001005A,
        "import_table_pointer_field": 0x270010078,
        "import_table_address": 0x270020000,
        "import_vector_count": 8,
        "import_capacity_count": 8,
        "import_target_verified": True,
        "export_access_verified": True,
        "shape_word_counts": {"102": 8},
        "rtti_source": "calibrated_profile",
        "rtti_profile_id": profile_id,
        "locator_diagnostics": {"rtti_profile": {"matched": True}},
    }


class Fh6RttiRecoveryTests(unittest.TestCase):
    def request(self, root: Path, purpose: str = "export") -> LocatorRequest:
        return LocatorRequest("fh6", 123, 8, purpose, root / "locator-session.json")

    def identity(self) -> dict:
        return {
            "pid": 123,
            "name": "forzahorizon6.exe",
            "started": 1.0,
            "executable": r"C:\XboxGames\Forza Horizon 6\Content\forzahorizon6.exe",
        }

    def test_local_profiles_are_separate_and_take_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = recovery_profile("22345678901234")
            remote_path = root / "runtime" / "fh6-rtti" / "RTTI.dat"
            remote_path.parent.mkdir(parents=True)
            remote_path.write_text(json.dumps({"sentinel": True}), encoding="utf-8")

            saved = persist_local_profile(root, recovery_profile())
            local_before_refresh = local_registry_path(root).read_bytes()
            refresh = refresh_runtime_registry(
                root,
                remote_url="https://registry.test/RTTI.dat",
                downloader=lambda _url: registry_with_profile(empty_registry(), remote),
                now=1000,
                force=True,
            )
            profiles = merge_local_profiles(root, [remote])

            self.assertEqual("ok", refresh["result"])
            self.assertEqual(saved["profile_id"], profiles[0]["profile_id"])
            self.assertEqual("local_recovery", profiles[0]["_registry_source"])
            self.assertEqual(remote["profile_id"], profiles[1]["profile_id"])
            self.assertNotIn(b"sentinel", remote_path.read_bytes())
            self.assertEqual(local_before_refresh, local_registry_path(root).read_bytes())
            self.assertTrue(local_registry_path(root).is_file())
            loaded, error = load_local_profiles(root)
            self.assertFalse(error)
            self.assertEqual(saved["profile_id"], loaded[0]["profile_id"])

    def test_cache_can_reuse_allocator_windows_across_fh6_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = LocatorCache(Path(temp) / "cache.json")
            cache.update_allocator_windows("fh6", "old", [(0x270000000, 0x280000000)])
            cache.update_allocator_windows("fm", "other", [(0x80000000, 0x90000000)])
            self.assertEqual(
                [(0x270000000, 0x280000000)],
                cache.all_allocator_windows("fh6"),
            )

    def test_rtti_derivation_requires_a_self_consistent_col_and_hierarchy(self):
        module_base = 0x140000000
        module_size = 0x0C000000
        group = 0x270010000
        vtable = module_base + 0x06000000
        locator = module_base + 0x05000000
        descriptor_rva = 0x09000000
        hierarchy_rva = 0x09100000
        base_array_rva = 0x09200000
        base_descriptor_rva = 0x09300000
        base_type_rva = 0x09400000
        update_code = b"12345678901234"
        segments = {
            vtable - 8: struct.pack("<Q", locator),
            locator: struct.pack(
                "<6I",
                1,
                0,
                0,
                descriptor_rva,
                hierarchy_rva,
                locator - module_base,
            ),
            module_base + descriptor_rva + 0x10: update_code + b"\0" + b"\0" * 113,
            module_base + hierarchy_rva: struct.pack("<4I", 0, 0, 1, base_array_rva),
            module_base + base_array_rva: struct.pack("<I", base_descriptor_rva),
            module_base + base_descriptor_rva: struct.pack("<I", base_type_rva) + b"\0" * 24,
        }

        def fake_read(_pid, address, size):
            for start, data in segments.items():
                offset = address - start
                if 0 <= offset and offset + size <= len(data):
                    return data[offset : offset + size]
            raise OSError(f"unmapped test read: {address:#x}/{size}")

        with patch("live_memory_locator.fh6_recovery.read_process_memory", side_effect=fake_read):
            profile, evidence = _derive_profile_from_group(
                fh6_probe,
                123,
                group,
                vtable,
                module_base,
                module_size,
                8,
            )
        self.assertEqual("derived", evidence["reason"])
        self.assertEqual(update_code.decode("ascii"), profile["update_code"])
        self.assertEqual([vtable - module_base], profile["vtable_offsets"])

        bad_locator = bytearray(segments[locator])
        struct.pack_into("<I", bad_locator, 0x14, 0x1234)
        segments[locator] = bytes(bad_locator)
        with patch("live_memory_locator.fh6_recovery.read_process_memory", side_effect=fake_read):
            profile, evidence = _derive_profile_from_group(
                fh6_probe,
                123,
                group,
                vtable,
                module_base,
                module_size,
                8,
            )
        self.assertIsNone(profile)
        self.assertEqual("complete_object_locator_identity_invalid", evidence["reason"])

    def test_allocator_recovery_accepts_one_complete_group_tree(self):
        module_base = 0x140000000
        module_size = 0x0C000000
        group = 0x270010000
        table = 0x270020000
        vtable = module_base + 0x06000000
        raw = bytearray(0xA0)
        struct.pack_into("<Q", raw, 0, vtable)
        struct.pack_into("<H", raw, 0x5A, 8)
        struct.pack_into("<Q", raw, 0x60, 0)
        struct.pack_into("<3Q", raw, 0x78, table, table + 64, table + 64)
        profile = recovery_profile()
        derived = dict(profile)
        derived["_registry_source"] = "local_recovery_candidate"
        memory_profile = SimpleNamespace(layer_table_offset=0x78, livery_count_offset=0x5A)

        with patch("live_memory_locator.fh6_recovery.get_base_address", return_value=module_base), patch.object(
            fh6_probe, "read_pe_image_size", return_value=module_size
        ), patch.object(
            fh6_probe,
            "iter_regions",
            return_value=iter([(group, len(raw), fh6_probe.PAGE_READWRITE, fh6_probe.MEM_PRIVATE)]),
        ), patch.object(
            fh6_probe, "build_region_contains", return_value=lambda _address, _size=1: True
        ), patch.object(
            fh6_probe,
            "read_region_resilient",
            return_value=([(group, bytes(raw))], [], 0, 0),
        ), patch.object(
            fh6_probe,
            "read_calibrated_group_vector",
            return_value={
                "group_address": group,
                "table_address": table,
                "vector_count": 8,
                "current_u16": 8,
                "parent_group": 0,
            },
        ), patch.object(
            fh6_probe,
            "flatten_calibrated_group",
            return_value={"shape_count": 8, "invalid_count": 0, "group_count": 3, "max_depth": 2},
        ), patch(
            "live_memory_locator.fh6_recovery._read_u64", return_value=vtable
        ), patch(
            "live_memory_locator.fh6_recovery._derive_profile_from_group",
            return_value=(derived, {"reason": "derived", "profile_id": profile["profile_id"]}),
        ):
            result = recover_local_profile(ROOT, 123, memory_profile, 8)

        self.assertEqual("derived", result["status"])
        self.assertEqual(1, result["candidate_count"])
        self.assertEqual(3, result["group_count"])
        self.assertEqual("disabled", result["publication"])

    def test_engine_recovers_once_revalidates_and_saves_locally(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = LiveMemoryLocatorEngine(root)
            profile = recovery_profile()
            recovery = {
                "status": "derived",
                "reason": "derived",
                "publication": "disabled",
                "profile": dict(profile),
            }
            with patch.object(engine, "_process_identity", return_value=self.identity()), patch.object(
                engine,
                "_fast_locate",
                side_effect=[
                    (initial_no_profile_payload(), {"name": "profile_locator", "status": "no_match"}),
                    (located_payload(profile["profile_id"]), {"name": "profile_locator", "status": "located"}),
                ],
            ) as fast, patch.object(
                engine, "_recover_fh6_profile", return_value=recovery
            ) as recover, patch(
                "live_memory_locator.fh6_recovery.persist_local_profile", return_value=profile
            ) as persist:
                report = engine.locate(self.request(root))

            self.assertEqual("located", report["outcome"]["status"])
            self.assertEqual(2, fast.call_count)
            recover.assert_called_once()
            persist.assert_called_once()
            self.assertTrue(
                any(item["name"] == "local_profile_persistence" for item in report["attempts"])
            )

    def test_forced_recovery_ignores_known_profiles_only_for_initial_lookup(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ,
            {"KFPS_FORCE_LOCAL_RTTI_RECOVERY": "1"},
            clear=False,
        ):
            root = Path(temp)
            engine = LiveMemoryLocatorEngine(root)
            with patch("live_memory_locator.engine.process_memory_session"), patch.object(
                fh6_probe,
                "auto_locate_count_table",
                return_value=initial_no_profile_payload(),
            ) as locate:
                adapter = get_adapter("fh6")
                _payload, forced_attempt = engine._fast_locate(self.request(root), adapter)
                engine._fast_locate(
                    self.request(root),
                    adapter,
                    calibrated_profiles=[recovery_profile()],
                )

            forced_kwargs = locate.call_args_list[0].kwargs
            revalidation_kwargs = locate.call_args_list[1].kwargs
            self.assertEqual([], forced_kwargs["calibrated_profiles"])
            self.assertTrue(forced_kwargs["defer_unmatched_profile_fallback"])
            self.assertTrue(forced_attempt["forced_local_profile_recovery"])
            self.assertEqual(1, len(revalidation_kwargs["calibrated_profiles"]))
            self.assertFalse(revalidation_kwargs["defer_unmatched_profile_fallback"])

            with patch("live_memory_locator.engine.process_memory_session"), patch.object(
                fh6_probe,
                "auto_locate_count_table",
                return_value=initial_no_profile_payload(),
            ):
                fh5_request = LocatorRequest(
                    "fh5",
                    123,
                    8,
                    "export",
                    root / "fh5-locator-session.json",
                )
                _payload, fh5_attempt = engine._fast_locate(
                    fh5_request,
                    get_adapter("fh5"),
                )
            self.assertFalse(fh5_attempt["forced_local_profile_recovery"])

    def test_unknown_build_defers_legacy_count_fallback_to_local_recovery(self):
        process = SimpleNamespace(name=lambda: "forzahorizon6.exe")

        def no_profile(_pid, _profile, _count, **_kwargs):
            fh6_probe.record_locator_diagnostic(
                "rtti_profile",
                module_size=0x0C000000,
                profile_count=0,
                matched=False,
            )
            return []

        with patch.object(fh6_probe.psutil, "Process", return_value=process), patch.object(
            fh6_probe, "locate_clivery_groups_by_rtti", side_effect=no_profile
        ), patch.object(
            fh6_probe, "locate_clivery_groups_by_layout_count"
        ) as layout, patch.object(
            fh6_probe, "find_count_candidates"
        ) as broad_count:
            payload = fh6_probe.auto_locate_count_table(
                123,
                SimpleNamespace(key="fh6"),
                8,
                limit_mb=1,
                max_matches=1,
                progress_every=1,
                radius=0x100,
                max_seconds=1,
                return_failure_payload=True,
                defer_unmatched_profile_fallback=True,
            )

        self.assertTrue(payload["profile_recovery_required"])
        self.assertFalse(payload.get("authoritative_no_match", False))
        layout.assert_not_called()
        broad_count.assert_not_called()

    def test_failed_recovery_is_one_shot_and_never_persists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(engine, "_process_identity", return_value=self.identity()), patch.object(
                engine,
                "_fast_locate",
                return_value=(
                    initial_no_profile_payload(),
                    {"name": "profile_locator", "status": "no_match"},
                ),
            ) as fast, patch.object(
                engine,
                "_recover_fh6_profile",
                return_value={
                    "status": "no_match",
                    "reason": "ambiguous",
                    "publication": "disabled",
                    "profile": None,
                },
            ) as recover, patch(
                "live_memory_locator.fh6_recovery.persist_local_profile"
            ) as persist:
                report = engine.locate(self.request(root))

            self.assertEqual("no_match", report["outcome"]["status"])
            self.assertEqual(1, fast.call_count)
            recover.assert_called_once()
            persist.assert_not_called()

    def test_verified_ownership_refusal_saves_profile_but_still_refuses_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = LiveMemoryLocatorEngine(root)
            profile = recovery_profile()
            refused = {
                "game": "fh6",
                "layer_count": 8,
                "refused": True,
                "refusal_reason": "Export refused: content is not exportable.",
                "locator_details": {"access_status": "foreign"},
                "rtti_profile_id": profile["profile_id"],
                "locator_diagnostics": {"rtti_profile": {"matched": True}},
            }
            with patch.object(engine, "_process_identity", return_value=self.identity()), patch.object(
                engine,
                "_fast_locate",
                side_effect=[
                    (initial_no_profile_payload(), {"name": "profile_locator", "status": "no_match"}),
                    (refused, {"name": "profile_locator", "status": "refused"}),
                ],
            ), patch.object(
                engine,
                "_recover_fh6_profile",
                return_value={
                    "status": "derived",
                    "reason": "derived",
                    "publication": "disabled",
                    "profile": dict(profile),
                },
            ), patch(
                "live_memory_locator.fh6_recovery.persist_local_profile", return_value=profile
            ) as persist:
                report = engine.locate(self.request(root))

            self.assertEqual("refused", report["outcome"]["status"])
            self.assertIsNone(report["selected"])
            persist.assert_called_once()

    def test_process_change_prevents_retry_and_profile_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = LiveMemoryLocatorEngine(root)
            profile = recovery_profile()
            changed = {**self.identity(), "started": 2.0}
            with patch.object(
                engine, "_process_identity", side_effect=[self.identity(), changed]
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(
                    initial_no_profile_payload(),
                    {"name": "profile_locator", "status": "no_match"},
                ),
            ) as fast, patch.object(
                engine,
                "_recover_fh6_profile",
                return_value={
                    "status": "derived",
                    "reason": "derived",
                    "publication": "disabled",
                    "profile": dict(profile),
                },
            ), patch(
                "live_memory_locator.fh6_recovery.persist_local_profile"
            ) as persist:
                report = engine.locate(self.request(root))

            self.assertEqual("no_match", report["outcome"]["status"])
            self.assertIn("process changed", report["outcome"]["reason"].lower())
            self.assertEqual(1, fast.call_count)
            persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
