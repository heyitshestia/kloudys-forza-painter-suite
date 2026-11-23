"""Real installer on disposable accounts only; never discover or write live saves."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/src"), str(ROOT / "tools/livery-studio/src")]

from tools.cgroup import fh6_identity
from tools.livery import fh6_save_installer as installer
from tools.cgroup.forza_source_decoder import clivery_to_layers, unwrap_forza_container
from test_studio_package_handoff import make_package


class ConfirmedDestinationInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="confirmed-destination-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.package = self.root / "fixture.kfpslivery"
        make_package(self.package)
        self.account = self.make_account(123)
        self.expected = installer.destination_snapshot(self.account)

    def make_account(self, user, version=1):
        account = self.root / f"u_{user}_16D460"
        folder = account / str(version) / "ContainersRoot"
        (folder / f"User_{user:x}").mkdir(parents=True)
        (account / f"{version}.json").write_text(json.dumps({"Manifest": {
            "UserId": str(user), "GameId": "16D460", "Version": version}}), encoding="utf-8")
        evidence = folder / "LayerGroup_IdentityFixture"
        evidence.mkdir()
        (evidence / "header").write_bytes(fh6_identity.build_vinyl_header("Fixture", user, "Fixture Owner", 1))
        current = account / "current"
        if current.exists():
            os.rmdir(current) if os.name == "nt" else current.unlink()
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(folder.parent), str(current))
        else:
            current.symlink_to(folder.parent, target_is_directory=True)
        return fh6_identity.read_account(account)

    def tree(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file()}

    def install(self, **options):
        values = {"scan_roots": [], "backup_root": self.root / "backups", "expected_model_code": "TEST_CAR",
                  "destination": self.expected["containers"], "expected_destination": self.expected,
                  "local_app_data": self.root / "no-system-pointer"}
        values.update(options)
        return installer.install_full_livery_package(self.package, **values)

    def assert_blocked_before_rewrite_or_write(self, **options):
        before = self.tree()
        with patch.object(installer, "rewrite_destination_identity", side_effect=AssertionError("Unexpected identity rewrite")) as rewrite, \
                patch.object(installer, "_write_exclusive", side_effect=AssertionError("Unexpected write")) as write:
            with self.assertRaises(installer.FullLiveryInstallError):
                self.install(**options)
        rewrite.assert_not_called()
        write.assert_not_called()
        self.assertEqual(before, self.tree())
        self.assertFalse((self.root / "backups").exists())

    def test_matching_snapshot_installs_and_reopens_real_synthetic_package(self):
        before = self.tree()
        result = self.install()
        self.assertEqual(self.account.containers, result.containers_root)
        self.assertTrue(result.installed_folder.is_relative_to(self.account.containers))
        header = installer.parse_fh6_header((result.installed_folder / "header").read_bytes())
        payload = unwrap_forza_container(result.installed_folder / "C_livery")
        layers, report = clivery_to_layers(payload)
        self.assertEqual((3307, 5, 123), (header.car_id, len(layers), int.from_bytes(header.creator_tag, "little")))
        self.assertFalse(report["warnings"])
        receipt = json.loads((result.backup_path / "install.json").read_bytes())
        self.assertEqual(str(self.account.containers), receipt["containers_root"])
        self.assertEqual(hashlib.sha256((result.installed_folder / "C_livery").read_bytes()).hexdigest(),
                         receipt["files"]["C_livery"])
        after = self.tree()
        self.assertTrue(all(after.get(name) == digest for name, digest in before.items()))
        self.assertEqual(self.expected, installer.destination_snapshot(fh6_identity.read_account(self.account.directory)))

    def test_trusted_direct_call_without_snapshot_keeps_existing_api(self):
        result = self.install(expected_destination=None)
        self.assertTrue((result.installed_folder / "C_livery").is_file())

    def test_directory_mtimes_do_not_participate_in_binding_or_normal_staging(self):
        for folder in (self.account.directory, self.account.containers.parent, self.account.containers):
            os.utime(folder, (1234567890, 1234567890))
        self.assertEqual(self.expected, installer.destination_snapshot(self.account))
        result = self.install()
        self.assertTrue(result.installed_folder.is_dir())
        self.assertEqual(self.expected, installer.destination_snapshot(self.account))

    def test_real_junction_retarget_to_other_account_is_blocked_before_rewrite(self):
        other = self.make_account(456)
        directory = self.account.directory
        directory.rename(self.root / "original-account")
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(other.directory), str(directory))
        else:
            directory.symlink_to(other.directory, target_is_directory=True)
        self.assertEqual(other.containers, Path(self.expected["containers"]).resolve(strict=True))
        self.assert_blocked_before_rewrite_or_write()

    def test_real_same_path_replacement_with_identical_metadata_changes_physical_id(self):
        containers = self.account.containers
        previous = containers.with_name("ContainersRoot-original")
        containers.rename(previous)
        shutil.copytree(previous, containers)
        current = fh6_identity.read_account(self.account.directory)
        self.assertEqual(self.account, current)
        fresh = installer.destination_snapshot(current)
        self.assertEqual(self.expected["directory_id"], fresh["directory_id"])
        self.assertEqual(self.expected["version_id"], fresh["version_id"])
        self.assertNotEqual(self.expected["containers_id"], fresh["containers_id"])
        self.assert_blocked_before_rewrite_or_write()

    def test_manifest_drift_on_same_account_and_version_is_blocked(self):
        manifest = self.account.directory / "1.json"
        value = json.loads(manifest.read_bytes())
        value["Extra"] = "new metadata"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        fresh = installer.destination_snapshot(fh6_identity.read_account(self.account.directory))
        self.assertEqual(self.expected["containers_id"], fresh["containers_id"])
        self.assertNotEqual(self.expected["manifest_sha256"], fresh["manifest_sha256"])
        self.assert_blocked_before_rewrite_or_write()

    def test_current_version_drift_is_blocked(self):
        self.make_account(123, version=2)
        self.assert_blocked_before_rewrite_or_write()

    def test_changed_automatic_pointer_cannot_redirect_confirmed_explicit_account(self):
        with patch.object(fh6_identity, "_pointer_accounts", side_effect=AssertionError("Must not follow a new pointer")):
            result = self.install()
        self.assertEqual(self.account.containers, result.containers_root)

    def test_snapshot_parser_never_resolves_expected_paths_and_preserves_large_ids(self):
        value = copy.deepcopy(self.expected)
        value["containers_id"][1] = 2**127 + 17
        value = json.loads(json.dumps(value))
        with patch.object(Path, "resolve", side_effect=AssertionError("Expected paths must not resolve")):
            parsed = installer.validate_destination_snapshot(value)
        self.assertEqual(2**127 + 17, parsed["containers_id"][1])
        value["containers_id"][1] = 1
        self.assertEqual(2**127 + 17, parsed["containers_id"][1])

    def test_zero_filesystem_id_blocks_snapshot_creation(self):
        original = Path.stat
        def zero(path, *args, **kwargs):
            if path == self.account.directory:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=1, st_ino=0)
            return original(path, *args, **kwargs)
        with patch.object(Path, "stat", zero):
            with self.assertRaises(installer.FullLiveryConcurrentChangeError):
                installer.destination_snapshot(self.account)

    def test_malformed_supplied_snapshots_fail_before_package_or_save_access(self):
        cases = [[], {}, True, {**self.expected, "extra": True}, {**self.expected, "schema": "future"}]
        for key, value in (("user_id", "456"), ("user_id", 123), ("directory", "relative"),
                           ("containers", str(self.root / "different")), ("manifest_sha256", "bad"),
                           ("directory_id", [1, 0]), ("version_id", [True, 4]),
                           ("containers_id", [1, 1.0])):
            cases.append({**self.expected, key: value})
        for value in cases:
            with self.subTest(value=value), patch.object(installer, "validate_full_livery_package") as validate:
                self.assert_blocked_before_rewrite_or_write(expected_destination=value)
                validate.assert_not_called()

    def test_drift_during_decode_is_rechecked_before_identity_rewrite(self):
        original = installer.clivery_to_layers
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.account.directory / "1.json").write_bytes(self.account.manifest + b" ")
            return result
        with patch.object(installer, "clivery_to_layers", side_effect=changed), \
                patch.object(installer, "rewrite_destination_identity", side_effect=AssertionError("Unexpected rewrite")) as rewrite, \
                patch.object(installer, "_write_exclusive", side_effect=AssertionError("Unexpected write")) as write:
            with self.assertRaises(installer.FullLiveryInstallError):
                self.install()
        rewrite.assert_not_called()
        write.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_drift_during_original_snapshot_is_rechecked_before_any_write(self):
        original = installer._snapshot
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.account.directory / "1.json").write_bytes(self.account.manifest + b" ")
            return result
        with patch.object(installer, "_snapshot", side_effect=changed), \
                patch.object(installer, "_write_exclusive", side_effect=AssertionError("Unexpected write")) as write:
            with self.assertRaises(installer.FullLiveryInstallError):
                self.install()
        write.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_existing_precommit_revalidation_rejects_late_identity_drift(self):
        original = installer._write_exclusive
        def changed(path, data):
            original(path, data)
            if path.name == "header" and path.parent.name.endswith(".tmp"):
                (self.account.directory / "1.json").write_bytes(self.account.manifest + b" ")
        with patch.object(installer, "_write_exclusive", side_effect=changed):
            with self.assertRaises(installer.FullLiveryInstallError):
                self.install()
        self.assertEqual([], list(self.account.containers.glob("Livery_*")))
        self.assertEqual([], list(self.account.containers.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
