"""Synthetic saved-livery JSON groups without changing canonical package decoding."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.cgroup import forza_source_decoder as decoder
from tools.cgroup.cgroup_codec import wrap_payload
from tools.cgroup.vinyl_document import encode_vinyl_document


def shape(x, path=()):
    return {"type": 1048677, "data": [x, 7, 1.25, -0.75, 31, 0.2, 0],
            "color": [10, 120, 230, 255], "mask": False,
            "editor_group_path": [{"id": key, "name": key} for key in path]}


def saved_payload(sections):
    def group(shapes, depth=0):
        children = []
        index = 0
        while index < len(shapes):
            item = shapes[index]
            path = item.get("editor_group_path", [])
            if len(path) > depth:
                stop = index + 1
                while stop < len(shapes) and shapes[stop].get("editor_group_path", [])[:depth + 1] == path[:depth + 1]:
                    stop += 1
                children.append((True, b"\x20" + group(shapes[index:stop], depth + 1)))
                index = stop
            else:
                x, y, sx, sy, angle, skew, _ = item["data"]
                r, g, b, a = item["color"]
                children.append((False, struct.pack("<BBH6f4B", 0, 2, item["type"] & 0xffff,
                                                   angle, x, y, sx, sy, skew, b, g, r, a)))
                index += 1
        bitmap = bytearray((len(children) + 7) // 8)
        for index, (nested, _) in enumerate(children):
            if nested:
                bitmap[index // 8] |= 1 << (index % 8)
        # Saved-livery records use count-delimited children, not standalone
        # vinyl explicit-close framing. Keep the synthetic formats independent.
        return struct.pack("<HH", len(children), len(bitmap)) + bytes(2) + bitmap + b"".join(data for _, data in children)

    body = bytearray()
    counts = []
    for slot, name in enumerate(decoder.LIVERY_SECTION_NAMES):
        shapes = sections.get(name, [])
        counts.append(len(shapes))
        if shapes:
            body.extend(group(shapes))
            body.extend(b"\0" + struct.pack("<4fB", 0, 0, 1, 0, 0))
        else:
            body.extend(bytes(6) + struct.pack("<4fB", 0, 0, 1, 0, 0))
    prefix = bytearray(51)
    prefix[:4] = b"vlrc"
    struct.pack_into("<I", prefix, 4, 2)
    struct.pack_into("<I", prefix, 16, 3307)
    prefix[26:30] = b"yrvl"
    struct.pack_into("<I", prefix, 30, 19)
    prefix[34:42] = b"TEST0001"
    chunk = b"gyvl" + struct.pack("<4fB", 0, 0, 1, 0, 0) + body
    struct.pack_into("<I", prefix, 47, len(chunk))
    return bytes(prefix) + chunk + b"yrvl" + struct.pack("<11I", *counts)


class LiveryGroupExportTests(unittest.TestCase):
    def fixture(self):
        return saved_payload({name: [shape(10, ("outer", "inner")), shape(20, ("outer", "inner")),
                                     shape(30, ("outer",)), shape(40)]
                              for name in ("Front", "Back", "Spoiler")})

    def test_opt_in_preserves_nested_groups_without_changing_geometry(self):
        raw = self.fixture()
        flat, old_report = decoder.clivery_to_layers(raw)
        grouped, report = decoder.clivery_to_layers(raw, preserve_groups=True)
        self.assertEqual(report, old_report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(len(flat), 12)
        self.assertEqual([{k: v for k, v in s.items() if k != "editor_group_path"} for s in grouped], flat)
        all_ids = []
        for section in ("Front", "Back", "Spoiler"):
            shapes = [s for s in grouped if s["section"] == section]
            paths = [s.get("editor_group_path", []) for s in shapes]
            self.assertEqual([len(p) for p in paths], [2, 2, 1, 0])
            self.assertEqual(paths[0], paths[1])
            self.assertEqual(paths[0][:1], paths[2])
            all_ids.append({g["id"] for p in paths for g in p})
        self.assertTrue(all_ids[0].isdisjoint(all_ids[1]))
        self.assertTrue(all_ids[0].isdisjoint(all_ids[2]))
        self.assertTrue(all_ids[1].isdisjoint(all_ids[2]))

    def test_actual_file_export_api_and_reencoding_keep_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "C_livery"
            source.write_bytes(wrap_payload(self.fixture()))
            exported = decoder.decode_forza_source(source, allow_locked=False)
            self.assertEqual(exported.report["warnings"], [])
            for name in ("Front", "Back", "Spoiler"):
                shapes = [s for s in exported.layers if s["source_section"] == name]
                self.assertEqual([len(s.get("editor_group_path", [])) for s in shapes], [2, 2, 1, 0])
                payload, encoded = encode_vinyl_document({"shapes": json.loads(json.dumps(shapes))}, "fh6")
                self.assertEqual(encoded["groups"], 2)
                restored, report = decoder.cgroup_to_layers(payload)
                self.assertFalse(report["warnings"])
                self.assertEqual([len(s.get("editor_group_path", [])) for s in restored], [2, 2, 1, 0])

    def test_flat_sections_do_not_gain_an_artificial_group(self):
        layers, report = decoder.clivery_to_layers(saved_payload({"Top": [shape(0), shape(1)]}), preserve_groups=True)
        self.assertFalse(report["warnings"])
        self.assertTrue(all("editor_group_path" not in s for s in layers))

    def test_privacy_still_blocks_unowned_saved_liveries(self):
        payload = bytearray(self.fixture())
        struct.pack_into("<I", payload, 8, 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "C_livery"
            path.write_bytes(wrap_payload(bytes(payload)))
            with self.assertRaises(decoder.DecodeError):
                decoder.decode_forza_source(path, allow_locked=False)


if __name__ == "__main__":
    unittest.main()
