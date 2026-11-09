from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kfps_ui import garage_catalogue as catalogue
from tools.livery import vehicle_assets


def swatch(color=(90, 60, 30, 128), width=4, height=4, premultiplied=True):
    """Synthetic PC RGBA texture, with no game bytes in the test fixture."""
    payload = bytes(color) * width * height
    data = bytearray(140 + len(payload))
    data[:6] = b"burG\x01\x01"
    struct.pack_into("<I", data, 16, 1)
    struct.pack_into("<IBBHIIII", data, 20, 0x54584342, 0, 0, 1, 44, 140, len(payload), len(payload))
    struct.pack_into("<IHH", data, 44, 0x54584348, 88 << 4, 8)
    struct.pack_into("<IIIHBBiiiiII", data, 76, width, height, 1, 1, 1,
                     2 if premultiplied else 0, 0, 0, 0, 0, 64, 0)
    struct.pack_into("<iII", data, 116, 13, 76, 0)
    struct.pack_into("<III", data, 128, len(payload), 0, 0)
    data[140:] = payload
    return bytes(data)


def local_path(url):
    path = unquote(urlparse(url).path)
    return Path(path[1:] if os.name == "nt" else path)


class GarageCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.stripped = self.game / "media/Stripped"
        self.stripped.mkdir(parents=True)
        self.index = self.root / "index.json"
        self.cache = self.root / "cache"
        self.write_index({344: "NIS_FairladyZ_03", 247: "TOY_2000GT_69"})
        self.archive({"Thumbnail_344_Big.swatchbin": swatch(),
                      "thumbnail_247_Big.swatchbin": swatch((10, 20, 30, 255))})
        self.names = patch.object(catalogue, "_titles", return_value={})
        self.names.start()
        self.addCleanup(self.names.stop)

    def write_index(self, cars):
        directory = self.game / "media/cars"
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob("*.zip"):
            path.unlink()
        for ident, model in cars.items():
            with zipfile.ZipFile(directory / (model + ".zip"), "w") as bundle:
                bundle.writestr(f"Scene/clip/carclips_{ident}.clipd", b"synthetic")
        vehicle_assets.load_or_build_vehicle_asset_index(self.game, self.index)

    def archive(self, members, name="RC0.zip"):
        path = self.stripped / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for key, value in members.items():
                bundle.writestr(key, value)
        return path

    def load(self, cancel=None):
        return catalogue.load_catalogue(self.game, self.index, self.cache, cancel)

    def test_exact_ids_and_local_320_by_180_images(self):
        result = self.load()
        self.assertEqual([247, 344], [row["carId"] for row in result["cars"]])
        self.assertIn("2", result["status"])
        for row in result["cars"]:
            self.assertEqual({"carId", "title", "modelCode", "thumbnailUrl"}, set(row))
            path = local_path(row["thumbnailUrl"])
            self.assertTrue(path.resolve().is_relative_to(self.cache.resolve()))
            with Image.open(path) as image:
                image.load()
                self.assertEqual((320, 180), image.size)
        self.assertIn("FairladyZ", result["cars"][1]["title"])

    def test_missing_image_never_uses_another_id_or_saved_artwork(self):
        self.archive({"thumbnail_3440_Big.swatchbin": swatch(),
                      "../Thumbnail_344_Big.swatchbin": swatch(),
                      "0344_guidbm0_Big.webp": b"not stock"})
        self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))

    def test_missing_game_assets_preserves_complete_index(self):
        (self.stripped / "RC0.zip").unlink()
        result = self.load()
        self.assertEqual(2, len(result["cars"]))
        self.assertTrue(all(not row["thumbnailUrl"] for row in result["cars"]))

    def test_missing_or_malformed_indexes_rebuild_automatically(self):
        for raw in (b"{broken", b"[]", b'{"format":"bad"}', b"{}"):
            self.index.write_bytes(raw)
            result = self.load()
            self.assertEqual(2, len(result["cars"]))
            self.assertNotIn(str(self.root), result["status"])
        self.index.unlink()
        self.assertEqual(2, len(self.load()["cars"]))
        self.assertTrue(self.index.is_file())

    def test_index_rejects_mismatched_ids_and_unsafe_models(self):
        payload = {"format": "kfps_fh6_vehicle_asset_index_v1", "vehicles": {
            "344": {"car_id": 247, "model_code": "NIS_FairladyZ_03"}}}
        self.index.write_text(json.dumps(payload))
        self.assertEqual([247, 344], [row["carId"] for row in self.load()["cars"]])
        payload = json.loads(self.index.read_text())
        payload["vehicles"]["344"]["model_code"] = "../../outside"
        self.index.write_text(json.dumps(payload))
        self.assertEqual("NIS_FairladyZ_03", self.load()["cars"][1]["modelCode"])

    def test_malformed_zip_and_texture_are_placeholders(self):
        (self.stripped / "RC0.zip").write_bytes(b"not zip")
        self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))
        self.archive({"Thumbnail_344_Big.swatchbin": b"burGbad"})
        self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))

    def test_duplicate_id_is_ambiguous_not_last_archive_wins(self):
        self.archive({"thumbnail_344_Big.swatchbin": swatch()}, "RC1.zip")
        rows = self.load()["cars"]
        self.assertTrue(rows[0]["thumbnailUrl"])
        self.assertFalse(rows[1]["thumbnailUrl"])

    def test_hires_and_unrelated_archives_are_ignored(self):
        self.archive({"thumbnail_344_Big.swatchbin": b"bad"}, "RC0HiRes.zip")
        self.archive({"thumbnail_344_Big.swatchbin": b"bad"}, "OfflineThumbnails.zip")
        self.assertTrue(all(row["thumbnailUrl"] for row in self.load()["cars"]))

    def test_warm_cache_does_not_decode_and_corruption_recovers(self):
        before = self.load()
        with patch.object(catalogue, "_decode_thumbnail", side_effect=AssertionError("warm decode")):
            self.assertEqual(before, self.load())
        path = local_path(before["cars"][0]["thumbnailUrl"])
        path.write_bytes(b"bad png")
        after = self.load()
        with Image.open(local_path(after["cars"][0]["thumbnailUrl"])) as image:
            image.load()

    def test_source_change_invalidates_url_and_removed_source_is_not_reused(self):
        before = self.load()["cars"][1]["thumbnailUrl"]
        self.archive({"Thumbnail_344_Big.swatchbin": swatch((20, 30, 40, 255))})
        after = self.load()["cars"][1]["thumbnailUrl"]
        self.assertNotEqual(before, after)
        self.assertFalse(local_path(before).exists())
        (self.stripped / "RC0.zip").unlink()
        self.assertFalse(self.load()["cars"][1]["thumbnailUrl"])

    def test_cancellation_before_and_during_decode_and_restart(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            self.load(event)
        self.assertFalse(self.cache.exists())
        event.clear()
        original = catalogue._decode_thumbnail
        def decode(data, **kwargs):
            event.set()
            return original(data, **kwargs)
        with patch.object(catalogue, "_decode_thumbnail", side_effect=decode):
            with self.assertRaises(InterruptedError):
                self.load(event)
        self.assertEqual([], list(self.cache.rglob("*.tmp")))
        event.clear()
        self.assertTrue(all(row["thumbnailUrl"] for row in self.load(event)["cars"]))

    def test_limits_for_index_members_archives_and_disk(self):
        self.index.unlink()
        with patch.object(vehicle_assets, "MAX_INDEX_BYTES", 4):
            self.assertEqual([], self.load()["cars"])
        with patch.object(catalogue, "MAX_CARS", 1):
            self.assertEqual([], self.load()["cars"])
        with patch.object(catalogue, "MAX_ZIP_ENTRIES", 1):
            self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))
        with patch.object(catalogue, "MAX_TEXTURE_BYTES", 32):
            self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))
        with patch.object(catalogue, "MAX_CACHE_BYTES", 1):
            self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))

    def test_game_cache_destination_is_rejected_without_writes(self):
        self.cache = self.game / "cache"
        result = self.load()
        self.assertEqual(2, len(result["cars"]))
        self.assertFalse(self.cache.exists())
        self.assertTrue(all(not row["thumbnailUrl"] for row in result["cars"]))

    def test_cache_failure_retains_catalogue_and_unrelated_files(self):
        self.cache.mkdir()
        keep = self.cache / "personal.txt"
        keep.write_text("leave alone")
        with patch.object(catalogue, "_publish", side_effect=OSError("unavailable")):
            result = self.load()
        self.assertEqual(2, len(result["cars"]))
        self.assertTrue(all(not row["thumbnailUrl"] for row in result["cars"]))
        self.assertEqual("leave alone", keep.read_text())

    def test_index_changes_are_observed(self):
        self.load()
        self.write_index({344: "NIS_FairladyZ_03"})
        self.assertEqual([344], [row["carId"] for row in self.load()["cars"]])

    def test_premultiplied_alpha_is_unpremultiplied_not_darkened(self):
        png = catalogue._decode_thumbnail(swatch((50, 25, 10, 128)))
        with Image.open(io.BytesIO(png)) as image:
            red, green, blue, alpha = image.getpixel((160, 90))
        self.assertTrue(98 <= red <= 100)
        self.assertTrue(48 <= green <= 50)
        self.assertTrue(18 <= blue <= 20)
        self.assertEqual(128, alpha)

    def test_swapped_valid_cache_images_are_not_accepted(self):
        rows = self.load()["cars"]
        first, second = [local_path(row["thumbnailUrl"]) for row in rows]
        before = first.read_bytes()
        first.write_bytes(second.read_bytes())
        self.load()
        self.assertEqual(before, first.read_bytes())

    def test_deadline_is_explicit_and_does_not_write(self):
        with patch.object(catalogue, "MAX_SECONDS", -1):
            result = self.load()
        self.assertIn("limit", result["status"].lower())
        self.assertFalse(self.cache.exists())

    def test_source_replaced_during_warm_open_does_not_return_stale_url(self):
        self.load()
        original = catalogue._archive
        calls = 0
        def open_archive(path, budget):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.archive({"Thumbnail_344_Big.swatchbin": swatch((200, 100, 0, 255))})
            return original(path, budget)
        with patch.object(catalogue, "_archive", side_effect=open_archive):
            result = self.load()
        self.assertTrue(all(not row["thumbnailUrl"] for row in result["cars"]))

    def test_cancellation_predicate_raises_immediately_and_is_not_swallowed(self):
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            return calls == 14
        with self.assertRaises(InterruptedError):
            self.load(cancel)

    def test_oversized_pixels_and_zip_directory_are_rejected(self):
        data = bytearray(swatch())
        struct.pack_into("<II", data, 76, 5000, 5000)
        with self.assertRaises(ValueError):
            catalogue._decode_thumbnail(bytes(data))
        path = self.stripped / "RC0.zip"
        data = bytearray(path.read_bytes())
        end = data.rfind(b"PK\x05\x06")
        struct.pack_into("<I", data, end + 12, 100 * 1024 * 1024)
        path.write_bytes(data)
        self.assertTrue(all(not row["thumbnailUrl"] for row in self.load()["cars"]))

    def test_cache_root_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.cache.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlinks unavailable")
        result = self.load()
        self.assertTrue(all(not row["thumbnailUrl"] for row in result["cars"]))
        self.assertEqual([], list(outside.iterdir()))

    def test_two_workers_share_one_bounded_cache(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.load(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertTrue(all(row["thumbnailUrl"] for row in results[0]["cars"]))
        self.assertEqual(2, len(list(self.cache.rglob("*.png"))))
        self.assertEqual([], list(self.cache.rglob("*.tmp")))

    def test_first_use_defaults_to_index_in_safe_cache_root(self):
        self.index = None
        result = self.load()
        self.assertEqual(2, len(result["cars"]))
        self.assertTrue((self.cache / "vehicle-index.json").is_file())

    def test_other_install_index_and_embedded_wrong_paths_are_rebuilt(self):
        self.load()
        original = self.index.read_bytes()
        other = self.root / "other-game"
        cars = other / "media/cars"
        cars.mkdir(parents=True)
        with zipfile.ZipFile(cars / "NEW_CAR_26.zip", "w") as bundle:
            bundle.writestr("Scene/carclips_123.clipd", b"synthetic")
        result = catalogue.load_catalogue(other, self.index, self.cache)
        self.assertEqual([123], [row["carId"] for row in result["cars"]])
        self.assertNotEqual(original, self.index.read_bytes())
        self.assertEqual([247, 344], [row["carId"] for row in self.load()["cars"]])
        payload = json.loads(self.index.read_text())
        payload["vehicles"]["344"]["archive_path"] = str(cars / "NEW_CAR_26.zip")
        self.index.write_text(json.dumps(payload))
        self.load()
        corrected = json.loads(self.index.read_text())
        self.assertTrue(Path(corrected["vehicles"]["344"]["archive_path"]).is_relative_to(self.game))

    def test_missing_game_never_reuses_another_install_index(self):
        result = catalogue.load_catalogue(self.root / "absent", self.index, self.cache)
        self.assertEqual([], result["cars"])
        self.assertNotIn(str(self.root), result["status"])

    def test_shared_index_cancel_during_build_keeps_previous_file(self):
        before = self.index.read_bytes()
        self.archive({"Thumbnail_344_Big.swatchbin": swatch()})
        path = self.game / "media/cars/EXTRA_CAR_26.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("Scene/carclips_123.clipd", b"synthetic")
        event = threading.Event()
        original = vehicle_assets._car_clip_in_archive
        calls = 0
        def clip(archive, cancel_event=None):
            nonlocal calls
            result = original(archive, cancel_event)
            if archive.name == path.name:
                calls += 1
                if calls == 3:
                    event.set()
            return result
        with patch.object(vehicle_assets, "_car_clip_in_archive", side_effect=clip):
            with self.assertRaises(InterruptedError):
                self.load(event)
        self.assertEqual(before, self.index.read_bytes())
        self.assertEqual([], list(self.root.glob("index.json.*.tmp")))

    def test_shared_index_cancel_before_commit_preserves_previous_file(self):
        before = self.index.read_bytes()
        path = self.game / "media/cars/EXTRA_CAR_26.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("Scene/carclips_123.clipd", b"synthetic")
        event = threading.Event()
        with patch.object(vehicle_assets.os, "fsync", side_effect=lambda _: event.set()):
            with self.assertRaises(InterruptedError):
                self.load(event)
        self.assertEqual(before, self.index.read_bytes())
        self.assertEqual([], list(self.root.glob("index.json.*.tmp")))

    def test_shared_index_parallel_first_use_unique_temporary_files(self):
        from concurrent.futures import ThreadPoolExecutor
        self.index.unlink()
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: vehicle_assets.load_or_build_vehicle_asset_index(
                self.game, self.index), range(2)))
        self.assertEqual(values[0], values[1])
        self.assertEqual(2, len(json.loads(self.index.read_text())["vehicles"]))
        self.assertEqual([], list(self.root.glob("index.json.*.tmp")))

    def test_shared_index_detects_non_newest_archive_changes(self):
        path = self.game / "media/cars/TOY_2000GT_69.zip"
        first = vehicle_assets.load_or_build_vehicle_asset_index(self.game, self.index)
        newer = self.game / "media/cars/NIS_FairladyZ_03.zip"
        os.utime(newer, ns=(newer.stat().st_atime_ns, path.stat().st_mtime_ns + 10**10))
        vehicle_assets.load_or_build_vehicle_asset_index(self.game, self.index)
        stamp = path.stat()
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("Scene/carclips_123.clipd", b"changed synthetic")
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        result = vehicle_assets.load_or_build_vehicle_asset_index(self.game, self.index)
        self.assertEqual({247, 344}, set(first))
        self.assertEqual({123, 344}, set(result))

    def test_names_refresh_installed_catalogue_and_require_exact_identity(self):
        self.names.stop()
        _, cache, names, _, _ = catalogue._studio_imports()
        directory = self.game / "media/stripped/stringtables"
        directory.mkdir(parents=True)
        with zipfile.ZipFile(directory / "EN.zip", "w") as bundle:
            bundle.writestr("Data_Car.str", b"synthetic")
            bundle.writestr("List_CarMake.str", b"synthetic")
        db = sqlite3.connect(":memory:")
        try:
            db.execute("CREATE TABLE Data_Car (Id, MediaName, Year, DisplayName, MakeName)")
            db.execute("INSERT INTO Data_Car VALUES (344, 'nis_fairladyz_03', 2003, 'Fairlady Z', 'Nissan')")
            db.execute("INSERT INTO Data_Car VALUES (247, 'WRONG_MODEL', 1969, 'Wrong car', 'Wrong make')")
            data = db.serialize()
        finally:
            db.close()
        with (patch.object(cache, "load_installed_catalogue", return_value={'database': data}) as acquire,
              patch.object(names, "_parse_strings", return_value={})):
            rows = self.load()["cars"]
            acquire.assert_called_once()
        self.assertEqual("2003 Nissan Fairlady Z", rows[1]["title"])
        self.assertEqual('Nissan', rows[1]['manufacturer'])
        self.assertEqual('Fairlady Z', rows[1]['modelName'])
        self.assertEqual(2003, rows[1]['year'])
        self.assertEqual("TOY 2000GT 69", rows[0]["title"])

    def test_source_signature_detects_new_model_metadata_and_thumbnail_changes(self):
        before = catalogue.catalogue_signature(self.game)
        self.assertEqual(before, catalogue.catalogue_signature(self.game))
        (self.game / 'media/cars/HON_S660_16.zip').write_bytes(b'synthetic new car')
        car = catalogue.catalogue_signature(self.game)
        self.assertNotEqual(before, car)
        (self.stripped / 'gamedbRC.slt').write_bytes(b'synthetic metadata')
        metadata = catalogue.catalogue_signature(self.game)
        self.assertNotEqual(car, metadata)
        self.archive({'Thumbnail_344_Big.swatchbin': swatch((50, 20, 10, 255))})
        self.assertNotEqual(metadata, catalogue.catalogue_signature(self.game))
        with self.assertRaises(InterruptedError):
            catalogue.catalogue_signature(self.game, lambda: True)

    def test_time_limit_during_decode_is_resumable(self):
        with patch.object(catalogue, "_decode_thumbnail", side_effect=catalogue._TimeLimit()):
            result = self.load()
        self.assertEqual(2, len(result["cars"]))
        self.assertIn("limit", result["status"])
        self.assertEqual([], list(self.cache.rglob("*.tmp")))
        self.assertTrue(all(row["thumbnailUrl"] for row in self.load()["cars"]))


if __name__ == "__main__":
    unittest.main()
