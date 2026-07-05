import json, os, sys, tempfile, unittest
from pathlib import Path
UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT));os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService
from kfps_ui.supporter_service import SupporterService
APP=QCoreApplication.instance() or QCoreApplication([])

class DummyVersion: localVersion="3.0.12"
class ServiceTests(unittest.TestCase):
 def test_report_is_local_markdown(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/"VERSION").write_text("3.0.12");paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");log=LogService();svc=ReportService(paths,log,DummyVersion());text=svc.build("Bug","Test","Details",True,False,False);self.assertIn("# KFPS Report",text);self.assertNotIn("Visible runtime log",text)
 def test_no_memory_write_in_tests(self):
  dangerous=["fh6_import_typecode_json.py","fh6_export_typecode_json.py","fh6_trim_group_count.py"]
  self.assertTrue(all((ROOT/name).exists() for name in dangerous))
 def test_supporter_unlock_install_handles_stale_temp_source(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);source=app_root/"runtime"/"supporter"/"supporter.tmp";source.parent.mkdir(parents=True);source.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root);payload={"supporter_name":"Test","entitlements":["supporter_theme"]}
   self.assertTrue(svc._install_key(source,payload,"Local unlock verified.",remove_source=True))
   self.assertTrue((app_root/"supporter.kfpskey").exists())
   self.assertFalse(source.exists())
   self.assertTrue(svc.unlocked)
 def test_supporter_unlock_install_preserves_personal_key_name(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);source=app_root/"downloads"/"Alice Custom.kfpskey";source.parent.mkdir(parents=True);source.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root);payload={"supporter_name":"Alice","entitlements":["supporter_theme"]}
   self.assertTrue(svc._install_key(source,payload,"Local unlock verified."))
   self.assertTrue((app_root/"Alice Custom.kfpskey").exists())
   self.assertTrue(svc.unlocked)
 def test_supporter_unlock_reload_accepts_root_key_drop(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);key=app_root/"Manual Drop.kfpskey";key.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root);payload={"supporter_name":"Manual","entitlements":["supporter_theme"]}
   svc._validate_file=lambda path:(True,payload,"Local unlock verified.") if path==key else (False,None,"wrong key")
   svc.reload()
   self.assertTrue(svc.unlocked)
   self.assertEqual(svc.supporterLabel,"Manual")

if __name__=="__main__":unittest.main()
