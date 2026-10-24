"""Generated imports use native geometry without weakening saved-project checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab.model import NativeVinylRenderer, ValidationError, validate_shapes
from kfps_livery_lab.vinyl_import import import_shapes
import test_studio_preview_quality_routes as routes
from test_studio_offline_save_codec import project, NAMES
from kfps_livery_lab.save_codec import compile_section_vinyl


def generated(kind=16, **changes):
    return {"type": kind, "data": [300, 200, 126, 63, 30, .2],
            "color": [120, 40, 200, 220], **changes}


class GeneratedImportTests(unittest.TestCase):
    def test_known_primitives_use_existing_codec_units_and_editor_centering(self):
        for kind, word, divisor in ((1, 101, 127), (2, 101, 127), (8, 102, 63), (16, 102, 63)):
            with self.subTest(kind=kind):
                source = {"shapes": [generated(kind)]}
                before = copy.deepcopy(source)
                result = import_shapes(source, lambda _: True)["shapes"][0]
                self.assertEqual(result["type"], 0x100000 + word)
                self.assertEqual(result["data"], [0, 0, 126 / divisor, 63 / divisor,
                                                  330 if kind in (2, 16) else 0, .2])
                self.assertEqual(result["color"], source["shapes"][0]["color"])
                self.assertEqual(source, before)

    def test_native_groups_masks_and_metadata_remain_unchanged(self):
        native = {"type": 0x100065, "type_word": 101, "data": [43, -17, -1, .3, 28, .4, 1],
                  "mask": True, "color": [40, 80, 120, 0],
                  "editor_group_path": [{"id": "parent", "name": "Parent"}, {"id": "child", "name": "Child"}]}
        value = {"shapes": [native]}
        result = import_shapes(value, lambda _: True)
        self.assertEqual(result, value)
        self.assertIsNot(result["shapes"][0], native)
        self.assertEqual(import_shapes(result, lambda _: True), result)

    def test_relative_positions_rotation_mirroring_transparency_and_groups(self):
        value = {"shapes": [generated(2, data=[10, 20, -127, 127, 45],
                                      editor_group_id="g", editor_group_path=[{"id":"g", "name":"Group"}]),
                            generated(16, data=[10, 40, 63, -63, -10, .3, 1], mask=True),
                            generated(16, color=[255, 255, 255, 0])]}
        result = import_shapes(value, lambda _: True)["shapes"]
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[1]["data"][1] - result[0]["data"][1], -20)
        self.assertEqual(result[0]["data"][2], -1)
        self.assertEqual(result[1]["data"][3], -1)
        self.assertEqual(result[1]["data"][4], 10)
        self.assertTrue(result[1]["mask"])
        self.assertEqual(result[2]["color"][3], 0)
        self.assertEqual(result[0]["editor_group_path"], value["shapes"][0]["editor_group_path"])

    def test_leading_transparent_spacer_and_3000_shape_limit(self):
        spacer = generated(1, data=[300, 200, 600, 400], color=[0, 0, 0, 0])
        value = {"shapes": [spacer] + [generated()] * 3000}
        result = import_shapes(value, lambda _: True)
        self.assertEqual(len(result["shapes"]), 3000)
        self.assertEqual(result["shapes"][0]["data"][:2], [0, 0])
        for shapes in ([], [spacer], [generated()] * 3001, [spacer] + [generated()] * 3001):
            with self.assertRaises(ValidationError): import_shapes({"shapes": shapes}, lambda _: True)
        spacer["mask"] = True
        self.assertEqual(len(import_shapes({"shapes": [spacer, generated()]}, lambda _: True)["shapes"]), 2)

    def test_invalid_inputs_never_become_partial_vinyls(self):
        invalid = [None, {}, generated(4), generated(type=True), generated(data=[0, 1]),
                   generated(data=[0, 0, 0, 63]), generated(data=[0, 0, float("nan"), 63]),
                   generated(data=[0, 0, 63, 63, float("inf")]), generated(data=[0, 0, 63, 63, 20000]),
                   generated(color=[256, 0, 0, 255]), generated(color=[True, 0, 0, 255]),
                   generated(type_word=102), generated(resource_family="Primitives"),
                   generated(is_raster_logo=True), generated(mask="yes"),
                   generated(data=[0, 0, 63, 63, 0, 0, 1], mask=False)]
        for bad in invalid:
            with self.subTest(shape=bad), self.assertRaises(ValidationError):
                import_shapes({"shapes": [generated(), bad]}, lambda _: True)
        with self.assertRaises(ValidationError): import_shapes({"shapes": [generated()]}, lambda _: None)
        with self.assertRaises(ValidationError): import_shapes({"shapes": [generated()], "extra": True}, lambda _: True)

    def test_native_render_validator_stays_strict(self):
        with self.assertRaises(ValidationError): validate_shapes({"shapes": [generated()]}, lambda _: True)


class GeneratedImportRoutes(unittest.TestCase):
    setUp = routes.PreviewQualityRouteTests.setUp
    start = routes.PreviewQualityRouteTests.start
    request = routes.PreviewQualityRouteTests.request
    post = routes.PreviewQualityRouteTests.post

    def test_import_then_render_reopen_and_section_export(self):
        self.server.renderer = NativeVinylRenderer()
        source = {"shapes": [generated(2, editor_group_id="nested"), generated(16)]}
        status, _, body = self.post(source, "api/import-vinyl")
        self.assertEqual(status, 200, body)
        normalized = json.loads(body)
        for quality, size in (("fast", (1024, 512)), ("balanced", (2048, 1024)), ("sharp", (4096, 2048))):
            status, _, image_body = self.post({**normalized, "preview_quality": quality}, "api/render-vinyl")
            self.assertEqual(status, 200, image_body[:200])
            image = json.loads(image_body)
            self.assertEqual((image["width"], image["height"]), size)
            self.assertIsNotNone(image["bounds"])
        saved = json.loads(json.dumps(project(normalized["shapes"])))
        output = compile_section_vinyl(saved, 4267, NAMES, "Left")
        self.assertEqual(len(output["shapes"]), 2)
        self.assertTrue(all(s["type"] >= 0x100000 for s in output["shapes"]))
        self.assertEqual(self.post(output, "api/render-vinyl")[0], 200)

    def test_native_passthrough_and_errors_use_existing_http_boundaries(self):
        shape = routes.shape(editor_group_id="unchanged")
        source = {"shapes": [shape]}
        self.assertEqual(json.loads(self.post(source, "api/import-vinyl")[2]), source)
        self.assertEqual(self.post({"shapes": [generated()]}, "api/render-vinyl")[0], 422)
        self.assertEqual(self.post({"shapes": [generated(4)]}, "api/import-vinyl")[0], 422)
        self.assertEqual(self.request("POST", "api/import-vinyl", b'{"shapes":[],"shapes":[]}',
                                     {"Content-Type": "application/json"})[0], 422)
        self.assertEqual(self.post(source, "api/import-vinyl", Origin="https://example.invalid")[0], 403)
        self.assertEqual(self.request("GET", "api/import-vinyl")[0], 404)
        self.assertFalse(self.settings.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
