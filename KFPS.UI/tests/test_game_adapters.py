from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game_adapters import ADAPTERS, get_adapter, iter_adapters  # noqa: E402
from game_adapters.discovery import (  # noqa: E402
    discover_save_artifacts,
    discover_save_roots,
    discover_steam_remote_roots,
)
from game_profiles import PROFILES, get_profile  # noqa: E402
from kfps_ui.cgroup_library_service import CGroupLibraryService  # noqa: E402


class GameAdapterDeclarationTests(unittest.TestCase):
    def test_registry_has_one_canonical_adapter_per_supported_game(self):
        self.assertEqual(["fh6", "fh5", "fh4", "fm8"], list(ADAPTERS))
        for adapter in iter_adapters():
            self.assertTrue(adapter.label)
            self.assertTrue(adapter.short_label)
            self.assertTrue(adapter.stores)
            self.assertTrue(adapter.ownership.live_export_policy)
            self.assertTrue(adapter.ownership.offline_export_policy)
            self.assertTrue(adapter.save_discovery.key)
            self.assertTrue(adapter.locator.key)
            self.assertTrue(adapter.shape_schema.canonical_game)
            self.assertTrue(adapter.process_names)

    def test_capabilities_match_the_current_product_surface(self):
        for key in ("fh4", "fh5", "fh6", "fm8"):
            adapter = get_adapter(key)
            self.assertTrue(adapter.supports("live_import"))
            self.assertTrue(adapter.supports("live_export"))
            self.assertTrue(adapter.supports("offline_export"))
        self.assertFalse(get_adapter("fh5").supports("offline_import"))
        for key in ("fh4", "fh6", "fm8"):
            self.assertTrue(get_adapter(key).supports("offline_import"))
            self.assertTrue(get_adapter(key).offline_import_handler)

    def test_aliases_and_legacy_memory_profile_keys_remain_compatible(self):
        self.assertIs(get_adapter("Forza Horizon 4"), ADAPTERS["fh4"])
        self.assertIs(get_adapter("FM"), ADAPTERS["fm8"])
        self.assertEqual(["fh6", "fh5", "fh4", "fm"], list(PROFILES))
        self.assertIs(get_profile("FM8"), PROFILES["fm"])
        self.assertEqual("fm", get_adapter("FM8").bridge_key)

    def test_store_and_locator_variants_are_explicit(self):
        for adapter in iter_adapters():
            self.assertEqual({"microsoft", "steam"}, {store.key for store in adapter.stores})
        self.assertEqual("cloudflare_then_local", ADAPTERS["fh6"].locator.profile_source)
        self.assertEqual("packaged_fixed_descriptors", ADAPTERS["fh5"].locator.profile_source)
        self.assertEqual("packaged_final_build", ADAPTERS["fh4"].locator.profile_source)
        self.assertEqual("dedicated_live_root", ADAPTERS["fm8"].locator.profile_source)
        self.assertFalse(ADAPTERS["fm8"].locator.allow_research_fallback)
        self.assertEqual("2440510", ADAPTERS["fm8"].save_discovery.steam_app_id)

    def test_offline_import_dispatch_uses_declared_handler(self):
        source = Path("example.json")
        calls: list[Path] = []
        fake = SimpleNamespace(
            _create_fh6_layer_group_install_work=lambda path: calls.append(path) or {"game": "fh6"},
            _create_fh4_layer_group_install_work=lambda path: calls.append(path) or {"game": "fh4"},
            _create_fm8_layer_group_install_work=lambda path: calls.append(path) or {"game": "fm8"},
        )
        for key in ("fh6", "fh4", "fm8"):
            result = CGroupLibraryService._create_folder_install_work(fake, source, key)
            self.assertEqual(key, result["game"])
        self.assertEqual([source, source, source], calls)
        with self.assertRaisesRegex(ValueError, "not available"):
            CGroupLibraryService._create_folder_install_work(fake, source, "fh5")


class GameAdapterDiscoveryTests(unittest.TestCase):
    def test_fh6_targeted_xbox_layout_is_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "XboxGames" / "GameSave"
            source = root / "pgs" / "user" / "slot" / "ContainersRoot" / "LayerGroup_1" / "C_group"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fixture")
            self.assertEqual([source], discover_save_artifacts(ADAPTERS["fh6"], [root]))

    def test_fm8_only_targets_layer_group_data(self):
        with tempfile.TemporaryDirectory() as temp:
            ugc = Path(temp) / "UGC"
            group = ugc / "LayerGroups" / "owned" / "data"
            design = ugc / "Liveries" / "design" / "data"
            group.parent.mkdir(parents=True)
            design.parent.mkdir(parents=True)
            group.write_bytes(b"group")
            design.write_bytes(b"design")
            self.assertEqual([group], discover_save_artifacts(ADAPTERS["fm8"], [ugc]))

    def test_fm8_microsoft_store_localcache_layout_is_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp)
            ugc = (
                local
                / "Packages"
                / "Microsoft.ForzaMotorsport_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "UGC"
            )
            data = ugc / "LayerGroups" / "local-group" / "data"
            data.parent.mkdir(parents=True)
            data.write_bytes(b"group")

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), patch(
                "game_adapters.discovery.discover_xbox_game_save_roots",
                return_value=[],
            ), patch(
                "game_adapters.discovery.discover_steam_remote_roots",
                return_value=[],
            ):
                roots = discover_save_roots(ADAPTERS["fm8"])

            self.assertIn(ugc, roots)
            self.assertEqual([data], discover_save_artifacts(ADAPTERS["fm8"], roots))

    def test_fm8_steam_remote_layout_is_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            steam = Path(temp) / "Steam"
            remote = steam / "userdata" / "1234" / "2440510" / "remote"
            remote.mkdir(parents=True)
            with patch("game_adapters.discovery.steam_install_roots", return_value=[steam]):
                self.assertEqual([remote], discover_steam_remote_roots("2440510"))

    def test_shape_schema_gate_is_adapter_owned(self):
        self.assertTrue(ADAPTERS["fh5"].accepts_decoded_source("cgroup", 10))
        self.assertFalse(ADAPTERS["fh5"].accepts_decoded_source("livery", 10))
        self.assertFalse(ADAPTERS["fm8"].accepts_decoded_source("cgroup", 0))
        self.assertTrue(ADAPTERS["fm8"].accepts_decoded_source("cgroup", 1))


if __name__ == "__main__":
    unittest.main()
