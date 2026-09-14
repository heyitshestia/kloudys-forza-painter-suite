import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from test_fabric_editor_server import RunningEditorServer, fabric_server, post_json


class EditorPreferencesTests(unittest.TestCase):
    def test_centered_resize_survives_restart_and_failed_write_without_changing_favorites(self):
        key = "kloudyFabricCenteredResize"
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker):
                with RunningEditorServer() as server:
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {
                        key: "1", "kloudyFabricFavorites": "[101,102]"}})
                    original = marker.read_bytes()
                    with patch.object(fabric_server, "_write_json_atomic", side_effect=OSError("disk unavailable")):
                        with self.assertRaises(urllib.error.HTTPError):
                            post_json(server, "/api/fabric-editor/preferences", {"settings": {key: "0"}})
                    self.assertEqual(original, marker.read_bytes())
                for expected in ("1", "0"):
                    with RunningEditorServer() as server:
                        with urllib.request.urlopen(f"{server}/api/fabric-editor/preferences") as response:
                            self.assertEqual(json.load(response)["settings"], {
                                key: expected, "kloudyFabricFavorites": "[101,102]"})
                        post_json(server, "/api/fabric-editor/preferences", {"settings": {key: "0"}})

    def test_update_notice_survives_restart_language_change_and_failed_write(self):
        key = "kloudyFabricEditorUpdateAcknowledged"
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker):
                with RunningEditorServer() as server:
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {
                        "kloudyFabricFavorites": "[101,102]", "kloudyFabricLanguage": "en"}})
                    original = marker.read_bytes()
                    with patch.object(fabric_server, "_write_json_atomic", side_effect=OSError("disk unavailable")):
                        with self.assertRaises(urllib.error.HTTPError):
                            post_json(server, "/api/fabric-editor/preferences", {"settings": {key: "modernization-1"}})
                    self.assertEqual(original, marker.read_bytes())
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {key: "modernization-1"}})
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricLanguage": "ko"}})
                with RunningEditorServer() as server:
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/preferences") as response:
                        settings = json.load(response)["settings"]
                self.assertEqual(settings, {key: "modernization-1", "kloudyFabricLanguage": "ko",
                                            "kloudyFabricFavorites": "[101,102]"})

    def test_language_and_notice_acknowledgment_survive_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker):
                with RunningEditorServer() as server:
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {
                        "kloudyFabricFavorites": "[101,102]", "kloudyFabricLanguage": "ko"}})
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {
                        "kloudyFabricLanguageNoticeAcknowledged": "1"}})
                with RunningEditorServer() as server:
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/preferences") as response:
                        settings = json.load(response)["settings"]
                self.assertEqual(settings, {"kloudyFabricFavorites": "[101,102]",
                                           "kloudyFabricLanguage": "ko",
                                           "kloudyFabricLanguageNoticeAcknowledged": "1"})

    def test_matte_themes_and_custom_base_survive_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", root / "preferences.json"), patch.object(fabric_server, "EDITOR_THEME_ROOT", root / "themes"):
                with RunningEditorServer() as server:
                    for theme in ("blackout", "whiteout"):
                        post_json(server, "/api/fabric-editor/preferences", {"theme": theme})
                        self.assertEqual(theme + "-custom", fabric_server._theme_id_from_name(theme))
                    post_json(server, "/api/fabric-editor/themes", {"name": "My matte", "base": "blackout", "values": {"--text": "#eeeeee"}})
                with RunningEditorServer() as server:
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/themes") as response:
                        themes = json.load(response)["themes"]
                    self.assertTrue({"blackout", "whiteout"}.issubset({theme["id"] for theme in themes if theme["builtin"]}))
                    self.assertEqual("blackout", next(theme["base"] for theme in themes if theme["name"] == "My matte"))

    def test_project_sharing_acknowledgment_survives_restart_without_changing_favorites(self):
        key = "kloudyFabricProjectSharingAcknowledged"
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker):
                with RunningEditorServer() as server:
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricFavorites": "[1,2]"}})
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {key: "1"}})
                with RunningEditorServer() as server:
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/preferences") as response:
                        settings = json.load(response)["settings"]
                self.assertEqual({"kloudyFabricFavorites": "[1,2]", key: "1"}, settings)

    def test_corrupt_preferences_are_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            marker.write_text("{broken settings", encoding="utf-8")
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker), RunningEditorServer() as server:
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(f"{server}/api/fabric-editor/preferences")
                with self.assertRaises(urllib.error.HTTPError):
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricLastColor": "#000000"}})
                self.assertEqual("{broken settings", marker.read_text())

    def test_settings_merge_survives_server_restart_and_theme_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker):
                with RunningEditorServer() as server:
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricFavorites": "[1,2]"}})
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricLastColor": "#123456"}})
                    post_json(server, "/api/fabric-editor/preferences", {"theme": "dark"})
                with RunningEditorServer() as server:
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/preferences") as response:
                        data = json.load(response)
                    self.assertEqual("[1,2]", data["settings"]["kloudyFabricFavorites"])
                    self.assertEqual("#123456", data["settings"]["kloudyFabricLastColor"])
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricFavorites": None}})
                self.assertNotIn("kloudyFabricFavorites", json.loads(marker.read_text())["settings"])

    def test_invalid_or_unauthorized_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker), RunningEditorServer() as server:
                post_json(server, "/api/fabric-editor/preferences", {"settings": {"kloudyFabricLastColor": "#123456"}})
                original = marker.read_bytes()
                for payload in ({"settings": {"artwork": "private"}}, {"settings": {"kloudyFabricLastColor": 1}}, {"settings": []}, {"settings": {"kloudyFabricFavorites": "a" * 32769}}):
                    with self.subTest(payload_type=type(payload)), self.assertRaises(urllib.error.HTTPError):
                        post_json(server, "/api/fabric-editor/preferences", payload)
                    self.assertEqual(original, marker.read_bytes())
                with self.assertRaises(urllib.error.HTTPError):
                    post_json(server, "/api/fabric-editor/preferences", {"settings": {}}, token=False)
                self.assertEqual(original, marker.read_bytes())

    def test_failed_write_retains_settings_for_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "preferences.json"
            with patch.object(fabric_server, "EDITOR_PREFS_MARKER", marker), RunningEditorServer() as server:
                payload = {"settings": {"kloudyFabricLastColor": "#123456"}}
                with patch.object(fabric_server, "_write_json_atomic", side_effect=OSError("disk unavailable")):
                    with self.assertRaises(urllib.error.HTTPError):
                        post_json(server, "/api/fabric-editor/preferences", payload)
                post_json(server, "/api/fabric-editor/preferences", payload)
                self.assertEqual(payload["settings"], json.loads(marker.read_text())["settings"])
