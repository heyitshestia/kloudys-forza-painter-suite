"""Equal, fail-closed Studio handoff preflight; no UI or live saves."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/tests"),
               str(ROOT / "tools/livery-studio/src")]

from kfps_livery_lab import package_handoff as handoff
from kfps_livery_lab.save_codec import SaveTemplate
from tools.livery.fh6_save_installer import build_destination_header, parse_fh6_header
from test_studio_package_handoff import make_package


class HandoffPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kfps-handoff-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / "fixture.kfpslivery"
        self.source = self.root / "C_livery"
        self.header = self.root / "header"
        self.snapshots = self.root / "snapshots"
        self.snapshots.mkdir()
        self.vehicle = {"car_id": 3307, "model_code": "TEST_CAR"}
        self.fixture()

    def fixture(self, **options):
        make_package(self.package, **options)
        with zipfile.ZipFile(self.package) as archive:
            self.source.write_bytes(archive.read("source/fh6/C_livery"))
            self.header.write_bytes(archive.read("source/fh6/header"))

    def rewrite_header(self, body):
        if body is None:
            self.header.unlink()
        else:
            self.header.write_bytes(body)
        with zipfile.ZipFile(self.package) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        if body is None:
            entries.pop("source/fh6/header")
        else:
            entries["source/fh6/header"] = body
        manifest = json.loads(entries["manifest.json"])
        manifest["files"] = [
            {"path": name, "role": "fixture", "size": len(data),
             "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(entries.items()) if name != "manifest.json"]
        entries["manifest.json"] = json.dumps(manifest).encode()
        with zipfile.ZipFile(self.package, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def open_save(self, expected=""):
        return handoff.request_for_save(self.source, self.vehicle, expected)

    def open_package(self, expected=""):
        return handoff.request_for_package(self.package, self.snapshots, expected)

    def assert_both_reject(self, reason=None):
        for opener in (self.open_save, self.open_package):
            with self.subTest(route=opener.__name__):
                with self.assertRaises(ValueError) as caught:
                    opener()
                message = str(caught.exception)
                self.assertNotIn(str(self.root), message)
                self.assertNotIn("TEST0001", message)
                if reason:
                    self.assertRegex(message, reason)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_owned_nested_artwork_is_identical_through_both_routes(self):
        original = {path: path.read_bytes() for path in (self.source, self.header, self.package)}
        direct = self.open_save(hashlib.sha256(original[self.source]).hexdigest())
        packaged = self.open_package(hashlib.sha256(original[self.package]).hexdigest())
        self.assertEqual(direct["layout"], packaged["layout"])
        shapes = direct["layout"]["vinyls"][0]["shapes"]
        self.assertEqual([len(s.get("editor_group_path", [])) for s in shapes], [2, 2, 1, 0])
        self.assertEqual(original, {path: path.read_bytes() for path in original})
        self.assertNotIn(str(self.root), json.dumps(direct))

    def test_both_require_matching_header_creator_car_and_count(self):
        for change in ({"creator_tag": b"OTHER001"}, {"car_id": 99}, {"placement_count": 4}):
            with self.subTest(change=change):
                fields = dict(title="Fixture", creator_tag=b"TEST0001", creator_name="Fixture",
                              car_id=3307, placement_count=5, now=datetime.now(timezone.utc))
                fields.update(change)
                self.rewrite_header(build_destination_header(**fields))
                self.assert_both_reject("header")

    def test_missing_truncated_oversized_and_invalid_headers_fail_closed(self):
        for body in (None, b"x", b"x" * 65537, b"\0" * 160):
            with self.subTest(size=None if body is None else len(body)):
                self.fixture()
                self.rewrite_header(body)
                self.assert_both_reject()

    def test_only_saved_and_base_header_records_are_accepted(self):
        original = self.header.read_bytes()
        tag_start = original.index(b"TEST0001")
        for kind in (4, 5, 0, 0xffffffff):
            with self.subTest(kind=kind):
                header = bytearray(original)
                struct.pack_into("<I", header, tag_start - 4, kind)
                self.rewrite_header(bytes(header))
                if kind == 4:
                    self.assertEqual(self.open_save()["layout"], self.open_package()["layout"])
                else:
                    self.assert_both_reject("header")

    def test_raster_error_is_specific_and_actionable_in_both_routes(self):
        self.fixture(raster=True)
        self.assert_both_reject(r"raster decals.*[Rr]emove.*in.game")

    def test_raster_does_not_override_creator_validation(self):
        self.fixture(raster=True)
        self.rewrite_header(build_destination_header(title="Fixture", car_id=3307,
            creator_tag=b"OTHER001", creator_name="Fixture", placement_count=5,
            now=datetime.now(timezone.utc)))
        self.assert_both_reject("header")

    def test_protected_sources_still_fail_closed(self):
        self.fixture(protected=True)
        self.assert_both_reject()

    def test_expected_fingerprints_still_reject_stale_artwork(self):
        for opener in (self.open_save, self.open_package):
            with self.subTest(route=opener.__name__), self.assertRaisesRegex(ValueError, "changed"):
                opener("0" * 64)

    def test_header_hardlink_is_rejected_before_decoding(self):
        os.link(self.header, self.root / "linked-header")
        with patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded unsafe pair")):
            with self.assertRaises(ValueError):
                self.open_save()

    def test_header_reparse_checks_do_not_require_os_symlink_privileges(self):
        for method in ("is_symlink", "is_junction"):
            if not hasattr(Path, method):
                continue
            original = getattr(Path, method)
            with self.subTest(method=method), patch.object(
                    Path, method, lambda path: path == self.header or original(path)), \
                    patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded redirected pair")):
                with self.assertRaisesRegex(ValueError, "Redirected"):
                    self.open_save()

    def test_source_bounds_and_empty_header_are_checked_before_decoding(self):
        for path, content in ((self.source, b""), (self.header, b"")):
            original = path.read_bytes()
            path.write_bytes(content)
            with self.subTest(path=path.name), patch.object(
                    SaveTemplate, "read", side_effect=AssertionError("decoded empty pair")):
                with self.assertRaises(ValueError):
                    self.open_save()
            path.write_bytes(original)
        with patch.object(handoff, "MAX_PAYLOAD", self.source.stat().st_size - 1), \
                patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded oversized pair")):
            with self.assertRaises(ValueError):
                self.open_save()

    def test_unreadable_header_is_private_and_releases_reader_slot(self):
        original = Path.open

        def opened(path, *args, **kwargs):
            if path == self.header:
                raise PermissionError(str(self.header))
            return original(path, *args, **kwargs)

        for _ in range(3):
            with patch.object(Path, "open", opened), self.assertRaises(ValueError) as caught:
                self.open_save()
            self.assertNotIn(str(self.root), str(caught.exception))
        self.assertEqual(self.open_save()["layout"], self.open_package()["layout"])

    def test_redirected_header_is_rejected_before_decoding(self):
        real = self.root / "original-header"
        self.header.rename(real)
        try:
            self.header.symlink_to(real)
        except OSError:
            self.skipTest("Symlinks require Windows developer mode or privilege")
        with patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded unsafe pair")):
            with self.assertRaises(ValueError):
                self.open_save()

    @contextmanager
    def after_read(self, watched, callback):
        original = Path.open

        class ObservedStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def fileno(self):
                return self.stream.fileno()

            def read(self, *args):
                body = self.stream.read(*args)
                callback()
                return body

        def opened(path, mode="r", *args, **kwargs):
            stream = original(path, mode, *args, **kwargs)
            return ObservedStream(stream) if path == watched and mode == "rb" else stream

        with patch.object(Path, "open", opened):
            yield

    @staticmethod
    def change_stamp(path):
        current = path.stat()
        os.utime(path, ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000_000))

    def test_pair_races_cover_each_file_while_the_other_is_read(self):
        for watched, changed in ((self.source, self.header), (self.header, self.source)):
            with self.subTest(watched=watched.name), \
                    self.after_read(watched, lambda: self.change_stamp(changed)), \
                    patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded unstable pair")):
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.open_save()

    def test_header_growth_during_artwork_read_is_bounded_and_rejected(self):
        def grow():
            with self.header.open("ab") as stream:
                stream.write(b"x" * 65537)

        with self.after_read(self.source, grow), \
                patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded grown header")):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.open_save()

    def test_late_package_mutation_after_descriptor_check_is_rejected(self):
        original = os.fstat
        calls = 0

        def fstat(fd):
            nonlocal calls
            result = original(fd)
            calls += 1
            if calls == 2:
                self.change_stamp(self.package)
            return result

        with patch.object(handoff.os, "fstat", fstat), \
                patch.object(SaveTemplate, "read", side_effect=AssertionError("decoded unstable package")):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.open_package()


@unittest.skipUnless(os.environ.get("KFPS_TEST_PRIVATE_CORPUS") == "1", "Private corpus is opt-in")
class PrivateCorpusPreflightTests(unittest.TestCase):
    def test_verified_copied_saves_and_package(self):
        corpus = ROOT / "runtime/studio-completion-20261111/corpus"
        manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8-sig"))
        records = manifest["records"]
        files = {}
        for record in records:
            path = Path(record["copy"])
            self.assertTrue(path.is_relative_to(corpus / "inputs"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            files[path] = record["sha256"]
        checked = 0
        alignment = None
        for source in files:
            if source.name != "C_livery":
                continue
            header = source.with_name("header")
            self.assertIn(header, files)
            metadata = parse_fh6_header(header.read_bytes())
            vehicle = {"car_id": metadata.car_id, "model_code": "COPIED_CAR"}
            try:
                template = SaveTemplate.read(source.read_bytes(), metadata.car_id)
            except ValueError:
                with self.assertRaises(ValueError):
                    handoff.request_for_save(source, vehicle, files[source])
                checked += 1
                continue
            if template.payload[34:42] != metadata.creator_tag:
                with self.assertRaisesRegex(ValueError, "header"):
                    handoff.request_for_save(source, vehicle, files[source])
            elif metadata.title == "GR86 CC - Final":
                with self.assertRaisesRegex(ValueError, r"raster decals.*[Rr]emove.*in.game"):
                    handoff.request_for_save(source, vehicle, files[source])
            else:
                result = handoff.request_for_save(source, vehicle, files[source])
                self.assertEqual(sum(len(v["shapes"]) for v in result["layout"]["vinyls"]), metadata.type_value)
                if metadata.title == "AlignmenttestNissan":
                    alignment = source
            checked += 1
        self.assertGreaterEqual(checked, 11)
        self.assertIsNotNone(alignment)
        package_record = json.loads((corpus / "qualification.json").read_text())["packages"][0]
        package = corpus / "packages" / package_record["file"]
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), package_record["sha256"])
        with tempfile.TemporaryDirectory(prefix="kfps-corpus-preflight-") as snapshots:
            packaged = handoff.request_for_package(package, snapshots, package_record["sha256"])
        direct = handoff.request_for_save(alignment, packaged["layout"]["vehicle"], files[alignment])
        self.assertEqual(direct["layout"], packaged["layout"])
        for path, digest in files.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), package_record["sha256"])


if __name__ == "__main__":
    unittest.main()
