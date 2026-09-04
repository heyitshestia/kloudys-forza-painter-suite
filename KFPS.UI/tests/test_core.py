import json, os, sys, tempfile, unittest
from pathlib import Path

UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QNetworkReply
from kfps_ui.bridge_events import parse_bridge_line
from kfps_ui.changelog_service import ChangelogService
from kfps_ui.qt_utils import is_remote_newer, version_tuple
from kfps_ui.settings_service import SettingsService
from kfps_ui.version_service import VersionService

APP=QCoreApplication.instance() or QCoreApplication([])

class FakeNetworkReply:
 def __init__(self,content=b"",error=QNetworkReply.NetworkError.NoError,error_string=""):
  self.content=content;self.network_error=error;self.error_string=error_string;self.deleted=False
 def error(self):return self.network_error
 def errorString(self):return self.error_string
 def readAll(self):return self.content
 def deleteLater(self):self.deleted=True

class CoreTests(unittest.TestCase):
 def test_version_compare(self):
  self.assertTrue(is_remote_newer("3.0.12","3.0.13"));self.assertFalse(is_remote_newer("3.0.12","3.0.12"));self.assertEqual(version_tuple("v3.0.12"),(3,0,12))
 def test_bridge_events(self):
  self.assertEqual(parse_bridge_line("KFPS_RUN_DIR: C:/run").kind,"run_started");self.assertEqual(parse_bridge_line("WPF_RUN_DIR: C:/run").kind,"run_started");self.assertEqual(parse_bridge_line("normal").kind,"log")
 def test_clean_settings_and_window_geometry(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"settings.json";path.write_text('{"uiScale": 1.35}',encoding="utf-8");svc=SettingsService(path);self.assertEqual(svc.theme,"Night Blossom");self.assertFalse(hasattr(svc,"uiScale"));svc.save_window_geometry(10,20,1200,700,True);self.assertEqual(svc.window_geometry(),{"x":10,"y":20,"width":1200,"height":700,"maximized":True});self.assertNotIn("uiScale",json.loads(path.read_text(encoding="utf-8")))
 def test_changelog_separates_summary_from_line_preserved_details(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"CHANGELOG.md"
   path.write_text("# Changes\n\n## 1.2.3\n- First change.\n- Second change.\n- Third change.\n",encoding="utf-8")
   row=ChangelogService(path).model.rows[0]
   self.assertEqual(row["summary"],"First change.")
   self.assertEqual(row["details"],"- Second change.\n- Third change.")
 def test_version_refresh_uses_raw_github_and_reports_success_and_failure(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"VERSION";path.write_text("3.0.99\n",encoding="utf-8")
   svc=VersionService(path,demo=True)
   try:
    self.assertIn("raw.githubusercontent.com",svc.URL)
    channel={"schema":"kfps.update-channel.v1","channel":"stable","sequence":9,"manifest":{"url":"https://github.com/example/releases/download/kfps-update-data-v3.0.100-s9/kfps-update-3.0.100-s9.json"}}
    svc._checking=True;success=FakeNetworkReply(json.dumps(channel).encode("utf-8"));svc._finished(success)
    self.assertTrue(success.deleted);self.assertFalse(svc.checking);self.assertTrue(svc.checkSucceeded);self.assertEqual(svc.latestVersion,"3.0.100");self.assertTrue(svc.updateAvailable)
    self.assertIn("available",svc.checkStatus.lower())
    svc._checking=True;invalid=FakeNetworkReply(b'{"schema":"kfps.update-channel.v1","channel":"stable","sequence":9,"manifest":{"url":"https://example.invalid/not-an-update.json"}}');svc._finished(invalid)
    self.assertTrue(invalid.deleted);self.assertFalse(svc.checkSucceeded);self.assertIn("installable",svc.checkStatus.lower())
    svc._checking=True;failure=FakeNetworkReply(error=QNetworkReply.NetworkError.ContentAccessDenied,error_string="HTTP 403")
    svc._finished(failure)
    self.assertTrue(failure.deleted);self.assertFalse(svc.checkSucceeded);self.assertIn("HTTP 403",svc.checkStatus)
   finally:
    svc._poll.stop();svc._blink_timer.stop()
 def test_changelog_refresh_accepts_remote_notes_without_replacing_local_file(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"CHANGELOG.md";local="# Changes\n\n## 3.0.99\n- Local note.\n";path.write_text(local,encoding="utf-8")
   svc=ChangelogService(path)
   self.assertIn("raw.githubusercontent.com",svc.URL)
   svc._refreshing=True;reply=FakeNetworkReply(b"# Changes\n\n## 3.0.100\n- Remote note.\n- More detail.\n");svc._finished(reply)
   self.assertTrue(reply.deleted);self.assertFalse(svc.refreshing);self.assertEqual(svc.model.rows[0]["version"],"3.0.100")
   self.assertEqual(svc.model.rows[0]["details"],"- More detail.");self.assertEqual(path.read_text(encoding="utf-8"),local)
   self.assertIn("refreshed",svc.status.lower())

if __name__=="__main__":unittest.main()
