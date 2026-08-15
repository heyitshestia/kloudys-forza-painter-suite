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
