"""Offline baseline faults; fixtures never touch an installed runtime/profile."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor import baseline

ENGINE = {"python": "3.12.10", "bits": 64, "pyside": "6.11.1", "qt": "6.11.1",
          "webengine": "6.11.1", "chromium": "140.0.7339.225"}


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = ["python/python.exe", "python/Lib/site-packages/engine.dll",
                      "KFPS.Editor/editor.py", "KFPS.Editor/manifest.json",
                      "KFPS.Editor/src/kfps_editor/host.py", "KFPS.Editor/web/index.html",
                      "KFPS.Editor/web/vendor/fabric.min.js"]
        for relative in self.files:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture:" + relative)
        self.contract = {"schema": baseline.SCHEMA, "engine": ENGINE, "files": [
            {"path": p, "size": (self.root / p).stat().st_size,
             "sha256": baseline.file_hash(self.root / p)} for p in self.files]}
        self.write()

    def write(self):
        (self.root / baseline.CONTRACT).write_text(json.dumps(self.contract))

    def verify(self, **kwargs):
        return baseline.verify(self.root, executable=kwargs.pop("executable", self.root / "python/python.exe"),
                               identity=kwargs.pop("identity", ENGINE), isolated=kwargs.pop("isolated", True), **kwargs)

    def test_exact_offline_baseline(self):
        report = self.verify()
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["files"], len(self.files))
        self.assertEqual(report["baseline"], hashlib.sha256((self.root / baseline.CONTRACT).read_bytes()).hexdigest())

    def test_missing_record_is_not_release(self):
        (self.root / baseline.CONTRACT).unlink()
        with self.assertRaises(baseline.BaselineError): self.verify()

    def test_real_source_is_explicitly_development(self):
        self.assertTrue(baseline.development_root(ROOT))
        (self.root / baseline.CONTRACT).unlink()
        (self.root / ".git").mkdir()
        self.assertEqual(self.verify()["status"], "development")

    def test_stage_marker_alone_does_not_bypass(self):
        (self.root / baseline.CONTRACT).unlink()
        (self.root / "editor-stage.json").write_text("{}")
        # The runner may place TEMP inside a real checkout's test-runs tree.
        # Model an installed layout with no checkout ancestor, not that deliberate
        # development exception. Keep all fixture files and verification real.
        exists = Path.exists
        with patch.object(Path, "exists", lambda path: False if path.name == ".git" else exists(path)):
            self.assertFalse(baseline.development_root(self.root))
            with self.assertRaises(baseline.BaselineError): self.verify()

    def test_wrong_interpreter_or_isolation(self):
        for args in ({"executable": self.root / "other/python.exe"}, {"isolated": False}):
            with self.subTest(args=args), self.assertRaises(baseline.BaselineError): self.verify(**args)

    def test_engine_mismatch(self):
        for field in ENGINE:
            with self.subTest(field=field), self.assertRaises(baseline.BaselineError):
                self.verify(identity={**ENGINE, field: "wrong"})

    def test_each_file_missing_and_same_length_corruption(self):
        for relative in self.files:
            path = self.root / relative
            original = path.read_bytes()
            with self.subTest(file=relative, fault="missing"):
                path.unlink()
                with self.assertRaises(baseline.BaselineError): self.verify()
            path.write_bytes(b"x" * len(original))
            with self.subTest(file=relative, fault="same length"):
                with self.assertRaises(baseline.BaselineError): self.verify()
            path.write_bytes(original)

    def test_extra_files_in_each_program_tree(self):
        for tree in ("python", "KFPS.Editor/web", "KFPS.Editor/src"):
            path = self.root / tree / "stale.py"
            path.write_text("stale")
            with self.subTest(tree=tree), self.assertRaises(baseline.BaselineError): self.verify()
            path.unlink()

    def test_profiles_never_count_as_program_files(self):
        path = self.root / "runtime/fabric-editor/projects/private.json"
        path.parent.mkdir(parents=True)
        path.write_text("keep me")
        self.assertEqual(self.verify()["status"], "verified")
        self.assertEqual(path.read_text(), "keep me")

    def test_generated_bytecode_does_not_force_repairs(self):
        path = self.root / "python/__pycache__/module.cpython-312.pyc"
        path.parent.mkdir()
        path.write_bytes(b"cache")
        self.assertEqual(self.verify()["status"], "verified")

    def test_invalid_record_variants(self):
        saved = json.loads(json.dumps(self.contract))
        for record in ({"path": "../private", "size": 0, "sha256": "0" * 64},
                       {"path": "C:/private", "size": 0, "sha256": "0" * 64},
                       {"path": "python//python.exe", "size": 0, "sha256": "0" * 64},
                       {"path": "python/python.exe", "size": True, "sha256": "bad"},
                       saved["files"][0]):
            self.contract = {**saved, "files": [*saved["files"], record]}
            self.write()
            with self.subTest(record=record), self.assertRaises(baseline.BaselineError): self.verify()

    def test_missing_required_inventory(self):
        self.contract["files"] = self.contract["files"][1:]
        self.write()
        with self.assertRaises(baseline.BaselineError): self.verify()

    def test_bad_json_schema_or_size(self):
        for payload in (b"{", b"[]", b'{"schema":"bad"}'):
            (self.root / baseline.CONTRACT).write_bytes(payload)
            with self.subTest(payload=payload), self.assertRaises(baseline.BaselineError): self.verify()
        self.write()
        with patch.object(baseline, "MAX_CONTRACT_BYTES", 8), self.assertRaises(baseline.BaselineError): self.verify()

    def test_environment_isolation_is_idempotent(self):
        source = {"PATH": "keep", "QTWEBENGINEPROCESS_PATH": "wrong", "QT_SCALE_FACTOR": "3",
                  "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu", "PYTHONPATH": "wrong",
                  "PYTHONHOME": "wrong", "QML2_IMPORT_PATH": "wrong", "LOCALAPPDATA": "keep"}
        result = baseline.isolated_environment(source)
        self.assertEqual(result, {"PATH": "keep", "LOCALAPPDATA": "keep", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result, baseline.isolated_environment(result))
        self.assertIn("QT_SCALE_FACTOR", source)

    def test_launch_ignores_system_override_and_requires_local(self):
        with patch.dict("os.environ", {"KFPS_PYTHON": "elsewhere", "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"}):
            args, env = baseline.launch_command(self.root, self.root / "KFPS.Editor/editor.py", ["--mode", "new"])
        self.assertEqual(args[:3], [str(self.root / "python/python.exe"), "-I", "-B"])
        self.assertEqual(args[3], "-X")
        self.assertIn("pycache_prefix=", args[4])
        self.assertFalse(Path(args[4].split("=", 1)[1]).exists())
        self.assertNotIn("QTWEBENGINE_CHROMIUM_FLAGS", env)
        (self.root / "python/python.exe").unlink()
        with self.assertRaises(baseline.BaselineError): baseline.managed_python(self.root)


if __name__ == "__main__": unittest.main()
