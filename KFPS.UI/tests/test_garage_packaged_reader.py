"""Installed Garage worker contract; no game installation or player data needed."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = ROOT / "tools" / "garage-reader"
sys.path.insert(0, str(ROOT / "KFPS.UI" / "src"))
from kfps_ui import garage_reader
from kfps_ui.garage_index import GarageError


class PackagedReaderTests(unittest.TestCase):
    def test_synthetic_format_contract_in_isolated_child(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).with_name("garage_worker_cases.py"))],
                                capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))

    def test_release_policy_requires_complete_worker(self):
        spec = importlib.util.spec_from_file_location("garage_policy_test", ROOT / "tools/release/garage_release_policy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(1, module.validate_packaged_garage(ROOT)["schema"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module.validate_packaged_garage(root)
            marker = root / "KFPS.UI/src/kfps_ui/garage_reader.py"
            marker.parent.mkdir(parents=True)
            marker.write_text("# worker client")
            with self.assertRaises(RuntimeError):
                module.validate_packaged_garage(root)

    def test_checks_do_not_generate_untracked_bytecode(self):
        for entrypoint in ("reader.py", "catalogue.py"):
            result = subprocess.run([sys.executable, "-I", str(SUPPORT / entrypoint), "--check"],
                                    capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode)
            self.assertEqual({"ready": True}, json.loads(result.stdout))
        script = "import runpy,sys; runpy.run_path(sys.argv[1])['validate_packaged_garage'](sys.argv[2])"
        result = subprocess.run([sys.executable, "-I", "-c", script,
                                 str(ROOT / "tools/release/garage_release_policy.py"), str(ROOT)],
                                capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        self.assertFalse(list(SUPPORT.rglob("__pycache__")))

    def test_timeout_and_launch_failure_are_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "slow.py"
            script.write_text("import time; time.sleep(30)")
            processes = []
            original = subprocess.Popen
            def capture(*args, **kwargs):
                process = original(*args, **kwargs)
                processes.append(process)
                return process
            command = [sys.executable, "-I", "-B", str(script)]
            with patch.object(garage_reader, "_reader_command", return_value=command), \
                 patch.object(garage_reader, "READER_TIMEOUT", .05), \
                 patch.object(subprocess, "Popen", side_effect=capture), self.assertRaisesRegex(GarageError, "resource limit"):
                garage_reader.reader_records(root / "C_ProfileData", b"sample", root / "reader.json", threading.Event())
            self.assertTrue(processes and all(p.poll() is not None for p in processes))
            with patch.object(subprocess, "Popen", side_effect=OSError("private path")), self.assertRaisesRegex(GarageError, "could not start"):
                garage_reader.reader_records(root / "C_ProfileData", b"sample", root / "reader.json", threading.Event())

    def test_command_uses_app_owned_isolated_runtime(self):
        command = garage_reader._reader_command()
        self.assertEqual(["-I", "-B"], command[1:3])
        self.assertEqual(SUPPORT / "reader.py", Path(command[3]))
        self.assertEqual("--stdin", command[4])

    def test_installation_check_and_malformed_input_are_quiet(self):
        command = garage_reader._reader_command()
        result = subprocess.run(command[:-1] + ["--check"], capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        self.assertEqual({"ready": True}, json.loads(result.stdout))
        self.assertEqual(b"", result.stderr)
        for data in (b"", b"damaged profile", b"[]"):
            with self.subTest(data=data):
                result = subprocess.run(command, input=data, capture_output=True, timeout=30)
                self.assertEqual(2, result.returncode)
                self.assertEqual((b"", b""), (result.stdout, result.stderr))

    def test_catalogue_entrypoint_checks_and_rejects_bad_input(self):
        command = garage_reader._reader_command()
        command[3] = str(SUPPORT / "catalogue.py")
        checked = subprocess.run(command[:-1] + ["--check"], capture_output=True, timeout=30)
        self.assertEqual((0, b""), (checked.returncode, checked.stderr))
        self.assertEqual({"ready": True}, json.loads(checked.stdout))
        for data in (b"", b"bad catalogue", bytes(36 + 128 * 1024 + 16)):
            with self.subTest(size=len(data)):
                result = subprocess.run(command, input=data, capture_output=True, timeout=30)
                self.assertEqual((2, b"", b""), (result.returncode, result.stdout, result.stderr))

    def test_old_config_is_never_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "EXECUTED"
            legacy = root / "old.py"
            legacy.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()")
            config = root / "reader.json"
            config.write_text(json.dumps({"python": sys.executable, "script": str(legacy)}))
            with self.assertRaises(GarageError):
                garage_reader.reader_records(root / "C_ProfileData", b"bad", config, threading.Event())
            self.assertFalse(marker.exists())

    def test_distribution_rejects_missing_changed_and_extra_files(self):
        spec = importlib.util.spec_from_file_location("garage_distribution_test", SUPPORT / "distribution.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Garage support"
            shutil.copytree(SUPPORT, root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            module.verify(root)
            target = root / "profile_reader.py"
            original = target.read_bytes()
            target.write_bytes(original + b"\n# altered\n")
            with self.assertRaises(module.DistributionError):
                module.verify(root)
            target.write_bytes(original)
            target.unlink()
            with self.assertRaises(module.DistributionError):
                module.verify(root)
            target.write_bytes(original)
            dependency = root / "vendor" / "_cffi_backend.cp312-win_amd64.pyd"
            self.assertTrue(dependency.is_file())
            saved = dependency.read_bytes()
            dependency.unlink()
            with self.assertRaises(module.DistributionError):
                module.verify(root)
            command = [sys.executable, "-I", "-B", str(root / "reader.py"), "--check"]
            result = subprocess.run(command, capture_output=True, timeout=30)
            self.assertEqual((3, b"", b""), (result.returncode, result.stdout, result.stderr))
            dependency.write_bytes(saved)
            module.verify(root)
            (root / "unexpected.py").write_text("pass")
            with self.assertRaises(module.DistributionError):
                module.verify(root)


if __name__ == "__main__":
    unittest.main()
