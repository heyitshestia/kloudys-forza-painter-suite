import json, os, sys, tempfile, unittest
from pathlib import Path

UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.bridge_events import parse_bridge_line
from kfps_ui.changelog_service import ChangelogService
from kfps_ui.qt_utils import is_remote_newer, version_tuple
from kfps_ui.settings_service import SettingsService

APP=QCoreApplication.instance() or QCoreApplication([])

class CoreTests(unittest.TestCase):
 def test_version_compare(self):
  self.assertTrue(is_remote_newer("3.0.12","3.0.13"));self.assertFalse(is_remote_newer("3.0.12","3.0.12"));self.assertEqual(version_tuple("v3.0.12"),(3,0,12))
 def test_bridge_events(self):
  self.assertEqual(parse_bridge_line("KFPS_RUN_DIR: C:/run").kind,"run_started");self.assertEqual(parse_bridge_line("WPF_RUN_DIR: C:/run").kind,"run_started");self.assertEqual(parse_bridge_line("normal").kind,"log")
 def test_clean_settings_and_clamp(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"settings.json";svc=SettingsService(path);self.assertEqual(svc.theme,"Night Blossom");self.assertEqual(svc.uiScale,1.05);svc.uiScale=5;self.assertEqual(svc.uiScale,1.35);self.assertTrue(path.exists())
 def test_changelog_separates_summary_from_line_preserved_details(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"CHANGELOG.md"
   path.write_text("# Changes\n\n## 1.2.3\n- First change.\n- Second change.\n- Third change.\n",encoding="utf-8")
   row=ChangelogService(path).model.rows[0]
   self.assertEqual(row["summary"],"First change.")
   self.assertEqual(row["details"],"- Second change.\n- Third change.")

if __name__=="__main__":unittest.main()
