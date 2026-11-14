from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI.parent), str(UI / "src")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from test_fm8_group_boundaries import payload, shape
from test_fm8_offline_transfer import fm8_header, write_group
from tools.cgroup import forza_source_decoder as decoder


class CGroupScanPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.groups = self.base / "LayerGroups"
        self.folder = write_group(self.groups, "preservation-fixture")
        self.source = self.folder / "data"
        (self.folder / "header").write_bytes(fm8_header(layer_count=2))
        self.complete = payload(shape() + shape(3514), [False, False])
        self.partial = payload(shape(), [False, False])
        self.repaired = payload(shape(3515) + shape(3514), [False, False])
        self.source.write_bytes(self.complete)
        paths = AppPaths(self.base, UI, UI / "qml", UI / "assets",
                         self.base / "runtime", Path(sys.executable))
        self.service = CGroupLibraryService(paths, None, None, None)
        self.addCleanup(self.service.close)
        for name, value in (("_default_save_roots", [self.groups]),
                            ("_discover_save_artifacts", [self.source]),
                            ("_save_cached_roots", None), ("_write_preview", None)):
            mock = patch.object(self.service, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def scan(self):
        return self.service._scan_work("fm8")

    def snapshot(self):
        return {p.relative_to(self.service._library_root("fm8")): p.read_bytes()
                for p in self.service._library_root("fm8").rglob("*") if p.is_file()}

    def assert_preserved(self, before, result):
        self.assertEqual(0, result["exported"])
        self.assertEqual(1, result["skipped"])
        self.assertEqual([], result["outputs"])
        self.assertEqual(before, self.snapshot())
        self.assertTrue(result["issues"])

    def test_complete_partial_repaired_rescan_preserves_then_replaces(self):
        first = Path(self.scan()["outputs"][0])
        self.assertEqual(2, len(json.loads(first.read_text())["shapes"]))
        before = self.snapshot()
        self.source.write_bytes(self.partial)
        self.assert_preserved(before, self.scan())
        self.assertEqual(self.partial, self.source.read_bytes())
        self.source.write_bytes(self.repaired)
        final = self.scan()
        self.assertEqual(1, final["exported"])
        self.assertFalse(first.exists())
        document = json.loads(Path(final["outputs"][0]).read_text())
        self.assertEqual(2, len(document["shapes"]))
        self.assertEqual(3515, document["shapes"][0]["type_word"])
        self.assertEqual(self.repaired, self.source.read_bytes())

    def test_first_partial_scan_does_not_publish(self):
        self.source.write_bytes(self.partial)
        self.assert_preserved({}, self.scan())

    def test_skipped_unsupported_record_cannot_replace_complete_export(self):
        self.scan()
        before = self.snapshot()
        self.source.write_bytes(payload(shape() + shape(0x1000), [False, False]))
        self.assert_preserved(before, self.scan())

    def test_mutation_during_discovery_or_export_decode_preserves_previous(self):
        self.scan()
        before = self.snapshot()
        original = decoder.decode_forza_source
        for mutate_call in (1, 2):
            with self.subTest(mutate_call=mutate_call):
                self.source.write_bytes(self.complete)
                calls = 0

                def changing_decode(*args, **kwargs):
                    nonlocal calls
                    decoded = original(*args, **kwargs)
                    calls += 1
                    if calls == mutate_call:
                        self.source.write_bytes(self.repaired)
                    return decoded

                with patch.object(decoder, "decode_forza_source", side_effect=changing_decode), patch(
                    "tools.cgroup.find_forza_sources.decode_forza_source", side_effect=changing_decode
                ):
                    self.assert_preserved(before, self.scan())
                self.assertEqual(self.repaired, self.source.read_bytes())

    def test_source_disappearing_during_decode_is_a_preserving_skip(self):
        self.scan()
        before = self.snapshot()
        original = decoder.decode_forza_source
        calls = 0

        def removing_decode(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.source.unlink()
            return original(*args, **kwargs)

        with patch.object(decoder, "decode_forza_source", side_effect=removing_decode), patch(
            "tools.cgroup.find_forza_sources.decode_forza_source", side_effect=removing_decode
        ):
            self.assert_preserved(before, self.scan())

    def test_identity_warnings_do_not_block_complete_scan(self):
        original = decoder.decode_forza_source

        def warning_decode(*args, **kwargs):
            decoded = original(*args, **kwargs)
            decoded.report["identity_warnings"] = ["ambiguous resource identity"]
            return decoded

        with patch.object(decoder, "decode_forza_source", side_effect=warning_decode):
            result = self.scan()
        self.assertEqual(1, result["exported"])
        report = json.loads(Path(result["outputs"][0]).with_suffix(".report.json").read_text())
        self.assertEqual(["ambiguous resource identity"], report["identity_warnings"])

    def test_structural_warnings_and_counters_block_publication(self):
        self.scan()
        before = self.snapshot()
        original = decoder.decode_forza_source
        for fields in ({"warnings": ["decoder stopped before end"]},
                       {"incomplete_counted_groups": 1}, {"missing_counted_children": 1},
                       {"skipped_counted_children": 1}, {"unrecognized_byte_count": 1}):
            with self.subTest(fields=fields):
                def damaged_decode(*args, **kwargs):
                    decoded = original(*args, **kwargs)
                    decoded.report.update(fields)
                    return decoded

                with patch.object(decoder, "decode_forza_source", side_effect=damaged_decode):
                    self.assert_preserved(before, self.scan())


if __name__ == "__main__":
    unittest.main()
