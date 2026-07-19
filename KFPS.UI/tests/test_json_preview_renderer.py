import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from json_preview_renderer import _ellipse_points, _rect_points, render_json_preview


def _span(points, axis):
    values = [point[axis] for point in points]
    return max(values) - min(values)


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


if __name__ == "__main__":
    unittest.main()
