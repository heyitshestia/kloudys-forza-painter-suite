"""Manifest runtime lookup and installation validation are different contracts."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.editor_manifest import MANIFEST, editor_web_root, load_manifest, native_source


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "runtime/test-runs/editor-modernization-2026-09-12/runs")
        self.root = Path(self.temp.name)
        self.path = self.root / MANIFEST.relative_to(ROOT)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = load_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_runtime_metadata_does_not_require_main_ui_or_full_source(self):
        self.write(self.data)
        self.assertEqual(self.root / self.data["web_root"], editor_web_root(self.root))
        self.assertEqual(self.root / next(row["path"] for row in self.data["native"] if row["role"] == "host"), native_source("host", self.root))
        with self.assertRaisesRegex(ValueError, "Missing editor source"):
            load_manifest(self.root)

    def test_unknown_and_ambiguous_roles_fail(self):
        self.write(self.data)
        with self.assertRaises(ValueError):
            native_source("nonexistent", self.root)
        duplicate = copy.deepcopy(self.data)
        duplicate["native"].append({"path": "other.py", "owner": "O18", "role": "host"})
        self.write(duplicate)
        with self.assertRaises(ValueError):
            native_source("host", self.root)

    def test_unsafe_roots_entries_and_changed_mount_fail_without_file_access(self):
        for section, value in (("web_root", "../private"), ("profile", "C:/private"), ("legacy_web_mount", "/new/")):
            data = copy.deepcopy(self.data); data[section] = value; self.write(data)
            with self.subTest(section=section), self.assertRaises(ValueError):
                load_manifest(self.root, verify_files=False)
        for value in ("../private", "C:/private", "\\private", "", "file\x00name"):
            data = copy.deepcopy(self.data); data["web"][0]["path"] = value; self.write(data)
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_manifest(self.root, verify_files=False)


if __name__ == "__main__":
    unittest.main()
