"""Preview resolution never changes source geometry or canonical picking bounds."""
import base64
import copy
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))

from kfps_livery_lab.model import (
    NativeVinylRenderer, SECTION_SIZE, WORLD_BOUNDS, ValidationError, validate_shapes,
)
from kfps_livery_lab.prepare import load_baseline


SIZES = {"fast": (1024, 512), "balanced": (2048, 1024), "sharp": (4096, 2048)}


def shape(**changes):
    return {"type": 0x100065, "data": [0, 0, 1, 1, 0, 0, 0],
            "color": [230, 40, 70, 255], "mask": False, **changes}


def png_image(result):
    return Image.open(io.BytesIO(base64.b64decode(result["png"].split(",", 1)[1])))


class PreviewQualityModelTests(unittest.TestCase):
    def setUp(self):
        self.renderer = NativeVinylRenderer.__new__(NativeVinylRenderer)
        self.render = Mock(side_effect=self.canvas)
        self.renderer.baseline = SimpleNamespace(render_typecode_layers_canvas=self.render)
        self.renderer._resource = Mock(return_value=("Primitives", 1))

    @staticmethod
    def canvas(shapes, *, width, height, world_bounds, strict_assets):
        image = Image.new("RGBA", (width, height))
        image.putpixel((width // 3, height // 3), tuple(shapes[0]["color"]))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def test_shapes_only_is_byte_compatible_with_explicit_balanced(self):
        payload = {"shapes": [shape()]}
        legacy = self.renderer(payload)
        self.assertEqual(legacy, self.renderer({**payload, "preview_quality": "balanced"}))
        self.assertEqual(set(legacy), {"png", "width", "height", "shapes", "bounds"})
        self.assertEqual((legacy["width"], legacy["height"]), SECTION_SIZE)
        self.assertEqual(self.render.call_count, 2)

    def test_exact_dimensions_direct_shapes_and_canonical_bounds(self):
        payload = {"shapes": [shape(data=[.125, -.875, -1.25, .75, 31, .3, 0])]}
        original = copy.deepcopy(payload)
        expected = self.renderer(payload)
        for quality, size in SIZES.items():
            with self.subTest(quality=quality):
                self.render.reset_mock()
                result = self.renderer({**payload, "preview_quality": quality})
                self.assertEqual((result["width"], result["height"]), size)
                self.assertEqual(result["bounds"], expected["bounds"])
                self.assertEqual(result["shapes"], expected["shapes"])
                with png_image(result) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, size)
                    self.assertEqual(image.getpixel((size[0] // 3, size[1] // 3)), (230, 40, 70, 255))
                calls = self.render.call_args_list
                self.assertEqual(len(calls), 1 if quality == "balanced" else 2)
                self.assertIn(SECTION_SIZE, [(c.kwargs["width"], c.kwargs["height"]) for c in calls])
                self.assertIn(size, [(c.kwargs["width"], c.kwargs["height"]) for c in calls])
                for call in calls:
                    self.assertEqual(call.args, (expected["shapes"],))
                    self.assertEqual(call.kwargs["world_bounds"], WORLD_BOUNDS)
                    self.assertIs(call.kwargs["strict_assets"], True)
        self.assertEqual(payload, original)

    def test_strict_enum_and_preview_envelope_fail_before_render(self):
        for quality in (None, True, 1, 1024, "", "FAST", "balanced ", "ultra", [], {}):
            with self.subTest(quality=quality), self.assertRaises(ValidationError):
                self.renderer({"shapes": [shape()], "preview_quality": quality})
        for payload in (None, [], {}, {"preview_quality": "fast"},
                        {"shapes": [shape()], "quality": "fast"},
                        {"shapes": [shape()], "preview_quality": "fast", "width": 1024}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                self.renderer(payload)
        self.render.assert_not_called()

    def test_non_preview_shape_validation_still_rejects_quality(self):
        with self.assertRaises(ValidationError):
            validate_shapes({"shapes": [shape()], "preview_quality": "fast"}, self.renderer._resource)

    def test_transparent_fallback_matches_each_resolution(self):
        self.render.side_effect = None
        self.render.return_value = None
        for quality, size in SIZES.items():
            result = self.renderer({"shapes": [shape(color=[0, 0, 0, 0])], "preview_quality": quality})
            self.assertIsNone(result["bounds"])
            with png_image(result) as image:
                self.assertEqual(image.size, size)
                self.assertIsNone(image.getchannel("A").getbbox())

    def test_rejects_wrong_sized_or_invalid_render_in_either_pass(self):
        for invalid_pass in (SECTION_SIZE, SIZES["fast"]):
            for malformed in (True, False):
                def render(shapes, **kwargs):
                    if (kwargs["width"], kwargs["height"]) == invalid_pass:
                        if malformed:
                            return b"not a png"
                        kwargs.update(width=1, height=1)
                    return self.canvas(shapes, **kwargs)
                self.render.side_effect = render
                with self.subTest(size=invalid_pass, malformed=malformed), self.assertRaises(ValidationError):
                    self.renderer({"shapes": [shape()], "preview_quality": "fast"})


@unittest.skipUnless(os.environ.get("KFPS_LAB_TEST_BASELINE"), "Explicit KFPS baseline not selected")
class PreviewQualityNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_baseline(Path(os.environ["KFPS_LAB_TEST_BASELINE"]))
        cls.renderer = NativeVinylRenderer()

    def test_dense_synthetic_fixtures_at_all_qualities(self):
        for count in (300, 3000):
            shapes = [shape(data=[-900 + (i % 100) * 18, -400 + (i // 100) * 26,
                                  .02, .02, i % 90, 0, 0]) for i in range(count)]
            self.assertEqual(len(shapes), count)
            original = copy.deepcopy(shapes)
            canonical = self.renderer({"shapes": shapes})
            for quality, size in SIZES.items():
                with self.subTest(shapes=count, quality=quality):
                    result = self.renderer({"shapes": shapes, "preview_quality": quality})
                    self.assertEqual(result["shapes"], canonical["shapes"])
                    self.assertEqual(result["bounds"], canonical["bounds"])
                    with png_image(result) as image:
                        self.assertEqual(image.size, size)
                        self.assertIsNotNone(image.getchannel("A").getbbox())
                        expected = self.renderer.baseline.render_typecode_layers_canvas(
                            canonical["shapes"], width=size[0], height=size[1],
                            world_bounds=WORLD_BOUNDS, strict_assets=True)
                        with Image.open(io.BytesIO(expected)) as reference:
                            self.assertEqual(image.tobytes(), reference.tobytes())
                    if quality == "balanced":
                        self.assertEqual(result["png"], canonical["png"])
            self.assertEqual(shapes, original)

    def test_real_native_pixels_bounds_masks_and_clipping(self):
        cases = (
            [shape()],
            [shape(data=[.125, -.875, -1.25, .75, 31, .3, 0])],
            [shape(), shape(data=[0, 0, .5, .5, 0, 0, 1], mask=True)],
            [shape(data=[1020, -510, .5, 1, 32, .3, 0])],
            [shape(data=[.125, .375, .0031, .0023, 13, 0, 0])],
            [shape(data=[4000, 4000, 1, 1, 0, 0, 0])],
            [shape(color=[0, 0, 0, 0])],
            [shape(), shape(data=[0, 0, 2, 2, 0, 0, 1], mask=True)],
        )
        for index, shapes in enumerate(cases):
            original = copy.deepcopy(shapes)
            canonical = self.renderer({"shapes": shapes})
            for quality, size in SIZES.items():
                with self.subTest(case=index, quality=quality):
                    result = self.renderer({"shapes": shapes, "preview_quality": quality})
                    expected = self.renderer.baseline.render_typecode_layers_canvas(
                        canonical["shapes"], width=size[0], height=size[1],
                        world_bounds=WORLD_BOUNDS, strict_assets=True)
                    self.assertEqual(result["bounds"], canonical["bounds"])
                    self.assertEqual(result["shapes"], canonical["shapes"])
                    self.assertEqual((result["width"], result["height"]), size)
                    with png_image(result) as image:
                        self.assertEqual(image.size, size)
                        if expected:
                            with Image.open(io.BytesIO(expected)) as baseline:
                                self.assertEqual(image.tobytes(), baseline.tobytes())
                        else:
                            self.assertIsNone(image.getchannel("A").getbbox())
                        if quality == "balanced":
                            bounds = image.getchannel("A").getbbox()
                            self.assertEqual(result["bounds"], list(bounds) if bounds else None)
            self.assertEqual(shapes, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
