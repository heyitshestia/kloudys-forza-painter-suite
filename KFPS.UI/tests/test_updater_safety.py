import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


UI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI_ROOT / "src"))

from kfps_ui.app_paths import AppPaths
from kfps_ui.update_service import UpdateService


ROOT = Path(__file__).resolve().parents[2]


class UpdaterSafetyTests(unittest.TestCase):
    def test_git_checkout_cleanup_preserves_ignored_local_state(self):
        text = (ROOT / "03_update_from_github.bat").read_text(encoding="utf-8")
        lines = text.splitlines()
        clean_line = next(line.strip() for line in lines if line.strip().startswith("git clean "))

        self.assertIn("git clean -fd ", clean_line)
        self.assertNotIn("git clean -fdx", clean_line)
        for exclusion in (
            "runtime/",
            "imgs/",
            "webui-data/",
            "python/",
            "*.kfpskey",
            "node_modules/",
            ".wrangler/",
            ".dev.vars",
            ".dev.vars.*",
            ".venv/",
        ):
            with self.subTest(exclusion=exclusion):
                self.assertIn(exclusion, clean_line)

        self.assertNotIn("Get-FileHash", text)
        self.assertIn("[Security.Cryptography.SHA256]::Create()", text)

    def test_updater_executes_only_the_shipped_local_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary)
            batch = app_root / "03_update_from_github.bat"
            batch.write_text("@echo off\nexit /b 0\n", encoding="ascii")
            paths = AppPaths(
                app_root,
                UI_ROOT,
                UI_ROOT / "qml",
                UI_ROOT / "assets",
                app_root / "runtime",
                app_root / "python" / "python.exe",
            )
            messages = []
            log = type("Log", (), {"append": lambda self, message, level="info": messages.append((message, level))})()
            service = UpdateService(paths, log)

            with patch("kfps_ui.update_service.subprocess.Popen") as popen, patch(
                "kfps_ui.update_service.QCoreApplication.quit"
            ) as quit_app:
                service.startUpdate()

            command = popen.call_args.args[0]
            self.assertEqual(str(batch), command[-1])
            self.assertEqual(str(app_root), popen.call_args.kwargs["env"]["KFPS_UPDATER_ROOT"])
            self.assertNotIn("raw.githubusercontent.com", " ".join(command))
            quit_app.assert_called_once_with()

    def test_batch_pins_commit_and_has_no_mutable_remote_bootstrap(self):
        text = (ROOT / "03_update_from_github.bat").read_text(encoding="utf-8")
        self.assertNotIn("raw.githubusercontent.com", text)
        self.assertNotIn("KFPS_UPDATER_REMOTE_BOOTSTRAP", text)
        self.assertIn("git ls-remote", text)
        self.assertIn("fetch --depth 1 origin !TARGET_COMMIT!", text)
        self.assertIn("checkout --detach !TARGET_COMMIT!", text)
        self.assertIn('if /I not "!VERIFY_HEAD!"=="!TARGET_COMMIT!"', text)
        self.assertNotIn(":cleanup_stale_release_git", text)
        self.assertIn(":restore_failed_update", text)

    @unittest.skipUnless(os.name == "nt", "PowerShell path-boundary test is Windows-specific")
    def test_path_safety_rejects_prefix_siblings(self):
        module = ROOT / "tools" / "update" / "UpdatePathSafety.psm1"
        script = (
            f"Import-Module -Name '{module}' -Force; "
            "$good=Test-KfpsPathInTree 'C:\\KFPS\\app\\KFPS.exe' 'C:\\KFPS'; "
            "$bad=Test-KfpsPathInTree 'C:\\KFPS-other\\KFPS.exe' 'C:\\KFPS'; "
            "$cmdGood=Test-KfpsCommandReferencesTree 'python.exe \"C:\\KFPS\\KFPS.UI\\app.py\"' 'C:\\KFPS'; "
            "$cmdBad=Test-KfpsCommandReferencesTree 'python.exe \"C:\\KFPS-other\\app.py\"' 'C:\\KFPS'; "
            "if($good -and -not $bad -and $cmdGood -and -not $cmdBad){exit 0}else{exit 1}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    @unittest.skipUnless(os.name == "nt", "Batch updater integration test is Windows-specific")
    def test_failed_non_git_update_restores_program_files_and_parent_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote"
            remote.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=remote, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "updater-tests@example.invalid"],
                cwd=remote,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Updater Tests"], cwd=remote, check=True)
            required_files = {
                "VERSION": b"2.0.0\n",
                "KFPS.exe": b"new-invalid-launcher",
                "fh6_probe.py": b"# target\n",
                "generator_backend.py": b"# target\n",
                "KloudysGalateaGenesis.exe": b"target-generator",
                "KFPS.UI/keep.txt": b"target",
                "assets/keep.txt": b"target",
                "settings/keep.txt": b"target",
                "new-program-file.txt": b"new",
            }
            for relative, payload in required_files.items():
                target = remote / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            shutil_targets = (
                "03_update_from_github.bat",
                "tools/update/Stop-KfpsProcesses.ps1",
                "tools/update/Replace-NativeLauncher.ps1",
                "tools/update/UpdatePathSafety.psm1",
            )
            for relative in shutil_targets:
                target = remote / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            subprocess.run(["git", "add", "."], cwd=remote, check=True)
            subprocess.run(["git", "commit", "-m", "target"], cwd=remote, check=True, capture_output=True)

            outer = root / "install"
            app_root = outer / "KloudysFH6Painter"
            for directory in ("KFPS.UI", "assets", "settings"):
                (app_root / directory).mkdir(parents=True, exist_ok=True)
            old_files = {
                "VERSION": b"1.0.0\n",
                "KFPS.exe": b"old-app-launcher",
                "fh6_probe.py": b"# old\n",
                "generator_backend.py": b"# old\n",
                "KloudysGalateaGenesis.exe": b"old-generator",
                "old-program-file.txt": b"old",
            }
            for relative, payload in old_files.items():
                (app_root / relative).write_bytes(payload)
            (app_root / "03_update_from_github.bat").write_bytes((ROOT / "03_update_from_github.bat").read_bytes())
            (outer / "KFPS.exe").write_bytes(b"old-parent-launcher")

            environment = os.environ.copy()
            environment.update(
                {
                    "KFPS_ALLOW_CUSTOM_UPDATE_SOURCE": "1",
                    "REPO_URL": str(remote),
                    "BRANCH": "main",
                    "KFPS_UPDATER_ROOT": str(app_root),
                    "FORZA_PAINTER_NO_PAUSE": "1",
                    "LOCALAPPDATA": str(root / "local-app-data"),
                    "TEMP": str(root / "temp"),
                    "TMP": str(root / "temp"),
                }
            )
            (root / "temp").mkdir()
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", str(app_root / "03_update_from_github.bat")],
                cwd=app_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(b"1.0.0\n", (app_root / "VERSION").read_bytes(), result.stdout + result.stderr)
            self.assertEqual(b"old-app-launcher", (app_root / "KFPS.exe").read_bytes())
            self.assertEqual(b"old-parent-launcher", (outer / "KFPS.exe").read_bytes())
            self.assertTrue((app_root / "old-program-file.txt").is_file())
            self.assertFalse((app_root / "new-program-file.txt").exists())
            self.assertIn("Previous program files restored", result.stdout)


if __name__ == "__main__":
    unittest.main()
