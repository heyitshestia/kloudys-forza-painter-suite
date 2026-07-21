import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.app_paths import AppPaths
from kfps_ui.json_thumbnail_worker import warm_thumbnail_cache
from kfps_ui.preview_service import PreviewService


class GeneratedPreviewPersistenceTests(unittest.TestCase):
    def test_generated_preview_is_saved_in_the_run_and_migrated_from_cache(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td)
            final_json = app_root / "imgs" / "generated" / "Vinyl" / "finals" / "Vinyl.500v2.json"
            final_json.parent.mkdir(parents=True)
            final_json.write_text(
                json.dumps(
                    {
                        "shapes": [
                            {
                                "type": 1048677,
                                "data": [0, 0, 400, 200, 0, 0, 0],
                                "color": [220, 40, 40, 255],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", app_root / "python/python.exe")
            service = PreviewService(paths)
            expected = app_root / "imgs" / "generated" / "Vinyl" / "previews" / "Vinyl.preview.500v2.png"

            preview_url = service.preview_for_json(final_json, "generated")
            self.assertTrue(preview_url)
            self.assertTrue(expected.is_file())
            self.assertGreater(expected.stat().st_size, 0)
            self.assertFalse(service.generated_preview_needs_persistence(final_json))

            expected.write_bytes(b"stale-managed-preview")
            regenerated_url = service.regenerate_preview_for_json(final_json, "generated")
            self.assertTrue(regenerated_url)
            self.assertTrue(expected.read_bytes().startswith(b"\x89PNG"))

            legacy_cache = service._cache_target(final_json, "generated")
            legacy_cache.parent.mkdir(parents=True, exist_ok=True)
            legacy_cache.write_bytes(expected.read_bytes())
            expected.unlink()
            self.assertTrue(service.generated_preview_needs_persistence(final_json))

            cache_file = paths.runtime_root / "json-browser-index.v1.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {
                        "sources": {
                            "0": {
                                "rows": [
                                    {
                                        "path": str(final_json),
                                        "previewUrl": legacy_cache.resolve().as_uri(),
                                    }
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(1, warm_thumbnail_cache(paths, cache_file=cache_file, preview=service))
            self.assertTrue(expected.is_file())
            migrated = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertIn("Vinyl.preview.500v2.png", migrated["sources"]["0"]["rows"][0]["previewUrl"])


if __name__ == "__main__":
    unittest.main()
