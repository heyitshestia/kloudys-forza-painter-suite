"""Existing future/custom fields survive recognized preference updates."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from kfps_editor.server import EditorServer, Handler, ServerPaths


class PreferencesCompatibilityTests(unittest.TestCase):
    def test_http_reads_known_settings_without_exposing_or_rewriting_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            paths = ServerPaths.for_runtime(ROOT, runtime, exports=runtime / "exports")
            paths.preferences.write_text(json.dumps({"settings": {"kloudyFabricLanguage": "ja",
                "customFont": {"family": "Fixture Font"}}, "unrelated": [1, 2]}), encoding="utf-8")
            original = paths.preferences.read_bytes()
            with EditorServer(("127.0.0.1", 0), Handler, paths=paths) as server:
                worker = threading.Thread(target=server.serve_forever)
                worker.start()
                try:
                    with urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/fabric-editor/preferences", timeout=5) as response:
                        result = json.load(response)
                    self.assertEqual(result["settings"], {"kloudyFabricLanguage": "ja"})
                    self.assertEqual(paths.preferences.read_bytes(), original)
                finally:
                    server.shutdown()
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())

    def test_existing_unknown_fields_survive_and_new_unknown_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "preferences.json"
            initial = {"settings": {"kloudyFabricLanguage": "ko", "kloudyFabricShortcuts": '{"duplicate":"Ctrl+Alt+D"}',
                "customFont": {"family": "Fixture Font", "weight": 500}, "future": [1, "kept"]},
                "unrelated": {"nested": True}}
            target.write_text(json.dumps(initial), encoding="utf-8")
            server = EditorServer.__new__(EditorServer)
            server.paths = SimpleNamespace(preferences=target)
            server.preferences_lock = threading.Lock()
            result = server.store_preferences({"settings": {"kloudyFabricLanguage": "ja"}})
            expected = json.loads(json.dumps(initial))
            expected["settings"]["kloudyFabricLanguage"] = "ja"
            self.assertEqual(result, expected)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), expected)
            before = target.read_bytes()
            for invalid in [{"customFont": "new"}, {"future": None}, {"kloudyFabricLanguage": {"invalid": True}}]:
                with self.assertRaises(ValueError): server.store_preferences({"settings": invalid})
                self.assertEqual(target.read_bytes(), before)
            server.store_preferences({"settings": {"kloudyFabricLanguage": None}})
            expected["settings"].pop("kloudyFabricLanguage")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), expected)


if __name__ == "__main__":
    unittest.main()
