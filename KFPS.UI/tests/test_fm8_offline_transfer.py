from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.app_paths import AppPaths  # noqa: E402
from kfps_ui.cgroup_library_service import CGroupLibraryService  # noqa: E402
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload  # noqa: E402
from tools.cgroup.fm8_ownership import (  # noqa: E402
    assess_fm8_layer_group,
    assess_fm8_layer_group_files,
    parse_fm8_header,
)
from tools.cgroup.forza_source_decoder import decode_forza_source  # noqa: E402
from tools.cgroup.shape_identity import normalize_game_shape_word  # noqa: E402


def fm8_header(
    *,
    title: str = "Fixture",
    description: str = "Description",
    creator: str = "LocalUser",
    catalog_state: int = 0,
    asset_id: uuid.UUID | None = None,
    layer_count: int = 1,
) -> bytes:
    output = bytearray(struct.pack("<I", 9))
    for value in (title, description):
        encoded = value.encode("utf-16le")
        output.extend(struct.pack("<I", len(encoded) // 2))
        output.extend(encoded)
    output.extend(struct.pack("<8HIQ", 2026, 9, 5, 18, 12, 30, 0, 0, 2, 123456789))
    encoded = creator.encode("utf-16le")
    output.extend(struct.pack("<I", len(encoded) // 2))
    output.extend(encoded)
    output.extend(struct.pack("<I", catalog_state))
    asset_id = asset_id or uuid.UUID("11111111-2222-4333-8444-555555555555")
    output.extend(bytes(8) + asset_id.bytes_le)
    output.extend(b"\x01\x02\x00\x00\x00" + b"\xff" * 8)
    output.extend(struct.pack("<I", layer_count) + asset_id.bytes_le)
    return bytes(output)


def fm8_payload(*, restricted: bool = False) -> bytes:
    payload = bytearray(
        build_flat_payload(
            [CGroupLayer(0x0066, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, (255, 255, 255, 255))]
        )
    )
    if restricted:
        payload[0x1D] = 0x21
    return bytes(payload)


def fm8_legacy_import_payload() -> bytes:
    payload = build_flat_payload(
        [
            CGroupLayer(0x0065, -10.0, 20.0, 3.0, 4.0, 5.0, 0.0, (12, 34, 56, 255)),
            CGroupLayer(0x0066, 30.0, -40.0, 5.0, 6.0, 7.0, 0.0, (78, 90, 123, 255)),
            CGroupLayer(0x0202, 50.0, 60.0, 2.0, 3.0, 9.0, 0.0, (45, 67, 89, 255)),
        ]
    )
    first_shape = 0x24 + payload[0x20]
    records = [
        b"\x01" + payload[first_shape + 1 : first_shape + 31],
        b"\x01" + payload[first_shape + 33 : first_shape + 63],
        b"\x01" + payload[first_shape + 65 : first_shape + 95],
    ]
    return payload[:first_shape] + b"".join(records) + payload[first_shape + 95 :]


def write_group(
    root: Path,
    name: str,
    *,
    creator: str = "LocalUser",
    catalog_state: int = 0,
    restricted: bool = False,
    legacy_import: bool = False,
) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    try:
        asset_id = uuid.UUID(name)
    except ValueError:
        asset_id = None
    (folder / "header").write_bytes(
        fm8_header(title=name, creator=creator, catalog_state=catalog_state, asset_id=asset_id)
    )
    payload = fm8_legacy_import_payload() if legacy_import else fm8_payload(restricted=restricted)
    if restricted and legacy_import:
        payload = bytearray(payload)
        payload[0x1D] = 0x21
        payload = bytes(payload)
    (folder / "data").write_bytes(payload)
    return folder


class FM8OfflineTransferTests(unittest.TestCase):
    def test_rescan_corrects_existing_community_json_without_source_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            app_root = Path(temp)
            groups = app_root / "LayerGroups"
            folder = write_group(groups, "community-fixture")
            (folder / "data").write_bytes(build_flat_payload([
                CGroupLayer(2103, 0, 0, 1, 1, 0, 0, (255, 255, 255, 255)),
            ]))
            before = {path.name: path.read_bytes() for path in folder.iterdir()}
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets",
                             app_root / "runtime", Path(sys.executable))
            service = CGroupLibraryService(paths, None, None, None)
            self.addCleanup(service.close)

            def legacy_mapping(word, game):
                result = normalize_game_shape_word(word, game)
                if result and word == 2103:
                    result.update(canonical_word=2101, canonical_type=0x100000 + 2101,
                                  resource_index=1)
                return result

            with patch.object(service, "_default_save_roots", return_value=[groups]), patch.object(
                service, "_discover_save_artifacts", return_value=[folder / "data"]
            ), patch.object(service, "_save_cached_roots"), patch.object(service, "_write_preview") as preview:
                with patch("tools.cgroup.forza_source_decoder.normalize_game_shape_word", side_effect=legacy_mapping):
                    initial = service._scan_work("fm8")
                output = Path(initial["outputs"][0])
                self.assertEqual(2101, json.loads(output.read_text())["shapes"][0]["type_word"])

                refreshed = service._scan_work("fm8")

            self.assertEqual(initial["outputs"], refreshed["outputs"])
            corrected = json.loads(output.read_text())["shapes"][0]
            self.assertEqual(2103, corrected["type_word"])
            self.assertEqual(2103, corrected["source_raw_type_word"])
            self.assertEqual(3, corrected["resource_index"])
            self.assertEqual(2, preview.call_count)
            self.assertEqual(before, {path.name: path.read_bytes() for path in folder.iterdir()})

    def test_legacy_import_shape_records_decode_only_for_fm8(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "data"
            source.write_bytes(fm8_legacy_import_payload())

            decoded = decode_forza_source(source, allow_locked=False, game="fm8")
            wrong_game = decode_forza_source(source, allow_locked=False, game="fh6")

            self.assertEqual(3, len(decoded.layers))
            self.assertEqual(3, decoded.report["fm8_legacy_shape_records"])
            self.assertEqual(0, len(wrong_game.layers))
            self.assertEqual([12, 34, 56, 255], decoded.layers[0]["color"])
            self.assertEqual(0x0202, decoded.layers[2]["source_raw_type_word"])

    def test_header_parser_handles_variable_text_lengths(self):
        parsed = parse_fm8_header(
            fm8_header(
                title="A longer title",
                description="Short",
                creator="ProfileName",
                catalog_state=1,
            )
        )
        self.assertEqual(9, parsed.version)
        self.assertEqual("A longer title", parsed.title)
        self.assertEqual("Short", parsed.description)
        self.assertEqual("ProfileName", parsed.creator)
        self.assertEqual(1, parsed.catalog_state)

    def test_offline_ownership_requires_clear_header_and_payload(self):
        owned = assess_fm8_layer_group(fm8_header(), fm8_payload())
        downloaded = assess_fm8_layer_group(fm8_header(catalog_state=1), fm8_payload())
        resaved_foreign = assess_fm8_layer_group(fm8_header(), fm8_payload(restricted=True))
        unknown_header = assess_fm8_layer_group(b"short", fm8_payload())
        unknown_payload = assess_fm8_layer_group(fm8_header(), b"short")

        self.assertTrue(owned.allowed)
        self.assertEqual("clear", owned.status)
        self.assertFalse(downloaded.allowed)
        self.assertEqual("restricted", downloaded.status)
        self.assertFalse(resaved_foreign.allowed)
        self.assertEqual("restricted", resaved_foreign.status)
        self.assertEqual("unknown", unknown_header.status)
        self.assertEqual("unknown", unknown_payload.status)

    def test_latest_template_skips_newer_non_owned_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "LayerGroups"
            root.mkdir()
            safe = write_group(root, str(uuid.uuid4()))
            unsafe = write_group(root, str(uuid.uuid4()), restricted=True)
            os.utime(safe / "data", (100, 100))
            os.utime(unsafe / "data", (200, 200))
            fake_service = SimpleNamespace(
                _fm8_layer_groups_root=lambda: root,
                _targeted_fm8_layer_groups=CGroupLibraryService._targeted_fm8_layer_groups,
            )

            selected = CGroupLibraryService._latest_fm8_layer_group(fake_service)

            self.assertEqual(safe, selected)

    def test_scan_does_not_require_or_filter_by_creator_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            app_root = Path(temp)
            groups = app_root / "LayerGroups"
            groups.mkdir()
            first = write_group(groups, "first", creator="LocalUser")
            second = write_group(groups, "second", creator="AnotherLocalName")
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CGroupLibraryService(
                paths,
                SimpleNamespace(preview_for_json=lambda *_args: None),
                object(),
                SimpleNamespace(append=lambda *_args, **_kwargs: None),
            )
            self.addCleanup(service.close)
            library = app_root / "imgs" / "library"
            with patch.object(service, "_default_save_roots", return_value=[groups]), patch.object(
                service,
                "_discover_save_artifacts",
                return_value=[first / "data", second / "data"],
            ), patch.object(service, "_save_cached_roots"), patch.object(
                service,
                "_library_root",
                return_value=library,
            ), patch.object(service, "_flatten_legacy_game_library_roots"), patch.object(
                service,
                "_prune_non_layergroup_library_entries",
            ), patch.object(service, "_write_preview"), patch.object(
                service,
                "_load_creator_profile",
                side_effect=AssertionError("FM8 scanning must not request a creator profile"),
            ):
                result = service._scan_work("fm8")

            self.assertEqual(2, result["exported"])
            creators = {
                json.loads(Path(output).read_text(encoding="utf-8"))["metadata"]["creator"]
                for output in result["outputs"]
            }
            self.assertEqual({"LocalUser", "AnotherLocalName"}, creators)

    def test_scan_exports_only_verified_local_groups(self):
        with tempfile.TemporaryDirectory() as temp:
            app_root = Path(temp)
            groups = app_root / "LayerGroups"
            groups.mkdir()
            safe = write_group(groups, "safe")
            safe_legacy = write_group(groups, "safe-legacy", legacy_import=True)
            downloaded = write_group(groups, "downloaded", catalog_state=1)
            resaved = write_group(groups, "resaved", restricted=True)
            downloaded_legacy = write_group(
                groups,
                "downloaded-legacy",
                catalog_state=1,
                legacy_import=True,
            )
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CGroupLibraryService(
                paths,
                SimpleNamespace(preview_for_json=lambda *_args: None),
                object(),
                SimpleNamespace(append=lambda *_args, **_kwargs: None),
            )
            self.addCleanup(service.close)
            library = app_root / "imgs" / "library"
            with patch.object(service, "_default_save_roots", return_value=[groups]), patch.object(
                service,
                "_discover_save_artifacts",
                return_value=[
                    safe / "data",
                    safe_legacy / "data",
                    downloaded / "data",
                    resaved / "data",
                    downloaded_legacy / "data",
                ],
            ), patch.object(service, "_save_cached_roots"), patch.object(
                service,
                "_library_root",
                return_value=library,
            ), patch.object(service, "_flatten_legacy_game_library_roots"), patch.object(
                service,
                "_prune_non_layergroup_library_entries",
            ), patch.object(service, "_write_preview"):
                result = service._scan_work("fm8")

            self.assertEqual(2, result["exported"])
            self.assertEqual(3, result["ignored_restricted_fm8"])
            self.assertEqual(3, result["skipped"])
            self.assertEqual(2, len(result["outputs"]))
            self.assertEqual(3, result["fm8_legacy_shape_records"])
            payloads = [
                json.loads(Path(output).read_text(encoding="utf-8"))
                for output in result["outputs"]
            ]
            self.assertTrue(all(payload["metadata"]["ownership_verified"] for payload in payloads))
            self.assertEqual([1, 3], sorted(len(payload["shapes"]) for payload in payloads))

    def test_created_group_is_reopened_and_ownership_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "LayerGroups"
            root.mkdir()
            source_group = write_group(root, str(uuid.uuid4()))
            source_json = Path(temp) / "Offline Test.json"
            source_json.write_text(
                json.dumps(
                    {
                        "name": "Offline Test",
                        "shapes": [
                            {"type": 8, "data": [0, 0, 100, 100, 0], "color": [255, 255, 255, 255]}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fake_service = SimpleNamespace(
                _fm8_layer_groups_root=lambda: root,
                _latest_fm8_layer_group=lambda: source_group,
                _check_fm8_import_ready=lambda: None,
                _title_for_install_json=CGroupLibraryService._title_for_install_json,
                _atomic_write_bytes=CGroupLibraryService._atomic_write_bytes,
                _rename_header=CGroupLibraryService._rename_header,
                _build_draft_header=CGroupLibraryService._build_draft_header,
                _write_save_thumb=lambda *_args: False,
            )

            result = CGroupLibraryService._create_fm8_layer_group_install_work(fake_service, source_json)

            created = [folder for folder in root.iterdir() if folder.is_dir() and folder != source_group]
            self.assertEqual(1, len(created))
            self.assertTrue(assess_fm8_layer_group_files(created[0] / "data").allowed)
            decoded = decode_forza_source(created[0] / "data", allow_locked=False, game="fm8")
            self.assertEqual(1, len(decoded.layers))
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
