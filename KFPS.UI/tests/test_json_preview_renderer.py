import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "fabric-editor"))

from json_preview_renderer import (
    _ellipse_points,
    _rect_points,
    _render_polygons,
    _resolve_full_type_resource,
    _shape_mask_flag,
    render_json_preview,
    _resource_triangles,
    VINYL_RESOURCE_ROOT,
)
from start_fabric_editor import _resolve_full_type_resource as editor_resolve_full_type_resource


def _span(points, axis):
    values = [point[axis] for point in points]
    return max(values) - min(values)


def _square(radius):
    return [(-radius, -radius), (radius, -radius), (radius, radius), (-radius, radius)]


def _open_preview(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA")


class JsonPreviewRendererTests(unittest.TestCase):
    def test_all_fonts_omit_four_transparent_registration_triangles(self):
        for font in range(1, 12):
            for block in ("Upper", "Lower"):
                family = f"{block}_Letters_{font}"
                for index in range(1, 41):
                    payload = json.loads((VINYL_RESOURCE_ROOT / family / str(index)).read_text())
                    self.assertEqual(len(payload["Indices"]) // 3 - 4, len(_resource_triangles(family, index)), (family, index))

    def test_typecode_preview_preserves_vertex_alpha_and_omits_invisible_geometry(self):
        visible = [(-10, -10), (10, -10), (0, 10)]
        invisible = [(1000, 1000), (1010, 1000), (1000, 1010)]
        shape = {"type": 0x100000 + 1901, "data": [0, 0, 1, 1, 0, 0, 0], "color": [10, 20, 30, 255]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "font.json"
            path.write_text(json.dumps({"shapes": [shape]}))
            with patch("json_preview_renderer._resource_alpha_triangles", return_value=[(visible, (0, 128, 255)), (invisible, (0, 0, 0))]):
                image = _open_preview(render_json_preview(path, max_size=128, transparent_background=True))
        self.assertLessEqual(max(image.size), 128)
        histogram = image.getchannel("A").histogram()
        alphas = [value for value, count in enumerate(histogram) if count]
        self.assertEqual(0, min(alphas))
        self.assertGreater(max(alphas), 200)
        self.assertGreater(len(set(alphas)), 50)
        self.assertGreater(sum(histogram[1:]), 500)

    def test_partial_vertex_alpha_masks_preserve_partial_coverage(self):
        image = _open_preview(_render_polygons([
            {"polygons": [_square(10)], "color": (255, 0, 0, 255)},
            {"polygons": [[(-8, -8), (8, -8), (0, 8)]], "vertex_alpha": [(128, 128, 128)], "mask": True, "color": None},
        ], max_size=128, transparent_background=True))
        self.assertIn(image.getpixel((image.width // 2, image.height // 2))[3], (127, 128))

    def test_all_upper_letter_resource_slots_are_resolved(self):
        cases = {
            1051503: ("Upper_Letters_7", 27),
            1051512: ("Upper_Letters_7", 36),
            1051516: ("Upper_Letters_7", 40),
        }
        for type_code, expected in cases.items():
            with self.subTest(type_code=type_code):
                self.assertEqual(expected, _resolve_full_type_resource(type_code))
                self.assertEqual(expected, editor_resolve_full_type_resource(type_code))

    def test_legacy_ellipse_dimensions_are_radii(self):
        points = _ellipse_points(10.0, -5.0, 40.0, 30.0, 0.0)

        self.assertAlmostEqual(80.0, _span(points, 0), places=6)
        self.assertAlmostEqual(60.0, _span(points, 1), places=6)

    def test_legacy_rectangle_dimensions_remain_full_extents(self):
        points = _rect_points(10.0, -5.0, 40.0, 20.0, 0.0)

        self.assertAlmostEqual(40.0, _span(points, 0), places=6)
        self.assertAlmostEqual(20.0, _span(points, 1), places=6)

    def test_typecode_json_keeps_the_separate_resource_renderer(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "typecode.json"
            source.write_text(
                json.dumps(
                    {
                        "shapes": [
                            {
                                "type": 1048678,
                                "type_word": 102,
                                "data": [0, 0, 1.0, 0.5, 0, 0, 0],
                                "color": [255, 255, 255, 255],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("json_preview_renderer._render_typecode_preview", return_value=b"typecode") as typecode:
                with patch("json_preview_renderer._render_primitive_preview", return_value=b"primitive") as primitive:
                    self.assertEqual(b"typecode", render_json_preview(source))

            typecode.assert_called_once()
            primitive.assert_not_called()

    def test_mask_flag_accepts_exported_and_legacy_spellings(self):
        self.assertTrue(_shape_mask_flag({"mask": True}, [0, 0, 1, 1, 0, 0, 0]))
        self.assertTrue(_shape_mask_flag({"is_mask": 1}, [0, 0, 1, 1, 0, 0, 0]))
        self.assertTrue(_shape_mask_flag({"isMask": 1}, [0, 0, 1, 1, 0, 0, 0]))
        self.assertTrue(_shape_mask_flag({}, [0, 0, 1, 1, 0, 0, 1]))
        self.assertFalse(_shape_mask_flag({"mask": False}, [0, 0, 1, 1, 0, 0, 1]))

    def test_masks_cut_lower_layers_but_not_later_layers(self):
        preview = _open_preview(
            _render_polygons(
                [
                    {"polygons": [_square(10)], "color": (255, 0, 0, 255)},
                    {"polygons": [_square(4)], "color": None, "mask": True},
                    {"polygons": [_square(1)], "color": (0, 80, 255, 255)},
                ],
                max_size=128,
                transparent_background=True,
            )
        )

        center_x = preview.width // 2
        center_y = preview.height // 2
        self.assertEqual((0, 80, 255, 255), preview.getpixel((center_x, center_y)))
        self.assertEqual(0, preview.getpixel((center_x + 8, center_y))[3])
        self.assertEqual((255, 0, 0, 255), preview.getpixel((center_x + 26, center_y)))

    def test_mask_reveals_checkerboard_instead_of_erasing_it(self):
        preview = _open_preview(
            _render_polygons(
                [
                    {"polygons": [_square(10)], "color": (255, 255, 255, 255)},
                    {"polygons": [_square(4)], "color": (255, 0, 255, 0), "mask": True},
                ],
                max_size=128,
                transparent_background=False,
            )
        )

        pixel = preview.getpixel((preview.width // 2, preview.height // 2))
        self.assertIn(pixel[:3], {(38, 38, 38), (58, 58, 58)})
        self.assertEqual(255, pixel[3])

    def test_mask_only_geometry_does_not_expand_artwork_bounds(self):
        base = [{"polygons": [_square(10)], "color": (255, 255, 255, 255)}]
        remote_mask = {"polygons": [[(900, 900), (1100, 900), (1100, 1100), (900, 1100)]], "color": None, "mask": True}

        without_mask = _open_preview(_render_polygons(base, max_size=128, transparent_background=True))
        with_mask = _open_preview(_render_polygons(base + [remote_mask], max_size=128, transparent_background=True))

        self.assertEqual(without_mask.size, with_mask.size)


if __name__ == "__main__":
    unittest.main()
