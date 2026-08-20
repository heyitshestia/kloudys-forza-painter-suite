from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import urlopen

from PySide6.QtCore import QCoreApplication
from PIL import Image

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.livery.inspector_server import LiveryInspectorServer
from tools.livery.fh6_save_installer import (
    FullLiveryConcurrentChangeError,
    FullLiveryInstallError,
    HeaderMetadata,
    _wrap_payload,
    build_destination_header,
    install_full_livery_package,
    parse_fh6_header,
    select_destination_identity,
)
from tools.livery.package import (
    PACKAGE_COMPILER_REVISION,
    PACKAGE_FORMAT,
    PRIVATE_PREVIEW_FORMAT,
    FullLiveryPackageError,
    _png_pixels_match,
    _render_livery_sections,
    compatibility_decision,
    create_full_livery_package,
    create_local_livery_preview,
    migrate_full_livery_package,
    validate_full_livery_package,
    validate_livery_inspection_artifact,
)
from tools.cgroup.forza_source_decoder import (
    LIVERY_SECTION_NAMES,
    extract_livery_payload,
    inspect_clivery_privacy,
    unwrap_forza_container,
)
from tools.livery.render_contract import (
    FLIP_X_SLOTS,
    FLIP_Y_SLOTS,
    RENDER_CONTRACT_FORMAT,
    SECTION_FACING,
    SECTION_FILTER,
    SECTION_TO_SLOT,
    TRANSPOSED_SLOTS,
    _projection_pixel_bounds,
    build_local_livery_atlases,
)
from tools.livery.vehicle_assets import (
    VehicleAsset,
    discover_fh6_game_folder,
    inspection_model_entries,
    load_or_build_vehicle_asset_index,
    normalize_fh6_game_folder,
    read_projection_metadata,
    read_vehicle_assembly_metadata,
)
from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.log_service import LogService
from json_preview_renderer import render_typecode_layers_canvas


APP = QCoreApplication.instance() or QCoreApplication([])


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def livery_payload(
    *, state: int = 0, car_id: int = 3304, foreign_group: bool = False, placement_count: int = 0
) -> bytes:
    body = bytearray(23 * 11)
    counts = [0] * 11
    if foreign_group:
        transform = struct.pack("<ffff", 0.0, 0.0, 1.0, 0.0)
        protected_wrapper = b"\x21\x01\x02\x03\x04\x00\x00\x09\x00"
        markerless_group = b"\x01\x00\x01\x00\x00\x00"
        shape = bytearray(32)
        shape[:2] = b"\x00\x02"
        struct.pack_into("<H", shape, 2, 1)
        struct.pack_into("<f", shape, 16, 1.0)
        struct.pack_into("<f", shape, 20, 1.0)
        shape[28:32] = b"\xff\xff\xff\xff"
        body = bytearray(b"\x01" + transform + protected_wrapper + markerless_group + shape)
        counts[0] = 1
    elif placement_count > 0:
        counts[0] = placement_count

    payload = bytearray(0x40)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 4, 1)
    struct.pack_into("<I", payload, 8, state)
    struct.pack_into("<I", payload, 0x10, car_id)
    payload.extend(b"gyvl" + bytes(0x11) + body + b"yrvl")
    payload.extend(b"".join(struct.pack("<I", value) for value in counts))
    return bytes(payload)


def raster_livery_payload(*, raster_id: int, car_id: int = 3304) -> bytes:
    shape = bytearray(32)
    shape[:2] = b"\x00\x02"
    struct.pack_into("<H", shape, 2, 0x8000 | int(raster_id))
    struct.pack_into("<f", shape, 16, 1.0)
    struct.pack_into("<f", shape, 20, 1.0)
    shape[28:32] = b"\xff\xff\xff\xff"
    body = bytes(shape) + bytes(18) + bytes(23 * 10)
    counts = [1] + [0] * 10

    payload = bytearray(0x40)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 4, 1)
    struct.pack_into("<I", payload, 8, 0)
    struct.pack_into("<I", payload, 0x10, car_id)
    payload.extend(b"gyvl" + bytes(0x11) + body + b"yrvl")
    payload.extend(b"".join(struct.pack("<I", value) for value in counts))
    return bytes(payload)


def build_package(path: Path, *, car_id: int = 3304, payload_override: bytes | None = None) -> dict:
    payload = payload_override or livery_payload(car_id=car_id)
    _, counts, payload_meta = extract_livery_payload(payload)
    source_car_id = struct.unpack_from("<I", payload, 0x10)[0]
    source_state = struct.unpack_from("<I", payload, 0x08)[0]
    compressed = zlib.compress(bytes(payload))
    container = struct.pack("<II", len(compressed), len(payload)) + compressed
    layers = json_bytes({
        "format": "kfps_full_livery_layers_v1",
        "game": "fh6",
        "target_car_id": source_car_id,
        "section_order": list(LIVERY_SECTION_NAMES),
        "section_counts": dict(zip(LIVERY_SECTION_NAMES, counts)),
        "layers": [],
    })
    vehicle = json_bytes({"car_id": source_car_id, "model_code": "TEST_CAR", "portable_mesh": False})
    projection = json_bytes({
        "format": "kfps_fh6_projection_source_v1",
        "decoded_for_viewer": False,
        "rendered_sections": [],
        "source_container_preserved": True,
        "canonical_decode_complete": True,
        "preview_complete": True,
        "source_exact": True,
        "incomplete_preview": False,
        "native_raster_verified": True,
        "unresolved_raster_ids": [],
    })
    members = {
        "source/fh6/C_livery": container,
        "source/fh6/header": destination_header(car_id=source_car_id),
        "livery/layers.json": layers,
        "mesh/vehicle.json": vehicle,
        "projection/index.json": projection,
    }
    manifest = {
        "format": PACKAGE_FORMAT,
        "format_version": 1,
        "compiler_revision": PACKAGE_COMPILER_REVISION,
        "package_id": str(uuid.uuid4()),
        "source": {
            "game": "fh6",
            "source_state": source_state,
            "container_sha256": sha(container),
            "payload_sha256": sha(bytes(payload)),
            "payload_size": len(payload),
            "container_version": struct.unpack_from("<I", payload, 4)[0],
            "category_state": struct.unpack_from("<I", payload, 0x14)[0],
        },
        "livery": {
            "title": "Fixture",
            "target_car_id": source_car_id,
            "logical_placement_count": sum(counts),
            "decoded_layer_count": 0,
            "section_counts": dict(zip(LIVERY_SECTION_NAMES, counts)),
            "preview_complete": True,
            "unresolved_raster_ids": [],
            "payload_offsets": payload_meta,
        },
        "vehicle": {"car_id": source_car_id, "model_code": "TEST_CAR", "portable_mesh": False},
        "sharing": {
            "exportable": True,
            "preview_only": False,
            "external_game_assets_embedded": False,
            "source_container_preserved": True,
            "preview_complete": True,
            "unresolved_raster_references": False,
        },
        "compatibility": {
            "fh6": {
                "status": "exact-source-supported",
                "keep_roles": ["source-container", "canonical-layers"],
                "translate": ["destination-save-identity"],
                "discard_roles_on_game_install": ["inspection-mesh"],
            },
            "fh4": {
                "status": "recompile-required-not-implemented",
                "keep_roles": ["canonical-layers"],
                "translate": ["target-car-id"],
                "discard_roles": ["source-container"],
            },
        },
        "files": [
            {"path": name, "role": "fixture", "size": len(data), "sha256": sha(data)}
            for name, data in sorted(members.items())
        ],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json_bytes(manifest))
        for name, data in members.items():
            bundle.writestr(name, data)
    return manifest


def rewrite_package(source: Path, target: Path, transform) -> None:
    with zipfile.ZipFile(source) as original:
        entries = {info.filename: original.read(info) for info in original.infolist()}
    transform(entries)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries.items():
            bundle.writestr(name, data)


def refresh_manifest_hashes(entries: dict[str, bytes]) -> None:
    manifest = json.loads(entries["manifest.json"])
    by_name = {record["path"]: record for record in manifest["files"]}
    for name, data in entries.items():
        if name == "manifest.json":
            continue
        record = by_name[name]
        record["size"] = len(data)
        record["sha256"] = sha(data)
    entries["manifest.json"] = json_bytes(manifest)


def build_livery_source(path: Path, *, state: int, car_id: int = 3304, placement_count: int = 1) -> None:
    payload = livery_payload(state=state, car_id=car_id, placement_count=placement_count)
    compressed = zlib.compress(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)


def installable_livery_payload(*, car_id: int = 3304, creator_tag: bytes = b"SOURCE01") -> bytes:
    payload = bytearray(0x40)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 4, 1)
    struct.pack_into("<I", payload, 8, 0)
    struct.pack_into("<I", payload, 0x10, car_id)
    payload[0x1A:0x1E] = b"yrvl"
    struct.pack_into("<I", payload, 0x1E, 8)
    payload[0x22:0x2A] = creator_tag
    payload.extend(b"gyvl" + bytes(0x11) + bytes(23) + b"yrvl")
    payload.extend(struct.pack("<I", 1) + bytes(40))
    return bytes(payload)


