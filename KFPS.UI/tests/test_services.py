import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT));os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.generation_service import GenerationService
from kfps_ui.json_service import JsonService, build_startup_json_index_cache
from kfps_ui.json_thumbnail_worker import regenerate_thumbnail_cache, warm_thumbnail_cache, worker_command
from kfps_ui.log_service import LogService
from kfps_ui.preview_service import PreviewService
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
 def test_force_stop_preserves_finalizer_and_kills_only_genesis(self):
  class FakeProcess:
   def __init__(self,name):self._name=name;self.killed=False
   def name(self):return self._name
   def kill(self):self.killed=True
  class FakeParent(FakeProcess):
   def __init__(self,children):super().__init__("bridge-python.exe");self._children=children
   def children(self,recursive=True):return self._children
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");log=DummyLog();svc=GenerationService(paths,log)
   wrapper=FakeProcess("python.exe");genesis=FakeProcess("KloudysGalateaGenesis.exe");parent=FakeParent([wrapper,genesis])
   svc._process=SimpleNamespace(processId=lambda:42);svc._running=True
   with patch("kfps_ui.generation_service.psutil.Process",return_value=parent):svc.forceStop()
   self.assertTrue(genesis.killed)
   self.assertFalse(wrapper.killed)
   self.assertFalse(parent.killed)
   self.assertIn("finalizing saved checkpoints",svc.status.lower())

 def test_generation_preview_revision_changes_when_same_file_is_rewritten(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);run=root/"imgs"/"generated"/"run";previews=run/"previews";previews.mkdir(parents=True)
   preview=previews/"sample.raw.preview.png";preview.write_bytes(b"first")
   paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");svc=GenerationService(paths,DummyLog());svc._run_dir=str(run)
   svc.refreshPreview();first_revision=svc.previewRevision;first_url=svc.previewUrl
   first_mtime=preview.stat().st_mtime_ns;preview.write_bytes(b"second-preview");os.utime(preview,ns=(first_mtime+1_000_000,first_mtime+1_000_000))
   svc.refreshPreview()
   self.assertEqual(first_url,svc.previewUrl)
   self.assertEqual(first_revision+1,svc.previewRevision)
   svc.refreshPreview();self.assertEqual(first_revision+1,svc.previewRevision)

 def test_manual_generator_defaults_follow_the_selected_preset(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");svc=GenerationService(paths,DummyLog())
   expected=[
    {"maxResolution":"1250","randomSamples":"200000","mutatedSamples":"15000","seed":"0"},
    {"maxResolution":"1000","randomSamples":"220000","mutatedSamples":"15000","seed":"0"},
    {"maxResolution":"1075","randomSamples":"240000","mutatedSamples":"15000","seed":"0"},
   ]
   for index,values in enumerate(expected):
    svc.setSelectedPresetIndex(index)
    self.assertEqual(values,svc.manualOverrideDefaults)
 def test_report_is_local_markdown(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/"VERSION").write_text("3.0.12");paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");log=LogService();svc=ReportService(paths,log,DummyVersion());text=svc.build("Bug","Test","Details",True,False,False);self.assertIn("# KFPS Report",text);self.assertNotIn("Visible runtime log",text)
 def test_no_memory_write_in_tests(self):
  dangerous=["fh6_import_typecode_json.py","fh6_export_typecode_json.py","fh6_trim_group_count.py"]
  self.assertTrue(all((ROOT/name).exists() for name in dangerous))
 def test_supporter_unlock_install_handles_stale_temp_source(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);source=app_root/"runtime"/"supporter"/"supporter.tmp";source.parent.mkdir(parents=True);source.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root,enforce_activation=False);payload={"supporter_name":"Test","entitlements":["supporter_theme"]}
   self.assertTrue(svc._install_key(source,payload,"Local unlock verified.",remove_source=True))
   self.assertTrue((app_root/"supporter.kfpskey").exists())
   self.assertFalse(source.exists())
   self.assertTrue(svc.unlocked)
 def test_supporter_unlock_install_preserves_personal_key_name(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);source=app_root/"downloads"/"Alice Custom.kfpskey";source.parent.mkdir(parents=True);source.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root,enforce_activation=False);payload={"supporter_name":"Alice","entitlements":["supporter_theme"]}
   self.assertTrue(svc._install_key(source,payload,"Local unlock verified."))
   self.assertTrue((app_root/"Alice Custom.kfpskey").exists())
   self.assertTrue(svc.unlocked)
 def test_supporter_unlock_reload_accepts_root_key_drop(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);key=app_root/"Manual Drop.kfpskey";key.write_text("validated key bytes",encoding="utf-8")
   svc=SupporterService(app_root,enforce_activation=False);payload={"supporter_name":"Manual","entitlements":["supporter_theme"]}
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
 def test_regenerate_thumbnail_cache_clears_only_runtime_cache_and_rebuilds_every_source(self):
  class RebuildPreview:
   def __init__(self):self.cleared=False;self.calls=[]
   def clear_cached_thumbnails(self):self.cleared=True;return 2
   def existing_preview_for_json(self,path,source=""):raise AssertionError("forced rebuild searched stale previews")
   def regenerate_preview_for_json(self,path,source=""):
    self.calls.append((Path(path).name,source));return f"file:///{source}-rebuilt.png"
   def preview_for_json(self,path,source=""):raise AssertionError("forced rebuild used the normal preview lookup")
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"exported"/"Rebuild.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"layers":1},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   nearby=target.with_suffix(".png");nearby.write_bytes(b"personal-preview")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   cache=paths.runtime_root/"qml-json-previews";cache.mkdir(parents=True);(cache/"old.png").write_bytes(b"old")
   outside=paths.runtime_root/"keep.txt";outside.write_text("keep",encoding="utf-8")
   self.assertEqual(1,PreviewService(paths).clear_cached_thumbnails())
   self.assertFalse(cache.exists());self.assertTrue(nearby.exists());self.assertTrue(outside.exists())
   preview=RebuildPreview();rendered,removed,indexed=regenerate_thumbnail_cache(paths,preview=preview)
   self.assertEqual((1,2,1),(rendered,removed,indexed));self.assertTrue(preview.cleared)
   self.assertEqual([("Rebuild.json","exported")],preview.calls)
   payload=json.loads((paths.runtime_root/"json-browser-index.v1.json").read_text(encoding="utf-8"))
   self.assertEqual("file:///exported-rebuilt.png",payload["sources"]["2"]["rows"][0]["previewUrl"])
 def test_regenerate_thumbnail_cache_force_renders_more_than_900_indexed_jsons(self):
  class BulkPreview:
   def __init__(self):self.calls=[]
   def clear_cached_thumbnails(self):return 0
   def existing_preview_for_json(self,path,source=""):raise AssertionError("bulk rebuild searched stale previews")
   def regenerate_preview_for_json(self,path,source=""):
    self.calls.append((Path(path).name,source));return f"file:///rebuilt/{Path(path).stem}.png"
   def preview_for_json(self,path,source=""):raise AssertionError("forced rebuild skipped its renderer")
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);library=app_root/"imgs"/"library";library.mkdir(parents=True)
   payload=json.dumps({"metadata":{"layers":1},"shapes":[{"type":1048677,"data":[0,0,1,1,0],"color":[255,255,255,255]}]})
   for index in range(905):(library/f"Local-{index:04d}.json").write_text(payload,encoding="utf-8")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   preview=BulkPreview();rendered,removed,indexed=regenerate_thumbnail_cache(paths,preview=preview)
   self.assertEqual((905,0,905),(rendered,removed,indexed))
   self.assertEqual(905,len(preview.calls))
   self.assertTrue(all(source=="library" for _name,source in preview.calls))
 def test_forced_regeneration_keeps_personal_adjacent_png_and_replaces_managed_cache(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);target=app_root/"imgs"/"exported"/"Managed.json";target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"metadata":{"layers":1},"shapes":[{"type":1048677,"data":[0,0,100,60,0],"color":[255,255,255,255]}]}),encoding="utf-8")
   adjacent=target.with_suffix(".png");adjacent.write_bytes(b"personal-preview")
   paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   preview=PreviewService(paths);url=preview.regenerate_preview_for_json(target,"exported")
   managed=preview._cache_target(target,"general")
   self.assertTrue(url);self.assertTrue(managed.is_file());self.assertTrue(managed.read_bytes().startswith(b"\x89PNG"))
   self.assertEqual(b"personal-preview",adjacent.read_bytes())
 def test_online_import_guard_distinguishes_community_downloads_from_save_scans(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   community=paths.library_root/"Community"/"Creator"/"Artwork"/"Artwork.json"
   scanned=paths.library_root/"0001E505-save-scan"/"Scanned.json"
   community.parent.mkdir(parents=True);scanned.parent.mkdir(parents=True)
   payload=json.dumps({"shapes":[]})
   community.write_text(payload,encoding="utf-8");scanned.write_text(payload,encoding="utf-8")
   svc=JsonService(paths,DummyPreview(),DummyDesktop(community),DummyLog())
   try:
    svc.selectPath(str(community))
    self.assertFalse(svc.selectedIsGameLibraryItem)
    svc.selectPath(str(scanned))
    self.assertTrue(svc.selectedIsGameLibraryItem)
    exported=paths.exported_root/"Manual.json";exported.parent.mkdir(parents=True,exist_ok=True);exported.write_text(payload,encoding="utf-8")
    svc.selectPath(str(exported))
    self.assertFalse(svc.selectedIsGameLibraryItem)
    qml=(UI/"qml"/"pages"/"JsonPage.qml").read_text(encoding="utf-8")
    self.assertIn("jsonService.selectedIsGameLibraryItem",qml)
    self.assertNotIn("jsonService.sourceIndex === 3 ? \"Already in Game Library\"",qml)
   finally:
    shutdown_json_service(svc)
 def test_settings_regeneration_command_uses_the_dedicated_worker_mode(self):
  with tempfile.TemporaryDirectory() as td:
   app_root=Path(td);paths=AppPaths(app_root,UI,UI/"qml",UI/"assets",app_root/"runtime",app_root/"python/python.exe")
   svc=JsonService(paths,DummyPreview(),DummyDesktop(app_root),DummyLog())
   try:
    with patch.object(svc,"_thumbnail_worker_enabled",return_value=True), patch.object(svc,"_start_thumbnail_worker") as start:
     svc.regenerateLocalThumbnails()
    self.assertTrue(svc.thumbnailRegenerating);self.assertTrue(svc.thumbnailActive)
    start.assert_called_once_with(regenerate=True)
    qml=(UI/"qml"/"pages"/"SettingsPage.qml").read_text(encoding="utf-8")
    self.assertIn('text: jsonService.thumbnailRegenerating ? "Regenerating..." : "Regenerate Local Thumbnails"',qml)
    self.assertIn("jsonService.regenerateLocalThumbnails()",qml)
    command=worker_command(paths,regenerate=True,app_executable=sys.executable)
    self.assertIn("--thumbnail-worker-regenerate",command)
   finally:
    shutdown_json_service(svc)
if __name__=="__main__":unittest.main()
