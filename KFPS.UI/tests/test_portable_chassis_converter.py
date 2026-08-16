from __future__ import annotations

import json
import struct
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from tools.livery.portable_mesh_converter import (
    ChassisConversionCancelled,
    PortableMeshConverterError,
    convert_vehicle_model_to_glb,
    validate_local_chassis_glb,
)
from tools.livery.vehicle_assets import VehicleAsset, load_or_build_vehicle_asset_index


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((-len(data)) % 4)


def _write_minimal_chassis(
    path: Path,
    *,
    role: str = "paint",
    index_max: int = 2,
    short_view: bool = False,
    position_accessor: int = 0,
    node_mesh: int = 0,
    allowed_sides: int | float | None = None,
    include_uv3: bool = True,
) -> None:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    normals = struct.pack("<9f", 0, 0, 1, 0, 0, 1, 0, 0, 1)
    uv3 = struct.pack("<6f", 0, 0, 1, 0, 0, 1)
    indices = struct.pack("<3I", 0, 1, 2)
    binary = positions + normals + uv3 + indices
    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
        {"buffer": 0, "byteOffset": len(positions), "byteLength": len(normals)},
        {"buffer": 0, "byteOffset": len(positions) + len(normals), "byteLength": len(uv3)},
        {
            "buffer": 0,
            "byteOffset": len(positions) + len(normals) + len(uv3),
            "byteLength": 4 if short_view else len(indices),
        },
    ]
    accessors = [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": 3,
            "type": "VEC3",
            "min": [0, 0, 0],
            "max": [1, 1, 0],
        },
        {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
        {
            "bufferView": 3,
            "componentType": 5125,
            "count": 3,
            "type": "SCALAR",
            "min": [0],
            "max": [index_max],
        },
    ]
    extras = {"kfps_role": role}
    if allowed_sides is not None:
        extras["kfps_allowed_sides"] = allowed_sides
    attributes = {"POSITION": position_accessor, "NORMAL": 1}
    if include_uv3:
        attributes["TEXCOORD_3"] = 2
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": node_mesh, "extras": extras}],
        "meshes": [{
            "primitives": [{
                "attributes": attributes,
                "indices": 3,
                "mode": 4,
            }],
            "extras": extras,
        }],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    encoded_json = _pad(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    encoded_binary = _pad(binary, b"\0")
    total = 12 + 8 + len(encoded_json) + 8 + len(encoded_binary)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(encoded_json), 0x4E4F534A)
        + encoded_json
        + struct.pack("<II", len(encoded_binary), 0x004E4942)
        + encoded_binary
    )


