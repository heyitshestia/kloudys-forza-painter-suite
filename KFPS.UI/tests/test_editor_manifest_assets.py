from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor import manifest


class SupportDiagnosticInventoryTests(unittest.TestCase):
    def test_current_inventory_matches_without_changing_serialization_order(self):
        source = (ROOT / "tools/support_worker/public/editor-diagnostics.mjs").read_text(encoding="utf-8")
        actual = manifest.support_diagnostic_assets(source)
        self.assertEqual(set(actual), set(manifest.diagnostic_assets()))
        self.assertEqual(actual[-3:], ["locales/ja.js", "release-announcement.js", "activity-client.js"])

    def test_static_extensions_preserve_order(self):
        source = 'export const ASSETS = ["index.html"];'
        source += "\nASSETS.push('extra.js', 'locale.js');\n"
        self.assertEqual(manifest.support_diagnostic_assets(source), ["index.html", "extra.js", "locale.js"])

    def test_duplicate_and_non_string_entries_are_rejected(self):
        for source in ('export const ASSETS = ["same.js", "same.js"];',
                       'export const ASSETS = ["same.js"];\nASSETS.push("same.js");',
                       'export const ASSETS = [1];', 'const ASSETS = ["unexported.js"];'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                manifest.support_diagnostic_assets(source)

    def test_sync_preserves_order_removes_obsolete_assets_and_folds_extensions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            public = root / "tools/support_worker/public/editor-diagnostics.mjs"
            public.parent.mkdir(parents=True)
            public.write_text('export const ASSETS = ["old.js", "first.js"];\n'
                              'ASSETS.push("last.js");\nconst other = 1;\n', encoding="utf-8")
            with patch.object(manifest, "ROOT", root), patch.object(
                    manifest, "diagnostic_assets", return_value=("new.js", "last.js", "first.js")):
                manifest.sync()
                once = public.read_bytes()
                manifest.sync()
            self.assertEqual(public.read_bytes(), once)
            source = public.read_text(encoding="utf-8")
            self.assertEqual(manifest.support_diagnostic_assets(source), ["first.js", "last.js", "new.js"])
            self.assertNotIn("ASSETS.push", source)
            self.assertIn("const other = 1;", source)


if __name__ == "__main__":
    unittest.main()
