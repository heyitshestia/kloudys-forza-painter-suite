from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UI / "src"))

from tools.livery import vehicle_assets as assets


def make_archive(path: Path, car_id: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as bundle:
        name = "readme.txt" if car_id is None else f"Scene/clip/carclips_{car_id}.clipd"
        bundle.writestr(name, b"fixture")
    return path


def make_install(root: Path, platform: str) -> tuple[Path, Path]:
    game = root / "ForzaHorizon6"
    content = game / "Content" if platform == "xbox" else game
    make_archive(content / "media" / "Cars" / "TEST_CAR.zip", 3622)
    make_archive(game / "unrelated.zip")
    if content != game:
        make_archive(content / "unrelated.zip")
    return game, content


class FH6VehicleDiscoveryTests(unittest.TestCase):
    def test_install_roots_and_direct_cars_selection_ignore_unrelated_zips(self):
        for platform in ("steam", "xbox"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                game, content = make_install(Path(temp), platform)
                cars = content / "media" / "Cars"
                for selected in (game, content, cars):
                    with self.subTest(selected=str(selected)):
                        self.assertEqual(cars.resolve(), assets.resolve_fh6_cars_dir(selected))
                        normalized = assets.normalize_fh6_game_folder(selected)
                        self.assertEqual(content.resolve(), normalized)
                        self.assertEqual(cars.resolve(), assets.resolve_fh6_cars_dir(normalized))
                        self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(normalized)))

    def test_nested_cars_win_even_if_root_zip_also_contains_a_car_identifier(self):
        for platform in ("steam", "xbox"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                game, content = make_install(Path(temp), platform)
                make_archive(game / "old-car.zip", 999)
                self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(game)))

    def test_direct_archive_folder_remains_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "standalone-car-assets"
            make_archive(root / "car.zip", 3622)
            self.assertEqual(root.resolve(), assets.resolve_fh6_cars_dir(root))
            self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(root)))

    def test_unrelated_zip_alone_is_not_a_game_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_archive(root / "unrelated.zip")
            with self.assertRaises(assets.VehicleAssetError):
                assets.resolve_fh6_cars_dir(root)

    def test_empty_car_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "media" / "Cars").mkdir(parents=True)
            with self.assertRaises(assets.VehicleAssetError):
                assets.load_or_build_vehicle_asset_index(root)

    def test_invalid_archive_reports_the_file_instead_of_linking_zero_cars(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cars = root / "media" / "Cars"
            cars.mkdir(parents=True)
            (cars / "broken-car.zip").write_bytes(b"not a zip")
            with self.assertRaisesRegex(assets.VehicleAssetError, "broken-car.zip"):
                assets.load_or_build_vehicle_asset_index(root)

    def test_unreadable_archive_reports_the_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_archive(root / "blocked-car.zip", 3622)
            with patch.object(assets.zipfile, "ZipFile", side_effect=PermissionError("Access denied")):
                with self.assertRaisesRegex(assets.VehicleAssetError, "blocked-car.zip"):
                    assets.load_or_build_vehicle_asset_index(root)

    def test_mixed_archive_directory_keeps_readable_cars(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_archive(root / "unrelated.zip")
            (root / "broken.zip").write_bytes(b"not a zip")
            make_archive(root / "car.zip", 3622)
            self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(root)))

    def test_clip_paths_support_case_and_backslashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(root / "car.zip", "w") as bundle:
                bundle.writestr(r"Scene\Clip\CARCLIPS_3622.CLIPD", b"fixture")
            self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(root)))

    def test_startup_discovery_prefers_the_selected_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, _ = make_install(root / "steam", "steam")
            xbox, _ = make_install(root / "xbox", "xbox")
            discovered = assets.discover_fh6_game_folder(
                game, drive_roots=[], process_executables=[xbox / "Content" / "ForzaHorizon6.exe"],
                steam_roots=[],
            )
            self.assertEqual(game.resolve(), discovered)

    def test_automatic_discovery_handles_both_platforms_with_root_zips(self):
        for platform in ("steam", "xbox"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                parent = root / "SteamLibrary" / "steamapps" / "common" if platform == "steam" else root / "XboxGames"
                _, content = make_install(parent, platform)
                discovered = assets.discover_fh6_game_folder(
                    drive_roots=[root], process_executables=[], steam_roots=[root / "SteamLibrary"],
                )
                self.assertEqual(content.resolve(), discovered)

    def test_misdirected_empty_cache_is_rebuilt_automatically(self):
        for platform in ("steam", "xbox"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                game, content = make_install(Path(temp), platform)
                cache = Path(temp) / "index.json"
                cache.write_text(json.dumps({
                    "format": "kfps_fh6_vehicle_asset_index_v1",
                    "signature": assets._index_signature(game), "vehicles": {},
                }), encoding="utf-8")
                index = assets.load_or_build_vehicle_asset_index(game, cache)
                self.assertEqual({3622}, set(index))
                saved = json.loads(cache.read_text(encoding="utf-8"))
                self.assertEqual(str((content / "media" / "Cars").resolve()), saved["signature"]["cars_dir"])
                self.assertEqual({"3622"}, set(saved["vehicles"]))

    def test_empty_cache_with_matching_signature_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as temp:
            game, content = make_install(Path(temp), "steam")
            cache = Path(temp) / "index.json"
            cache.write_text(json.dumps({
                "format": "kfps_fh6_vehicle_asset_index_v1",
                "signature": assets._index_signature(content / "media" / "Cars"), "vehicles": {},
            }), encoding="utf-8")
            self.assertEqual({3622}, set(assets.load_or_build_vehicle_asset_index(game, cache)))

    def test_nonempty_valid_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            game, _ = make_install(Path(temp), "steam")
            cache = Path(temp) / "index.json"
            expected = assets.load_or_build_vehicle_asset_index(game, cache)
            with patch.object(assets, "build_vehicle_asset_index", side_effect=AssertionError("cache not reused")):
                self.assertEqual(expected, assets.load_or_build_vehicle_asset_index(game, cache))

    def test_failed_rebuild_does_not_replace_a_previous_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, _ = make_install(root, "steam")
            cache = root / "index.json"
            assets.load_or_build_vehicle_asset_index(game, cache)
            original = cache.read_bytes()
            invalid = root / "not-a-game"
            make_archive(invalid / "unrelated.zip")
            with self.assertRaises(assets.VehicleAssetError):
                assets.load_or_build_vehicle_asset_index(invalid, cache)
            self.assertEqual(original, cache.read_bytes())

    def run_link_worker(self, root: Path, selected: Path):
        from kfps_ui.app_paths import AppPaths
        from kfps_ui.experimental.full_livery.paths import FullLiveryPaths

        paths = AppPaths(
            app_root=root, ui_root=UI, qml_root=UI / "qml", asset_root=UI / "assets",
            runtime_root=root / "runtime", bundled_python=Path(sys.executable),
        )
        experiment = FullLiveryPaths.for_app(paths)
        experiment.ensure()
        session = experiment.sessions / "folder-link-test"
        session.mkdir(parents=True, exist_ok=True)
        request = session / "request.json"
        result = session / "result.json"
        request.write_text(json.dumps({
            "protocol": 1, "request_id": "folder-link-test", "operation": "link-game",
            "paths": {**experiment.as_worker_payload(), "app_root": str(root),
                      "inspector_root": str(root / "tools" / "livery-inspector")},
            "payload": {"folder": str(selected)}, "session_dir": str(session),
        }), encoding="utf-8")
        bootstrap = (
            f"import sys; sys.path[:0] = {[str(UI / 'src'), str(ROOT)]!r}; "
            "from kfps_ui.experimental.full_livery.worker_main import main; raise SystemExit(main())"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", bootstrap, "--request", str(request), "--result", str(result)],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.assertTrue(result.exists(), completed.stderr)
        return completed.returncode, json.loads(result.read_text(encoding="utf-8")), experiment

    def test_real_link_worker_handles_manual_selections_and_restart(self):
        for platform in ("steam", "xbox"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                game, content = make_install(root, platform)
                originals = {p: p.read_bytes() for p in game.rglob("*.zip")}
                for selected in (game, content, content / "media" / "Cars"):
                    code, result, experiment = self.run_link_worker(root, selected)
                    self.assertEqual(0, code, result)
                    self.assertTrue(result["ok"])
                    self.assertEqual(1, result["value"]["vehicle_count"])
                    self.assertEqual(str(content.resolve()), result["value"]["game_folder"])
                    index = json.loads(experiment.vehicle_index.read_text(encoding="utf-8"))
                    self.assertEqual({"3622"}, set(index["vehicles"]))
                self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_real_link_worker_reports_failure_instead_of_zero_car_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "not-a-game"
            make_archive(game / "unrelated.zip")
            code, result, experiment = self.run_link_worker(root, game)
            self.assertNotEqual(0, code)
            self.assertFalse(result["ok"])
            self.assertEqual("VehicleAssetError", result["error_type"])
            self.assertFalse(experiment.vehicle_index.exists())


if __name__ == "__main__":
    unittest.main()
