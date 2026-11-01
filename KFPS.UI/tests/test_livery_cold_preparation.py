"""Synthetic cold-preparation contracts; no private fixtures or installed game."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools/livery-studio/src")]

from tools.livery import portable_mesh_converter as mesh
from tools.livery import render_contract as native
from kfps_livery_lab import prepare, render_adapter
from PIL import Image


def reference_warp(artwork, slot, projection):
    """Previous always-transform behavior, independent of the new shortcut."""
    if artwork.size != native.ATLAS_SIZE:
        raise native.LiveryRenderContractError(
            f"{slot} artwork must be {native.ATLAS_SIZE[0]} x {native.ATLAS_SIZE[1]} pixels.")
    affine = native._atlas_to_local_affine(slot, artwork.width, artwork.height,
                                          float(projection.get("xorigin", 0.0)),
                                          float(projection.get("yorigin", 0.0)))
    return artwork.convert("RGBA").transform(native.ATLAS_SIZE, Image.Transform.AFFINE, affine,
                                             resample=Image.Resampling.BILINEAR, fillcolor=(0, 0, 0, 0))


def index_fixture(values, component=5125, *, stride=None, view_offset=5, offset=3):
    width = 2 if component == 5123 else 4
    stride = width if stride is None else stride
    length = offset + (len(values) - 1) * stride + width if values else offset
    binary = bytearray(b"\xff" * (view_offset + length))
    for i, value in enumerate(values):
        struct.pack_into("<H" if width == 2 else "<I", binary, view_offset + offset + i * stride, value)
    document = {
        "accessors": [{"bufferView": 0, "componentType": component, "type": "SCALAR",
                       "count": len(values), "byteOffset": offset, "max": [max(values, default=0)]}],
        "bufferViews": [{"buffer": 0, "byteOffset": view_offset, "byteLength": length, "byteStride": stride}],
    }
    return document, bytes(binary)


def write_glb(path, index_document, index_bytes):
    document = copy.deepcopy(index_document)
    geometry = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    geometry += struct.pack("<9f", 0, 0, 1, 0, 0, 1, 0, 0, 1)
    geometry += struct.pack("<6f", 0, 0, 1, 0, 0, 1)
    document["bufferViews"][0]["byteOffset"] += len(geometry)
    document["bufferViews"][:0] = [
        {"buffer": 0, "byteOffset": 0, "byteLength": 36},
        {"buffer": 0, "byteOffset": 36, "byteLength": 36},
        {"buffer": 0, "byteOffset": 72, "byteLength": 24},
    ]
    document["accessors"][0]["bufferView"] = 3
    document["accessors"][:0] = [
        {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 3},
        {"bufferView": 1, "componentType": 5126, "type": "VEC3", "count": 3},
        {"bufferView": 2, "componentType": 5126, "type": "VEC2", "count": 3},
    ]
    binary = geometry + index_bytes
    document.update({"asset": {"version": "2.0"}, "scene": 0,
                     "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
                     "buffers": [{"byteLength": len(binary)}],
                     "meshes": [{"extras": {"kfps_role": "paint"}, "primitives": [{
                         "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_3": 2},
                         "indices": 3, "mode": 4}]}]})
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
                     + struct.pack("<I4s", len(encoded), b"JSON") + encoded
                     + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


class IndexReductionTests(unittest.TestCase):
    def test_contiguous_strided_offsets_endian_and_uint_extremes(self):
        for component, width, maximum in ((5123, 2, 65535), (5125, 4, 4294967295)):
            for stride in (width, width + 1, width * 3):
                with self.subTest(component=component, stride=stride):
                    document, binary = index_fixture([0, 0x0102, maximum, 3], component, stride=stride)
                    self.assertEqual(maximum, mesh._actual_index_max(document, binary, 0))
                    self.assertIs(int, type(mesh._actual_index_max(document, binary, 0)))
                    self.assertEqual(binary, bytes(binary))

    def test_little_endian_bytes_are_not_host_native_or_big_endian(self):
        for component, width in ((5123, 2), (5125, 4)):
            document, binary = index_fixture([1, 0x0102, 3], component)
            self.assertEqual(0x0102, mesh._actual_index_max(document, binary, 0))
            start = 8
            self.assertEqual(b"\x02\x01" + b"\0" * (width - 2), binary[start + width:start + 2 * width])

    def test_matches_struct_reference_across_deterministic_buffers(self):
        rng = random.Random(931)
        for component, width in ((5123, 2), (5125, 4)):
            for count in (1, 3, 257):
                for stride in (width, width + 3, 32):
                    values = [rng.randrange(1 << (width * 8)) for _ in range(count)]
                    document, binary = index_fixture(values, component, stride=stride)
                    expected = max(struct.unpack_from("<H" if width == 2 else "<I", binary, 8 + i * stride)[0]
                                   for i in range(count))
                    self.assertEqual(expected, mesh._actual_index_max(document, binary, 0))

    def test_empty_and_truncated_helper_inputs_still_fail(self):
        document, binary = index_fixture([])
        with self.assertRaises(ValueError):
            mesh._actual_index_max(document, binary, 0)
        for width, component in ((2, 5123), (4, 5125)):
            for stride in (width, width + 1):
                document, binary = index_fixture([0, 1, 2], component, stride=stride)
                with self.subTest(component=component, stride=stride), self.assertRaises(ValueError):
                    mesh._actual_index_max(document, binary[:-1], 0)

    def validate(self, document, binary):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.glb"
            write_glb(path, document, binary)
            return mesh.validate_local_chassis_glb(path)

    def test_full_validator_keeps_exact_report_for_interleaved_indices(self):
        for component, width in ((5123, 2), (5125, 4)):
            for stride in (width, width + 1, 32):
                document, binary = index_fixture([0, 1, 2], component, stride=stride)
                self.assertEqual({"mesh_count": 1, "paint_meshes": 1, "glass_meshes": 0,
                                  "triangle_count": 1, "direct_uv3_meshes": 1,
                                  "projected_livery_meshes": 0, "part_option_count": 0},
                                 self.validate(document, binary))

    def test_full_validator_rejects_out_of_range_and_false_declared_max(self):
        for component in (5123, 5125):
            for indices, declared in (([0, 1, 3], 3), ([0, 1, 65535], 65535), ([0, 1, 2], 1)):
                document, binary = index_fixture(indices, component)
                document["accessors"][0]["max"] = [declared]
                with self.subTest(component=component, indices=indices), self.assertRaisesRegex(
                        mesh.PortableMeshConverterError, "out-of-range"):
                    self.validate(document, binary)

    def test_full_validator_rejects_invalid_views_counts_and_strides(self):
        changes = [("accessors", "count", 0), ("accessors", "count", -1),
                   ("accessors", "count", 4), ("accessors", "byteOffset", -1),
                   ("bufferViews", "byteLength", 8), ("bufferViews", "byteStride", 2),
                   ("bufferViews", "byteOffset", -1), ("bufferViews", "byteOffset", 1000)]
        for group, key, value in changes:
            document, binary = index_fixture([0, 1, 2])
            document[group][0][key] = value
            with self.subTest(group=group, key=key, value=value), self.assertRaises(mesh.PortableMeshConverterError):
                self.validate(document, binary)

    def test_full_validator_rejects_truncated_binary_even_when_index_max_is_small(self):
        document, binary = index_fixture([0, 1, 2])
        with self.assertRaises(mesh.PortableMeshConverterError):
            self.validate(document, binary[:-5])


class BlankAtlasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / "blank.zip"
        prepare.blank_sections(self.package, native.SECTION_TO_SLOT)
        self.mesh = self.root / "mesh.glb"
        self.mesh.write_bytes(b"synthetic; direct-UV path uses supplied validation")
        self.asset = SimpleNamespace(model_code="SYNTHETIC", archive_size=123, archive_mtime_ns=456)
        self.validation = {"projected_livery_meshes": 0}
        self.masks = {}
        for index, slot in enumerate(native.SECTION_TO_SLOT.values()):
            image = Image.new("L", native.ATLAS_SIZE)
            if slot != "glass_top":
                image.paste(12 + index * 17, (100 + index, 50, 1300 + index, 800))
            projection = {"left": "-256.25", "right": "128.75", "top": "192.5", "bottom": "-128.5",
                          "xAxis": "-X", "yAxis": "Z", "xScale": "1.5", "yScale": "0.75",
                          "xorigin": str(index - 4.25), "yorigin": str(index + 2.5)}
            self.masks[slot] = image, projection, f"{index:064x}"
        self.mask_read = self.enterContext(patch.object(native, "_archive_masks", return_value=self.masks))
        self.enterContext(patch.object(native, "read_vehicle_assembly_metadata", return_value={"checked": "assembly"}))

    def candidate(self, name="candidate", validation=None):
        return render_adapter.build_authoring_atlases(
            self.package, self.asset, self.root / name, mesh_path=self.mesh,
            mesh_validation=self.validation if validation is None else validation)

    def baseline(self, name="baseline"):
        with patch.object(native, "_warped_uv_layer", side_effect=reference_warp):
            return native.build_local_livery_atlases(self.package, self.asset, self.root / name,
                                                    mesh_path=self.mesh, mesh_validation=self.validation)

    def edit_package(self, transform):
        with zipfile.ZipFile(self.package) as source:
            members = {name: source.read(name) for name in source.namelist()}
        transform(members)
        with zipfile.ZipFile(self.package, "w", compression=zipfile.ZIP_DEFLATED) as destination:
            for name, body in members.items():
                destination.writestr(name, body)

    def png(self, color, size=None):
        output = io.BytesIO()
        Image.new("RGBA", size or native.ATLAS_SIZE, color).save(output, format="PNG")
        return output.getvalue()

    def assert_equivalent(self, first, second):
        self.assertEqual({k: v for k, v in first.items() if k != "root"},
                         {k: v for k, v in second.items() if k != "root"})
        for name in [first["files"]["paint"], *first["files"]["masks"]]:
            left, right = Path(first["root"]) / name, Path(second["root"]) / name
            self.assertEqual(left.read_bytes(), right.read_bytes(), name)
            with Image.open(left) as a, Image.open(right) as b:
                self.assertEqual((a.mode, a.size, a.tobytes()), (b.mode, b.size, b.tobytes()), name)

    def test_exact_metadata_png_bytes_pixels_one_mask_decode_and_no_warps(self):
        expected = self.baseline()
        self.mask_read.reset_mock()
        with patch.object(Image.Image, "transform", side_effect=AssertionError("blank transform")), \
                patch.object(native, "build_local_livery_atlases", wraps=native.build_local_livery_atlases) as builder:
            actual = self.candidate()
        self.mask_read.assert_called_once_with(self.asset)
        builder.assert_called_once()
        self.assertIs(self.masks, builder.call_args.kwargs["_predecoded_masks"])
        self.assert_equivalent(expected, actual)
        self.assertEqual(json.loads((Path(actual["root"]) / "index.json").read_text()),
                         {k: v for k, v in actual.items() if k not in ("root", "cache_hit")})

    def test_nonblank_or_invisible_rgb_artwork_preserves_native_path(self):
        for index, color in enumerate(((200, 10, 30, 255), (200, 10, 30, 0))):
            self.edit_package(lambda rows: rows.update({"projection/rendered/Top.png": self.png(color)}))
            expected = self.baseline(f"baseline-{index}")
            calls = []
            original_transform = Image.Image.transform

            def transform(image, *args, **kwargs):
                calls.append(image.mode)
                return original_transform(image, *args, **kwargs)

            with patch.object(Image.Image, "transform", transform):
                actual = self.candidate(f"candidate-{index}")
            self.assertTrue(calls, "Nonzero RGB or alpha must not bypass the native warp")
            self.assert_equivalent(expected, actual)

    def test_missing_section_and_empty_mask_preserve_exact_native_inventory(self):
        self.edit_package(lambda rows: rows.pop("projection/rendered/Left.png"))
        self.assert_equivalent(self.baseline(), self.candidate())

    def test_corrupt_unused_empty_mask_artwork_is_ignored_as_before(self):
        self.edit_package(lambda rows: rows.update({"projection/rendered/TopWindow.png": b"not an image"}))
        self.assert_equivalent(self.baseline(), self.candidate())

    def test_incorrect_size_or_corrupt_used_artwork_still_fails(self):
        for index, body in enumerate((self.png((0, 0, 0, 0), (8, 8)), b"not an image")):
            self.edit_package(lambda rows: rows.update({"projection/rendered/Top.png": body}))
            with self.assertRaises(Exception) as expected:
                self.baseline(f"baseline-{index}")
            with self.assertRaises(type(expected.exception)) as actual:
                self.candidate(f"candidate-{index}")
            self.assertEqual(str(expected.exception).split("<")[0],
                             str(actual.exception).split("<")[0])
            self.assertFalse((self.root / f"candidate-{index}/index.json").exists())

    def test_bad_projection_bounds_axes_scales_and_origins_still_fail(self):
        projection = self.masks["top"][1]
        original = dict(projection)
        for index, (key, value) in enumerate((("left", "-5000"), ("xAxis", "invalid"),
                                               ("yScale", "0"), ("xScale", "nan"),
                                               ("xorigin", "invalid"))):
            projection.clear()
            projection.update({**original, key: value})
            with self.subTest(key=key), self.assertRaises(Exception) as expected:
                self.baseline(f"baseline-{index}")
            with self.assertRaises(type(expected.exception)):
                self.candidate(f"candidate-{index}")
            self.assertFalse((self.root / f"candidate-{index}/index.json").exists())

    def test_missing_or_projected_validation_keeps_existing_native_path(self):
        for validation in ({}, {"projected_livery_meshes": 1}):
            with patch.object(native, "build_local_livery_atlases", return_value={"fallback": True}) as fallback:
                self.assertEqual({"fallback": True}, self.candidate(validation=validation))
            fallback.assert_called_once()

    def test_existing_index_keeps_verified_native_cache_path(self):
        first = self.candidate()
        with patch.object(native, "_warped_uv_layer", side_effect=AssertionError("verified cache must not warp")):
            second = self.candidate()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["file_sha256"], second["file_sha256"])

    def test_corrupt_cached_png_rebuilds_through_native_checks(self):
        first = self.candidate()
        (self.root / "candidate" / first["files"]["paint"]).write_bytes(b"corrupt")
        with patch.object(native, "build_local_livery_atlases", wraps=native.build_local_livery_atlases) as fallback:
            rebuilt = self.candidate()
        fallback.assert_called_once()
        self.assertFalse(rebuilt["cache_hit"])
        self.assertEqual(first["file_sha256"], rebuilt["file_sha256"])

    def test_no_shared_sections_still_rejected(self):
        self.edit_package(lambda rows: rows.clear())
        with self.assertRaisesRegex(native.LiveryRenderContractError, "no shared"):
            self.candidate()

    def test_mixed_or_unsupported_masks_keep_existing_rejection(self):
        for size in ((1024, 1024), (64, 64)):
            original = self.masks["top"]
            self.masks["top"] = (Image.new("L", size), *original[1:])
            with self.assertRaisesRegex(ValueError, "unsupported or mixed"):
                self.candidate()
            self.masks["top"] = original


    def test_native_predecoded_mask_dimensions_are_still_validated(self):
        for size in ((1024, 1024), (64, 64)):
            invalid = {**self.masks, "front": (Image.new("L", size), *self.masks["front"][1:])}
            with patch.object(native, "_archive_masks", side_effect=AssertionError("must use supplied masks")), \
                    self.assertRaisesRegex(native.LiveryRenderContractError, "mask is"):
                native.build_local_livery_atlases(self.package, self.asset, self.root / "wrong-masks",
                                                 mesh_path=self.mesh, mesh_validation=self.validation,
                                                 _predecoded_masks=invalid)

    def test_empty_predecoded_masks_are_not_silently_redecoded(self):
        with patch.object(native, "_archive_masks", side_effect=AssertionError("must use supplied masks")), \
                self.assertRaisesRegex(native.LiveryRenderContractError, "no shared"):
            native.build_local_livery_atlases(self.package, self.asset, self.root / "empty-masks",
                                             mesh_path=self.mesh, mesh_validation=self.validation,
                                             _predecoded_masks={})


class BlankWarpTests(unittest.TestCase):
    def test_zero_rgba_matches_original_across_projection_orientations(self):
        artwork = Image.new("RGBA", native.ATLAS_SIZE)
        projection = {"xorigin": "12.25", "yorigin": "-19.5"}
        for slot in native.SECTION_TO_SLOT.values():
            expected = reference_warp(artwork, slot, projection)
            with patch.object(Image.Image, "transform", side_effect=AssertionError("zero transform")):
                actual = native._warped_uv_layer(artwork, slot, projection)
            self.assertEqual((expected.mode, expected.size, expected.tobytes()),
                             (actual.mode, actual.size, actual.tobytes()))

    def test_black_rgb_is_opaque_and_still_transformed(self):
        artwork = Image.new("RGB", native.ATLAS_SIZE)
        expected = reference_warp(artwork, "front", {"xorigin": 40})
        with patch.object(Image.Image, "transform", autospec=True, return_value=expected) as transform:
            self.assertIs(expected, native._warped_uv_layer(artwork, "front", {"xorigin": 40}))
        transform.assert_called_once()

    def test_nonfinite_affine_does_not_bypass_existing_transform(self):
        artwork = Image.new("RGBA", native.ATLAS_SIZE)
        sentinel = Image.new("RGBA", (1, 1))
        for origin in ("nan", "inf", "-inf"):
            with patch.object(Image.Image, "transform", autospec=True, return_value=sentinel) as transform:
                self.assertIs(sentinel, native._warped_uv_layer(artwork, "front", {"xorigin": origin}))
            transform.assert_called_once()

    def test_wrong_dimensions_and_malformed_origin_reject_before_shortcut(self):
        with self.assertRaises(native.LiveryRenderContractError):
            native._warped_uv_layer(Image.new("RGBA", (8, 8)), "front", {})
        with self.assertRaises(ValueError):
            native._warped_uv_layer(Image.new("RGBA", native.ATLAS_SIZE), "front", {"xorigin": "invalid"})


if __name__ == "__main__":
    unittest.main()
