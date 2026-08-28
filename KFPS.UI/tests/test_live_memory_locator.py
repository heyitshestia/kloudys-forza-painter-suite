from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from game_adapters import get_adapter  # noqa: E402
import fh6_export_typecode_json as live_export  # noqa: E402
from live_memory_locator.cache import LocatorCache  # noqa: E402
from live_memory_locator.contracts import (  # noqa: E402
    CACHE_SCHEMA,
    DIAGNOSTIC_SCHEMA,
    LocatorRequest,
    LocatorSelection,
    REPORT_INDEX_SCHEMA,
)
from live_memory_locator.diagnostics import (  # noqa: E402
    build_diagnostic,
    infer_store_variant,
    persist_diagnostic,
    read_diagnostic,
    wrap_backend_payload,
)
from live_memory_locator.engine import LiveMemoryLocatorEngine  # noqa: E402
from live_memory_locator.__main__ import main as locator_main  # noqa: E402
from live_memory_locator.validation import (  # noqa: E402
    fallback_candidate_sort_key,
    select_fallback_candidate,
    validate_fast_payload,
)


def fast_payload(*, count: int = 8, game: str = "fh6") -> dict:
    return {
        "game": game,
        "layer_count": count,
        "group_address": 0x100000000,
        "count_address": 0x10000005A,
        "table_pointer_field": 0x100000078,
        "table_address": 0x200000000,
        "locator": "rtti_allocator_exact",
        "validated_entries": count,
        "vector_count": count,
        "capacity_count": count,
        "import_group_address": 0x100000000,
        "import_count_address": 0x10000005A,
        "import_table_pointer_field": 0x100000078,
        "import_table_address": 0x200000000,
        "import_vector_count": count,
        "import_capacity_count": count,
        "import_target_verified": True,
        "export_access_verified": True,
        "flattened_from_groups": True,
        "flattened_group_count": 47,
        "flattened_max_depth": 4,
        "shape_word_counts": {"102": count},
        "rtti_source": "calibrated_profile",
        "rtti_profile_id": "profile-test",
    }


