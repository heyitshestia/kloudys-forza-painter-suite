from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
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


def fm8_header(
    *,
    title: str = "Fixture",
    description: str = "Description",
    creator: str = "LocalUser",
    catalog_state: int = 0,
) -> bytes:
    output = bytearray(struct.pack("<I", 9))
    for value in (title, description):
        output.extend(struct.pack("<I", len(value)))
        output.extend(value.encode("utf-16le"))
    output.extend(bytes(28))
    output.extend(struct.pack("<I", len(creator)))
    output.extend(creator.encode("utf-16le"))
    output.extend(struct.pack("<I", catalog_state))
    output.extend(bytes(48))
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


def write_group(
    root: Path,
    name: str,
    *,
    creator: str = "LocalUser",
    catalog_state: int = 0,
    restricted: bool = False,
) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "header").write_bytes(
        fm8_header(title=name, creator=creator, catalog_state=catalog_state)
    )
    (folder / "data").write_bytes(fm8_payload(restricted=restricted))
    return folder


class FM8OfflineTransferTests(unittest.TestCase):
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
            safe = write_group(root, "safe")
            unsafe = write_group(root, "unsafe", restricted=True)
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
            downloaded = write_group(groups, "downloaded", catalog_state=1)
            resaved = write_group(groups, "resaved", restricted=True)
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
                return_value=[safe / "data", downloaded / "data", resaved / "data"],
            ), patch.object(service, "_save_cached_roots"), patch.object(
                service,
                "_library_root",
                return_value=library,
            ), patch.object(service, "_flatten_legacy_game_library_roots"), patch.object(
                service,
                "_prune_non_layergroup_library_entries",
            ), patch.object(service, "_write_preview"):
                result = service._scan_work("fm8")

            self.assertEqual(1, result["exported"])
            self.assertEqual(2, result["ignored_restricted_fm8"])
            self.assertEqual(2, result["skipped"])
            self.assertEqual(1, len(result["outputs"]))
            payload = json.loads(Path(result["outputs"][0]).read_text(encoding="utf-8"))
            self.assertTrue(payload["metadata"]["ownership_verified"])

    def test_created_group_is_reopened_and_ownership_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "LayerGroups"
            root.mkdir()
            source_group = write_group(root, "source")
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
