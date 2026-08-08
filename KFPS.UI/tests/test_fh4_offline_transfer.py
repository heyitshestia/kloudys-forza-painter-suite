from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, wrap_payload
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.xbox_wgs import (
    WgsConcurrentChangeError,
    WgsFolderEntry,
    WgsFormatError,
    WgsIndex,
    create_wgs_layer_group,
    datetime_to_filetime,
    find_wgs_slots,
    parse_wgs_file_list,
    read_wgs_index,
    read_wgs_layer_groups,
    serialize_wgs_file_list,
    serialize_wgs_index,
)


def png_bytes(color=(255, 0, 255, 255)) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (32, 32), color).save(output, "PNG")
    return output.getvalue()


def build_wgs_fixture(root: Path, *, layer_count: int = 1) -> tuple[Path, Path, bytes]:
    wgs = root / "Microsoft.SunriseBaseGame_8wekyb3d8bbwe" / "SystemAppData" / "wgs"
    slot = wgs / "000901F000000001_000000000000000000000000765B6743"
    slot.mkdir(parents=True)
    folder_guid = uuid.UUID("11111111-2222-4333-8444-555555555555")
    cgroup_guid = uuid.UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
    header_guid = uuid.UUID("12345678-1234-4234-9234-1234567890ab")
    thumb_guid = uuid.UUID("87654321-4321-4321-8321-ba0987654321")
    folder = slot / folder_guid.hex.upper()
    folder.mkdir()

    payload = build_flat_payload(
        [
            CGroupLayer(
                0x0066,
                float(index),
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                (255, 255, 255, 255),
            )
            for index in range(layer_count)
        ]
    )
    cgroup_data = wrap_payload(payload)
    header_data = CGroupLibraryService._build_draft_header("Fixture Vinyl")
    thumbnail_data = png_bytes()
    (folder / cgroup_guid.hex.upper()).write_bytes(cgroup_data)
    (folder / header_guid.hex.upper()).write_bytes(header_data)
    (folder / thumb_guid.hex.upper()).write_bytes(thumbnail_data)
    file_list = serialize_wgs_file_list(
        3,
        (
            ("C_group", cgroup_guid, cgroup_guid),
            ("header", header_guid, header_guid),
            ("thumb.png", thumb_guid, thumb_guid),
        ),
    )
    (folder / "container.3").write_bytes(file_list)

    now = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
    folder_entry = WgsFolderEntry(
        name="LayerGroup_0000_20260808140000",
        repeated_name="LayerGroup_0000_20260808140000",
        cloud_id='"0x8DEF00000000000"',
        sequence=3,
        flags=1,
        folder_guid=folder_guid,
        modified_filetime=datetime_to_filetime(now),
        unknown=0,
        size=len(cgroup_data) + len(header_data) + len(thumbnail_data),
    )
    index = WgsIndex(
        version=0x0E,
        flag1=0,
        package_name="Microsoft.SunriseBaseGame_8wekyb3d8bbwe!SunriseReleaseFinal",
        modified_filetime=datetime_to_filetime(now),
        flag2=0,
        index_guid="00000000-1111-4222-8333-444444444444",
        unknown=0,
        folders=(folder_entry,),
    )
    index_bytes = serialize_wgs_index(index)
    (slot / "containers.index").write_bytes(index_bytes)
    return wgs, slot, index_bytes


