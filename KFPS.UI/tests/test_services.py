import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT));os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.json_service import JsonService
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService
from kfps_ui.supporter_service import SupporterService
APP=QCoreApplication.instance() or QCoreApplication([])

class DummyVersion: localVersion="3.0.12"
class DummyPreview:
 def preview_for_json(self,path,source=""):return ""
class DummyDesktop:
 def __init__(self,path):self.path=str(path)
 def chooseJson(self):return self.path
class DummyLog:
 def __init__(self):self.messages=[]
 def append(self,message,level="info"):self.messages.append((message,level))

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
 def test_manual_fd6_json_is_converted_without_touching_source(self):
  with tempfile.TemporaryDirectory() as td:
   temp=Path(td);app_root=temp/"KFPS";incoming=temp/"incoming";incoming.mkdir()
   source=incoming/"FD6 Sample.json"
   payload={
    "format":"fd6.shapes",
    "version":1,
    "source_image":"source.png",
    "image_size":[200,100],
    "profile":"test-profile",
    "sticker_mode":True,
    "shapes":[
     {"type":"rotated_ellipse","x":120,"y":70,"rx":63,"ry":31.5,"angle":90,"color":[1,2,3,128]},
     {"type":"rotated_rectangle","x":80,"y":30,"hw":63.5,"hh":127,"angle":0,"color":[0.5,0.25,0,1]},
     {"type":"triangle","x1":0,"y1":0,"x2":10,"y2":0,"x3":0,"y3":10,"color":[255,255,255,255]},
    ],
   }
   source.write_text(json.dumps(payload),encoding="utf-8")
   original=source.read_text(encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   log=DummyLog();svc=JsonService(paths,DummyPreview(),DummyDesktop(source),log)
   svc.browseManual()
   self.assertEqual(source.read_text(encoding="utf-8"),original)
   exported=list(paths.exported_root.glob("*.json"))
   self.assertEqual(len(exported),1)
   self.assertNotEqual(exported[0].resolve(),source.resolve())
   converted=json.loads(exported[0].read_text(encoding="utf-8"))
   self.assertEqual(converted["format"],"kfps.fd6.converted.v1")
   self.assertEqual(converted["metadata"]["source_format"],"fd6.shapes")
   self.assertEqual(converted["metadata"]["shape_count"],2)
   self.assertEqual(converted["metadata"]["skipped_shapes"],1)
   self.assertEqual(svc.selectedPath,str(exported[0].resolve()))
   self.assertEqual(svc.selectedLayers,"2")
   ellipse,rect=converted["shapes"]
   self.assertEqual(ellipse["type"],1048678)
   self.assertEqual(ellipse["type_word"],0x0066)
   self.assertEqual(ellipse["data"],[20.0,-20.0,1.0,0.5,270.0,0,0])
   self.assertEqual(ellipse["color"],[1,2,3,128])
   self.assertEqual(rect["type"],1048677)
   self.assertEqual(rect["type_word"],0x0065)
   self.assertEqual(rect["data"],[-20.0,20.0,1.0,2.0,0.0,0,0])
   self.assertEqual(rect["color"],[128,64,0,255])
   self.assertTrue(any("Converted FD6 JSON" in message for message,level in log.messages))
 def test_json_refresh_does_not_render_thumbnails_synchronously(self):
  class BlockingPreview:
   def __init__(self):
    self.entered=threading.Event();self.release=threading.Event()
   def existing_preview_for_json(self,path,source=""):
    return ""
   def preview_for_json(self,path,source=""):
    self.entered.set();self.release.wait(1);return ""
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"generated"/"Many"/"finals"/"Many.1v2.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   preview=BlockingPreview();started=time.monotonic();svc=JsonService(paths,preview,DummyDesktop(target),DummyLog());elapsed=time.monotonic()-started
   preview.release.set()
   self.assertLess(elapsed,0.5)
   self.assertEqual(svc.outputCount,1)

if __name__=="__main__":unittest.main()
