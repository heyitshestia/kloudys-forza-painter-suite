from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from game_adapters import get_adapter_or_default
from game_adapters.discovery import discover_save_artifacts
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup import steam_offline as steam
from tools.cgroup.cgroup_codec import wrap_payload
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.horizon_vinyl_header import parse_vinyl_header
from tools.cgroup.vinyl_document import encode_vinyl_document
from test_fh5_offline_transfer import header_bytes, png_bytes

OWNER = 1234567890123456
STAMP = datetime(2026, 10, 20, 12, 30, 0)


def document(count=6):
    return {"name": "Steam Test", "shapes": [
        {"type": 1048677, "type_word": 101,
         "data": [i * 2, -i, -1.2, 0.6, i % 360, 0.12, int(i == count - 1)],
         "color": [30, 80, 140, 0 if i == count - 1 else 220], "mask": i == count - 1,
         "editor_group_path": [{"id": "outer", "name": "Outer"},
                               {"id": f"part-{i // 3}", "name": f"Part {i // 3}"}]}
        for i in range(count)]}


def fixture(root, game="fh5", owner=OWNER):
    account = root / "userdata" / "1234567" / steam.APP_IDS[game] / "remote" / str(owner)
    account.mkdir(parents=True)
    path = account / "LayerGroup_0000_20261020123000.header"
    path.write_bytes(header_bytes(count=1, owner=owner, version=4 if game == "fh4" else 6))
    payload, _ = encode_vinyl_document(document(1), game)
    path.with_suffix(".C_group").write_bytes(wrap_payload(payload))
    path.with_suffix(".thumb.png").write_bytes(png_bytes())
    (account / "test.ProfileData").write_bytes(b"UNTOUCHED PROFILE")
    (account.parent.parent / "remotecache.vdf").write_bytes(b"UNTOUCHED STEAM CACHE")
    return account, path


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class SteamOfflineTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        parent = ROOT / "runtime" / "offline-transfer-20261020" / "steam" / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.account, self.header = fixture(self.root)
        self.target = steam.inspect_steam_target(self.header, "fh5")
        self.before = snapshot(self.account)
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(document()), encoding="utf-8")

    def install(self, target=None, count=6, **kwargs):
        target = target or self.target
        payload, report = encode_vinyl_document(document(count), target.game)
        args = dict(payload=payload, title="Repeated Test", thumbnail_data=png_bytes(),
                    expected_layers=report["layers"], backup_root=self.root / "backups",
                    check_ready=lambda: None, now=STAMP)
        args.update(kwargs)
        return steam.create_steam_layer_group(target, **args)

    def unchanged(self):
        self.assertEqual(self.before, snapshot(self.account))
        self.assertFalse(list(self.account.glob(".kfps-stage-*")))

    def service(self):
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        service = CGroupLibraryService(paths, None, None, SimpleNamespace(append=Mock()))
        self.addCleanup(service.close)
        return service

    def test_both_games_repeated_imports_preserve_originals_backup_and_identity(self):
        for game in ("fh4", "fh5"):
            with self.subTest(game=game):
                account, header = fixture(self.root / game, game)
                target = steam.inspect_steam_target(header, game)
                before = snapshot(account)
                first = self.install(target, title="Test \u65e5\ubcf8\U0001f680")
                second = self.install(target)
                self.assertNotEqual(first.cgroup_path, second.cgroup_path)
                for name, data in before.items():
                    self.assertEqual(data, (account / name).read_bytes())
                self.assertEqual(before, snapshot(first.backup_path / "account"))
                self.assertTrue((first.backup_path / "committed.json").is_file())
                headers = [parse_vinyl_header(r.header_path.read_bytes(), game) for r in (first, second)]
                self.assertEqual(4 if game == "fh4" else 6, headers[0].version)
                self.assertEqual("Test \u65e5\ubcf8\U0001f680", headers[0].title)
                self.assertEqual(OWNER, headers[0].creator_id)
                self.assertEqual(3, len({target.header.asset_id, *(h.asset_id for h in headers)}))
                self.assertEqual(b"UNTOUCHED STEAM CACHE", (account.parent.parent / "remotecache.vdf").read_bytes())
                decoded = decode_forza_source(first.cgroup_path, allow_locked=False, game=game)
                self.assertEqual(6, len(decoded.layers))
                self.assertGreaterEqual(decoded.report["group_nodes"], 3)
                self.assertTrue(decoded.layers[-1]["mask"])
                self.assertEqual(0, decoded.layers[-1]["color"][3])
                found = discover_save_artifacts(get_adapter_or_default(game), [account.parent])
                self.assertIn(first.cgroup_path, found)
                self.assertIn(second.cgroup_path, found)

    def test_3000_shapes_reopen_for_both_games(self):
        for game in ("fh4", "fh5"):
            account, header = fixture(self.root / game, game)
            result = self.install(steam.inspect_steam_target(header, game), count=3000)
            decoded = decode_forza_source(result.cgroup_path, allow_locked=False, game=game)
            self.assertEqual(3000, len(decoded.layers))
            self.assertFalse(decoded.report["warnings"])

    def test_wrong_game_account_header_version_and_bad_draft_are_rejected(self):
        with self.assertRaises(ValueError):
            steam.inspect_steam_target(self.header, "fh4")
        for raw in (
            header_bytes(owner=OWNER + 1), header_bytes(owner=OWNER, version=7),
            header_bytes(owner=OWNER, count=2), b"broken",
        ):
            self.header.write_bytes(raw)
            with self.assertRaises(ValueError):
                steam.inspect_steam_target(self.header, "fh5")

    def test_missing_sidecars_wrong_thumbnail_and_wrong_filename_are_rejected(self):
        thumb = self.header.with_suffix(".thumb.png")
        thumb.unlink()
        with self.assertRaises(FileNotFoundError):
            steam.inspect_steam_target(self.header, "fh5")
        thumb.write_bytes(b"not png")
        with self.assertRaises(ValueError):
            steam.inspect_steam_target(self.header, "fh5")
        with self.assertRaises(ValueError):
            steam.inspect_steam_target(self.source, "fh5")

    def test_hard_links_are_rejected(self):
        linked = self.root / "linked.header"
        os.link(self.header, linked)
        with self.assertRaisesRegex(ValueError, "Hard-linked"):
            steam.inspect_steam_target(self.header, "fh5")

    def test_changed_template_and_invalid_payload_do_not_write(self):
        self.header.write_bytes(header_bytes(owner=OWNER, creator="Changed Owner"))
        before = snapshot(self.account)
        with self.assertRaises(steam.SteamSaveChangedError):
            self.install()
        self.assertEqual(before, snapshot(self.account))
        self.header.write_bytes(self.before[self.header.name])
        for kwargs in ({"payload": b"broken"}, {"expected_layers": 7}, {"thumbnail_data": b"bad"}):
            with self.assertRaises(ValueError):
                self.install(**kwargs)
            self.unchanged()

    def test_backup_under_account_and_nested_save_directory_are_rejected(self):
        with self.assertRaises(ValueError):
            self.install(backup_root=self.account / "backup")
        self.unchanged()
        (self.account / "unexpected").mkdir()
        with self.assertRaisesRegex(ValueError, "nested"):
            self.install()
        (self.account / "unexpected").rmdir()
        self.unchanged()

    def test_cancel_before_backup_during_backup_and_after_stage_write(self):
        def cancel():
            raise concurrent.futures.CancelledError("test cancel")
        with self.assertRaises(concurrent.futures.CancelledError):
            self.install(check_ready=cancel)
        self.unchanged()
        for stop_at in (2, 7):
            calls = 0
            def ready():
                nonlocal calls
                calls += 1
                if calls == stop_at:
                    cancel()
            with self.assertRaises(concurrent.futures.CancelledError):
                self.install(check_ready=ready)
            self.unchanged()

    def test_corrupted_backup_is_rejected_before_any_save_write(self):
        copy = steam.shutil.copy2
        def corrupt(source, destination):
            copy(source, destination)
            Path(destination).write_bytes(b"corrupt")
        with patch.object(steam.shutil, "copy2", side_effect=corrupt), self.assertRaises(steam.SteamSaveChangedError):
            self.install()
        self.unchanged()

    def test_concurrent_original_change_during_backup_is_preserved(self):
        copy = steam.shutil.copy2
        def change(source, destination):
            copy(source, destination)
            (self.account / "test.ProfileData").write_bytes(b"changed elsewhere")
        with patch.object(steam.shutil, "copy2", side_effect=change), self.assertRaises(steam.SteamSaveChangedError):
            self.install()
        self.assertEqual(b"changed elsewhere", (self.account / "test.ProfileData").read_bytes())
        self.assertEqual(1, len(list(self.account.glob("*.C_group"))))

    def test_partial_publish_failure_rolls_back_only_new_files(self):
        rename = steam.os.rename
        count = 0
        def fail(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated disk failure")
            rename(source, destination)
        with patch.object(steam.os, "rename", side_effect=fail), self.assertRaises(OSError):
            self.install()
        self.unchanged()

    def test_file_collision_never_overwrites_another_writer(self):
        rename = steam.os.rename
        collision = []
        def race(source, destination):
            if not collision:
                Path(destination).write_bytes(b"someone else's file")
                collision.append(Path(destination))
            rename(source, destination)
        with patch.object(steam.os, "rename", side_effect=race), self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(b"someone else's file", collision[0].read_bytes())
        for name, data in self.before.items():
            self.assertEqual(data, (self.account / name).read_bytes())

    def test_readback_failure_rolls_back_and_changed_new_file_is_retained(self):
        decode = steam.decode_forza_source
        def fail(path, **kwargs):
            if Path(path).parent == self.account and Path(path) != self.header.with_suffix(".C_group"):
                raise ValueError("readback failure")
            return decode(path, **kwargs)
        with patch.object(steam, "decode_forza_source", side_effect=fail), self.assertRaisesRegex(ValueError, "readback"):
            self.install()
        self.unchanged()
        rename = steam.os.rename
        changed = []
        def change(source, destination):
            rename(source, destination)
            if Path(destination).suffix == ".C_group":
                Path(destination).write_bytes(b"changed after publish")
                changed.append(Path(destination))
        with patch.object(steam.os, "rename", side_effect=change), self.assertRaisesRegex(steam.SteamRecoveryRequiredError, "Safety backup"):
            self.install()
        self.assertEqual(b"changed after publish", changed[0].read_bytes())
        self.assertFalse(list(self.account.glob(".kfps-stage-*")))

    def test_late_cancel_does_not_report_a_successful_commit_as_cancelled(self):
        cancelled = False
        def ready():
            if cancelled:
                raise concurrent.futures.CancelledError()
        rename = steam.os.rename
        def late_cancel(source, destination):
            nonlocal cancelled
            rename(source, destination)
            cancelled = True
        with patch.object(steam.os, "rename", side_effect=late_cancel):
            result = self.install(check_ready=ready)
        self.assertTrue(result.header_path.is_file())

    def test_explicit_second_account_is_used_without_touching_the_first(self):
        other, header = fixture(self.root / "other", owner=OWNER + 1)
        result = self.install(steam.inspect_steam_target(header, "fh5"))
        self.assertEqual(other, result.cgroup_path.parent)
        self.assertEqual(OWNER + 1, parse_vinyl_header(result.header_path.read_bytes()).creator_id)
        self.unchanged()

    def test_public_service_real_thumbnail_and_rescan_for_both_games(self):
        for game in ("fh4", "fh5"):
            account, header = fixture(self.root / game, game)
            service = self.service()
            with patch("kfps_ui.cgroup_library_service.QMessageBox.question", return_value=QMessageBox.Yes), patch(
                "kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=(str(header), "")
            ), patch.object(service, "_game_process_running", return_value=False), patch(
                "kfps_ui.cgroup_library_service.game_discovery.discover_steam_remote_roots", return_value=[account.parent]
            ):
                service.createLayerGroupFromSelectedJson(str(self.source), game, "steam")
                deadline = time.monotonic() + 30
                while service.running and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.005)
            self.assertFalse(service.running)
            self.assertEqual("Complete", service.status, service.summary)
            self.assertIn("cannot confirm", service.summary)
            self.assertIn("Steam Import (Test)", service.offlineImportLabel(game, "steam"))
            created, = [p for p in account.glob("*.C_group") if p != header.with_suffix(".C_group")]
            decoded = decode_forza_source(created, allow_locked=False, game=game)
            self.assertEqual(6, len(decoded.layers))
            # This is KFPS's actual scan-to-library export, not just a decoder call.
            with patch.object(service, "_default_save_roots", return_value=[account.parent]):
                scan = service._scan_work(game)
            self.assertTrue(scan["ok"], scan)
            exported = list(service.paths.library_root.rglob("*.json"))
            documents = [json.loads(p.read_text(encoding="utf-8")) for p in exported]
            self.assertTrue(any(len(d.get("shapes", [])) == 6 for d in documents))

    def test_cancelled_dialogs_unsupported_store_and_running_game_write_nothing(self):
        service = self.service()
        for answer in (QMessageBox.No, QMessageBox.Yes):
            with patch("kfps_ui.cgroup_library_service.QMessageBox.question", return_value=answer), patch(
                "kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=("", "")
            ):
                service.createLayerGroupFromSelectedJson(str(self.source), "fh5", "steam")
            self.assertIsNone(service._future)
        service.createLayerGroupFromSelectedJson(str(self.source), "fh5", "unknown")
        service.createLayerGroupFromSelectedJson(str(self.source), "fh6", "steam")
        self.assertIsNone(service._future)
        for process in ("ForzaHorizon5.exe", "steam.exe"):
            with patch.object(service, "_game_process_running", side_effect=lambda name: name == process):
                with self.assertRaisesRegex(ValueError, "exit Steam"):
                    service._create_steam_layer_group_install_work(self.source, "fh5", self.header)
        with patch.object(service, "_game_process_running", return_value=False), patch.object(
            service, "_render_save_thumb_bytes", return_value=None
        ), self.assertRaisesRegex(ValueError, "thumbnail"):
            service._create_steam_layer_group_install_work(self.source, "fh5", self.header)
        self.unchanged()

    def test_failure_during_staging_keeps_partial_evidence_and_never_publishes(self):
        write = steam._write
        def fail(path, data):
            if path.parent.name.startswith(".kfps-stage-"):
                path.write_bytes(data[:8])
                raise OSError("partial staged write")
            write(path, data)
        with patch.object(steam, "_write", side_effect=fail), self.assertRaisesRegex(
            steam.SteamRecoveryRequiredError, "Staging cleanup"
        ):
            self.install()
        self.assertEqual(1, len(list(self.account.glob("*.C_group"))))
        self.assertEqual(1, len(list(self.account.glob(".kfps-stage-*"))))
        for name, data in self.before.items():
            self.assertEqual(data, (self.account / name).read_bytes())

    def test_foreign_account_change_during_publication_survives_rollback(self):
        rename = steam.os.rename
        def change(source, destination):
            rename(source, destination)
            (self.account / "test.ProfileData").write_bytes(b"foreign change")
        with patch.object(steam.os, "rename", side_effect=change), self.assertRaises(steam.SteamSaveChangedError):
            self.install()
        self.assertEqual(b"foreign change", (self.account / "test.ProfileData").read_bytes())
        self.assertEqual(1, len(list(self.account.glob("*.C_group"))))

    def test_oversized_account_readiness_failure_and_locked_payload_fail_before_writes(self):
        with patch.object(steam, "MAX_ACCOUNT_BYTES", 1), self.assertRaises(ValueError):
            self.install()
        with self.assertRaises(TypeError):
            self.install(check_ready=None)
        payload, _ = encode_vinyl_document(document(), "fh5")
        payload = payload[:0x1D] + b"\x21" + payload[0x1E:]
        with self.assertRaisesRegex(ValueError, "unlocked"):
            self.install(payload=payload)
        self.unchanged()


if __name__ == "__main__":
    unittest.main()
