"""Public offline-library slots remain payment-neutral, with real save guards."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup.fh6_identity import build_vinyl_header, parse_vinyl_header
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files
from tools.cgroup.xbox_wgs import read_wgs_layer_groups
from test_fh4_offline_transfer import build_wgs_fixture
from test_fh6_offline_identity import make_account, snapshot
from test_fm8_offline_transfer import write_group


KEY_STATES = (("absent", None), ("locked", False), ("unlocked", True))


class OfflineLibraryAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @contextmanager
    def fixture(self, unlocked):
        with tempfile.TemporaryDirectory(prefix="kfps-library-access-") as temp, ExitStack() as stack:
            root = Path(temp)
            account = make_account(root / "saves")
            target = account.containers / "LayerGroup_0000_fixture"
            source = root / "input.json"
            source.write_text(json.dumps({"name": "Synthetic access fixture", "shapes": [
                {"type": 8, "data": [i * 12, -i * 7, 100, 80, i], "color": [80, 140, 220, 255]}
                for i in range(6)
            ]}), encoding="utf-8")
            source_before = source.read_bytes()
            stack.enter_context(patch.dict(os.environ, {"LOCALAPPDATA": str(root / "local")}))
            paths = AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", Path(sys.executable))
            supporter = None if unlocked is None else SimpleNamespace(unlocked=unlocked)
            jsons, log, preview = Mock(), Mock(), Mock()
            service = CGroupLibraryService(paths, preview, jsons, log, supporter=supporter)
            self.assertIs(service.supporter, supporter)
            self.assertFalse(service.demo)
            stack.enter_context(patch.object(service, "_default_save_roots", side_effect=lambda game=None:
                [root / "saves" / "LayerGroups"] if game == "fm8" else [account.directory]))
            stack.enter_context(patch.object(service, "_game_process_running", return_value=False))
            dialog = stack.enter_context(patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=""))
            threads = []
            service.changed.connect(lambda: threads.append(threading.get_ident()))
            try:
                yield SimpleNamespace(root=root, account=account, source=source, target=target,
                                      service=service, dialog=dialog, jsons=jsons, log=log, threads=threads)
                self.assertEqual(source_before, source.read_bytes())
                self.assertNotIn("Supporter unlock required", service.status)
                self.assertTrue(all(ident == threading.get_ident() for ident in threads))
            finally:
                service.close()
            self.assertTrue(service._closed)
            self.assertTrue(all(not thread.is_alive() for thread in service._executor._threads))

    def wait(self, fixture, status="Complete"):
        service = fixture.service
        self.assertIsNotNone(service._future, "The public slot did not submit its real worker")
        deadline = time.monotonic() + 10
        while service.running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.002)
        self.assertFalse(service.running, service.summary)
        self.assertEqual(status, service.status, service.summary)
        self.assertTrue(service._future.done())
        self.assertTrue(fixture.threads)

    def unchanged(self, f, before):
        self.assertEqual(before, snapshot(f.account.containers))
        self.assertEqual([], list(f.account.containers.glob(".kfps-*")))

    def test_real_fh6_scan_same_output_and_ui_completion_for_all_keys(self):
        outcomes = []
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                f.service.scanSaves("fh6")
                self.wait(f)
                self.assertEqual((1, 1, 0), (f.service.candidateCount, f.service.exportedCount, f.service.skippedCount))
                output = Path(f.service.lastOutput)
                self.assertTrue(output.is_relative_to(f.root))
                decoded = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual("fh6", decoded["target_game"])
                self.assertEqual(1, len(decoded["shapes"]))
                outcomes.append(decoded["shapes"])
                f.jsons.setSource.assert_called_once_with(3)
                f.jsons.selectPath.assert_called_once_with(str(output))
                f.jsons.refresh.assert_called_once_with()
                f.jsons.refreshRecent.assert_called_once_with()
                self.unchanged(f, before)
        self.assertEqual([outcomes[0]] * 3, outcomes)

    def test_real_fm8_scan_preserves_ownership_and_format_checks_for_all_keys(self):
        outcomes = []
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                groups = f.root / "saves" / "LayerGroups"
                owned = write_group(groups, "owned")
                write_group(groups, "catalog", catalog_state=3)
                write_group(groups, "restricted", restricted=True)
                invalid = write_group(groups, "invalid")
                (invalid / "data").write_bytes(b"invalid native data")
                before = snapshot(groups)
                f.service.scanSaves("fm8")
                self.wait(f)
                self.assertEqual(1, f.service.exportedCount)
                self.assertGreaterEqual(f.service.skippedCount, 2)
                output = json.loads(Path(f.service.lastOutput).read_text(encoding="utf-8"))
                self.assertEqual(str(owned / "data"), output["source_path"])
                self.assertTrue(output["metadata"]["ownership_verified"])
                outcomes.append(output["shapes"])
                self.assertEqual(before, snapshot(groups))
        self.assertEqual([outcomes[0]] * 3, outcomes)

    def test_real_create_same_identity_and_shapes_for_all_keys_with_game_running(self):
        outcomes = []
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.target)
                with patch.object(f.service, "_game_process_running", return_value=True):
                    f.service.createLayerGroupFromSelectedJson(str(f.source), "fh6")
                    self.wait(f)
                created, = [p for p in f.account.containers.glob("LayerGroup_*") if p != f.target]
                identity = parse_vinyl_header((created / "header").read_bytes())
                self.assertEqual((6, f.account.user_id, "Local Painter"),
                                 (identity.layer_count, identity.creator_id, identity.creator))
                self.assertNotEqual(parse_vinyl_header(before["header"]).asset_id, identity.asset_id)
                outcomes.append(decode_forza_source(created / "C_group", allow_locked=False, game="fh6").layers)
                self.assertEqual(before, snapshot(f.target))
                self.assertIsNone(f.service._pending_fh6_json)
        self.assertEqual([outcomes[0]] * 3, outcomes)

    def test_real_direct_and_picker_replacement_keep_id_and_exact_backup_for_all_keys(self):
        outcomes = []
        for picker in (False, True):
            for name, unlocked in KEY_STATES:
                with self.subTest(key=name, picker=picker), self.fixture(unlocked) as f:
                    before = snapshot(f.target)
                    if picker:
                        f.dialog.return_value = str(f.target)
                        f.service.installSelectedJsonToFH6(str(f.source))
                        f.dialog.assert_called_once()
                    else:
                        f.service.installJsonToFH6LayerGroup(str(f.source), str(f.target))
                        f.dialog.assert_not_called()
                    self.wait(f)
                    identity = parse_vinyl_header((f.target / "header").read_bytes())
                    self.assertEqual(parse_vinyl_header(before["header"]).asset_id, identity.asset_id)
                    self.assertEqual(6, identity.layer_count)
                    backup, = (f.root / "runtime" / "cgroup-folder-import-backups").iterdir()
                    self.assertEqual(before, snapshot(backup))
                    outcomes.append(decode_forza_source(f.target / "C_group", allow_locked=False, game="fh6").layers)
                    self.assertEqual([], list(f.account.containers.glob(".kfps-*")))
        self.assertEqual([outcomes[0]] * 6, outcomes)

    def test_real_fm8_create_dispatches_and_reopens_for_all_keys(self):
        outcomes = []
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                groups = f.root / "saves" / "LayerGroups"
                donor = write_group(groups, str(uuid.uuid4()))
                before = snapshot(donor)
                f.service.createLayerGroupFromSelectedJson(str(f.source), "fm8")
                self.wait(f)
                created, = [p for p in groups.iterdir() if p != donor]
                self.assertTrue(assess_fm8_layer_group_files(created / "data").allowed)
                decoded = decode_forza_source(created / "data", allow_locked=False, game="fm8")
                self.assertEqual(6, len(decoded.layers))
                outcomes.append(decoded.layers)
                self.assertEqual(before, snapshot(donor))
                self.assertEqual("fm8", f.service.activeGame)
        self.assertEqual([outcomes[0]] * 3, outcomes)

    def test_real_fh4_create_dispatches_and_preserves_complete_backup_for_all_keys(self):
        outcomes = []
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                wgs, slot, _index = build_wgs_fixture(f.root / "saves")
                before = snapshot(slot)
                original = read_wgs_layer_groups(slot)[0].cgroup_path
                with patch.object(f.service, "_default_save_roots", return_value=[wgs]):
                    f.service.createLayerGroupFromSelectedJson(str(f.source), "fh4")
                    self.wait(f)
                created, = [g for g in read_wgs_layer_groups(slot) if g.cgroup_path != original]
                decoded = decode_forza_source(created.cgroup_path, allow_locked=False, game="fh4")
                self.assertEqual(6, len(decoded.layers))
                outcomes.append(decoded.layers)
                backup, = (f.root / "runtime" / "fh4-offline-import-backups").iterdir()
                self.assertEqual(before, snapshot(backup))
                self.assertEqual(before[str(original.relative_to(slot))], original.read_bytes())
                self.assertEqual("fh4", f.service.activeGame)
        self.assertEqual([outcomes[0]] * 3, outcomes)

    def test_existing_destination_picker_cancel_has_no_work_or_writes_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                f.service.installSelectedJsonToFH6(str(f.source))
                f.dialog.assert_called_once()
                self.assertIsNone(f.service._future)
                self.assertFalse(f.service.running)
                self.unchanged(f, before)

    def test_ambiguous_new_destination_cancel_has_no_writes_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                make_account(f.root / "saves", 456)
                with patch.object(f.service, "_default_save_roots", return_value=[f.root / "saves"]):
                    before = snapshot(f.root / "saves")
                    f.service.createFH6LayerGroupFromSelectedJson(str(f.source))
                    self.wait(f, "Failed")
                f.dialog.assert_called_once()
                self.assertIn("cancelled", f.service.summary)
                self.assertEqual(before, snapshot(f.root / "saves"))
                self.assertIsNone(f.service._pending_fh6_json)

    def test_unsupported_game_and_missing_source_keep_validation_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                missing = str(f.root / "missing.json")
                f.service.createLayerGroupFromSelectedJson(missing, "fh6")
                f.service.installSelectedJsonToFH6(missing)
                self.assertIsNone(f.service._future)
                f.dialog.assert_not_called()
                f.service.createLayerGroupFromSelectedJson(str(f.source), "fh5")
                self.assertEqual("FH5 offline import disabled", f.service.status)
                self.assertIsNone(f.service._future)
                self.unchanged(f, before)

    def test_closed_worker_slots_still_reject_submissions_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                f.service.close()
                f.service.scanSaves("fh6")
                f.service.createLayerGroupFromSelectedJson(str(f.source), "fh6")
                f.service.installJsonToFH6LayerGroup(str(f.source), str(f.target))
                self.assertIsNone(f.service._future)
                self.assertFalse(f.service.running)
                self.unchanged(f, before)

    def test_invalid_format_fails_before_commit_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                bad = f.root / "bad.json"
                bad.write_text('{"shapes": []}', encoding="utf-8")
                before = snapshot(f.account.containers)
                f.service.createLayerGroupFromSelectedJson(str(bad), "fh6")
                self.wait(f, "Failed")
                self.unchanged(f, before)

    def test_foreign_identity_replacement_still_fails_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                (f.target / "header").write_bytes(build_vinyl_header("Foreign", 999, "Other", 1))
                before = snapshot(f.account.containers)
                f.service.installJsonToFH6LayerGroup(str(f.source), str(f.target))
                self.wait(f, "Failed")
                self.unchanged(f, before)
                self.assertFalse((f.root / "runtime" / "cgroup-folder-import-backups").exists())

    def test_game_running_replacement_still_fails_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                with patch.object(f.service, "_game_process_running", return_value=True):
                    f.service.installJsonToFH6LayerGroup(str(f.source), str(f.target))
                    self.wait(f, "Failed")
                self.assertIn("replacing an existing vinyl", f.service.summary)
                self.unchanged(f, before)

    def test_mid_staging_cancellation_keeps_original_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.account.containers)
                def cancel(*args):
                    f.service._cancel_event.set()
                    return False
                with patch.object(f.service, "_write_save_thumb", side_effect=cancel):
                    f.service.createLayerGroupFromSelectedJson(str(f.source), "fh6")
                    self.wait(f, "Failed")
                self.assertIn("cancelled", f.service.summary)
                self.unchanged(f, before)

    def test_failed_replacement_commit_rolls_back_with_exact_backup_for_all_keys(self):
        for name, unlocked in KEY_STATES:
            with self.subTest(key=name), self.fixture(unlocked) as f:
                before = snapshot(f.target)
                rename = os.rename
                calls = []
                def fail_install(source, destination):
                    calls.append((source, destination))
                    if len(calls) == 2:
                        raise OSError("Synthetic blocked commit")
                    return rename(source, destination)
                with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=fail_install):
                    f.service.installJsonToFH6LayerGroup(str(f.source), str(f.target))
                    self.wait(f, "Failed")
                self.assertEqual(3, len(calls))
                self.assertIn("Synthetic blocked commit", f.service.summary)
                self.assertEqual(before, snapshot(f.target))
                backup, = (f.root / "runtime" / "cgroup-folder-import-backups").iterdir()
                self.assertEqual(before, snapshot(backup))
                self.assertEqual([], list(f.account.containers.glob(".kfps-*")))


if __name__ == "__main__":
    unittest.main()
