"""Installed workflow path/isolation contracts; never launches an installation."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
EVIDENCE = WORKSPACE / "livery/runs/20261018-confirm-transfer/editor-tips/workflow-driver-tests"


class InstalledWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("installed_workflow_support_test", HERE / "installed_workflow_support.py")
        cls.support = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.support)

    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=EVIDENCE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.target = self.base / "selected-install"
        self.target.mkdir()
        self.out = self.base / "new-run"

    def resolve(self, **kwargs):
        return self.support.resolve_paths(self.target, self.out, **kwargs)

    def test_separate_installed_root_keeps_all_writable_roots_in_evidence(self):
        paths = self.resolve()
        self.assertEqual(paths["app"], self.target)
        self.assertEqual(paths["profile"], self.out / "profile")
        self.assertEqual(paths["exports"], self.out / "exports")
        self.assertFalse(self.out.exists(), "Path validation must not write")

    def test_installed_and_evidence_roots_must_not_overlap(self):
        for out in (self.target, self.target / "runs/test", self.base):
            with self.subTest(out=out), self.assertRaises(ValueError):
                self.support.resolve_paths(self.target, out)

    def test_external_output_and_canonical_profile_rejected(self):
        for out, profile in ((Path("C:/KfpsSyntheticExternalEvidence"), None),
                             (self.out, self.target / "runtime/fabric-editor")):
            with self.subTest(out=out, profile=profile), self.assertRaises(ValueError):
                self.support.resolve_paths(self.target, out, profile=profile)

    def test_existing_unowned_profile_rejected_without_reading_preferences(self):
        profile = self.base / "prior/profile"
        profile.mkdir(parents=True)
        sentinel = profile / "preferences.json"
        sentinel.write_text("not ours")
        with self.assertRaises(ValueError):
            self.resolve(profile=profile)
        self.assertEqual(sentinel.read_text(), "not ours")

    def test_owned_profile_can_restart_only_for_same_installation(self):
        paths = self.resolve()
        self.support.initialize_private_run(paths)
        after = self.support.resolve_paths(self.target, self.base / "restart", profile=paths["profile"])
        self.assertEqual(after["profile"], paths["profile"])
        other = self.base / "other-install"
        other.mkdir()
        with self.assertRaises(ValueError):
            self.support.resolve_paths(other, self.base / "restart", profile=paths["profile"])

    def test_existing_output_is_not_reused(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):
            self.resolve()

    def test_environment_is_private_but_preserves_test_options(self):
        paths = self.resolve()
        with patch.dict(os.environ, {"PYTHONPATH": "do-not-use", "QT_PLUGIN_PATH": "do-not-use", "KFPS_TEST_OPTIONS": '{"preserveStartupNotices":true}'}):
            self.support.initialize_private_run(paths)
            self.assertNotIn("PYTHONPATH", os.environ)
            self.assertNotIn("QT_PLUGIN_PATH", os.environ)
            self.assertEqual(json.loads(os.environ["KFPS_TEST_OPTIONS"])["preserveStartupNotices"], True)
            for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
                self.assertTrue(Path(os.environ[key]).is_relative_to(self.out))
            self.assertEqual(Path(os.environ["KFPS_TEST_APP_ROOT"]), self.target)
            self.assertEqual(Path(os.environ["KFPS_TEST_REFERENCE_ROOT"]), WORKSPACE / "repo")

    def test_private_environment_matches_windows_known_folders(self):
        paths = self.resolve()
        self.support.initialize_private_run(paths)
        user = Path(os.environ["USERPROFILE"])
        self.assertEqual(Path(os.environ["LOCALAPPDATA"]), user / "AppData/Local")
        self.assertEqual(Path(os.environ["APPDATA"]), user / "AppData/Roaming")
        report = self.support.validate_private_windows_profile(paths["profile"] / "browser-profile")
        self.assertEqual(Path(report["localAppData"]), Path(os.environ["LOCALAPPDATA"]))
        self.assertEqual(Path(report["roamingAppData"]), Path(os.environ["APPDATA"]))
        self.assertTrue(report["distinctFromDefaultChrome"])

    def test_private_environment_rejects_default_chrome_profile(self):
        paths = self.resolve()
        self.support.initialize_private_run(paths)
        with self.assertRaises(ValueError):
            self.support.validate_private_windows_profile(Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data")

    def test_private_known_folder_check_does_not_recreate_missing_directory(self):
        paths = self.resolve()
        self.support.initialize_private_run(paths)
        local = Path(os.environ["LOCALAPPDATA"])
        local.rmdir()
        with self.assertRaises(ValueError):
            self.support.validate_private_windows_profile(paths["profile"] / "browser-profile")
        self.assertFalse(local.exists())

    def test_stale_asset_override_is_rejected(self):
        with patch.dict(os.environ, {"KFPS_EDITOR_BASELINE_DIR": "unrelated"}):
            with self.assertRaises(ValueError):
                self.resolve()

    def test_baseline_must_be_genuine_and_runtime_installed(self):
        paths = self.resolve()
        with self.assertRaises(RuntimeError):
            self.support.verify_installed(paths)

    def test_both_drivers_have_explicit_installed_branch_and_private_export_root(self):
        for name in ("run-native-page.py", "run-workflow-chrome.py"):
            source = (HERE / name).read_text(encoding="utf-8")
            ast.parse(source)
            self.assertIn('"--installed-root"', source)
            self.assertIn("resolve_paths(", source)
            self.assertIn("verify_installed(", source)
            self.assertIn('installed["exports"]', source)
            self.assertIn("finish_installed(", source)
            self.assertIn("WA_DontShowOnScreen", source)
        chrome = (HERE / "run-workflow-chrome.py").read_text()
        self.assertIn('KFPS_TEST_APP_ROOT=str(ROOT)', chrome)

    def test_historical_assets_are_separate_from_installed_asset_identity(self):
        for name in ("regression-cross-version-projects.js", "regression-customization-compat.js"):
            source = (HERE / name).read_text(encoding="utf-8")
            self.assertIn("KFPS_TEST_REFERENCE_ROOT", source)
            self.assertIn("cwd: referenceRoot", source)
            self.assertIn("KFPS_TEST_APP_ROOT", source)

    def test_project_only_is_explicit_and_does_not_fake_native_export(self):
        source = (HERE / "regression-cross-version-projects.js").read_text(encoding="utf-8")
        self.assertIn("options.projectOnly === true", source)
        self.assertIn("nativeExportVerified: !projectOnly", source)
        self.assertIn("projectOnly ? null : await exportNative(name)", source)
        self.assertIn("installedNumericEditUndoRedo = true", source)
        self.assertIn("#selectProjectEntry", source)
        self.assertNotIn("_safe_relpath", source)


if __name__ == "__main__":
    unittest.main()