def destination_header(*, car_id: int = 3304, creator_tag: bytes = b"DEST0001") -> bytes:
    template = HeaderMetadata(
        format_version=7,
        title="Template",
        published=False,
        description="",
        year=2026,
        month=8,
        day_of_week=0,
        day=0,
        hour=0,
        minute=0,
        second=0,
        millisecond=0,
        date_trailing=struct.pack("<HH", 3, 0),
        creator_tag=creator_tag,
        creator_name="Destination",
        section_prefix=bytes(28),
        type_value=1,
        car_id=car_id,
        asset_guid=bytes(16),
        trailing=b"",
    )
    return build_destination_header(
        template,
        title="Template",
        car_id=car_id,
        placement_count=1,
        creator_tag=creator_tag,
        now=datetime(2026, 8, 13).astimezone(),
        asset_guid=bytes.fromhex("00112233445566778899aabbccddeeff"),
    )


def build_install_destination(root: Path, *, car_id: int = 3304, creator_tag: bytes = b"DEST0001") -> Path:
    containers = root / "pgs" / "account" / "slot" / "ContainersRoot"
    folder = containers / f"Livery_{car_id:04d}_20260801000000"
    folder.mkdir(parents=True)
    (folder / "C_livery").write_bytes(_wrap_payload(installable_livery_payload(car_id=car_id, creator_tag=creator_tag)))
    (folder / "header").write_bytes(destination_header(car_id=car_id, creator_tag=creator_tag))
    return containers


