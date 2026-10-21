from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.vinyl_document import encode_vinyl_document
from tools.cgroup.xbox_wgs import read_wgs_layer_groups
from test_fh4_offline_transfer import build_wgs_fixture, png_bytes
from test_fh5_offline_transfer import fixture as fh5_fixture, png_bytes as fh5_png
from test_fh6_offline_identity import make_account, snapshot
from test_fm8_offline_transfer import write_group
from test_offline_native_framing import read_native_tree
from tools.cgroup.cgroup_codec import unwrap_payload


class GroupedOfflineServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.document = {"shapes": [
            {"type": 1048677, "type_word": 101,
             "data": [i * 4, -i, -1.2, 0.6, 17 * i, 0.12, int(i == 2)],
             "color": [20, 70, 120, 0 if i == 2 else 210], "mask": i == 2,
             "editor_group_path": [{"id": "outer", "name": "Outer"},
                                   {"id": f"part-{i // 3}", "name": f"Part {i // 3}"}]}
            for i in range(6)]}
        self.source = self.root / "grouped.json"
        self.source.write_text(json.dumps(self.document), encoding="utf-8")

    def check_decoded(self, path, game):
        raw = path.read_bytes()
        read_native_tree(raw if raw.startswith(b"gyvl") else unwrap_payload(raw))
        decoded = decode_forza_source(path, allow_locked=False, game=game)
        self.assertEqual(6, len(decoded.layers))
        self.assertFalse(decoded.report["warnings"])
        self.assertGreaterEqual(decoded.report["group_nodes"], 3)
        self.assertTrue(all(layer.get("editor_group_path") for layer in decoded.layers))
        self.assertTrue(decoded.layers[2]["mask"])
        self.assertEqual(0, decoded.layers[2]["color"][3])
        encode_vinyl_document({"shapes": decoded.layers}, game)
        return decoded

    def service(self):
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        service = CGroupLibraryService(paths, None, None, SimpleNamespace(append=Mock()))
        self.addCleanup(service.close)
        return service

    def test_fh5_public_action_uses_selected_account_and_real_thumbnail_renderer(self):
        slot, descriptor = fh5_fixture(self.root / "selected")
        other_slot, _ = fh5_fixture(self.root / "other", owner=12345)
        before, other_before = snapshot(slot), snapshot(other_slot)
        service = self.service()
        with patch("kfps_ui.cgroup_library_service.QMessageBox.question", return_value=QMessageBox.Yes), patch(
            "kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=(str(descriptor), "")
        ), patch.object(service, "_game_process_running", return_value=False), patch.object(
            service, "_default_save_roots", side_effect=AssertionError("Never choose another account")
        ):
            service.createLayerGroupFromSelectedJson(str(self.source), "fh5")
            deadline = time.monotonic() + 30
            while service.running and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
        self.assertFalse(service.running)
        self.assertEqual("Complete", service.status, service.summary)
        created, = [group for group in read_wgs_layer_groups(slot) if group.file_list.path != descriptor]
        self.check_decoded(created.cgroup_path, "fh5")
        self.assertEqual(other_before, snapshot(other_slot))
        for name, content in before.items():
            if name != "containers.index":
                self.assertEqual(content, (slot / name).read_bytes())
        self.assertIn("cannot confirm", service.summary)
        self.assertIn("Test", service.offlineImportLabel("fh5"))

    def test_fh5_declining_confirmation_or_picker_starts_no_worker(self):
        slot, _ = fh5_fixture(self.root)
        before = snapshot(slot)
        service = self.service()
        for answer in (QMessageBox.No, QMessageBox.Yes):
            with patch("kfps_ui.cgroup_library_service.QMessageBox.question", return_value=answer), patch(
                "kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=("", "")
            ) as picker:
                service.createLayerGroupFromSelectedJson(str(self.source), "fh5")
            self.assertEqual(answer == QMessageBox.Yes, picker.called)
            self.assertIsNone(service._future)
            self.assertFalse(service.running)
            self.assertEqual(before, snapshot(slot))

    def test_fh5_unsupported_destination_running_game_and_failed_thumbnail_do_not_write(self):
        slot, descriptor = fh5_fixture(self.root)
        before = snapshot(slot)
        service = self.service()
        with patch.object(service, "_game_process_running", return_value=True):
            with self.assertRaisesRegex(ValueError, "Close FH5"):
                service._create_fh5_layer_group_install_work(self.source, descriptor)
        with patch.object(service, "_game_process_running", return_value=False):
            with self.assertRaisesRegex(ValueError, "Select your FH5"):
                service._create_fh5_layer_group_install_work(self.source)
            with self.assertRaises(ValueError):
                service._create_fh5_layer_group_install_work(self.source, self.source)
            with patch.object(service, "_render_save_thumb_bytes", return_value=None):
                with self.assertRaisesRegex(ValueError, "thumbnail"):
                    service._create_fh5_layer_group_install_work(self.source, descriptor)
        self.assertEqual(before, snapshot(slot))

    def test_fh5_game_starting_during_preparation_prevents_commit(self):
        slot, descriptor = fh5_fixture(self.root)
        before = snapshot(slot)
        service = self.service()
        with patch.object(service, "_game_process_running", side_effect=[False, True]), patch.object(
            service, "_render_save_thumb_bytes", return_value=fh5_png()
        ):
            with self.assertRaisesRegex(ValueError, "Close FH5"):
                service._create_fh5_layer_group_install_work(self.source, descriptor)
        self.assertEqual(before, snapshot(slot))

    def test_fh4_semantic_readback_failure_rolls_back_inside_transaction(self):
        wgs, slot, _ = build_wgs_fixture(self.root)
        original = read_wgs_layer_groups(slot)[0].cgroup_path.parent
        before = snapshot(slot)
        service = self.service()

        def decode(path, **kwargs):
            path = Path(path)
            if path.parent != original and not path.parent.name.startswith("."):
                raise ValueError("Injected committed-file semantic failure")
            return decode_forza_source(path, **kwargs)

        with patch.object(service, "_game_process_running", return_value=False), patch.object(
            service, "_default_save_roots", return_value=[wgs]
        ), patch.object(service, "_render_save_thumb_bytes", return_value=png_bytes()), patch(
            "tools.cgroup.forza_source_decoder.decode_forza_source", side_effect=decode
        ):
            with self.assertRaisesRegex(ValueError, "semantic failure"):
                service._create_fh4_layer_group_install_work(self.source)
        self.assertEqual(before, snapshot(slot))

    def test_fh4_worker_installs_nested_groups_without_touching_original(self):
        wgs, slot, _ = build_wgs_fixture(self.root)
        original = read_wgs_layer_groups(slot)[0]
        before = snapshot(original.cgroup_path.parent)
        service = SimpleNamespace(
            _game_process_running=lambda _: False,
            _default_save_roots=lambda _: [wgs],
            _title_for_install_json=CGroupLibraryService._title_for_install_json,
            _rename_header=CGroupLibraryService._rename_header,
            _build_draft_header=CGroupLibraryService._build_draft_header,
            _render_save_thumb_bytes=lambda *_: png_bytes(),
            _save_cached_roots=lambda *_: None,
            paths=SimpleNamespace(runtime_root=self.root / "runtime"),
        )
        result = CGroupLibraryService._create_fh4_layer_group_install_work(service, self.source)
        self.assertTrue(result["ok"])
        created, = [group for group in read_wgs_layer_groups(slot)
                    if group.cgroup_path != original.cgroup_path]
        self.check_decoded(created.cgroup_path, "fh4")
        self.assertEqual(before, snapshot(original.cgroup_path.parent))

    def test_fh6_worker_and_library_export_preserve_groups(self):
        account = make_account(self.root)
        original = next(account.containers.glob("LayerGroup_*"))
        before = snapshot(original)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        service = CGroupLibraryService(paths, None, None, None)
        self.addCleanup(service.close)
        with patch.object(service, "_write_save_thumb", return_value=False):
            result = service._create_fh6_layer_group_install_work(self.source, account.containers)
        self.assertTrue(result["ok"])
        created, = [path for path in account.containers.glob("LayerGroup_*") if path != original]
        self.check_decoded(created / "C_group", "fh6")
        with patch.object(service, "_default_save_roots", return_value=[account.containers]), patch.object(
            service, "_discover_save_artifacts", return_value=[created / "C_group"]
        ), patch.object(service, "_save_cached_roots"), patch.object(service, "_write_preview"):
            exported = service._scan_work("fh6")
        saved = json.loads(Path(exported["outputs"][0]).read_text(encoding="utf-8"))
        self.assertTrue(all(shape.get("editor_group_path") for shape in saved["shapes"]))
        encode_vinyl_document(saved, "fh6")
        self.assertEqual(before, snapshot(original))

    def fm8_service(self):
        root = self.root / "LayerGroups"
        source = write_group(root, str(uuid.uuid4()))
        return root, source, SimpleNamespace(
            _fm8_layer_groups_root=lambda: root,
            _latest_fm8_layer_group=lambda: source,
            _check_fm8_import_ready=lambda: None,
            _title_for_install_json=CGroupLibraryService._title_for_install_json,
            _atomic_write_bytes=CGroupLibraryService._atomic_write_bytes,
            _write_save_thumb=lambda *_: False,
        )

    def test_fm8_worker_preserves_nested_groups(self):
        root, source, service = self.fm8_service()
        before = snapshot(source)
        result = CGroupLibraryService._create_fm8_layer_group_install_work(service, self.source)
        self.assertTrue(result["ok"])
        created, = [path for path in root.iterdir() if path != source]
        self.check_decoded(created / "data", "fm8")
        self.assertEqual(before, snapshot(source))

    def test_fm8_post_commit_corruption_removes_only_new_entry(self):
        root, source, service = self.fm8_service()
        before = snapshot(source)
        rename = os.rename

        def corrupt(src, dst):
            rename(src, dst)
            path = Path(dst) / "data"
            payload = bytearray(path.read_bytes())
            payload[-8] ^= 1
            path.write_bytes(payload)

        with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=corrupt):
            with self.assertRaises(ValueError):
                CGroupLibraryService._create_fm8_layer_group_install_work(service, self.source)
        self.assertEqual([source], list(root.iterdir()))
        self.assertEqual(before, snapshot(source))


if __name__ == "__main__":
    unittest.main()
