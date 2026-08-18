from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "release"))

from build_release_bundles import build_one, commit_timestamp, read_version, resolve_commit


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
            bundle_path = build_one(
                repo,
                output,
                commit=commit,
                version="9.8.7",
                timestamp=commit_timestamp(repo, commit),
                kind="recommended",
                python_source=runtime,
            )
            with zipfile.ZipFile(bundle_path) as bundle:
                self.assertIn("KFPS-9.8.7/KloudysFH6Painter/python/python.exe", bundle.namelist())
                self.assertIn("KFPS-9.8.7/KloudysFH6Painter/python/dependency.pyd", bundle.namelist())


if __name__ == "__main__":
    unittest.main()
