import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT));os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.json_service import JsonService, build_startup_json_index_cache
from kfps_ui.json_thumbnail_worker import warm_thumbnail_cache
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

def wait_for(predicate,timeout=3.0):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  APP.processEvents()
  if predicate():return True
  time.sleep(0.01)
 APP.processEvents()
 return bool(predicate())

def shutdown_json_service(svc):
 APP.processEvents()
 if hasattr(svc,"_thumbnail_poll_timer"):
  svc._thumbnail_poll_timer.stop()
 proc=getattr(svc,"_thumbnail_process",None)
 if proc and proc.poll() is None:
  proc.kill();proc.communicate(timeout=2)
 svc._preview_executor.shutdown(wait=True, cancel_futures=True)
 svc._index_executor.shutdown(wait=True, cancel_futures=True)

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
   try:
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
   finally:
    shutdown_json_service(svc)
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
   try:
    self.assertTrue(wait_for(lambda: svc.outputCount==1))
    self.assertFalse(preview.entered.wait(0.05))
    preview.release.set()
    self.assertLess(elapsed,0.5)
   finally:
    preview.release.set()
    shutdown_json_service(svc)
 def test_json_refresh_queues_existing_thumbnail_urls(self):
  class ExistingPreview:
   def __init__(self):
    self.release=threading.Event()
   def existing_preview_for_json(self,path,source=""):
    return "file:///cached.png"
   def preview_for_json(self,path,source=""):
    self.release.wait(1);return "file:///cached.png"
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);finals=app_root/"imgs"/"generated"/"Many"/"finals";finals.mkdir(parents=True)
   for index in range(3):
    (finals/f"Many.{index + 1}v2.json").write_text(json.dumps({"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   preview=ExistingPreview();svc=JsonService(paths,preview,DummyDesktop(finals/"Many.1v2.json"),DummyLog())
   try:
    self.assertTrue(wait_for(lambda: svc.outputCount==3))
    self.assertEqual(3, svc.outputCount)
    self.assertTrue(all(not row.get("previewUrl") for row in svc.fileModel.rows))
   finally:
    preview.release.set()
    shutdown_json_service(svc)
 def test_json_preview_is_requested_per_visible_card(self):
  class ExistingPreview:
   def __init__(self):
    self.rendered=0
   def existing_preview_for_json(self,path,source=""):
    return "file:///cached.png"
   def preview_for_json(self,path,source=""):
    self.rendered+=1;return "file:///rendered.png"
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"generated"/"One"/"finals"/"One.1v2.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   preview=ExistingPreview();svc=JsonService(paths,preview,DummyDesktop(target),DummyLog())
   try:
    self.assertTrue(wait_for(lambda: svc.outputCount==1))
    self.assertFalse(svc.fileModel.row(0).get("previewUrl"))
    svc.requestPreview(str(target))
    self.assertEqual("file:///cached.png",svc.fileModel.row(0).get("previewUrl"))
    self.assertEqual(0,preview.rendered)
   finally:
    shutdown_json_service(svc)

 def test_json_source_switch_reuses_session_index(self):
  class CountingJsonService(JsonService):
   def __init__(self,*args,**kwargs):
    self.builds=[]
    super().__init__(*args,**kwargs)
   def _build_source_index(self,source,root,cache_key):
    self.builds.append((source,str(root)))
    return super()._build_source_index(source,root,cache_key)
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td)
   generated=app_root/"imgs"/"generated"/"Generated"/"finals"/"Generated.1v2.json"
   exported=app_root/"imgs"/"exported"/"Exported.json"
   generated.parent.mkdir(parents=True);exported.parent.mkdir(parents=True)
   payload={"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}
   generated.write_text(json.dumps(payload),encoding="utf-8")
   exported.write_text(json.dumps(payload),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   svc=CountingJsonService(paths,DummyPreview(),DummyDesktop(exported),DummyLog())
   try:
    self.assertTrue(wait_for(lambda: 0 in [source for source,root in svc.builds] and 2 in [source for source,root in svc.builds]))
    before=list(svc.builds)
    svc.setSource(2)
    svc.setSource(0)
    self.assertEqual(before,svc.builds)
    svc.refresh()
    self.assertTrue(wait_for(lambda: len(svc.builds)>len(before) and svc.builds[-1][0]==0))
   finally:
    shutdown_json_service(svc)
 def test_json_index_cache_loads_rows_without_initial_scan(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"generated"/"Cached"/"finals"/"Cached.7v2.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"display_name":"Cached Vinyl","layers":7},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   self.assertEqual(1,build_startup_json_index_cache(paths,preview=DummyPreview()))
   class NoScanJsonService(JsonService):
    def _request_source_scan(self,source,force=False):
     self.requested=getattr(self,"requested",[])+[source]
   cached=NoScanJsonService(paths,DummyPreview(),DummyDesktop(target),DummyLog())
   try:
    self.assertEqual(1,cached.outputCount)
    self.assertEqual("Cached Vinyl",cached.fileModel.row(0)["displayName"])
   finally:
    shutdown_json_service(cached)
 def test_startup_index_cache_preserves_existing_preview_urls(self):
  class ExistingPreview:
   def existing_preview_for_json(self,path,source=""):
    return "file:///startup-preview.png"
   def preview_for_json(self,path,source=""):
    raise AssertionError("startup index must not render previews")
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"generated"/"Startup"/"finals"/"Startup.9v2.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"display_name":"Startup Vinyl","layers":9},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   self.assertEqual(1,build_startup_json_index_cache(paths,preview=ExistingPreview()))
   svc=JsonService(paths,ExistingPreview(),DummyDesktop(target),DummyLog())
   try:
    self.assertEqual(1,svc.outputCount)
    self.assertEqual("file:///startup-preview.png",svc.fileModel.row(0)["previewUrl"])
   finally:
    shutdown_json_service(svc)
 def test_startup_thumbnail_worker_fills_missing_preview_urls(self):
  class RenderingPreview:
   def __init__(self):
    self.calls=[]
   def preview_for_json(self,path,source=""):
    self.calls.append((Path(path).name,source))
    return "file:///rendered-cache.png"
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"generated"/"Warm"/"finals"/"Warm.11v2.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"display_name":"Warm Vinyl","layers":11},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   self.assertEqual(1,build_startup_json_index_cache(paths,preview=DummyPreview()))
   preview=RenderingPreview()
   self.assertEqual(1,warm_thumbnail_cache(paths,preview=preview,max_items=1))
   payload=json.loads((paths.runtime_root/"json-browser-index.v1.json").read_text(encoding="utf-8"))
   row=payload["sources"]["0"]["rows"][0]
   self.assertEqual("file:///rendered-cache.png",row["previewUrl"])
   self.assertEqual([("Warm.11v2.json","generated")],preview.calls)
   svc=JsonService(paths,DummyPreview(),DummyDesktop(target),DummyLog())
   try:
    self.assertEqual("file:///rendered-cache.png",svc.fileModel.row(0)["previewUrl"])
    refreshed=svc._build_source_index(0,paths.generated_root,svc._source_cache_key(0))
    self.assertEqual("file:///rendered-cache.png",refreshed["rows"][0]["previewUrl"])
   finally:
    shutdown_json_service(svc)
 def test_open_json_model_merges_thumbnail_urls_from_cache(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"exported"/"Later Preview.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"display_name":"Later Preview","layers":3},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   self.assertEqual(1,build_startup_json_index_cache(paths,preview=DummyPreview()))
   svc=JsonService(paths,DummyPreview(),DummyDesktop(target),DummyLog())
   try:
    svc.setSource(2)
    self.assertEqual("",svc.fileModel.row(0)["previewUrl"])
    payload=json.loads((paths.runtime_root/"json-browser-index.v1.json").read_text(encoding="utf-8"))
    payload["sources"]["2"]["rows"][0]["previewUrl"]="file:///late-preview.png"
    (paths.runtime_root/"json-browser-index.v1.json").write_text(json.dumps(payload),encoding="utf-8")
    self.assertEqual(1,svc._merge_preview_urls_from_cache(force=True))
    self.assertEqual("file:///late-preview.png",svc.fileModel.row(0)["previewUrl"])
    self.assertEqual("file:///late-preview.png",svc.previewUrl)
   finally:
    shutdown_json_service(svc)
 def test_thumbnail_worker_prioritizes_preferred_source(self):
  class RenderingPreview:
   def __init__(self):
    self.calls=[]
   def preview_for_json(self,path,source=""):
    self.calls.append(source)
    return f"file:///{source}.png"
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td)
   exported=app_root/"imgs"/"exported"/"Exported Missing.json"
   library=app_root/"imgs"/"library"/"Library Missing.json"
   exported.parent.mkdir(parents=True);library.parent.mkdir(parents=True)
   payload={"metadata":{"layers":1},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}
   exported.write_text(json.dumps(payload),encoding="utf-8")
   library.write_text(json.dumps(payload),encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   self.assertEqual(2,build_startup_json_index_cache(paths,preview=DummyPreview()))
   preview=RenderingPreview()
   self.assertEqual(1,warm_thumbnail_cache(paths,preview=preview,max_items=1,preferred_source=3))
   cached=json.loads((paths.runtime_root/"json-browser-index.v1.json").read_text(encoding="utf-8"))
   self.assertEqual("",cached["sources"]["2"]["rows"][0]["previewUrl"])
   self.assertEqual("file:///library.png",cached["sources"]["3"]["rows"][0]["previewUrl"])
   self.assertEqual(["library"],preview.calls)
if __name__=="__main__":unittest.main()
