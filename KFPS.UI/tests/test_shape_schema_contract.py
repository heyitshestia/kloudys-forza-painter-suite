import json
import sys
import tempfile
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
for entry in (str(ROOT), str(UI / "src"), str(ROOT / "tools" / "fabric-editor")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from json_preview_renderer import _resolve_vinyl_resource as preview_resource
from kfps_shapes import (
    convert_fd6_payload,
    detect_payload_schema,
    payload_uses_typecodes,
    resolve_vinyl_resource,
    shape_list,
)
from kfps_ui.community_validation import detect_payload_schema as community_schema
from kfps_ui.json_service import JsonService
from start_fabric_editor import _resolve_vinyl_resource as editor_resource


class ShapeSchemaContractTests(unittest.TestCase):
    def test_shape_lists_share_one_contract(self):
        rows = [{"type": 16, "data": [0, 0, 1, 1], "color": [1, 2, 3, 255]}]
        for payload in (rows, {"shapes": rows}, {"layers": rows}, {"items": rows}):
            self.assertIs(shape_list(payload), rows)
        with self.assertRaisesRegex(ValueError, "supported shape list"):
            shape_list({"other": rows})

    def test_schema_detection_matches_community_boundary(self):
        cases = [
            {"format": "fh6_typecode_json_export_v1", "source": {"game": "fh4"}, "shapes": []},
            {"format": "fh6_typecode_json_export_v1", "shapes": []},
            {"format": "kfps.fd6.converted.v1", "shapes": []},
            {"shapes": [{"type": 1048678, "type_word": 102, "data": [0, 0, 1, 1], "color": [1, 2, 3, 255]}]},
            {"format": "unknown.v2", "shapes": []},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(detect_payload_schema(payload), community_schema(payload))

    def test_typecode_detection_is_tolerant_of_invalid_type_values(self):
        payload = {"shapes": [{"type": "not-an-integer", "data": [], "color": []}]}
        self.assertFalse(payload_uses_typecodes(payload))

    def test_resource_identity_matches_preview_and_editor(self):
        cases = [
            (1051516, {}, ("Upper_Letters_7", 40)),
            (0, {"resourceFamily": "Primitives", "resourceIndex": "2"}, ("Primitives", 2)),
            (0, {"type_word": 102}, ("Primitives", 2)),
        ]
        for type_code, shape, expected in cases:
            with self.subTest(type_code=type_code, shape=shape):
                self.assertEqual(expected, resolve_vinyl_resource(type_code, shape, ROOT / "tools" / "fabric-editor" / "shape-words.json"))
                self.assertEqual(expected, preview_resource(type_code, shape))
                self.assertEqual(expected, editor_resource(type_code, shape))

    def test_fd6_conversion_matches_json_service_compatibility_api(self):
        payload = {
            "format": "fd6.shapes",
            "image_size": [200, 100],
            "shapes": [
                {"type": "rotated_ellipse", "x": 120, "y": 70, "rx": 63, "ry": 31.5, "angle": 90, "color": [1, 2, 3, 128]},
                {"type": "rotated_rectangle", "x": 80, "y": 30, "hw": 63.5, "hh": 127, "angle": 0, "color": [0.5, 0.25, 0, 1]},
                {"type": "triangle", "color": [255, 255, 255, 255]},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "sample.json"
            canonical = convert_fd6_payload(payload, source)
            compatibility = JsonService._convert_fd6_payload(payload, source)
        self.assertEqual(canonical, compatibility)
        converted, count, skipped = canonical
        self.assertEqual((count, skipped), (2, 1))
        self.assertEqual(converted["shapes"][0]["data"], [20.0, -20.0, 1.0, 0.5, 270.0, 0, 0])
        self.assertEqual(converted["shapes"][1]["color"], [128, 64, 0, 255])


if __name__ == "__main__":
    unittest.main()
