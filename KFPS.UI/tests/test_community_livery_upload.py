from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(UI.parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
APP = QApplication.instance() or QApplication([])

from kfps_ui import community_livery_upload as upload
from kfps_ui.community_preview_service import inspect_file
from test_full_livery_package import build_package, rewrite_package, validate_full_livery_package


class CommunityLiveryUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "original.kfpslivery"
        build_package(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def changed(self, changes, *, update_hashes=True):
        path = self.root / "changed.kfpslivery"
        def transform(entries):
            entries.update(changes)
            if update_hashes:
                manifest = json.loads(entries["manifest.json"])
                records = {record["path"]: record for record in manifest["files"]}
                for name, data in changes.items():
                    records.setdefault(name, {"path": name, "role": "fixture"}).update(
                        size=len(data), sha256=hashlib.sha256(data).hexdigest())
                manifest["files"] = list(records.values())
                entries["manifest.json"] = json.dumps(manifest).encode()
        rewrite_package(self.source, path, transform)
        return path

    def test_compatible_package_remains_byte_identical(self):
        original = self.source.read_bytes()
        manifest, payload = upload.prepare_livery_upload(self.source)
        self.assertEqual(payload, original)
        self.assertEqual(manifest, validate_full_livery_package(self.source))
        self.assertEqual(self.source.read_bytes(), original)

    def test_real_upload_preparation_compacts_existing_indented_packages(self):
        with zipfile.ZipFile(self.source) as bundle:
            layers = bundle.read(upload.LAYERS)
        path = self.changed({upload.LAYERS: layers + b" " * (upload.MAX_MEMBER_BYTES + 1)})
        original = path.read_bytes()
        result = inspect_file(path, self.root / "state")
        target = self.root / "prepared.kfpslivery"
        target.write_bytes(result["payload"])
        manifest = validate_full_livery_package(target)
        with zipfile.ZipFile(path) as before, zipfile.ZipFile(target) as after:
            self.assertEqual(before.namelist(), after.namelist())
            self.assertGreater(before.getinfo(upload.LAYERS).file_size, upload.MAX_MEMBER_BYTES)
            self.assertLess(after.getinfo(upload.LAYERS).file_size, upload.MAX_MEMBER_BYTES)
            for name in before.namelist():
                if name == "manifest.json":
                    expected = json.loads(before.read(name))
                    expected["files"] = manifest["files"]
                    self.assertEqual(expected, manifest)
                elif name == upload.LAYERS:
                    self.assertEqual(json.loads(before.read(name)), json.loads(after.read(name)))
                else:
                    self.assertEqual(before.read(name), after.read(name), name)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list((self.root / "state/staging").iterdir()), [])
        self.assertEqual(upload.prepare_livery_upload(target)[1], result["payload"])

    def test_integrity_failure_is_not_repaired_by_compaction(self):
        with zipfile.ZipFile(self.source) as bundle:
            layers = bundle.read(upload.LAYERS)
        path = self.changed({upload.LAYERS: layers + b" " * (upload.MAX_MEMBER_BYTES + 1)},
                            update_hashes=False)
        with self.assertRaisesRegex(Exception, "integrity check"):
            upload.prepare_livery_upload(path)

    def test_non_json_members_are_not_downscaled_or_dropped(self):
        path = self.changed({"preview/large.png": b"x" * (upload.MAX_MEMBER_BYTES + 1)})
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, r"preview/large.png.*after unpacking.*8 MiB"):
            upload.prepare_livery_upload(path)
        self.assertEqual(path.read_bytes(), before)

    def test_compact_layers_must_still_fit(self):
        with patch.object(upload, "MAX_MEMBER_BYTES", 64):
            with self.assertRaisesRegex(ValueError, "livery/layers.json.*after unpacking"):
                upload.prepare_livery_upload(self.source)

    def test_aggregate_limit_remains_enforced(self):
        path = self.changed({"preview/one.png": b"x" * 600_000,
                             "preview/two.png": b"x" * 600_000})
        with patch.object(upload, "MAX_EXPANDED_BYTES", 1024 * 1024):
            with self.assertRaisesRegex(ValueError, "complete package.*limit 1 MiB"):
                upload.prepare_livery_upload(path)

    def test_compressed_limit_is_checked_before_decode(self):
        with patch.object(upload, "MAX_PACKAGE_BYTES", 1), patch.object(upload, "validate_full_livery_package") as decode:
            with self.assertRaisesRegex(ValueError, "16 MiB"):
                upload.prepare_livery_upload(self.source)
            decode.assert_not_called()

    def test_corrupt_archive_rejected(self):
        self.source.write_bytes(b"not a ZIP")
        with self.assertRaises(Exception):
            upload.prepare_livery_upload(self.source)


if __name__ == "__main__":
    unittest.main()
