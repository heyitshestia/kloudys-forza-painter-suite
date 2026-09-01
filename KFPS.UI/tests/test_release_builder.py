from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "release"))

from build_release_bundles import (
    build_one,
    commit_timestamp,
    read_version,
    resolve_commit,
    synchronize_python_runtime,
    validate_python_distribution_records,
)


def run(*command: str, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


class ReleaseBuilderTests(unittest.TestCase):
    def make_repo(self, root: Path) -> tuple[Path, str]:
        repo = root / "repo"
        repo.mkdir()
        run("git", "init", cwd=repo)
        run("git", "config", "user.email", "release-tests@example.invalid", cwd=repo)
        run("git", "config", "user.name", "Release Tests", cwd=repo)
        (repo / "VERSION").write_text("9.8.7\n", encoding="ascii")
        (repo / "KFPS.exe").write_bytes(b"launcher")
        (repo / "app.py").write_text("print('KFPS')\n", encoding="ascii")
        logo = repo / "assets" / "app" / "KFPS Logo.json"
        logo.parent.mkdir(parents=True)
        logo.write_text('{"shapes": []}\n', encoding="ascii")
        (repo / "runtime").mkdir()
        (repo / "runtime" / "private.log").write_text("private", encoding="ascii")
        run("git", "add", "VERSION", "KFPS.exe", "app.py", "assets/app/KFPS Logo.json", cwd=repo)
        run("git", "commit", "-m", "fixture", cwd=repo)
        return repo, resolve_commit(repo, "HEAD")

    def test_advanced_bundle_is_reproducible_and_tracked_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, commit = self.make_repo(root)
            timestamp = commit_timestamp(repo, commit)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first = build_one(
                repo,
                first_dir,
                commit=commit,
                version=read_version(repo, commit),
                timestamp=timestamp,
                kind="advanced",
                python_source=None,
            )
            second = build_one(
                repo,
                second_dir,
                commit=commit,
                version="9.8.7",
                timestamp=timestamp,
                kind="advanced",
                python_source=None,
            )
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as bundle:
                names = set(bundle.namelist())
                self.assertIn("KFPS-9.8.7/KFPS.exe", names)
                self.assertIn("KFPS-9.8.7/Images/", names)
                self.assertIn("KFPS-9.8.7/KloudysFH6Painter/KFPS.exe", names)
                self.assertIn("KFPS-9.8.7/RELEASE-MANIFEST.json", names)
                self.assertNotIn("KFPS-9.8.7/KloudysFH6Painter/runtime/private.log", names)
                manifest = json.loads(bundle.read("KFPS-9.8.7/RELEASE-MANIFEST.json"))
                self.assertEqual(commit, manifest["commit"])
                self.assertEqual("advanced", manifest["kind"])

    def test_recommended_bundle_requires_and_includes_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, commit = self.make_repo(root)
            output = root / "output"
            output.mkdir()
            with self.assertRaisesRegex(RuntimeError, "requires --python-source"):
                build_one(
                    repo,
                    output,
                    commit=commit,
                    version="9.8.7",
                    timestamp=commit_timestamp(repo, commit),
                    kind="recommended",
                    python_source=None,
                )
            runtime = root / "python"
            runtime.mkdir()
            (runtime / "python.exe").write_bytes(b"python")
            (runtime / "dependency.pyd").write_bytes(b"dependency")
            (runtime / "__pycache__").mkdir()
            (runtime / "__pycache__" / "generated.cpython-312.pyc").write_bytes(b"cache")
            with (
                patch("build_release_bundles.synchronize_python_runtime") as synchronize,
                patch("build_release_bundles.validate_python_runtime") as validate,
            ):
                bundle_path = build_one(
                    repo,
                    output,
                    commit=commit,
                    version="9.8.7",
                    timestamp=commit_timestamp(repo, commit),
                    kind="recommended",
                    python_source=runtime,
                )
            synchronize.assert_called_once()
            validate.assert_called_once()
            with zipfile.ZipFile(bundle_path) as bundle:
                self.assertIn("KFPS-9.8.7/KloudysFH6Painter/python/python.exe", bundle.namelist())
                self.assertIn("KFPS-9.8.7/KloudysFH6Painter/python/dependency.pyd", bundle.namelist())
                self.assertFalse(any(
                    "__pycache__" in name or name.endswith(".pyc") for name in bundle.namelist()
                ))

    def test_distribution_record_validation_rejects_missing_required_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            site_packages = runtime / "Lib" / "site-packages"
            dist_info = site_packages / "example-1.0.dist-info"
            dist_info.mkdir(parents=True)
            (dist_info / "RECORD").write_text(
                "example/__init__.py,,12\nexample/__pycache__/__init__.pyc,,99\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "missing example/__init__.py"):
                validate_python_distribution_records(runtime)

    def test_distribution_record_validation_checks_recorded_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            site_packages = runtime / "Lib" / "site-packages"
            package_file = site_packages / "example" / "__init__.py"
            package_file.parent.mkdir(parents=True)
            package_file.write_bytes(b"first")
            digest = base64.urlsafe_b64encode(hashlib.sha256(b"first").digest()).rstrip(b"=").decode("ascii")
            dist_info = site_packages / "example-1.0.dist-info"
            dist_info.mkdir()
            (dist_info / "RECORD").write_text(
                f"example/__init__.py,sha256={digest},5\n",
                encoding="utf-8",
            )

            validate_python_distribution_records(runtime)
            package_file.write_bytes(b"other")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch for example/__init__.py"):
                validate_python_distribution_records(runtime)

    @patch("build_release_bundles.validate_python_runtime")
    @patch("build_release_bundles.installed_python_distributions")
    @patch("build_release_bundles.subprocess.run")
    def test_runtime_synchronization_force_reinstalls_locked_packages(
        self, run_process, installed, validate
    ):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "python"
            runtime.mkdir()
            python = runtime / "python.exe"
            python.write_bytes(b"python")
            requirements = Path(temporary) / "requirements.lock.txt"
            requirements.write_text("numpy==1.26.4\n", encoding="ascii")
            installed.return_value = {"numpy": "1.26.4", "opencv-python": "4.9.0.80"}

            synchronize_python_runtime(runtime, requirements)

            uninstall_command = run_process.call_args_list[0].args[0]
            self.assertEqual(str(python), uninstall_command[0])
            self.assertIn("--isolated", uninstall_command)
            self.assertEqual(["opencv-python"], uninstall_command[-1:])
            install_command = run_process.call_args_list[1].args[0]
            self.assertIn("--isolated", install_command)
            self.assertIn("--force-reinstall", install_command)
            self.assertIn("--no-deps", install_command)
            validate.assert_called_once_with(runtime.resolve(), requirements)


if __name__ == "__main__":
    unittest.main()
