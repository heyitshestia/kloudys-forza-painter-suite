import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_game_adapters import ADAPTERS
from game_adapters.discovery import discover_save_artifacts, discover_save_roots, discover_steam_remote_roots


class SaveLocationGroupsTests(unittest.TestCase):
    def test_fh6_pgs_root_user_slot_container_and_group_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "XboxGames" / "GameSave"
            first = base / "pgs" / "u_first" / "current" / "ContainersRoot" / "LayerGroup_A" / "C_group"
            second = base / "pgs" / "u_first" / "other-slot" / "ContainersRoot" / "LayerGroup_B" / "C_group"
            other = base / "pgs" / "u_second" / "current" / "ContainersRoot" / "LayerGroup_C" / "C_group"
            for target in (first, second, other):
                target.parent.mkdir(parents=True)
                target.write_bytes(b"fixture")
            cases = ((base, {first, second, other}), (base / "pgs", {first, second, other}),
                     (base / "pgs/u_first", {first, second}),
                     (first.parents[2], {first}), (first.parents[1], {first}), (first.parent, {first}))
            for selected, expected in cases:
                with self.subTest(selected=selected):
                    self.assertEqual(expected, set(discover_save_artifacts(ADAPTERS["fh6"], [selected])))

    def test_fh4_known_save_root_is_not_cut_off_by_generic_walk_budget(self):
        root = Path("C:/Users/Test/AppData/Local/Packages/Microsoft.SunriseBaseGame_test/SystemAppData/wgs")
        with patch("game_adapters.discovery._targeted_sources", return_value=[]), \
                patch("game_adapters.discovery.bounded_source_walk", return_value=[]) as walk:
            discover_save_artifacts(ADAPTERS["fh4"], [root])
        self.assertIsNone(walk.call_args.kwargs["max_files"])
        self.assertIsNone(walk.call_args.kwargs["max_seconds"])

    def test_fm8_native_ugc_location_is_a_recognized_cached_root(self):
        adapter = ADAPTERS["fm8"]
        for value in ("C:/Users/Test/AppData/Local/Microsoft.ForzaMotorsport/UGC",
                      "C:/Users/Test/AppData/Local/Microsoft.ForzaMotorsport/UGC/LayerGroups",
                      "C:/Users/Test/AppData/Local/Packages/Microsoft.ForzaMotorsport_test/LocalCache/Local/UGC"):
            self.assertTrue(adapter.is_save_root(Path(value)), value)
        self.assertFalse(adapter.is_save_root(Path("C:/Steam/userdata/123/1551360/remote")))


    def test_many_pgs_groups_and_overlapping_roots_are_not_truncated_or_duplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "XboxGames/GameSave/pgs"
            expected = set()
            for index in range(825):
                path = base / f"u_1/slot{index % 3}/ContainersRoot/LayerGroup_{index}/C_group"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
                expected.add(path)
            result = discover_save_artifacts(ADAPTERS["fh6"], [base.parent, base, base / "u_1"])
            self.assertEqual(len(expected), len(result))
            self.assertEqual(expected, set(result))

    def test_generic_folders_keep_scan_limits(self):
        for game in ("fh4", "fh5"):
            with patch("game_adapters.discovery._targeted_sources", return_value=[]), \
                    patch("game_adapters.discovery.bounded_source_walk", return_value=[]) as walk:
                discover_save_artifacts(ADAPTERS[game], [Path("C:/Exports")])
            self.assertEqual(60000, walk.call_args.kwargs["max_files"])
            self.assertEqual(18.0, walk.call_args.kwargs["max_seconds"])

    def test_similarly_named_folders_do_not_suppress_generic_discovery(self):
        with patch("game_adapters.discovery.bounded_source_walk", return_value=[]) as walk:
            discover_save_artifacts(ADAPTERS["fh6"], [Path("C:/XboxGames/GameSave-backup")])
        walk.assert_called_once()

    def test_steam_accounts_for_each_game_remain_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            steam = Path(folder) / "Steam"
            for app in ("1293830", "1551360", "2440510"):
                expected = {steam / f"userdata/{user}/{app}/remote" for user in ("101", "202")}
                for path in expected:
                    path.mkdir(parents=True)
                with patch("game_adapters.discovery.steam_install_roots", return_value=[steam]):
                    self.assertEqual(expected, set(discover_steam_remote_roots(app)))

    def test_fm8_cached_native_root_survives_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            ugc = Path(folder) / "Microsoft.ForzaMotorsport/UGC/LayerGroups"
            ugc.mkdir(parents=True)
            with patch("game_adapters.discovery.discover_package_roots", return_value=[]), \
                    patch("game_adapters.discovery.discover_steam_remote_roots", return_value=[]), \
                    patch("game_adapters.discovery.discover_xbox_game_save_roots", return_value=[]):
                self.assertIn(ugc, discover_save_roots(ADAPTERS["fm8"], [ugc]))


if __name__ == "__main__":
    unittest.main()