class LiveMemoryLocatorTests(unittest.TestCase):
    def request(self, root: Path, *, purpose: str = "export", count: int = 8, game: str = "fh6"):
        return LocatorRequest(
            game=game,
            pid=123,
            layer_count=count,
            purpose=purpose,
            output_path=root / "locator-session.json",
        )

    def test_request_rejects_invalid_layer_count_and_purpose(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "between 1 and 3000"):
                self.request(root, count=3001)
            with self.assertRaisesRegex(ValueError, "purpose"):
                LocatorRequest("fh6", 1, 8, "erase", root / "report.json")

    def test_store_variant_comes_from_the_running_executable(self):
        self.assertEqual(
            "steam",
            infer_store_variant(
                {
                    "name": "forza_steamworks_release_final.exe",
                    "executable": r"D:\SteamLibrary\steamapps\common\Forza Motorsport\game.exe",
                }
            ),
        )
        self.assertEqual(
            "microsoft_xbox",
            infer_store_variant(
                {
                    "name": "forzahorizon6.exe",
                    "executable": r"C:\Program Files\WindowsApps\ForzaHorizon6\game.exe",
                }
            ),
        )
        self.assertEqual(
            "microsoft_xbox",
            infer_store_variant(
                {
                    "name": "forzahorizon6.exe",
                    "executable": r"D:\XboxGames\Forza Horizon 6\Content\game.exe",
                }
            ),
        )
        self.assertEqual(
            "unknown",
            infer_store_variant({"name": "forzahorizon5.exe", "executable": ""}),
        )

    def test_diagnostic_scrubs_user_profile_paths(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "live_memory_locator.diagnostics._windows_gpu_snapshot",
            return_value=[],
        ):
            request = self.request(Path(temp))
            report = build_diagnostic(
                request=request,
                root=temp,
                process={
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": r"C:\Users\Alice\Games\Forza\game.exe",
                },
                profile={"game": "fh6", "strategy": "test", "profile_id": "test"},
                status="no_match",
                reason=r"See C:\Users\Alice\Desktop\report.json",
                authoritative=True,
                attempts=[],
                selection=None,
            )

        serialized = json.dumps(report)
        self.assertNotIn("Alice", serialized)
        self.assertIn(r"C:\\Users\\<user>", serialized)

    def test_fast_payload_requires_exact_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.request(Path(temp))
            payload = fast_payload()
            payload["validated_entries"] = 7
            result = validate_fast_payload(payload, request, get_adapter("fh6"))
            self.assertFalse(result.ok)
            self.assertIn("7/8", " ".join(result.reasons))

    def test_fast_payload_preserves_group_shape_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            result = validate_fast_payload(
                fast_payload(),
                self.request(Path(temp)),
                get_adapter("fh6"),
            )

        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(47, result.selection.details["flattened_group_count"])
        self.assertEqual(4, result.selection.details["flattened_max_depth"])

    def test_import_requires_exact_leaf_and_template_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.request(Path(temp), purpose="import")
            payload = fast_payload()
            payload["import_target_verified"] = False
            result = validate_fast_payload(payload, request, get_adapter("fh6"))
            self.assertFalse(result.ok)
            self.assertIn("single exact writable import table", " ".join(result.reasons))

            payload = fast_payload()
            payload["shape_word_counts"] = {"102": 1}
            result = validate_fast_payload(payload, request, get_adapter("fh6"))
            self.assertFalse(result.ok)
            self.assertIn("template shape check", " ".join(result.reasons))

    def test_research_ranking_is_stable_for_equal_candidates(self):
        common = {
            "strict_valid": True,
            "valid_ptrs": 8,
            "invalid_ptrs": 0,
            "duplicate_ptr_count": 0,
            "layer_ok_count": 8,
            "vector_ok": True,
            "vector_count": 8,
            "capacity_count": 8,
            "score": 100,
        }
        lower = {**common, "group": "0x100000000", "table": "0x200000000"}
        higher = {**common, "group": "0x100001000", "table": "0x200001000"}
        ordered = sorted(
            [higher, lower],
            key=lambda item: fallback_candidate_sort_key(item, 8),
            reverse=True,
        )
        self.assertIs(lower, ordered[0])

    def test_research_candidate_rejects_duplicate_or_partial_tables(self):
        with tempfile.TemporaryDirectory() as temp:
            request = self.request(Path(temp))
            candidate = {
                "group": "0x100000000",
                "table": "0x200000000",
                "valid_ptrs": 8,
                "invalid_ptrs": 0,
                "duplicate_ptr_count": 1,
                "layer_ok_count": 8,
                "vector_ok": True,
                "vector_count": 8,
                "capacity_count": 8,
            }
            result = select_fallback_candidate([candidate], request, get_adapter("fh6"))
            self.assertFalse(result.ok)
            self.assertIn("duplicate_ptrs=1", " ".join(result.reasons))

    def test_cache_migrates_allocator_windows_without_live_pointers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = root / "legacy.json"
            legacy.write_text(
                json.dumps(
                    {
                        "format": "kfps_fh6_allocator_cache_v2",
                        "profiles": {
                            "profile-test": {
                                "allocator_windows": [[0x270000000, 0x280000000]],
                                "group_address": 0x277000000,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cache = LocatorCache(root / "cache.json", legacy_path=legacy)
            self.assertEqual([(0x270000000, 0x280000000)], cache.allocator_windows("profile-test"))
            cache.update_allocator_windows("fh6", "profile-test", [(0x270000000, 0x280000000)])
            raw = json.loads((root / "cache.json").read_text(encoding="utf-8"))
            self.assertEqual(CACHE_SCHEMA, raw["schema"])
            self.assertNotIn("group_address", json.dumps(raw))

    def test_malformed_current_cache_does_not_block_legacy_window_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "cache.json"
            legacy = root / "legacy.json"
            current.write_text('{"schema":"unknown"}', encoding="utf-8")
            legacy.write_text(
                json.dumps(
                    {
                        "format": "kfps_fh6_allocator_cache_v2",
                        "profiles": {
                            "profile-test": {
                                "allocator_windows": [[0x270000000, 0x280000000]],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cache = LocatorCache(current, legacy_path=legacy)
            self.assertEqual([(0x270000000, 0x280000000)], cache.allocator_windows("profile-test"))

    def test_cache_rejects_any_session_pointer_field(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = LocatorCache(Path(temp) / "cache.json")
            with self.assertRaisesRegex(ValueError, "cannot be persisted"):
                cache.record_session("test", {"group_address": 0x100000000})
            with self.assertRaisesRegex(ValueError, "cannot be persisted"):
                cache.record_session("test", {"nested": [{"table_pointer": 0x200000000}]})

    def test_engine_writes_one_canonical_report_and_pointer_free_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "VERSION").write_text("test", encoding="utf-8")
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={"pid": 123, "name": "forzahorizon6.exe", "started": 1.0, "executable": ""},
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(fast_payload(), {"name": "profile_locator", "status": "located"}),
            ), patch.object(engine, "_research_locate") as research:
                report = engine.locate(request)

            research.assert_not_called()
            persisted = read_diagnostic(request.output_path)
            self.assertEqual(DIAGNOSTIC_SCHEMA, persisted["schema"])
            self.assertEqual("located", report["outcome"]["status"])
            self.assertEqual(0x100000000, report["selected"]["group_address"])
            self.assertIn("environment", report)
            self.assertIn("gpus", report["environment"])
            archive = root / report["report_archive"]["archive_path"]
            latest = root / report["report_archive"]["latest_path"]
            operation_latest = root / report["report_archive"]["operation_latest_path"]
            index_path = root / report["report_archive"]["index_path"]
            self.assertTrue(archive.is_file())
            self.assertTrue(latest.is_file())
            self.assertTrue(operation_latest.is_file())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(REPORT_INDEX_SCHEMA, index["schema"])
            self.assertEqual(1, len(index["reports"]))
            self.assertEqual(archive.name, Path(index["latest"]).name)
            cache_text = (root / "runtime" / "live-memory" / "locator-cache.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("group_address", cache_text)
            self.assertNotIn("table_address", cache_text)

    def test_report_index_rebuilds_from_dated_reports_after_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            identity = {
                "pid": 123,
                "name": "forzahorizon6.exe",
                "started": 1.0,
                "executable": r"C:\Program Files\WindowsApps\ForzaHorizon6\game.exe",
            }
            for index in range(2):
                with patch.object(engine, "_process_identity", return_value=identity), patch.object(
                    engine,
                    "_fast_locate",
                    return_value=(fast_payload(), {"name": "profile_locator", "status": "located"}),
                ):
                    engine.locate(request)
                if index == 0:
                    (root / "runtime" / "live-memory" / "reports" / "index.json").write_text(
                        "{broken",
                        encoding="utf-8",
                    )

            report_index = json.loads(
                (root / "runtime" / "live-memory" / "reports" / "index.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(2, len(report_index["reports"]))
            self.assertEqual(
                2,
                len(list((root / "runtime" / "live-memory" / "reports").glob("????-??-??/*.json"))),
            )

    def test_backfilled_report_cannot_replace_a_newer_latest_alias(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "live_memory_locator.diagnostics._windows_gpu_snapshot",
            return_value=[],
        ):
            root = Path(temp)
            request = self.request(root)
            common = {
                "request": request,
                "root": root,
                "process": {
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": "",
                },
                "profile": {"game": "fh6", "strategy": "test", "profile_id": "test"},
                "status": "no_match",
                "reason": "test",
                "authoritative": True,
                "attempts": [],
                "selection": None,
            }
            newer = build_diagnostic(**common)
            newer.update(
                {
                    "diagnostic_id": "newer-report",
                    "created": 20.0,
                    "created_utc": "2026-08-26T00:00:20Z",
                }
            )
            older = build_diagnostic(**common)
            older.update(
                {
                    "diagnostic_id": "older-report",
                    "created": 10.0,
                    "created_utc": "2026-08-26T00:00:10Z",
                }
            )
            persist_diagnostic(root, root / "newer.json", newer)
            persist_diagnostic(root, root / "older.json", older)

            reports_root = root / "runtime" / "live-memory" / "reports"
            self.assertEqual(
                "newer-report",
                json.loads((reports_root / "latest.json").read_text(encoding="utf-8"))[
                    "diagnostic_id"
                ],
            )
            self.assertEqual(
                "newer-report",
                json.loads(
                    (reports_root / "latest" / "fh6-export.json").read_text(encoding="utf-8")
                )["diagnostic_id"],
            )

    def test_archive_confines_untrusted_report_metadata_to_report_root(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "live_memory_locator.diagnostics._windows_gpu_snapshot",
            return_value=[],
        ):
            root = Path(temp)
            request = self.request(root)
            report = build_diagnostic(
                request=request,
                root=root,
                process={
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": "",
                },
                profile={"game": "fh6", "strategy": "test", "profile_id": "test"},
                status="no_match",
                reason="test",
                authoritative=True,
                attempts=[],
                selection=None,
            )
            report["created_utc"] = "../../outside"
            report["diagnostic_id"] = "../../escape"

            persisted = persist_diagnostic(root, request.output_path, report)
            reports_root = root / "runtime" / "live-memory" / "reports"
            archive_path = root / persisted["report_archive"]["archive_path"]

            self.assertTrue(archive_path.is_relative_to(reports_root))
            self.assertTrue(archive_path.is_file())
            self.assertNotIn("..", archive_path.name)

    def test_tampered_index_path_is_rebuilt_without_escaping_report_root(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "live_memory_locator.diagnostics._windows_gpu_snapshot",
            return_value=[],
        ):
            root = Path(temp)
            request = self.request(root)
            common = {
                "request": request,
                "root": root,
                "process": {
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": "",
                },
                "profile": {"game": "fh6", "strategy": "test", "profile_id": "test"},
                "status": "no_match",
                "reason": "test",
                "authoritative": True,
                "attempts": [],
                "selection": None,
            }
            first = build_diagnostic(**common)
            first.update(
                {
                    "diagnostic_id": "first-report",
                    "created": 10.0,
                    "created_utc": "2026-08-26T12:00:00Z",
                }
            )
            persist_diagnostic(root, request.output_path, first)
            reports_root = root / "runtime" / "live-memory" / "reports"
            index_path = reports_root / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["reports"][0]["path"] = "../../outside.json"
            index["latest"] = "../../outside.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")

            second = build_diagnostic(**common)
            second.update(
                {
                    "diagnostic_id": "second-report",
                    "created": 20.0,
                    "created_utc": "2026-08-26T12:01:00Z",
                }
            )
            persisted = persist_diagnostic(root, request.output_path, second)

            self.assertNotIn("write_error", persisted["report_archive"])
            latest = json.loads((reports_root / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual("second-report", latest["diagnostic_id"])

    def test_report_archive_failure_does_not_change_a_located_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": "",
                },
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(fast_payload(), {"name": "profile_locator", "status": "located"}),
            ), patch(
                "live_memory_locator.diagnostics._load_or_rebuild_report_index",
                side_effect=OSError("archive unavailable"),
            ):
                report = engine.locate(request)

            self.assertEqual("located", report["outcome"]["status"])
            self.assertIn("archive unavailable", report["report_archive"]["write_error"])
            self.assertEqual("located", read_diagnostic(request.output_path)["outcome"]["status"])

    def test_second_run_reports_safe_previous_session_without_reusing_addresses(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            identity = {
                "pid": 123,
                "name": "forzahorizon6.exe",
                "started": 1.0,
                "executable": "",
            }
            for index in range(2):
                with patch.object(engine, "_process_identity", return_value=identity), patch.object(
                    engine,
                    "_fast_locate",
                    return_value=(fast_payload(), {"name": "profile_locator", "status": "located"}),
                ):
                    report = engine.locate(request)
                if index == 0:
                    self.assertIsNone(report["cache"]["previous_session"])
                else:
                    self.assertEqual("located", report["cache"]["previous_session"]["status"])
            cache_text = (root / "runtime" / "live-memory" / "locator-cache.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("0x100000000", cache_text)
            self.assertNotIn("group_address", cache_text)

    def test_process_identity_change_rejects_an_otherwise_valid_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            before = {
                "pid": 123,
                "name": "forzahorizon6.exe",
                "started": 1.0,
                "executable": "",
            }
            after = {**before, "started": 2.0}
            with patch.object(engine, "_process_identity", side_effect=(before, after)), patch.object(
                engine,
                "_fast_locate",
                return_value=(fast_payload(), {"name": "profile_locator", "status": "located"}),
            ):
                report = engine.locate(request)
            self.assertEqual("error", report["outcome"]["status"])
            self.assertIsNone(report["selected"])

    def test_wrong_process_name_is_rejected_before_any_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={"pid": 123, "name": "notepad.exe", "started": 1.0, "executable": ""},
            ), patch.object(engine, "_fast_locate") as fast:
                with self.assertRaisesRegex(RuntimeError, "not a supported FH6 process"):
                    engine.locate(request)
            fast.assert_not_called()

    def test_cli_writes_canonical_diagnostic_when_engine_fails_before_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "locator-session.json"
            argv = [
                "live-memory-locator",
                "--root",
                str(root),
                "--game",
                "fh6",
                "--pid",
                "123",
                "--layer-count",
                "8",
                "--purpose",
                "export",
                "--output",
                str(output),
            ]
            with patch.object(sys, "argv", argv), patch(
                "live_memory_locator.__main__.LiveMemoryLocatorEngine.locate",
                side_effect=RuntimeError("pre-scan failure"),
            ):
                self.assertEqual(4, locator_main())
            report = read_diagnostic(output)
            self.assertEqual("error", report["outcome"]["status"])
            self.assertIn("pre-scan failure", report["outcome"]["reason"])

    def test_direct_backend_payload_uses_the_same_diagnostic_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            wrapped = wrap_backend_payload(
                {
                    "format": "fh6_group1000_probe_v2",
                    "pid": 123,
                    "game": "fh6",
                    "count": 8,
                    "candidates": [],
                    "no_match": True,
                    "failure_reason": "no exact candidate",
                },
                root=Path(temp),
            )
            self.assertEqual(DIAGNOSTIC_SCHEMA, wrapped["schema"])
            self.assertEqual("no_match", wrapped["outcome"]["status"])
            self.assertEqual(8, wrapped["request"]["layer_count"])

    def test_direct_fast_backend_payload_gets_a_canonical_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            wrapped = wrap_backend_payload(fast_payload(), root=Path(temp))
            self.assertEqual("located", wrapped["outcome"]["status"])
            self.assertEqual(0x100000000, wrapped["selected"]["group_address"])

    def test_report_reader_rejects_located_outcome_without_selected_addresses(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": DIAGNOSTIC_SCHEMA,
                        "request": {
                            "game": "fh6",
                            "pid": 123,
                            "layer_count": 8,
                            "purpose": "export",
                        },
                        "outcome": {"status": "located", "authoritative": True},
                        "selected": None,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no selected group"):
                read_diagnostic(path)

    def test_report_reader_rejects_partial_selected_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partial.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": DIAGNOSTIC_SCHEMA,
                        "request": {
                            "game": "fh6",
                            "pid": 123,
                            "layer_count": 8,
                            "purpose": "export",
                        },
                        "outcome": {"status": "located", "authoritative": True},
                        "selected": {
                            "group_address": 0x10000,
                            "table_address": 0x20000,
                            "validated_entries": 7,
                            "vector_count": 8,
                            "capacity_count": 8,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exact requested layer count"):
                read_diagnostic(path)

    def test_refusal_and_authoritative_no_match_are_terminal(self):
        cases = (
            ({"game": "fh6", "layer_count": 8, "refused": True, "refusal_reason": "blocked"}, "refused"),
            (
                {
                    "game": "fh6",
                    "layer_count": 8,
                    "no_match": True,
                    "authoritative_no_match": True,
                    "failure_reason": "complete scan",
                },
                "no_match",
            ),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                request = self.request(root)
                engine = LiveMemoryLocatorEngine(root)
                with patch.object(
                    engine,
                    "_process_identity",
                    return_value={"pid": 123, "name": "forzahorizon6.exe", "started": 1.0, "executable": ""},
                ), patch.object(
                    engine,
                    "_fast_locate",
                    return_value=(payload, {"name": "profile_locator", "status": expected}),
                ), patch.object(engine, "_research_locate") as research:
                    report = engine.locate(request)
                research.assert_not_called()
                self.assertEqual(expected, report["outcome"]["status"])

    def test_import_refusal_uses_import_wording(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root, purpose="import")
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={
                    "pid": 123,
                    "name": "forzahorizon6.exe",
                    "started": 1.0,
                    "executable": "",
                },
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(
                    {
                        "game": "fh6",
                        "layer_count": 8,
                        "refused": True,
                        "refusal_reason": "Export refused: this vinyl is not exportable.",
                    },
                    {"name": "profile_locator", "status": "refused"},
                ),
            ):
                report = engine.locate(request)

            self.assertEqual("refused", report["outcome"]["status"])
            self.assertEqual(
                "Import refused: this vinyl is not exportable.",
                report["outcome"]["reason"],
            )

    def test_unexpected_profile_locator_error_is_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={"pid": 123, "name": "forzahorizon6.exe", "started": 1.0, "executable": ""},
            ), patch.object(
                engine,
                "_fast_locate",
                side_effect=NameError("pid is not defined"),
            ), patch.object(engine, "_research_locate") as research:
                report = engine.locate(request)
            research.assert_not_called()
            self.assertEqual("error", report["outcome"]["status"])
            self.assertIn("pid is not defined", report["outcome"]["reason"])

    def test_non_authoritative_miss_uses_one_research_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            engine = LiveMemoryLocatorEngine(root)
            selection = LocatorSelection(
                0x100000000,
                0x200000000,
                0x10000005A,
                0x100000078,
                "research_count_header",
                8,
            )
            with patch.object(
                engine,
                "_process_identity",
                return_value={"pid": 123, "name": "forzahorizon6.exe", "started": 1.0, "executable": ""},
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(
                    {"game": "fh6", "layer_count": 8, "no_match": True},
                    {"name": "profile_locator", "status": "no_match"},
                ),
            ), patch.object(
                engine,
                "_research_locate",
                return_value=(selection, (), {"name": "research_count_table", "status": "located"}),
            ) as research:
                report = engine.locate(request)
            research.assert_called_once()
            self.assertEqual("located", report["outcome"]["status"])
            self.assertEqual(3, len(report["attempts"]))
            self.assertEqual("verified", report["attempts"][-1]["status"])

    def test_canonical_research_report_is_accepted_only_with_exact_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = self.request(root)
            candidate = {
                "group": "0x100000000",
                "table": "0x200000000",
                "valid_ptrs": 8,
                "invalid_ptrs": 0,
                "duplicate_ptr_count": 0,
                "layer_ok_count": 8,
                "vector_ok": True,
                "vector_count": 8,
                "capacity_count": 8,
                "score": 100,
            }
            selected_result = select_fallback_candidate([candidate], request, get_adapter("fh6"))
            self.assertTrue(selected_result.ok, selected_result.reasons)
            engine = LiveMemoryLocatorEngine(root)
            with patch.object(
                engine,
                "_process_identity",
                return_value={"pid": 123, "name": "forzahorizon6.exe", "started": 1.0, "executable": ""},
            ), patch.object(
                engine,
                "_fast_locate",
                return_value=(
                    {"game": "fh6", "layer_count": 8, "no_match": True},
                    {"name": "profile_locator", "status": "no_match"},
                ),
            ), patch.object(
                engine,
                "_research_locate",
                return_value=(
                    selected_result.selection,
                    (),
                    {"name": "research_count_table", "status": "located"},
                ),
            ):
                report = engine.locate(request)

            ok, reasons = live_export.validate_probe_report(
                request.output_path,
                8,
                0x100000000,
                0x200000000,
            )
            self.assertTrue(ok, reasons)

            report["selected"]["details"]["candidate"]["duplicate_ptr_count"] = 1
            ok, reasons = live_export.validate_canonical_locator_report(
                report,
                8,
                0x100000000,
                0x200000000,
            )
            self.assertFalse(ok)
            self.assertIn("duplicate", " ".join(reasons))


if __name__ == "__main__":
    unittest.main()