class Fh4OfflineTransferTests(unittest.TestCase):
    def test_wgs_metadata_round_trips_and_resolves_logical_files(self):
        with tempfile.TemporaryDirectory() as temp:
            wgs, slot, index_bytes = build_wgs_fixture(Path(temp))

            self.assertEqual([slot], find_wgs_slots([wgs]))
            index = read_wgs_index(slot)
            self.assertEqual(index_bytes, serialize_wgs_index(index))
            groups = read_wgs_layer_groups(slot)
            self.assertEqual(1, len(groups))
            group = groups[0]
            self.assertEqual("Fixture Vinyl", CGroupLibraryService._read_layer_group_metadata(group.cgroup_path)["title"])
            parsed_files = parse_wgs_file_list(group.file_list.path)
            self.assertEqual(
                group.file_list.path.read_bytes(),
                serialize_wgs_file_list(
                    parsed_files.sequence,
                    ((entry.name, entry.primary_guid, entry.secondary_guid) for entry in parsed_files.entries),
                ),
            )

    def test_fh4_discovery_decodes_opaque_wgs_cgroup(self):
        with tempfile.TemporaryDirectory() as temp:
            wgs, _slot, _index_bytes = build_wgs_fixture(Path(temp), layer_count=9)

            found = CGroupLibraryService._discover_save_artifacts([wgs], "fh4")

            self.assertEqual(1, len(found))
            decoded = decode_forza_source(found[0], game="fh4")
            self.assertEqual(9, len(decoded.layers))
            self.assertEqual("fh4", decoded.report["target_game"])

    def test_offline_import_creates_separate_verified_group_and_full_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            wgs, slot, original_index = build_wgs_fixture(base)
            original_group = read_wgs_layer_groups(slot)[0]
            original_cgroup = original_group.cgroup_path.read_bytes()
            runtime = base / "runtime"
            source = base / "offline-test.json"
            source.write_text(
                json.dumps(
                    {
                        "metadata": {"title": "Offline Test"},
                        "shapes": [
                            {
                                "type": 0x100000 + 101,
                                "type_word": 101,
                                "data": [10.0, 20.0, 1.5, 0.75, 15.0, 0.0, 0],
                                "color": [255, 0, 0, 255],
                            },
                            {
                                "type": 0x100000 + 123,
                                "type_word": 123,
                                "data": [-5.0, 7.0, 2.0, 1.0, 45.0, 0.2, 0],
                                "color": [0, 128, 255, 255],
                            },
                            {
                                "type": 0x100000 + 117,
                                "type_word": 117,
                                "resource_family": "Primitives",
                                "resource_index": 5,
                                "source_game": "fh4",
                                "data": [1.0, 2.0, 0.5, 0.75, 90.0, 0.0, 0],
                                "color": [10, 20, 30, 255],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            cached_roots: list[tuple[list[Path], str]] = []
            fake_service = SimpleNamespace(
                _game_process_running=lambda _name: False,
                _default_save_roots=lambda _game: [wgs],
                _title_for_install_json=CGroupLibraryService._title_for_install_json,
                _rename_header=CGroupLibraryService._rename_header,
                _build_draft_header=CGroupLibraryService._build_draft_header,
                _render_save_thumb_bytes=lambda _path, _format: png_bytes((20, 40, 60, 255)),
                _save_cached_roots=lambda roots, game: cached_roots.append((roots, game)),
                paths=SimpleNamespace(runtime_root=runtime),
            )

            result = CGroupLibraryService._create_fh4_layer_group_install_work(fake_service, source)

            self.assertTrue(result["ok"])
            self.assertEqual("fh4", result["game"])
            self.assertEqual(2, len(read_wgs_index(slot).folders))
            groups = read_wgs_layer_groups(slot)
            self.assertEqual(2, len(groups))
            imported = next(group for group in groups if group.folder.folder_guid != original_group.folder.folder_guid)
            decoded = decode_forza_source(imported.cgroup_path, game="fh4")
            self.assertEqual([101, 123, 117], [shape["type_word"] for shape in decoded.layers])
            self.assertEqual("Offline Test", CGroupLibraryService._read_layer_group_metadata(imported.cgroup_path)["title"])
            self.assertTrue(imported.thumbnail_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(original_cgroup, original_group.cgroup_path.read_bytes())
            backups = list((runtime / "fh4-offline-import-backups").iterdir())
            self.assertEqual(1, len(backups))
            self.assertEqual(original_index, (backups[0] / "containers.index").read_bytes())
            self.assertEqual([([slot.parent], "fh4")], cached_roots)

    def test_offline_import_refuses_to_write_while_fh4_is_running(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            wgs, slot, original_index = build_wgs_fixture(base)
            source = base / "blocked.json"
            source.write_text(json.dumps({"shapes": []}), encoding="utf-8")
            fake_service = SimpleNamespace(
                _game_process_running=lambda _name: True,
                _default_save_roots=lambda _game: [wgs],
                paths=SimpleNamespace(runtime_root=base / "runtime"),
            )

            with self.assertRaisesRegex(ValueError, "Close FH4 completely"):
                CGroupLibraryService._create_fh4_layer_group_install_work(fake_service, source)

            self.assertEqual(original_index, (slot / "containers.index").read_bytes())
            self.assertEqual(1, len(read_wgs_layer_groups(slot)))
            self.assertFalse((base / "runtime").exists())

    def test_offline_import_round_trips_3000_native_shapes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            wgs, slot, _original_index = build_wgs_fixture(base)
            source = base / "three-thousand-native-shapes.json"
            shape_words = (101, 102, 117, 123, 2103)
            source.write_text(
                json.dumps(
                    {
                        "metadata": {"title": "3000 Native Shapes"},
                        "shapes": [
                            {
                                "type": 0x100000 + shape_words[index % len(shape_words)],
                                "type_word": shape_words[index % len(shape_words)],
                                "data": [
                                    float((index % 100) - 50),
                                    float((index // 100) - 15),
                                    0.25 + (index % 7) * 0.1,
                                    0.25 + (index % 5) * 0.1,
                                    float(index % 360),
                                    0.0,
                                    0,
                                ],
                                "color": [index % 256, (index * 3) % 256, (index * 7) % 256, 255],
                            }
                            for index in range(3000)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fake_service = SimpleNamespace(
                _game_process_running=lambda _name: False,
                _default_save_roots=lambda _game: [wgs],
                _title_for_install_json=CGroupLibraryService._title_for_install_json,
                _rename_header=CGroupLibraryService._rename_header,
                _build_draft_header=CGroupLibraryService._build_draft_header,
                _render_save_thumb_bytes=lambda _path, _format: png_bytes(),
                _save_cached_roots=lambda _roots, _game: None,
                paths=SimpleNamespace(runtime_root=base / "runtime"),
            )

            result = CGroupLibraryService._create_fh4_layer_group_install_work(fake_service, source)

            self.assertTrue(result["ok"])
            imported = read_wgs_layer_groups(slot)[0]
            decoded = decode_forza_source(imported.cgroup_path, game="fh4")
            self.assertEqual(3000, len(decoded.layers))
            self.assertEqual(
                set(shape_words),
                {int(shape["type_word"]) for shape in decoded.layers},
            )

    def test_wgs_writer_aborts_if_save_changes_during_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            _wgs, slot, original_index = build_wgs_fixture(base)
            template = read_wgs_layer_groups(slot)[0]
            header_data = template.header_path.read_bytes()
            thumb_data = template.thumbnail_path.read_bytes()
            cgroup_data = template.cgroup_path.read_bytes()

            with patch(
                "tools.cgroup.xbox_wgs._slot_snapshot",
                side_effect=[{"before": (1, "a")}, {"after": (1, "b")}],
            ):
                with self.assertRaises(WgsConcurrentChangeError):
                    create_wgs_layer_group(
                        slot,
                        template,
                        cgroup_data=cgroup_data,
                        header_data=header_data,
                        thumbnail_data=thumb_data,
                        backup_root=base / "backups",
                    )

            self.assertEqual(original_index, (slot / "containers.index").read_bytes())
            self.assertEqual(1, len(read_wgs_layer_groups(slot)))

    def test_wgs_writer_rolls_back_a_failed_post_commit_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            _wgs, slot, original_index = build_wgs_fixture(base)
            template = read_wgs_layer_groups(slot)[0]
            original_folders = {item.name for item in slot.iterdir() if item.is_dir()}

            with patch(
                "tools.cgroup.xbox_wgs.read_wgs_layer_groups",
                side_effect=WgsFormatError("forced verification failure"),
            ):
                with self.assertRaisesRegex(WgsFormatError, "forced verification failure"):
                    create_wgs_layer_group(
                        slot,
                        template,
                        cgroup_data=template.cgroup_path.read_bytes(),
                        header_data=template.header_path.read_bytes(),
                        thumbnail_data=template.thumbnail_path.read_bytes(),
                        backup_root=base / "backups",
                    )

            self.assertEqual(original_index, (slot / "containers.index").read_bytes())
            self.assertEqual(original_folders, {item.name for item in slot.iterdir() if item.is_dir()})
            self.assertEqual(1, len(read_wgs_layer_groups(slot)))


if __name__ == "__main__":
    unittest.main()
