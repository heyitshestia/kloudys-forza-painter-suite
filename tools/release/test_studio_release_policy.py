from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio_release_policy as policy
import build_release_bundles as builder

RUN = HERE.parents[2] / "releases/20261019-public/packaging/policy-tests"
HOST_DEPENDENCIES = {
    "tools/kfps_activity.py", "tools/kfps_activity_host.py", "tools/kfps_display_language.py",
    "tools/kfps_release_announcement.py", "KFPS.UI/content/release-announcement.json",
    "KFPS.Editor/web/release-announcement.js", "KFPS.Editor/web/release-announcement.css",
    "KFPS.Editor/web/activity-client.js",
}
VENDOR_DEPENDENCIES = {
    "tools/livery-inspector/vendor/three/" + path for path in (
        "build/three.module.min.js", "build/three.core.min.js", "LICENSE",
        "examples/jsm/loaders/GLTFLoader.js", "examples/jsm/controls/OrbitControls.js",
        "examples/jsm/utils/BufferGeometryUtils.js", "examples/jsm/utils/SkeletonUtils.js",
    )
}


class StudioReleasePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RUN.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=RUN)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_private_and_nonshipping_paths_rejected(self):
        for name in ("settings/local-launch.json", "settings/confirmations.json", "recovery/projects.sqlite3",
                     "runs/studio-browser/Default/Preferences", "runs/studio-launch/instance.json",
                     "runs/studio-session-theme-v2/assets/car.glb", "tests/private.json", "docs/transfer-manifest.json",
                     "fixtures/synthetic-vinyls/example.json", "src/web/artwork.png", "src/kfps_livery_lab/private.kfpskey",
                     "src/web/locales/receipts.json", "../outside.py", "C:/outside.py", "src\\web\\index.html",
                     "scripts/apply-viewer-storage-transfer.ps1", "src/web/secrets.json"):
            with self.subTest(path=name):
                self.assertFalse(policy.studio_path_allowed(name))

    def test_exact_runtime_and_converter_paths_allowed(self):
        for name in policy.REQUIRED:
            with self.subTest(path=name):
                self.assertTrue(policy.studio_path_allowed(name))
        self.assertFalse(policy.studio_path_allowed("runs/component-converter/converter/publish/other.exe"))
        self.assertFalse(policy.studio_path_allowed("runs/component-converter/packages/nuget-cache.zip"))

    def test_shared_host_and_vendor_dependencies_are_required(self):
        self.assertTrue((HOST_DEPENDENCIES | VENDOR_DEPENDENCIES).issubset(policy.BASELINE_REQUIRED))
        self.assertIn("src/kfps_livery_lab/diagnostics.py", policy.REQUIRED)
        self.assertIn("src/kfps_livery_lab/storage_paths.py", policy.REQUIRED)

    def test_missing_shared_host_dependencies_fail_closed(self):
        lab, baseline = self.root / "studio", self.root / "baseline"
        for root, names in ((lab, policy.REQUIRED),
                            (baseline, set(policy.BASELINE_REQUIRED) | HOST_DEPENDENCIES | VENDOR_DEPENDENCIES)):
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic fixture")
        provenance = Mock()
        provenance.read_json.return_value = {"format": "kfps-converter-build-v2", "sources": []}
        with patch.object(policy, "_provenance", return_value=provenance):
            record = policy.inventory(lab, baseline)
            self.assertTrue((HOST_DEPENDENCIES | VENDOR_DEPENDENCIES).issubset(
                row["path"] for row in record["baseline_prerequisites"]))
            for name in sorted(HOST_DEPENDENCIES | VENDOR_DEPENDENCIES):
                with self.subTest(path=name):
                    path = baseline / name
                    path.unlink()
                    try:
                        with self.assertRaisesRegex(ValueError, "Missing distribution input"):
                            policy.inventory(lab, baseline)
                    finally:
                        path.write_bytes(b"synthetic fixture")

    def test_existing_images_project_storage_is_forbidden_in_bundle(self):
        for name in ("imgs/livery-projects", "imgs/livery-projects/toyota-1/projects/work.json",
                     "imgs/livery-projects/toyota-1/recovery/recovery.sqlite3"):
            self.assertTrue(builder._is_forbidden(Path(name)), name)

    def test_all_three_application_launchers_and_updater_copied_identically(self):
        app, outer = self.root / "app", self.root / "outer"
        app.mkdir()
        outer.mkdir()
        names = ("KFPS.exe", "KFPS Editor.exe", policy.LAUNCHER, "KFPS-Updater.exe")
        for name in names:
            (app / name).write_bytes(name.encode())
        self.assertEqual(set(policy.copy_outer_launchers(app, outer)), set(names))
        for name in names:
            self.assertEqual((outer / name).read_bytes(), (app / name).read_bytes())

    def test_historical_no_studio_package_retains_compatibility(self):
        self.assertIsNone(policy.validate_packaged_studio(self.root))
        (self.root / policy.LAUNCHER).write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError, "Missing distribution input"):
            policy.validate_packaged_studio(self.root)

    def test_personal_absolute_paths_detected_without_rejecting_standard_chrome_lookup(self):
        for value in (b'D:/Users/Example/Project', b'C:\\Users\\Example\\Desktop', b'E:\\\\ECC\\\\cache'):
            self.assertIsNotNone(policy.PERSONAL_PATH.search(value), value)
        self.assertIsNone(policy.PERSONAL_PATH.search(b'C:/Program Files/dotnet/dotnet.exe'))

    def test_unsafe_or_missing_distribution_path_rejected(self):
        for name in ("../outside", "C:/outside", "src\\secret", "absent"):
            with self.subTest(path=name), self.assertRaises(ValueError):
                policy.safe_file(self.root, name)

    def _studio_git_roundtrip(self):
        source, checkout = self.root / "git-source", self.root / "git-checkout"
        source.mkdir()
        checkout.mkdir()
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                   HOME=str(self.root), USERPROFILE=str(self.root), KFPS_ACTIVITY_DISABLED="1")

        def git(*args):
            return subprocess.run(["git", *args], cwd=source, env=env, check=True,
                                  capture_output=True, timeout=30,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout

        git("init", "--quiet", "--template=")
        git("config", "core.autocrlf", "true")
        git("config", "core.safecrlf", "false")
        files = {name: b"fixture line one\nfixture line two\n" for name in (
            "tools/livery-studio/scripts/build-converter.ps1",
            "tools/livery-studio/src/chassis-converter/Program.cs",
            "tools/livery-studio/src/chassis-converter/Kfps.LiveryLab.Converter.csproj",
            "tools/livery-studio/src/chassis-converter/NuGet.Config",
            "tools/livery-studio/src/chassis-converter/PROVENANCE.md",
            "tools/livery-studio/src/kfps_livery_lab/converter_provenance.py",
            "tools/livery-studio/src/web/livery-editor.mjs",
            "tools/livery-studio/runs/component-converter/converter/build-manifest.json",
            "tools/livery/chassis-converter/Program.cs",
        )}
        files["tools/livery-studio/runs/component-converter/converter/publish/"
              "Kfps.LiveryLab.Converter.exe"] = b"MZ\x00fixture\r\n\x00payload\n"
        files["unrelated.ps1"] = b"Write-Output 'unchanged CRLF policy'\r\n"
        (source / ".gitattributes").write_bytes((HERE.parents[1] / ".gitattributes").read_bytes())
        for name, data in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git("add", ".")
        # A tree is enough: the fixture creates no commits and never accesses a remote.
        tree = git("write-tree").decode().strip()
        git("checkout-index", "--all", "--prefix=" + checkout.as_posix() + "/")
        with zipfile.ZipFile(io.BytesIO(git("archive", "--format=zip", tree))) as archive:
            archived = {name: archive.read(name) for name in files}
        return files, {name: (checkout / name).read_bytes() for name in files}, archived

    def test_studio_windows_checkout_preserves_raw_fingerprints(self):
        original, checked_out, _ = self._studio_git_roundtrip()
        for name, data in original.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256(data).digest(), hashlib.sha256(checked_out[name]).digest())

    def test_studio_git_archive_preserves_raw_fingerprints(self):
        original, _, archived = self._studio_git_roundtrip()
        for name, data in original.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256(data).digest(), hashlib.sha256(archived[name]).digest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
