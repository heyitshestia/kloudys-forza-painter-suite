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

from json_preview_renderer import _ellipse_points, _rect_points, _render_polygons, _shape_mask_flag, render_json_preview


def _span(points, axis):
    values = [point[axis] for point in points]
    return max(values) - min(values)


def _square(radius):
    return [(-radius, -radius), (radius, -radius), (radius, radius), (-radius, radius)]


def _open_preview(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA")


class JsonPreviewRendererTests(unittest.TestCase):
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