def build_install_package(path: Path, *, car_id: int = 3304, model_code: str = "TEST_CAR") -> dict:
    payload = installable_livery_payload(car_id=car_id)
    manifest = {
        "sharing": {"exportable": True, "preview_only": False},
        "livery": {"title": "Install Fixture", "target_car_id": car_id, "logical_placement_count": 1},
        "vehicle": {"car_id": car_id, "model_code": model_code},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("source/fh6/C_livery", _wrap_payload(payload))
        bundle.writestr("source/fh6/header", destination_header(car_id=car_id))
    return manifest


class FullLiveryPackageTests(unittest.TestCase):
    def test_fh6_install_discovery_finds_an_xbox_install_on_another_drive(self):
        with tempfile.TemporaryDirectory() as temp:
            drive = Path(temp)
            content = drive / "XboxGames" / "Forza Horizon 6" / "Content"
            cars = content / "media" / "cars"
            cars.mkdir(parents=True)
            (cars / "test-car.zip").write_bytes(b"fixture")

            resolved = discover_fh6_game_folder(
                drive_roots=[drive],
                process_executables=[],
                steam_roots=[],
            )

            self.assertEqual(content.resolve(), resolved)

    def test_fh6_install_discovery_finds_a_steam_library(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "SteamLibrary"
            game = library / "steamapps" / "common" / "Forza Horizon 6"
            cars = game / "media" / "cars"
            cars.mkdir(parents=True)
            (cars / "test-car.zip").write_bytes(b"fixture")

            resolved = discover_fh6_game_folder(
                drive_roots=[],
                process_executables=[],
                steam_roots=[library],
            )

            self.assertEqual(game.resolve(), resolved)

    def test_linking_fh6_normalizes_the_folder_and_rescans(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = root / "Forza Horizon 6" / "Content"
            cars = content / "media" / "cars"
            cars.mkdir(parents=True)
            (cars / "test-car.zip").write_bytes(b"fixture")
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                with (
                    patch("kfps_ui.full_livery_service.QFileDialog.getExistingDirectory", return_value=str(root / "Forza Horizon 6")),
                    patch("kfps_ui.full_livery_service.load_or_build_vehicle_asset_index", return_value={3304: object()}),
                    patch.object(service, "_refresh_packages") as refresh,
                    patch.object(service, "scanSaves") as rescan,
                ):
                    service.chooseGameFolder()
                self.assertEqual(str(content.resolve()), service.gameFolder)
                self.assertEqual(str(content.resolve()), service._settings["fh6_game_folder"])
                refresh.assert_called_once_with(open_remembered=False)
                rescan.assert_called_once_with()
            finally:
                service.close()

    def test_manual_fh6_save_root_excludes_other_auto_detected_accounts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chosen = root / "chosen" / "ContainersRoot"
            chosen.mkdir(parents=True)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                service._save_root = str(chosen)
                self.assertEqual([chosen.resolve()], service._scan_roots())
            finally:
                service.close()

    def test_source_selection_without_fh6_never_builds_a_blank_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_test" / "C_livery"
            build_livery_source(source, state=0)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                with patch.object(service._executor, "submit") as submit:
                    service.selectSource(str(source))
                submit.assert_not_called()
                self.assertEqual("FH6 folder required", service.status)
                self.assertIn("build a 3D preview", service.summary)
                self.assertEqual("", service.selectedSource)
            finally:
                service.close()

    def test_livery_selection_is_public_without_a_supporter_unlock(self):
        class LockedSupporter:
            unlocked = False

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_test" / "C_livery"
            build_livery_source(source, state=0)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=LockedSupporter(), demo=False)
            try:
                service.selectSource(str(source))
                self.assertEqual("FH6 folder required", service.status)
                self.assertNotIn("supporter", service.summary.casefold())
                self.assertEqual("", service.selectedSource)
            finally:
                service.close()

    def test_canvas_renderer_uses_raster_dimensions_and_pixels(self):
        raster = Image.new("RGBA", (8, 4), (0, 0, 0, 0))
        raster.paste((255, 0, 0, 255), (0, 0, 4, 2))
        raster.paste((0, 255, 0, 255), (4, 0, 8, 2))
        raster.paste((0, 0, 255, 255), (0, 2, 4, 4))
        raster.paste((255, 255, 0, 255), (4, 2, 8, 4))
        data = render_typecode_layers_canvas(
            [{
                "type": 1000000 + 0xAAFA,
                "type_word": 0xAAFA,
                "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
                "is_raster_logo": True,
                "raster_id": 11002,
            }],
            width=64,
            height=64,
            world_bounds=(-32.0, -32.0, 32.0, 32.0),
            raster_resolver=lambda raster_id: raster if raster_id == 11002 else None,
        )

        self.assertIsNotNone(data)
        rendered = Image.open(io.BytesIO(data)).convert("RGBA")
        self.assertEqual((28, 30, 36, 34), rendered.getbbox())
        self.assertEqual((255, 0, 0, 255), rendered.getpixel((29, 31)))
        self.assertEqual((0, 255, 0, 255), rendered.getpixel((34, 31)))
        self.assertEqual((0, 0, 255, 255), rendered.getpixel((29, 32)))
        self.assertEqual((255, 255, 0, 255), rendered.getpixel((34, 32)))

    def test_canvas_renderer_keeps_raster_rgb_and_applies_placement_alpha_only(self):
        raster = Image.new("RGBA", (8, 4), (240, 80, 20, 255))
        data = render_typecode_layers_canvas(
            [{
                "type": 1000000 + 0xAAFA,
                "type_word": 0xAAFA,
                "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [0, 0, 0, 128],
                "is_raster_logo": True,
                "raster_id": 11002,
            }],
            width=64,
            height=64,
            world_bounds=(-32.0, -32.0, 32.0, 32.0),
            raster_resolver=lambda raster_id: raster if raster_id == 11002 else None,
        )

        self.assertIsNotNone(data)
        rendered = Image.open(io.BytesIO(data)).convert("RGBA")
        pixel = rendered.getpixel((32, 32))
        self.assertTrue(all(abs(actual - expected) <= 1 for actual, expected in zip(pixel[:3], (240, 80, 20))))
        self.assertEqual(128, pixel[3])

    def test_canvas_renderer_honors_preview_cancellation(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(concurrent.futures.CancelledError):
            render_typecode_layers_canvas(
                [{
                    "type": 1048677,
                    "type_word": 1,
                    "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                    "color": [255, 255, 255, 255],
                }],
                cancel_event=cancelled,
            )

    def test_canvas_renderer_preserves_native_vertex_alpha_gradients(self):
        data = render_typecode_layers_canvas(
            [{
                "type": 1050977,
                "resource_family": "Community_Vinyls_4",
                "resource_index": 1,
                "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
            }],
            width=256,
            height=256,
            world_bounds=(-128.0, -128.0, 128.0, 128.0),
            strict_assets=True,
        )

        self.assertIsNotNone(data)
        rendered = Image.open(io.BytesIO(data)).convert("RGBA")
        alpha_values = set(rendered.getchannel("A").getdata())
        self.assertTrue(any(0 < value < 255 for value in alpha_values))

    def test_canvas_renderer_clips_valid_off_canvas_gradient_in_strict_mode(self):
        data = render_typecode_layers_canvas(
            [{
                "type": 1050977,
                "resource_family": "Community_Vinyls_4",
                "resource_index": 1,
                "data": [5000.0, 5000.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
            }],
            width=256,
            height=256,
            world_bounds=(-128.0, -128.0, 128.0, 128.0),
            strict_assets=True,
        )

        self.assertIsNone(data)

    def test_canvas_renderer_strict_mode_rejects_missing_native_and_raster_assets(self):
        with self.assertRaisesRegex(ValueError, "no exact native resource"):
            render_typecode_layers_canvas(
                [{
                    "type": 1099999,
                    "type_word": 0xF00D,
                    "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                    "color": [255, 255, 255, 255],
                }],
                strict_assets=True,
            )

    def test_livery_renderer_omits_one_unavailable_raster_without_losing_the_section(self):
        layers = [
            {
                "type": 1050977,
                "resource_family": "Community_Vinyls_4",
                "resource_index": 1,
                "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
                "source_section": "Left",
            },
            {
                "type": 1000000 + 0x87EE,
                "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                "color": [255, 255, 255, 255],
                "source_section": "Left",
                "is_raster_logo": True,
                "raster_id": 2030,
            },
        ]
        warnings = []

        with patch("tools.livery.package.FH6RasterDecalResolver", return_value=lambda _raster_id: None):
            rendered, raster_verified, unresolved_raster_ids = _render_livery_sections(
                layers,
                game_folder=Path("C:/FH6"),
                warnings=warnings,
                strict_assets=True,
            )

        self.assertIn("Left", rendered)
        self.assertFalse(raster_verified)
        self.assertEqual([2030], unresolved_raster_ids)
        self.assertTrue(any("2030" in warning for warning in warnings))
        with self.assertRaisesRegex(ValueError, "raster decal resolver"):
            render_typecode_layers_canvas(
                [{
                    "type": 1000000 + 0xAAFA,
                    "type_word": 0xAAFA,
                    "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                    "color": [255, 255, 255, 255],
                    "is_raster_logo": True,
                    "raster_id": 11002,
                }],
                strict_assets=True,
            )

    def test_owned_livery_with_unresolved_raster_exports_and_remains_installable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_unresolved" / "C_livery"
            payload = raster_livery_payload(raster_id=20314)
            compressed = zlib.compress(payload)
            source.parent.mkdir(parents=True)
            source.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)
            output = root / "unresolved.kfpslivery"

            with (
                patch("tools.livery.package.load_or_build_vehicle_asset_index", return_value={}),
                patch("tools.livery.package.FH6RasterDecalResolver", return_value=lambda _raster_id: None),
            ):
                manifest = create_full_livery_package(source, output, game_folder=Path("C:/FH6"))
                validated = validate_full_livery_package(
                    output,
                    game_folder=Path("C:/FH6"),
                    verify_previews=True,
                )

            self.assertTrue(manifest["sharing"]["exportable"])
            self.assertTrue(manifest["sharing"]["source_container_preserved"])
            self.assertTrue(manifest["sharing"]["unresolved_raster_references"])
            self.assertFalse(manifest["sharing"]["preview_complete"])
            self.assertEqual([20314], manifest["livery"]["unresolved_raster_ids"])
            self.assertTrue(compatibility_decision(validated, "fh6")["installable"])
            with zipfile.ZipFile(output) as bundle:
                projection = json.loads(bundle.read("projection/index.json"))
                self.assertTrue(projection["source_container_preserved"])
                self.assertTrue(projection["canonical_decode_complete"])
                self.assertFalse(projection["preview_complete"])
                self.assertTrue(projection["incomplete_preview"])
                self.assertEqual([20314], projection["unresolved_raster_ids"])
                with Image.open(io.BytesIO(bundle.read("projection/rendered/Front.png"))) as preview:
                    self.assertIsNone(preview.convert("RGBA").getbbox())

    def test_saved_package_list_hides_zero_placement_liveries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            package_root = paths.exported_root / "full-liveries"
            package_root.mkdir(parents=True)
            empty = package_root / "empty.kfpslivery"
            populated = package_root / "populated.kfpslivery"
            empty.write_bytes(b"fixture")
            populated.write_bytes(b"fixture")

            def inspect(path):
                count = 0 if Path(path).name == empty.name else 12
                return {
                    "title": Path(path).stem,
                    "target_car_id": 3304,
                    "model_code": "TEST_CAR",
                    "logical_placement_count": count,
                    "portable_mesh": False,
                }

            with (
                patch("kfps_ui.full_livery_service.package_compiler_revision", return_value=PACKAGE_COMPILER_REVISION),
                patch("kfps_ui.full_livery_service.inspect_full_livery_package", side_effect=inspect),
            ):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                rows = service._packages.rows
                self.assertEqual(["populated.kfpslivery"], [Path(row["path"]).name for row in rows])
                self.assertEqual(12, rows[0]["placementCount"])
                self.assertTrue(empty.is_file())
            finally:
                service.close()

    def test_save_scan_refreshes_an_open_preview_only_when_source_content_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            source = root / "save" / "C_livery"
            build_livery_source(source, state=0, placement_count=1)
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._active_source_preview = str(source.resolve())
            service._selected_source = str(source.resolve())
            service._selected_package = str(service._source_preview_target(source).resolve())
            row = {"path": str(source.resolve()), "exportable": True, "privacyDetail": ""}
            try:
                with patch.object(service, "selectSource") as select:
                    self.assertFalse(service._refresh_active_source_after_scan([row]))
                    select.assert_not_called()

                    source.write_bytes(source.read_bytes() + b"changed")
                    self.assertTrue(service._refresh_active_source_after_scan([row]))
                    select.assert_called_once_with(str(source.resolve()))
            finally:
                service.close()

    def test_save_scan_closes_an_open_preview_when_source_is_no_longer_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            source = root / "save" / "C_livery"
            build_livery_source(source, state=0, placement_count=1)
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._active_source_preview = str(source.resolve())
            service._selected_source = str(source.resolve())
            service._selected_package = "old-preview.kfpspreview"
            service._viewer_url = "http://127.0.0.1/old-preview"
            try:
                self.assertFalse(service._refresh_active_source_after_scan([]))
                self.assertEqual("", service.selectedSource)
                self.assertEqual("", service.selectedPackage)
                self.assertEqual("", service.viewerUrl)
            finally:
                service.close()

    def test_service_removes_only_legacy_source_preview_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "runtime" / "full-livery" / "cache" / "source-previews"
            cache.mkdir(parents=True)
            legacy = cache / "old.kfpslivery"
            current = cache / "current.kfpspreview"
            legacy.write_bytes(b"legacy")
            current.write_bytes(b"current")
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )

            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                self.assertFalse(legacy.exists())
                self.assertTrue(current.exists())
            finally:
                service.close()

    def test_clear_full_livery_cache_removes_only_rebuildable_cache_and_recreates_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            cache = root / "runtime" / "full-livery" / "cache"
            cached_files = [
                cache / "fh6-vehicle-index.json",
                cache / "meshes" / "car.glb",
                cache / "section-render" / "car" / "index.json",
                cache / "source-previews" / "preview.kfpspreview",
            ]
            for path in cached_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"cached")
            settings = root / "runtime" / "full-livery" / "settings.json"
            settings.write_text('{"fh6_save_root": "preserve"}\n', encoding="utf-8")
            saved = root / "imgs" / "exported" / "full-liveries" / "preserve.kfpslivery"
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(b"saved package")
            try:
                service.clearFullLiveryCache()
                deadline = time.monotonic() + 5.0
                while service.running and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(0.01)
                APP.processEvents()

                self.assertFalse(service.running)
                self.assertTrue(cache.is_dir())
                self.assertEqual([], list(cache.iterdir()))
                self.assertTrue(settings.is_file())
                self.assertEqual(b"saved package", saved.read_bytes())
                self.assertEqual("Full-livery cache cleared", service.status)
                self.assertIn("4 cached files", service.summary)
            finally:
                service.close()

    def test_clear_full_livery_cache_reopens_the_active_source_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "save" / "C_livery"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._selected_source = str(source.resolve())
            service._active_source_preview = str(source.resolve())
            try:
                with patch.object(service, "selectSource") as reopen:
                    service.clearFullLiveryCache()
                    deadline = time.monotonic() + 5.0
                    while service.running and time.monotonic() < deadline:
                        APP.processEvents()
                        time.sleep(0.01)
                    APP.processEvents()
                reopen.assert_called_once_with(str(source.resolve()))
                self.assertEqual("", service.viewerUrl)
                self.assertEqual("", service.selectedPackage)
            finally:
                service.close()

    def test_privacy_inspection_distinguishes_owned_and_foreign_group_artwork(self):
        clean = inspect_clivery_privacy(livery_payload())
        protected = inspect_clivery_privacy(livery_payload(foreign_group=True))
        other_player = inspect_clivery_privacy(livery_payload(state=1))

        self.assertTrue(clean["source_owned"])
        self.assertFalse(clean["contains_foreign_groups"])
        self.assertEqual(0, clean["foreign_group_count"])
        self.assertTrue(protected["source_owned"])
        self.assertTrue(protected["contains_foreign_groups"])
        self.assertEqual(1, protected["foreign_group_count"])
        self.assertFalse(other_player["source_owned"])

    def test_share_export_rejects_foreign_groups_before_writing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_owned_with_foreign" / "C_livery"
            build_livery_source(source, state=0)
            payload = livery_payload(foreign_group=True)
            compressed = zlib.compress(payload)
            source.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)
            output = root / "blocked.kfpslivery"

            with self.assertRaisesRegex(FullLiveryPackageError, "created by another player"):
                create_full_livery_package(source, output)
            self.assertFalse(output.exists())

    def test_package_validation_rechecks_preserved_source_privacy(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "foreign-source.kfpslivery"
            build_package(package, payload_override=livery_payload(foreign_group=True))

            with self.assertRaisesRegex(FullLiveryPackageError, "created by another player"):
                validate_full_livery_package(package)

    def test_preview_verification_compares_pixels_not_png_compression(self):
        image = Image.new("RGBA", (32, 16), (12, 34, 56, 200))
        compressed = io.BytesIO()
        uncompressed = io.BytesIO()
        image.save(compressed, format="PNG", compress_level=9)
        image.save(uncompressed, format="PNG", compress_level=0)
        self.assertNotEqual(compressed.getvalue(), uncompressed.getvalue())
        self.assertTrue(_png_pixels_match(compressed.getvalue(), uncompressed.getvalue()))

    def test_package_json_rejects_non_standard_numeric_constants(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.kfpslivery"
            malformed = root / "nan.kfpslivery"
            build_package(source)

            def transform(entries):
                manifest = json.loads(entries["manifest.json"])
                manifest["livery"]["logical_placement_count"] = float("nan")
                entries["manifest.json"] = json.dumps(manifest).encode("utf-8")

            rewrite_package(source, malformed, transform)
            with self.assertRaisesRegex(FullLiveryPackageError, "manifest is invalid"):
                validate_full_livery_package(malformed)

    def test_private_preview_omits_shareable_source_and_layer_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_owned" / "C_livery"
            payload = livery_payload()
            compressed = zlib.compress(payload)
            source.parent.mkdir(parents=True)
            source.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)
            output = root / "preview.kfpspreview"

            manifest = create_local_livery_preview(source, output)
            self.assertEqual(PRIVATE_PREVIEW_FORMAT, manifest["format"])
            self.assertFalse(manifest["sharing"]["exportable"])
            self.assertFalse(manifest["sharing"]["contains_foreign_vinyl_groups"])
            validate_livery_inspection_artifact(output)
            with self.assertRaises(FullLiveryPackageError):
                validate_full_livery_package(output)
            with zipfile.ZipFile(output) as bundle:
                names = {name.casefold() for name in bundle.namelist()}
            self.assertNotIn("source/fh6/c_livery", names)
            self.assertNotIn("source/fh6/header", names)
            self.assertNotIn("livery/layers.json", names)

    def test_unowned_private_preview_remains_source_free_and_non_exportable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_unowned" / "C_livery"
            payload = livery_payload(state=1)
            compressed = zlib.compress(payload)
            source.parent.mkdir(parents=True)
            source.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)
            output = root / "comparison.kfpspreview"

            with self.assertRaisesRegex(FullLiveryPackageError, "belongs to another player"):
                create_local_livery_preview(source, output)

            manifest = create_local_livery_preview(
                source,
                output,
                _allow_unowned_private_preview=True,
            )
            self.assertEqual(PRIVATE_PREVIEW_FORMAT, manifest["format"])
            self.assertFalse(manifest["source"]["owned"])
            self.assertEqual("local-unowned-preview", manifest["source"]["kind"])
            self.assertFalse(manifest["sharing"]["exportable"])
            self.assertTrue(manifest["sharing"]["preview_only"])
            self.assertTrue(manifest["sharing"]["local_unowned_preview"])
            decision = compatibility_decision(manifest, "fh6")
            self.assertEqual("local-preview", decision["status"])
            self.assertFalse(decision["installable"])
            validate_livery_inspection_artifact(output)
            with self.assertRaises(FullLiveryPackageError):
                validate_full_livery_package(output)
            with zipfile.ZipFile(output) as bundle:
                names = {name.casefold() for name in bundle.namelist()}
            self.assertNotIn("source/fh6/c_livery", names)
            self.assertNotIn("source/fh6/header", names)
            self.assertNotIn("livery/layers.json", names)

    def test_private_preview_records_partial_decode_but_shareable_export_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_partial" / "C_livery"
            build_livery_source(source, state=0, placement_count=1)
            preview = root / "partial.kfpspreview"

            manifest = create_local_livery_preview(source, preview)
            with zipfile.ZipFile(preview) as bundle:
                projection = json.loads(bundle.read("projection/index.json"))
            self.assertFalse(projection["source_exact"])
            self.assertTrue(projection["incomplete_preview"])
            self.assertEqual(
                [{"section": "Front", "declared": 1, "decoded": 0}],
                manifest["livery"]["section_count_mismatches"],
            )
            self.assertFalse(manifest["sharing"]["exportable"])
            validate_livery_inspection_artifact(preview)

            with self.assertRaisesRegex(FullLiveryPackageError, "decoded 0 of 1 declared placements"):
                create_full_livery_package(source, root / "partial.kfpslivery")

    def test_source_preview_cache_changes_with_renderer_and_package_revisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Livery_test" / "C_livery"
            build_livery_source(source, state=0)
            (source.parent / "header").write_bytes(b"same header")
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = "C:/FH6"
            created: list[Path] = []

            def validate(path):
                if not Path(path).is_file():
                    raise OSError("not built")
                return {}

            def create(_source, output, **_kwargs):
                target = Path(output)
                target.write_bytes(b"package")
                created.append(target)

            try:
                with (
                    patch("kfps_ui.full_livery_service.validate_livery_inspection_artifact", side_effect=validate),
                    patch("kfps_ui.full_livery_service.create_local_livery_preview", side_effect=create),
                ):
                    first = service._preview_source_work(source)["path"]
                    repeated = service._preview_source_work(source)["path"]
                    with patch(
                        "kfps_ui.full_livery_service.PACKAGE_COMPILER_REVISION",
                        PACKAGE_COMPILER_REVISION + 1,
                    ):
                        package_revised = service._preview_source_work(source)["path"]
                    with patch(
                        "kfps_ui.full_livery_service.SOURCE_PREVIEW_CACHE_REVISION",
                        3,
                    ):
                        renderer_revised = service._preview_source_work(source)["path"]
                self.assertEqual(first, repeated)
                self.assertNotEqual(first, package_revised)
                self.assertNotEqual(first, renderer_revised)
                self.assertNotEqual(package_revised, renderer_revised)
                self.assertEqual(3, len(created))
            finally:
                service.close()

    def test_save_scan_hides_unowned_liveries_and_marks_foreign_groups_preview_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_root = root / "saves"
            shareable = save_root / "Livery_shareable" / "C_livery"
            locked = save_root / "Livery_locked" / "C_livery"
            protected = save_root / "Livery_protected" / "C_livery"
            empty = save_root / "Livery_empty" / "C_livery"
            build_livery_source(shareable, state=0)
            build_livery_source(locked, state=1)
            build_livery_source(empty, state=0, placement_count=0)
            payload = livery_payload(foreign_group=True)
            compressed = zlib.compress(payload)
            protected.parent.mkdir(parents=True)
            protected.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = ""
            service._scan_roots = lambda: [save_root]
            try:
                result = service._scan_saves_work()
                self.assertEqual(4, result["inspected"])
                self.assertEqual(1, result["locked"])
                self.assertEqual(0, result["rejected"])
                self.assertEqual(1, result["foreign_blocked"])
                self.assertEqual(1, result["empty"])
                self.assertFalse(result["game_assets_ready"])
                rows = {row["path"]: row for row in result["rows"]}
                self.assertEqual(
                    {str(shareable.resolve()), str(protected.resolve())},
                    set(rows),
                )
                self.assertTrue(rows[str(shareable.resolve())]["exportable"])
                self.assertFalse(rows[str(protected.resolve())]["exportable"])
                self.assertIn("Link the local FH6 folder", rows[str(shareable.resolve())]["detail"])
                self.assertIn("Remove every foreign vinyl group", rows[str(protected.resolve())]["privacyDetail"])
            finally:
                service.close()

    def test_local_marker_cannot_enable_unowned_liveries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_root = root / "saves"
            owned = save_root / "Livery_owned" / "C_livery"
            comparison = save_root / "Livery_comparison" / "C_livery"
            build_livery_source(owned, state=0)
            build_livery_source(comparison, state=1)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            marker = paths.runtime_root / "full-livery" / "allow-unowned-comparison-previews.local"
            marker.parent.mkdir(parents=True)
            marker.write_text("local test\n", encoding="utf-8")
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = "C:/FH6"
            service._scan_roots = lambda: [save_root]

            try:
                with patch("kfps_ui.full_livery_service.load_or_build_vehicle_asset_index", return_value={}):
                    result = service._scan_saves_work()
                rows = {row["path"]: row for row in result["rows"]}
                self.assertEqual(0, result["foreign_blocked"])
                self.assertEqual(1, result["locked"])
                self.assertEqual({str(owned.resolve())}, set(rows))
                self.assertTrue(rows[str(owned.resolve())]["exportable"])
                self.assertFalse(hasattr(service, "_allow_unowned_comparison"))

                with self.assertRaises(FullLiveryPackageError):
                    create_local_livery_preview(comparison, root / "unowned.kfpspreview")
                with self.assertRaises(FullLiveryPackageError):
                    service._preview_source_work(comparison)
            finally:
                service.close()

    def test_export_selected_uses_a_unique_saved_package_path_without_a_save_dialog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "saves" / "My Livery" / "C_livery"
            build_livery_source(source, state=0, car_id=3304)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            first = service._package_root / "My Livery - FH6 3304.kfpslivery"
            first.write_bytes(b"existing package")
            service._selected_source = str(source.resolve())
            try:
                with (
                    patch("kfps_ui.full_livery_service.QFileDialog.getSaveFileName") as save_dialog,
                    patch.object(service._executor, "submit") as submit,
                ):
                    service.exportSelected()

                save_dialog.assert_not_called()
                submit.assert_called_once()
                self.assertEqual(service._export_work, submit.call_args.args[0])
                self.assertEqual(source, submit.call_args.args[1])
                self.assertEqual(
                    service._package_root / "My Livery - FH6 3304 (2).kfpslivery",
                    submit.call_args.args[2],
                )
                self.assertEqual("Building full-livery package", service.status)
                self.assertIn("Saved packages", service.summary)
            finally:
                service.close()

    def test_completed_export_refreshes_saved_packages_and_opens_the_new_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            package = service._package_root / "Finished - FH6 3304.kfpslivery"
            try:
                service._running = True
                with (
                    patch.object(service, "_refresh_packages") as refresh,
                    patch.object(service, "selectPackage") as select,
                ):
                    service._apply_result({"ok": True, "kind": "export", "payload": {"path": str(package)}})

                refresh.assert_called_once_with(open_remembered=False)
                select.assert_called_once_with(str(package))
                self.assertFalse(service.running)
                self.assertEqual("Full-livery package created", service.status)
                self.assertIn(package.name, service.summary)
            finally:
                service.close()

    def test_package_validation_and_target_policy_are_content_aware(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "fixture.kfpslivery"
            build_package(package)

            manifest = validate_full_livery_package(package)
            self.assertEqual(3304, manifest["livery"]["target_car_id"])
            self.assertTrue(compatibility_decision(manifest, "fh6")["installation_eligible"])
            self.assertTrue(compatibility_decision(manifest, "fh6")["installable"])
            self.assertFalse(compatibility_decision(manifest, "fh6", target_car_id=9999)["installable"])
            self.assertEqual(
                "recompile-required-not-implemented",
                compatibility_decision(manifest, "fh4")["status"],
            )

    def test_same_car_installer_creates_a_new_verified_entry_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            containers = build_install_destination(root)
            package = root / "fixture.kfpslivery"
            manifest = build_install_package(package)
            existing = sorted(path.name for path in containers.iterdir())
            decoded = ([{"type": 1, "source_section": "left"}], {"warnings": ["known fixture warning"]})

            installed_at = datetime(2027, 9, 17, 12, 34, 56, 789000).astimezone()
            with (
                patch("tools.livery.fh6_save_installer.validate_full_livery_package", return_value=manifest),
                patch("tools.livery.fh6_save_installer.clivery_to_layers", return_value=decoded),
            ):
                result = install_full_livery_package(
                    package,
                    scan_roots=[root],
                    backup_root=root / "backups",
                    expected_model_code="TEST_CAR",
                    now=installed_at,
                )

            self.assertEqual(existing, sorted(path.name for path in containers.iterdir() if path != result.installed_folder))
            self.assertTrue(result.installed_folder.is_dir())
            self.assertTrue((result.backup_path / "install.json").is_file())
            self.assertEqual(1, result.placement_count)
            installed_header = parse_fh6_header((result.installed_folder / "header").read_bytes())
            self.assertEqual(
                (
                    installed_at.year,
                    installed_at.month,
                    (installed_at.weekday() + 1) % 7,
                    installed_at.day,
                    installed_at.hour,
                    installed_at.minute,
                    installed_at.second,
                    installed_at.microsecond // 1000,
                ),
                (
                    installed_header.year,
                    installed_header.month,
                    installed_header.day_of_week,
                    installed_header.day,
                    installed_header.hour,
                    installed_header.minute,
                    installed_header.second,
                    installed_header.millisecond,
                ),
            )

    def test_same_car_installer_converts_a_published_source_header_to_a_local_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_install_destination(root)
            package = root / "fixture.kfpslivery"
            manifest = build_install_package(package)
            with zipfile.ZipFile(package) as bundle:
                entries = {info.filename: bundle.read(info) for info in bundle.infolist()}
            draft_bytes = entries["source/fh6/header"]
            title_units = struct.unpack_from("<I", draft_bytes, 4)[0]
            description_offset = 8 + title_units * 2
            description = "Published source".encode("utf-16le")
            entries["source/fh6/header"] = (
                draft_bytes[:description_offset]
                + struct.pack("<I", len(description) // 2)
                + description
                + draft_bytes[description_offset + 4 :]
            )
            published = root / "published.kfpslivery"
            with zipfile.ZipFile(published, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name, data in entries.items():
                    bundle.writestr(name, data)
            decoded = ([{"type": 1, "source_section": "left"}], {"warnings": []})
            with (
                patch("tools.livery.fh6_save_installer.validate_full_livery_package", return_value=manifest),
                patch("tools.livery.fh6_save_installer.clivery_to_layers", return_value=decoded),
            ):
                result = install_full_livery_package(
                    published,
                    scan_roots=[root],
                    backup_root=root / "backups",
                    expected_model_code="TEST_CAR",
                )
            installed_header = parse_fh6_header((result.installed_folder / "header").read_bytes())
            self.assertFalse(installed_header.published)
            self.assertEqual("", installed_header.description)

    def test_same_car_installer_blocks_model_mismatch_before_touching_save(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            containers = build_install_destination(root)
            package = root / "fixture.kfpslivery"
            manifest = build_install_package(package)
            before = sorted(path.name for path in containers.iterdir())
            with patch("tools.livery.fh6_save_installer.validate_full_livery_package", return_value=manifest):
                with self.assertRaisesRegex(FullLiveryInstallError, "Same-car safety"):
                    install_full_livery_package(
                        package,
                        scan_roots=[root],
                        backup_root=root / "backups",
                        expected_model_code="OTHER_CAR",
                    )
            self.assertEqual(before, sorted(path.name for path in containers.iterdir()))

    def test_same_car_installer_rejects_ambiguous_destination_accounts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_install_destination(root / "first", creator_tag=b"ACCOUNT1")
            build_install_destination(root / "second", creator_tag=b"ACCOUNT2")
            with self.assertRaisesRegex(FullLiveryInstallError, "More than one FH6 account"):
                select_destination_identity([root], car_id=3304)

    def test_same_car_installer_aborts_if_save_changes_while_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            containers = build_install_destination(root)
            package = root / "fixture.kfpslivery"
            manifest = build_install_package(package)
            before = sorted(path.name for path in containers.iterdir())
            decoded = ([{"type": 1, "source_section": "left"}], {"warnings": []})
            with (
                patch("tools.livery.fh6_save_installer.validate_full_livery_package", return_value=manifest),
                patch("tools.livery.fh6_save_installer.clivery_to_layers", return_value=decoded),
                patch("tools.livery.fh6_save_installer._snapshot", side_effect=[(("before", 1, "a"),), (("after", 1, "b"),)]),
            ):
                with self.assertRaises(FullLiveryConcurrentChangeError):
                    install_full_livery_package(
                        package,
                        scan_roots=[root],
                        backup_root=root / "backups",
                        expected_model_code="TEST_CAR",
                    )
            self.assertEqual(before, sorted(path.name for path in containers.iterdir()))

    def test_same_car_installer_rolls_back_a_failed_post_commit_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            containers = build_install_destination(root)
            package = root / "fixture.kfpslivery"
            manifest = build_install_package(package)
            before = sorted(path.name for path in containers.iterdir())
            decoded = ([{"type": 1, "source_section": "left"}], {"warnings": []})
            real_unwrap = unwrap_forza_container
            calls = 0

            def fail_committed_reopen(path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ValueError("simulated committed-file corruption")
                return real_unwrap(path)

            with (
                patch("tools.livery.fh6_save_installer.validate_full_livery_package", return_value=manifest),
                patch("tools.livery.fh6_save_installer.clivery_to_layers", return_value=decoded),
                patch("tools.livery.fh6_save_installer.unwrap_forza_container", side_effect=fail_committed_reopen),
            ):
                with self.assertRaisesRegex(ValueError, "simulated committed-file corruption"):
                    install_full_livery_package(
                        package,
                        scan_roots=[root],
                        backup_root=root / "backups",
                        expected_model_code="TEST_CAR",
                    )
            self.assertEqual(before, sorted(path.name for path in containers.iterdir()))

    def test_service_submits_install_with_its_own_cancellation_token_and_no_process_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            manifest = build_package(package)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
                service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                service._selected_package = str(package)
                service._current_manifest = manifest
                service._game_folder = str(root)
                pending = MagicMock()
                pending.done.return_value = True
                with patch.object(service._executor, "submit", return_value=pending) as submit:
                    service.installSelectedPackage()
                submitted = submit.call_args.args
                self.assertEqual(service._install_package_work, submitted[0])
                self.assertEqual(package, submitted[1])
                self.assertIsInstance(submitted[2], threading.Event)
                self.assertIs(service._install_cancel_event, submitted[2])
                pending.add_done_callback.assert_called_once()
                self.assertNotIn("_fh6_running", FullLiveryService.__dict__)
            finally:
                service.close()

    def test_tampered_untracked_and_identity_mismatched_packages_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            build_package(package)

            tampered = root / "tampered.kfpslivery"
            rewrite_package(package, tampered, lambda entries: entries.__setitem__("livery/layers.json", b"{}"))
            with self.assertRaisesRegex(FullLiveryPackageError, "integrity check"):
                validate_full_livery_package(tampered)

            untracked = root / "untracked.kfpslivery"
            rewrite_package(package, untracked, lambda entries: entries.__setitem__("untracked.txt", b"no"))
            with self.assertRaisesRegex(FullLiveryPackageError, "untracked"):
                validate_full_livery_package(untracked)

            wrong_car = root / "wrong-car.kfpslivery"
            def mutate_manifest(entries):
                manifest = json.loads(entries["manifest.json"])
                manifest["livery"]["target_car_id"] = 9999
                entries["manifest.json"] = json_bytes(manifest)
            rewrite_package(package, wrong_car, mutate_manifest)
            with self.assertRaisesRegex(FullLiveryPackageError, "car identity"):
                validate_full_livery_package(wrong_car)

    def test_self_resigned_derived_layers_are_rejected_against_embedded_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            forged = root / "forged.kfpslivery"
            build_package(package)

            def forge(entries):
                layers = json.loads(entries["livery/layers.json"])
                layers["layers"] = [{
                    "type": 1000001,
                    "type_word": 1,
                    "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                    "color": [255, 255, 255, 255],
                    "mask": False,
                    "source_section": "Front",
                }]
                entries["livery/layers.json"] = json_bytes(layers)
                refresh_manifest_hashes(entries)

            rewrite_package(package, forged, forge)
            with self.assertRaisesRegex(FullLiveryPackageError, "does not match the preserved FH6 source"):
                validate_full_livery_package(forged)

    def test_noncanonical_package_id_and_incomplete_render_inventory_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            build_package(package)

            unsafe_id = root / "unsafe-id.kfpslivery"
            def forge_id(entries):
                manifest = json.loads(entries["manifest.json"])
                manifest["package_id"] = "../../outside"
                entries["manifest.json"] = json_bytes(manifest)
            rewrite_package(package, unsafe_id, forge_id)
            with self.assertRaisesRegex(FullLiveryPackageError, "identifier"):
                validate_full_livery_package(unsafe_id)

            incomplete = root / "incomplete.kfpslivery"
            def forge_inventory(entries):
                projection = json.loads(entries["projection/index.json"])
                projection["rendered_sections"] = [{
                    "section": "Front",
                    "path": "projection/rendered/Front.png",
                    "width": 2048,
                    "height": 1024,
                }]
                entries["projection/index.json"] = json_bytes(projection)
                refresh_manifest_hashes(entries)
            rewrite_package(package, incomplete, forge_inventory)
            with self.assertRaisesRegex(FullLiveryPackageError, "missing or unreadable"):
                validate_full_livery_package(incomplete)

    def test_legacy_package_migration_rebuilds_current_data_and_strips_embedded_mesh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = root / "legacy.kfpslivery"
            current = root / "current.kfpslivery"
            build_package(legacy)

            def make_legacy(entries):
                manifest = json.loads(entries["manifest.json"])
                manifest["compiler_revision"] = PACKAGE_COMPILER_REVISION - 1
                manifest["vehicle"]["portable_mesh"] = True
                manifest["sharing"]["external_game_assets_embedded"] = True
                vehicle = json.loads(entries["mesh/vehicle.json"])
                vehicle["portable_mesh"] = True
                entries["mesh/vehicle.json"] = json_bytes(vehicle)
                entries["mesh/model.glb"] = b"legacy-development-mesh"
                manifest["files"].append({
                    "path": "mesh/model.glb",
                    "role": "inspection-mesh",
                    "size": len(entries["mesh/model.glb"]),
                    "sha256": sha(entries["mesh/model.glb"]),
                })
                entries["manifest.json"] = json_bytes(manifest)
                refresh_manifest_hashes(entries)

            rewritten = root / "legacy-rewritten.kfpslivery"
            rewrite_package(legacy, rewritten, make_legacy)
            result = migrate_full_livery_package(rewritten, current)
            self.assertEqual(PACKAGE_COMPILER_REVISION - 1, result["migrated_from_revision"])
            validated = validate_full_livery_package(current, verify_previews=True)
            self.assertEqual(PACKAGE_COMPILER_REVISION, validated["compiler_revision"])
            with zipfile.ZipFile(current) as bundle:
                self.assertNotIn("mesh/model.glb", bundle.namelist())

    def test_current_package_migration_honors_a_distinct_output_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.kfpslivery"
            target = root / "copies" / "target.kfpslivery"
            build_package(source)
            result = migrate_full_livery_package(source, target)
            self.assertEqual(str(target.resolve()), result["package_path"])
            self.assertEqual(source.read_bytes(), target.read_bytes())
            validate_full_livery_package(target)

    def test_vehicle_index_derives_car_and_projection_contract_without_copying_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cars = root / "media" / "cars"
            cars.mkdir(parents=True)
            archive = cars / "TEST_CAR.zip"
            masks = b'''<?xml version="1.0"?><LiveryMasks><Top valid="true" xorigin="1" yorigin="2" top="-3" bottom="4" left="-5" right="6" xAxis="-z" yAxis="+x" xScale="1" yScale="1" rotation="0"/></LiveryMasks>'''
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Scene/animations/Mojo/clip/carclips_3304.clipd", b"clip")
                bundle.writestr("Scene/ProxyLOD.modelbin", b"model")
                bundle.writestr("LiveryMasks/Masks.xml", masks)
                bundle.writestr("LiveryMasks/top.swatchbin", b"swatch")

            index = load_or_build_vehicle_asset_index(root)
            self.assertEqual("TEST_CAR", index[3304].model_code)
            projection = read_projection_metadata(index[3304])
            self.assertEqual("Top", projection["sections"][0]["section"])
            self.assertEqual("-z", projection["sections"][0]["xAxis"])
            self.assertEqual(
                {"LiveryMasks/Masks.xml", "LiveryMasks/top.swatchbin"},
                {item["path"] for item in projection["source_inventory"]},
            )
            self.assertNotIn("data", projection["source_inventory"][0])

    def test_vehicle_assembly_uses_exact_locators_and_excludes_unplaced_corner_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "TEST_CAR.zip"
            locators = '''
<CarLocators Version="2">
  <Locator><Name value="carLocator_wheelLF"/><SceneTransform value._41="-1.0" value._42="0.25" value._43="1.4"/><AttachToBone BoneName="<root>"/></Locator>
  <Locator><Name value="carLocator_wheelRF"/><SceneTransform value._41="1.0" value._42="0.25" value._43="1.4"/><AttachToBone BoneName="<root>"/></Locator>
  <Locator><Name value="carLocator_wheelLR"/><SceneTransform value._41="-1.0" value._42="0.25" value._43="-1.3"/><AttachToBone BoneName="<root>"/></Locator>
  <Locator><Name value="carLocator_wheelRR"/><SceneTransform value._41="1.0" value._42="0.25" value._43="-1.3"/><AttachToBone BoneName="<root>"/></Locator>
</CarLocators>
'''.strip()
            paths = [
                "Scene/Exterior/Platform/body_a.modelbin",
                "Scene/Brakes/brakeLF_a.modelbin",
                "Scene/Wheels/wheelLF_a.modelbin",
            ]
            manifest = "<Manifest>" + "".join(
                f'<NonUpgradeablePart><Model path="game:/media/cars/TEST_CAR/{path}"/></NonUpgradeablePart>'
                for path in paths
            ) + "</Manifest>"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Locators.xml", locators)
                bundle.writestr("Manifest.xml", manifest)
                for path in paths:
                    bundle.writestr(path, b"model")
            asset = VehicleAsset(
                car_id=1,
                model_code="TEST_CAR",
                archive_path=str(archive),
                archive_name=archive.name,
                archive_size=archive.stat().st_size,
                archive_mtime_ns=archive.stat().st_mtime_ns,
                clip_entry="clip",
            )

            assembly = read_vehicle_assembly_metadata(asset)
            self.assertEqual("kfps_fh6_local_vehicle_assembly_v1", assembly["format"])
            self.assertEqual([-1.0, 0.25, 1.4], assembly["wheel_centers"]["front_left"])
            self.assertAlmostEqual(2.7, assembly["wheelbase"])
            self.assertEqual(
                ["Scene/Exterior/Platform/body_a.modelbin"],
                inspection_model_entries(asset),
            )

    def test_corrected_vehicle_assembly_uses_a_new_mesh_cache_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            asset = VehicleAsset(
                car_id=1,
                model_code="TEST_CAR",
                archive_path=str(root / "TEST_CAR.zip"),
                archive_name="TEST_CAR.zip",
                archive_size=1,
                archive_mtime_ns=1234,
                clip_entry="clip",
            )
            try:
                self.assertEqual(
                "TEST_CAR-1234.local-chassis-v10.glb",
                    service._cached_mesh_path(asset).name,
                )
            finally:
                service.close()

    def test_cancelled_mesh_future_is_a_quiet_superseded_result(self):
        future = concurrent.futures.Future()
        future.cancel()
        result = FullLiveryService._future_result("mesh", future)
        self.assertFalse(result["ok"])
        self.assertTrue(result["cancelled"])

    def test_apply_result_treats_superseded_work_as_quiet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            try:
                service._running = True
                original_status = service.status
                service._apply_result({"ok": False, "kind": "scan", "cancelled": True})
                self.assertFalse(service.running)
                self.assertEqual(original_status, service.status)
            finally:
                service.close()

    def test_selecting_a_source_immediately_unloads_the_previous_viewer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "save" / "C_livery"
            build_livery_source(source, state=0, placement_count=1)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = "C:/FH6"
            service._viewer_url = "http://127.0.0.1/previous"
            service._selected_package = "previous.kfpslivery"
            pending = concurrent.futures.Future()
            try:
                with patch.object(service._executor, "submit", return_value=pending) as submit:
                    service.selectSource(str(source))
                    service.selectSource(str(source))
                self.assertEqual("", service.viewerUrl)
                self.assertEqual("", service.selectedPackage)
                self.assertEqual(str(source.resolve()), service.selectedSource)
                submit.assert_called_once()
                pending.cancel()
            finally:
                service.close()

    def test_inspector_server_requires_its_session_token(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            build_package(package)
            static = root / "static"
            static.mkdir()
            (static / "index.html").write_text("ok", encoding="utf-8")
            server = LiveryInspectorServer(static)
            try:
                server.set_package(package)
                url = server.start()
                self.assertIn("127.0.0.1", url)
                self.assertGreater(len(url.rstrip("/").rsplit("/", 1)[-1]), 16)
            finally:
                server.close()

    def test_bundled_inspector_serves_every_javascript_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "fixture.kfpslivery"
            build_package(package)
            inspector_root = ROOT / "tools" / "livery-inspector"
            dependencies = (
                "viewer.js",
                "vendor/three/build/three.core.min.js",
                "vendor/three/build/three.module.min.js",
                "vendor/three/examples/jsm/controls/OrbitControls.js",
                "vendor/three/examples/jsm/loaders/GLTFLoader.js",
                "vendor/three/examples/jsm/utils/BufferGeometryUtils.js",
            )
            server = LiveryInspectorServer(inspector_root)
            try:
                server.set_package(package)
                url = server.start()
                for dependency in dependencies:
                    with self.subTest(dependency=dependency):
                        with urlopen(url + dependency, timeout=2) as response:
                            self.assertEqual(200, response.status)
                            self.assertIn("javascript", response.headers.get_content_type())
                            self.assertGreater(len(response.read()), 100)
            finally:
                server.close()

            index = (inspector_root / "index.html").read_text(encoding="utf-8")
            self.assertIn("__kfpsViewerBootTimer", index)
            self.assertIn("required viewer file is missing or unreadable", index)

    def test_section_projection_orientation_matches_the_fh6_mask_contract(self):
        self.assertEqual({"wing", "glass_front", "glass_back"}, TRANSPOSED_SLOTS)
        self.assertEqual({"wing", "right", "glass_front", "glass_right"}, FLIP_X_SLOTS)
        self.assertEqual({"right", "glass_back", "glass_right"}, FLIP_Y_SLOTS)

    def test_section_render_contract_uses_declared_bounds_and_independent_mask_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            artwork = {
                "Top": ((255, 0, 0, 255), "top"),
                "Left": ((0, 80, 255, 255), "left"),
            }
            with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as bundle:
                for section, (color, _) in artwork.items():
                    image = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
                    image.paste(color, (1020, 508, 1028, 516))
                    encoded = io.BytesIO()
                    image.save(encoded, format="PNG")
                    bundle.writestr(f"projection/rendered/{section}.png", encoded.getvalue())

            projection = {
                "left": "-4",
                "right": "4",
                "top": "4",
                "bottom": "-4",
                "xorigin": "0",
                "yorigin": "0",
                "xAxis": "+x",
                "yAxis": "+y",
                "xScale": "1",
                "yScale": "1",
            }
            mask = Image.new("L", (2048, 1024), 0)
            mask.paste(255, (1020, 508, 1028, 516))
            masks = {
                slot: (mask.copy(), dict(projection), hashlib.sha256(slot.encode()).hexdigest())
                for slot in ("top", "left")
            }
            asset = VehicleAsset(
                car_id=1,
                model_code="TEST_CAR",
                archive_path=str(root / "unused.zip"),
                archive_name="unused.zip",
                archive_size=123,
                archive_mtime_ns=456,
                clip_entry="clip",
            )
            output = root / "render"
            with patch("tools.livery.render_contract._archive_masks", return_value=masks):
                contract = build_local_livery_atlases(package, asset, output)

            self.assertEqual(RENDER_CONTRACT_FORMAT, contract["format"])
            sections = {row["section"]: row for row in contract["sections"]}
            self.assertEqual([1020 / 2048, 508 / 1024, 1028 / 2048, 516 / 1024], sections["Top"]["source_region"])
            self.assertEqual(64, sections["Top"]["visible_pixels"])
            self.assertEqual(64, sections["Left"]["visible_pixels"])
            self.assertEqual("left", sections["Left"]["slot"])
            self.assertEqual("left", sections["Left"]["filter"])
            self.assertEqual([1.0, 0.0, 0.0], sections["Left"]["facing"])
            self.assertNotEqual(sections["Top"]["paint_region"], sections["Left"]["paint_region"])

            page = Image.open(output / "section-masks-0.png").convert("RGBA")
            self.assertEqual((0, 0, 255, 255), page.getpixel((1024, 512)))
            paint = Image.open(output / "section-paint.png").convert("RGBA")
            for section, (color, _) in artwork.items():
                region = sections[section]["paint_region"]
                sample = (
                    int((region[0] + region[2]) * paint.width / 2),
                    int((region[1] + region[3]) * paint.height / 2),
                )
                self.assertEqual(color, paint.getpixel(sample))

    def test_portable_glb_side_contract_keeps_body_and_window_routes_together(self):
        self.assertEqual("left", SECTION_TO_SLOT["Left"])
        self.assertEqual("right", SECTION_TO_SLOT["Right"])
        self.assertEqual("glass_left", SECTION_TO_SLOT["LeftWindow"])
        self.assertEqual("glass_right", SECTION_TO_SLOT["RightWindow"])
        self.assertEqual("left", SECTION_FILTER["Left"])
        self.assertEqual("left", SECTION_FILTER["LeftWindow"])
        self.assertEqual("right", SECTION_FILTER["Right"])
        self.assertEqual("right", SECTION_FILTER["RightWindow"])
        self.assertEqual((1.0, 0.0, 0.0), SECTION_FACING["Left"])
        self.assertEqual((-1.0, 0.0, 0.0), SECTION_FACING["Right"])
        self.assertEqual((1.0, 0.0, 0.0), SECTION_FACING["LeftWindow"])
        self.assertEqual((-1.0, 0.0, 0.0), SECTION_FACING["RightWindow"])

    def test_projection_bounds_follow_masks_xml_without_inclusive_texel_growth(self):
        self.assertEqual(
            (47, 770, 990, 1019),
            _projection_pixel_bounds({
                "left": "-977",
                "right": "-34",
                "top": "-507",
                "bottom": "-258",
            }),
        )

    def test_inspector_serves_only_validated_local_render_contract_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            build_package(package)
            static = root / "static"
            static.mkdir()
            (static / "index.html").write_text("ok", encoding="utf-8")
            render = root / "render"
            render.mkdir()
            image = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
            for name in ("paint.png", "mask-0.png", "mask-1.png", "mask-2.png"):
                image.save(render / name)
            contract = {
                "format": RENDER_CONTRACT_FORMAT,
                "files": {"paint": "paint.png", "masks": ["mask-0.png", "mask-1.png", "mask-2.png"]},
                "sections": [{
                    "slot_index": 2,
                    "source_region": [0.0, 0.0, 0.5, 0.5],
                    "paint_region": [0.5, 0.5, 1.0, 1.0],
                }],
            }
            server = LiveryInspectorServer(static)
            try:
                server.set_package(package)
                server.set_local_render_contract(render, contract)
                url = server.start()
                with urlopen(url + "api/local-render/paint", timeout=2) as response:
                    self.assertEqual("image/png", response.headers.get_content_type())
                    self.assertGreater(len(response.read()), 0)

                outside = root / "outside.png"
                image.save(outside)
                unsafe = {**contract, "files": {**contract["files"], "paint": "../outside.png"}}
                with self.assertRaisesRegex(FullLiveryPackageError, "unsafe"):
                    server.set_local_render_contract(render, unsafe)

                invalid = json.loads(json.dumps(contract))
                invalid["sections"][0]["source_region"] = [float("nan"), 0.0, 0.5, 0.5]
                with self.assertRaisesRegex(FullLiveryPackageError, "outside"):
                    server.set_local_render_contract(render, invalid)
            finally:
                server.close()

    def test_received_name_collision_never_overwrites_an_existing_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_source = root / "incoming-a" / "shared.kfpslivery"
            second_source = root / "incoming-b" / "shared.kfpslivery"
            first_source.parent.mkdir()
            second_source.parent.mkdir()
            build_package(first_source, car_id=3304)
            build_package(second_source, car_id=4171)
            first_bytes = first_source.read_bytes()

            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = ""
            try:
                self.assertTrue(service.addPackage(str(first_source)))
                self.assertTrue(service.addPackage(str(second_source)))
                self.assertTrue(service.addPackage(str(first_source)))
                saved = sorted((root / "imgs" / "exported" / "full-liveries").glob("*.kfpslivery"))
                self.assertEqual(2, len(saved))
                self.assertEqual(first_bytes, (root / "imgs" / "exported" / "full-liveries" / "shared.kfpslivery").read_bytes())
                self.assertEqual({3304, 4171}, {validate_full_livery_package(path)["livery"]["target_car_id"] for path in saved})
            finally:
                service.close()

    def test_ui_package_addition_verifies_on_the_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "incoming.kfpslivery"
            build_package(source)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = ""
            try:
                service._start_add_package(str(source))
                self.assertTrue(service.running)
                deadline = time.monotonic() + 5.0
                while service.running and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(0.01)
                APP.processEvents()
                self.assertFalse(service.running)
                self.assertTrue(Path(service.selectedPackage).is_file())
                self.assertEqual("incoming.kfpslivery", Path(service.selectedPackage).name)
            finally:
                service.close()

    def test_package_switching_uses_a_fresh_inspector_session_and_survives_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.kfpslivery"
            second = root / "second.kfpslivery"
            build_package(first, car_id=3304)
            build_package(second, car_id=4171)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = ""
            try:
                self.assertTrue(service.addPackage(str(first)))
                self.assertEqual("", service.viewerUrl)
                first_url = service._inspector.start()
                first_manifest_url = first_url.split("?", 1)[0] + "api/manifest"
                with urlopen(first_manifest_url, timeout=2) as response:
                    self.assertEqual(3304, json.load(response)["livery"]["target_car_id"])

                self.assertTrue(service.addPackage(str(second)))
                self.assertEqual("", service.viewerUrl)
                second_url = service._inspector.start()
                second_manifest_url = second_url.split("?", 1)[0] + "api/manifest"
                self.assertNotEqual(first_url.split("?", 1)[0], second_url.split("?", 1)[0])
                with urlopen(second_manifest_url, timeout=2) as response:
                    self.assertEqual(4171, json.load(response)["livery"]["target_car_id"])
                with self.assertRaises(URLError):
                    urlopen(first_manifest_url, timeout=1)

                selected = service.selectedPackage
                service.refreshPackages()
                self.assertEqual(selected, service.selectedPackage)
                self.assertEqual("", service.viewerUrl)
            finally:
                service.close()

    def test_package_open_defers_the_embedded_viewer_until_local_rendering_is_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "fixture.kfpslivery"
            build_package(package, car_id=3304)
            paths = AppPaths(
                app_root=root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=root / "runtime",
                bundled_python=root / "python" / "python.exe",
            )
            service = FullLiveryService(paths, LogService(), supporter=None, demo=True)
            service._game_folder = "C:/FH6"
            try:
                with patch.object(service, "_prepare_local_mesh") as prepare:
                    service._open_package(str(package), remember=False)

                self.assertEqual(str(package.resolve()), service.selectedPackage)
                self.assertEqual("", service.viewerUrl)
                self.assertEqual("", service._inspector.url)
                prepare.assert_called_once()
            finally:
                service.close()

    def test_livery_page_qualifies_package_and_source_paths(self):
        source = (UI / "qml" / "pages" / "LiveryPage.qml").read_text(encoding="utf-8")
        self.assertIn("selectPackage(packageDelegate.path)", source)
        self.assertIn("selectSource(sourceDelegate.path)", source)
        self.assertIn("Game meshes stay local", source)
        self.assertNotIn("portable inspection mesh", source)

    def test_livery_page_places_clear_cache_between_save_and_scan(self):
        source = (UI / "qml" / "pages" / "LiveryPage.qml").read_text(encoding="utf-8")
        save = source.index('text: "Save Folder"')
        clear = source.index('text: "Clear Cache"')
        scan = source.index('"Scan Saves"')
        self.assertLess(save, clear)
        self.assertLess(clear, scan)
        self.assertIn("fullLiveryService.clearFullLiveryCache()", source)

    def test_livery_page_and_service_expose_only_the_fh6_package_policy(self):
        page = (UI / "qml" / "pages" / "LiveryPage.qml").read_text(encoding="utf-8")
        service = (UI / "src" / "kfps_ui" / "full_livery_service.py").read_text(encoding="utf-8")

        self.assertIn('text: "FH6 package policy"', page)
        self.assertNotIn("targetGames", page)
        self.assertNotIn("setTargetGame", page)
        self.assertNotIn('label: "FH5"', page)
        self.assertNotIn('label: "FH4"', page)
        self.assertNotIn('label: "FM8"', page)
        self.assertNotIn("def setTargetGame", service)
        self.assertNotIn("def targetGame", service)
        self.assertNotIn("_target_game", service)
        self.assertIn('compatibility_decision(self._current_manifest, "fh6")', service)

    def test_inspector_uses_independent_section_masks_and_direct_fh6_uv3(self):
        source = (ROOT / "tools" / "livery-inspector" / "viewer.js").read_text(encoding="utf-8")
        self.assertIn("attribute vec2 uv3", source)
        self.assertIn("uv3.x * 0.5", source)
        self.assertIn("maskMap0", source)
        self.assertIn("maskMap1", source)
        self.assertIn("maskMap2", source)
        self.assertIn("slotCoverage", source)
        self.assertIn("dot(sideFacing[slot], normalValue)", source)
        self.assertIn("decal.a *= bestCoverage", source)
        self.assertIn("renderContract.assembly", source)
        self.assertIn("new THREE.TorusGeometry", source)
        self.assertIn("mesh.userData?.kfps_role", source)
        self.assertLess(source.index("identity.includes('glassflivery')"), source.index("identity.includes('carpaint')"))
        self.assertNotIn("projection/vehicle-map.json", source)
        self.assertNotIn("sourceSilhouetteBounds", source)

    def test_inspector_releases_webgl_resources_between_livery_sessions(self):
        source = (ROOT / "tools" / "livery-inspector" / "viewer.js").read_text(encoding="utf-8")
        page = (UI / "qml" / "pages" / "LiveryPage.qml").read_text(encoding="utf-8")
        for contract in (
            "cancelAnimationFrame(animationFrameId)",
            "controls.dispose()",
            "geometry.dispose()",
            "material.dispose()",
            "texture.dispose()",
            "renderer.renderLists.dispose()",
            "renderer.dispose()",
            "renderer.forceContextLoss()",
            "window.addEventListener('pagehide', disposeViewer)",
            "document.addEventListener('visibilitychange', handleVisibilityChange)",
            "window.__kfpsViewerDiagnostics = viewerDiagnostics",
            "Promise.allSettled",
        ):
            self.assertIn(contract, source)
        self.assertIn("if (controls.autoRotate) requestRender()", source)
        self.assertNotIn("function animate()", source)
        self.assertNotIn("requestAnimationFrame(animate)", source)
        self.assertIn('active: root.pageActive && fullLiveryService.viewerUrl.length > 0', page)
        self.assertIn('sourceComponent: Component', page)
        self.assertNotIn(': "about:blank"', page)


if __name__ == "__main__":
    unittest.main()
