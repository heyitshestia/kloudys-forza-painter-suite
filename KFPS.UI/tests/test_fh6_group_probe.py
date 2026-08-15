from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_group1000_probe as group_probe  # noqa: E402
import fh6_probe  # noqa: E402
from game_profiles import get_profile  # noqa: E402


def candidate(**overrides):
    item = {
        "group": "0x1000",
        "table": "0x2000",
        "count": 100,
        "vector_ok": True,
        "vector_count": 100,
        "capacity_count": 128,
        "valid_ptrs": 100,
        "invalid_ptrs": 0,
        "duplicate_ptr_count": 0,
        "layer_ok_count": 100,
        "score": 1,
    }
    item.update(overrides)
    return item


class Fh6GroupProbeTests(unittest.TestCase):
    def test_allocator_window_selection_clips_regions_without_crossing_bounds(self):
        regions = [
            (0x260000000, 0x18000000, 0x04, fh6_probe.MEM_PRIVATE),
            (0x278000000, 0x10000000, 0x04, fh6_probe.MEM_PRIVATE),
            (0x290000000, 0x01000000, 0x04, fh6_probe.MEM_PRIVATE),
        ]

        selected = fh6_probe.regions_in_allocator_windows(
            regions,
            [(0x270000000, 0x280000000)],
        )

        self.assertEqual(
            [
                (0x270000000, 0x08000000, 0x04, fh6_probe.MEM_PRIVATE),
                (0x278000000, 0x08000000, 0x04, fh6_probe.MEM_PRIVATE),
            ],
            selected,
        )

    def test_allocator_cache_persists_windows_but_never_a_group_pointer(self):
        rtti = {"profile_id": "profile-test"}
        with tempfile.TemporaryDirectory() as temp, patch.object(
            fh6_probe,
            "FH6_LOCATOR_CACHE_PATH",
            Path(temp) / "locator-cache.json",
        ):
            fh6_probe.save_fh6_allocator_cache(
                rtti,
                [(0x270000000, 0x280000000)],
            )
            cached = fh6_probe.load_fh6_allocator_cache(rtti)
            self.assertEqual([(0x270000000, 0x280000000)], cached["windows"])
            raw = json.loads(fh6_probe.FH6_LOCATOR_CACHE_PATH.read_text(encoding="utf-8"))
            profile_cache = raw["profiles"]["profile-test"]
            self.assertNotIn("group_address", profile_cache)
            self.assertNotIn("process", profile_cache)

    def test_calibrated_profile_uses_allocator_locator_exclusively(self):
        profile = get_profile("fh6")
        rtti = {"source": "calibrated_profile", "profile_id": "profile-test"}
        expected = [{"group_address": 0x272773BA0}]
        with patch.object(
            fh6_probe,
            "locate_clivery_group_rtti",
            return_value=rtti,
        ), patch.object(
            fh6_probe,
            "locate_clivery_group_by_allocator",
            return_value=expected,
        ) as allocator_locator, patch.object(
            fh6_probe,
            "locate_clivery_groups_by_calibrated_count",
        ) as count_locator, patch.object(
            fh6_probe,
            "locate_clivery_groups_by_calibrated_graph",
        ) as graph_locator:
            actual = fh6_probe.locate_clivery_groups_by_rtti(123, profile, 82)

        self.assertIs(expected, actual)
        allocator_locator.assert_called_once_with(123, profile, 82, rtti)
        count_locator.assert_not_called()
        graph_locator.assert_not_called()

    def test_complete_exact_rtti_no_match_skips_all_count_fallbacks(self):
        profile = get_profile("fh6")
        process = SimpleNamespace(name=lambda: "forzahorizon6.exe")

        def exact_no_match(_pid, _profile, _layer_count):
            fh6_probe.record_locator_diagnostic(
                "calibrated_exact_authoritative",
                complete=True,
                active_group_found=False,
            )
            return []

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "session.json"
            with patch.object(fh6_probe.psutil, "Process", return_value=process), patch.object(
                fh6_probe,
                "locate_clivery_groups_by_rtti",
                side_effect=exact_no_match,
            ), patch.object(
                fh6_probe,
                "locate_clivery_groups_by_layout_count",
            ) as layout_locator, patch.object(
                fh6_probe,
                "find_count_candidates",
            ) as count_locator:
                result = fh6_probe.auto_locate_count_table(
                    123,
                    profile,
                    82,
                    limit_mb=1,
                    max_matches=1,
                    progress_every=1,
                    radius=0x100,
                    output_path=output,
                    max_seconds=1,
                )

            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsNone(result)
            self.assertTrue(persisted["no_match"])
            self.assertTrue(persisted["authoritative_no_match"])
            layout_locator.assert_not_called()
            count_locator.assert_not_called()

    def test_incomplete_allocator_retry_fails_closed(self):
        failed_region = (0x270000000, 0x1000, 0x04, fh6_probe.MEM_PRIVATE)
        initial = [{"group_address": 0x272773BA0}]
        stats = {
            "complete": False,
            "stopped_by": "read_failure",
            "failed_regions": [failed_region],
        }
        retry_stats = {
            "complete": False,
            "stopped_by": "read_failure",
            "failed_regions": [failed_region],
            "failed_mb": 1,
            "vtable_hits": 0,
        }
        with patch.object(
            fh6_probe,
            "scan_exact_calibrated_vtables",
            return_value=([], [], retry_stats),
        ) as retry:
            with self.assertRaisesRegex(
                fh6_probe.LocatorRefused,
                "could not read every eligible",
            ):
                fh6_probe.finish_incomplete_exact_scan(
                    123,
                    get_profile("fh6"),
                    82,
                    {"vtables": [0x140001000]},
                    [failed_region],
                    initial,
                    [],
                    stats,
                    diagnostic_name="allocator_retry_test",
                    locator_kind="rtti_allocator_exact_retry",
                )

        retry.assert_called_once()

    def test_rejects_the_observed_duplicate_vector_invalid_false_candidate(self):
        observed_false_match = candidate(
            vector_ok=False,
            vector_count=-786944,
            capacity_count=512,
            valid_ptrs=100,
            duplicate_ptr_count=87,
            layer_ok_count=98,
            score=99152,
        )

        self.assertEqual(
            "vector metadata invalid",
            group_probe.candidate_rejection(observed_false_match, 100),
        )
        self.assertFalse(group_probe.candidate_is_strict(observed_false_match, 100))

    def test_strict_candidate_sorts_above_a_higher_scoring_false_match(self):
        strict = candidate(score=10)
        false_match = candidate(vector_ok=False, duplicate_ptr_count=87, score=999999)

        ordered = sorted([false_match, strict], key=group_probe.candidate_sort_key, reverse=True)

        self.assertIs(strict, ordered[0])
        self.assertTrue(group_probe.candidate_is_strict(strict, 100))

    def test_chunk_reader_covers_large_region_with_boundary_overlap(self):
        base = 0x10000
        source = bytes(index % 251 for index in range(9000))

        def read_memory(_handle, address, size):
            offset = address - base
            return source[offset:offset + size]

        with patch.object(group_probe, "read_memory", side_effect=read_memory):
            chunks = list(
                group_probe.iter_region_chunks(
                    object(),
                    {"base": base, "size": len(source)},
                    chunk_size=4096,
                    overlap=7,
                )
            )

        self.assertEqual([base, base + 4089, base + 8178], [address for address, _raw in chunks])
        self.assertEqual(base + len(source), chunks[-1][0] + len(chunks[-1][1]))
        self.assertEqual(chunks[0][1][-7:], chunks[1][1][:7])
        self.assertEqual(chunks[1][1][-7:], chunks[2][1][:7])

    def test_research_scan_interleaves_large_chunks_and_small_regions(self):
        regions = [
            {"base": 0x10000, "size": 4},
            {"base": 0x20000, "size": 4},
            {"base": 0x30000, "size": 9000},
            {"base": 0x40000, "size": 8000},
        ]

        with patch.object(
            group_probe,
            "read_memory",
            side_effect=lambda _handle, _address, size: b"x" * size,
        ):
            chunks = list(
                group_probe.iter_balanced_region_chunks(
                    object(),
                    regions,
                    chunk_size=4096,
                    small_regions_per_large=1,
                )
            )

        self.assertEqual(
            [0x30000, 0x10000, 0x40000, 0x20000, 0x31000, 0x41000, 0x32000],
            [address for _region, address, _raw, _unique in chunks],
        )

    def test_fast_scan_interleaves_large_chunks_and_small_regions(self):
        regions = [
            (0x10000, 4, 0, 0),
            (0x20000, 4, 0, 0),
            (0x30000, 9000, 0, 0),
            (0x40000, 8000, 0, 0),
        ]

        with patch.object(
            fh6_probe,
            "read_region",
            side_effect=lambda _pid, _address, size, max_size=None: b"x" * size,
        ):
            chunks = list(
                fh6_probe.iter_balanced_region_chunks(
                    123,
                    regions,
                    chunk_size=4096,
                    small_regions_per_large=1,
                )
            )

        self.assertEqual(
            [0x30000, 0x10000, 0x40000, 0x20000, 0x31000, 0x41000, 0x32000],
            [address for _region, address, _raw, _unique in chunks],
        )

    def test_fast_scan_can_prioritize_probable_editor_arenas(self):
        regions = [
            (0x10000, 4, 0, 0),
            (0x20000, 9000, 0, 0),
            (0x30000, 20000, 0, 0),
        ]

        with patch.object(
            fh6_probe,
            "read_region",
            side_effect=lambda _pid, _address, size, max_size=None: b"x" * size,
        ):
            chunks = list(
                fh6_probe.iter_balanced_region_chunks(
                    123,
                    regions,
                    chunk_size=4096,
                    small_regions_per_large=1,
                    preferred_size_range=(8000, 10000),
                )
            )

        self.assertEqual(0x20000, chunks[0][1])
        self.assertEqual(9000, chunks[0][3])

    def test_malformed_count_candidate_does_not_skip_vector_scan(self):
        false_match = candidate(vector_ok=False, duplicate_ptr_count=87, layer_ok_count=98)

        def count_scan(_handle, _regions, _contains, _count, _deadline, _report_layers, candidates, _seen):
            candidates.append(false_match)
            return {"scanned_mb": 1, "count_hits": 1}

        vector_stats = {"scanned_mb": 2, "vector_triple_hits": 1}
        with patch.object(group_probe, "iter_regions", return_value=[]), patch.object(
            group_probe, "scan_count_headers", side_effect=count_scan
        ), patch.object(group_probe, "scan_vector_headers", return_value=vector_stats) as vector_scan:
            _candidates, scanner = group_probe.scan_groups(object(), 100, 90, 40)

        vector_scan.assert_called_once()
        self.assertEqual(vector_stats, scanner["vector_scan"])
        self.assertEqual(0, scanner["strict_candidate_count"])

    def test_strict_count_candidate_safely_skips_vector_scan(self):
        strict = candidate()

        def count_scan(_handle, _regions, _contains, _count, _deadline, _report_layers, candidates, _seen):
            candidates.append(strict)
            return {"scanned_mb": 1, "count_hits": 1}

        with patch.object(group_probe, "iter_regions", return_value=[]), patch.object(
            group_probe, "scan_count_headers", side_effect=count_scan
        ), patch.object(group_probe, "scan_vector_headers") as vector_scan:
            _candidates, scanner = group_probe.scan_groups(object(), 100, 90, 40)

        vector_scan.assert_not_called()
        self.assertTrue(scanner["vector_scan"]["skipped"])
        self.assertEqual(1, scanner["strict_candidate_count"])

    def test_fast_locator_persists_a_no_match_report(self):
        profile = get_profile("fh6")
        process = SimpleNamespace(name=lambda: "forzahorizon6.exe")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "session.json"
            with patch.object(fh6_probe.psutil, "Process", return_value=process), patch.object(
                fh6_probe, "locate_clivery_groups_by_rtti", return_value=[]
            ), patch.object(fh6_probe, "locate_clivery_groups_by_layout_count", return_value=[]), patch.object(
                fh6_probe, "find_count_candidates", return_value=[]
            ):
                result = fh6_probe.auto_locate_count_table(
                    123,
                    profile,
                    100,
                    limit_mb=1,
                    max_matches=1,
                    progress_every=1,
                    radius=0x100,
                    output_path=output,
                    max_seconds=1,
                )

            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsNone(result)
            self.assertTrue(persisted["no_match"])
            self.assertFalse(persisted["refused"])
            self.assertIn("locator_diagnostics", persisted)


if __name__ == "__main__":
    unittest.main()