class PortableChassisConverterTests(unittest.TestCase):
    def test_validator_accepts_complete_indexed_livery_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.glb"
            _write_minimal_chassis(path)
            self.assertEqual(
                {
                    "mesh_count": 1,
                    "paint_meshes": 1,
                    "glass_meshes": 0,
                    "triangle_count": 1,
                    "direct_uv3_meshes": 1,
                    "projected_livery_meshes": 0,
                    "part_option_count": 0,
                },
                validate_local_chassis_glb(path),
            )

    def test_validator_rejects_out_of_range_indices_and_short_binary_views(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out_of_range = root / "out-of-range.glb"
            _write_minimal_chassis(out_of_range, index_max=3)
            with self.assertRaisesRegex(PortableMeshConverterError, "out-of-range"):
                validate_local_chassis_glb(out_of_range)

            short = root / "short.glb"
            _write_minimal_chassis(short, short_view=True)
            with self.assertRaisesRegex(PortableMeshConverterError, "outside"):
                validate_local_chassis_glb(short)

    def test_validator_rejects_false_index_metadata_and_negative_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            false_metadata = root / "false-index-metadata.glb"
            _write_minimal_chassis(false_metadata, index_max=1)
            with self.assertRaisesRegex(PortableMeshConverterError, "out-of-range"):
                validate_local_chassis_glb(false_metadata)

            negative_accessor = root / "negative-accessor.glb"
            _write_minimal_chassis(negative_accessor, position_accessor=-1)
            with self.assertRaisesRegex(PortableMeshConverterError, "accessor index"):
                validate_local_chassis_glb(negative_accessor)

            negative_mesh = root / "negative-mesh.glb"
            _write_minimal_chassis(negative_mesh, node_mesh=-1)
            with self.assertRaisesRegex(PortableMeshConverterError, "mesh index"):
                validate_local_chassis_glb(negative_mesh)

    def test_validator_rejects_unknown_material_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unknown-role.glb"
            _write_minimal_chassis(path, role="external")
            with self.assertRaisesRegex(PortableMeshConverterError, "material role"):
                validate_local_chassis_glb(path)

    def test_validator_rejects_livery_geometry_without_exact_uv3_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "projected-paint.glb"
            _write_minimal_chassis(path, include_uv3=False)
            with self.assertRaisesRegex(PortableMeshConverterError, "exact FH6 livery coordinates"):
                validate_local_chassis_glb(path)

    def test_validator_accepts_role_appropriate_livery_sides_and_rejects_invalid_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paint = root / "paint.glb"
            _write_minimal_chassis(paint, allowed_sides=0x1F)
            self.assertEqual(1, validate_local_chassis_glb(paint)["paint_meshes"])

            wrong_kind = root / "wrong-kind.glb"
            _write_minimal_chassis(wrong_kind, allowed_sides=0x400)
            with self.assertRaisesRegex(PortableMeshConverterError, "livery-side"):
                validate_local_chassis_glb(wrong_kind)

            fractional = root / "fractional.glb"
            _write_minimal_chassis(fractional, allowed_sides=1.5)
            with self.assertRaisesRegex(PortableMeshConverterError, "livery-side"):
                validate_local_chassis_glb(fractional)

    def test_pre_cancelled_conversion_never_reads_the_game_archive(self):
        asset = VehicleAsset(
            car_id=1,
            model_code="TEST",
            archive_path=str(Path("missing-car.zip").resolve()),
            archive_name="missing-car.zip",
            archive_size=0,
            archive_mtime_ns=0,
            clip_entry="",
        )
        cancelled = threading.Event()
        cancelled.set()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ChassisConversionCancelled):
                convert_vehicle_model_to_glb(
                    asset,
                    Path(temp) / "unused.glb",
                    converter_path=(
                        ROOT
                        / "tools"
                        / "livery"
                        / "chassis-converter"
                        / "bin"
                        / "win-x64"
                        / "Kfps.ChassisConverter.exe"
                    ),
                    cancel_event=cancelled,
                )

    @unittest.skipUnless(sys.platform == "win32", "Windows process-tree memory guard")
    def test_converter_memory_guard_stops_a_runaway_child_and_removes_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "TEST.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "Manifest.xml",
                    '<Car><NonUpgradeablePart><Model path="game:/media/cars/TEST/Scene/Exterior/body.modelbin"/></NonUpgradeablePart></Car>',
                )
                bundle.writestr("Scene/Exterior/body.modelbin", b"unused")
                bundle.writestr("TEST.carbin", b"unused")
            asset = VehicleAsset(
                car_id=1,
                model_code="TEST",
                archive_path=str(archive),
                archive_name=archive.name,
                archive_size=archive.stat().st_size,
                archive_mtime_ns=archive.stat().st_mtime_ns,
                clip_entry="",
            )
            child = root / "runaway.py"
            child.write_text(
                "import time\npayload = bytearray(96 * 1024 * 1024)\ntime.sleep(30)\n",
                encoding="utf-8",
            )
            launcher = root / "runaway.cmd"
            launcher.write_text(f'@"{sys.executable}" "{child}" %*\n', encoding="utf-8")
            output = root / "guarded.glb"
            diagnostics: dict[str, int] = {}
            with self.assertRaisesRegex(PortableMeshConverterError, "safe conversion memory limit"):
                convert_vehicle_model_to_glb(
                    asset,
                    output,
                    converter_path=launcher,
                    timeout_seconds=10,
                    max_process_bytes=64 * 1024 * 1024,
                    diagnostics=diagnostics,
                )
            self.assertGreater(diagnostics.get("peak_resident_bytes", 0), 64 * 1024 * 1024)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(output.name + ".*.tmp*")))

    @unittest.skipUnless(
        Path(r"C:\XboxGames\Forza Horizon 6\Content").is_dir(),
        "FH6 local asset integration test",
    )
    def test_real_reference_cars_match_the_verified_geometry_contract(self):
        game = Path(r"C:\XboxGames\Forza Horizon 6\Content")
        index = load_or_build_vehicle_asset_index(
            game,
            ROOT / "runtime" / "full-livery" / "cache" / "vehicle-index.json",
        )
        expected = {
            3304: {
                "mesh_count": 683,
                "paint_meshes": 14,
                "glass_meshes": 8,
                "triangle_count": 698940,
                "direct_uv3_meshes": 22,
                "projected_livery_meshes": 0,
                "part_option_count": 0,
            },
            2738: {
                "mesh_count": 746,
                "paint_meshes": 43,
                "glass_meshes": 13,
                "triangle_count": 432488,
                "direct_uv3_meshes": 56,
                "projected_livery_meshes": 0,
                "part_option_count": 0,
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            for car_id, contract in expected.items():
                output = Path(temp) / f"{car_id}.glb"
                convert_vehicle_model_to_glb(index[car_id], output)
                self.assertEqual(contract, validate_local_chassis_glb(output))


if __name__ == "__main__":
    unittest.main()
