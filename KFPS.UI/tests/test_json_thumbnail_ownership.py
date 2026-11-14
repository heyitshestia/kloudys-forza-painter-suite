import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(UI.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_OPENGL", "software")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QImage

from kfps_ui.app_paths import AppPaths
from kfps_ui.json_index import build_startup_json_index_cache, write_index_cache_payload
from kfps_ui.json_service import JsonService
from kfps_ui.preview_service import PreviewService
from kfps_ui import json_thumbnail_worker as worker

APP = QCoreApplication.instance() or QCoreApplication([])


def make_paths(root):
    return AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", Path(sys.executable))


def write_art(path, layers=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    shape = {"type": 1048677, "data": [0, 0, 100, 60, 0], "color": [255, 40, 40, 255]}
    path.write_text(json.dumps({"shapes": [shape] * layers}), encoding="utf-8")


class QuietLog:
    def append(self, *args):
        pass


class ThumbnailOwnershipTests(unittest.TestCase):
    def setUp(self):
        parent = os.environ.get("KFPS_R6_TEST_ROOT")
        self.temp = tempfile.TemporaryDirectory(prefix="r6-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = make_paths(self.root)
        self.target = self.paths.exported_root / "Original.json"
        write_art(self.target)
        build_startup_json_index_cache(self.paths, include_existing_previews=False)
        self.cache = self.paths.runtime_root / "json-browser-index.v1.json"
        later = patch.object(JsonService, "_call_later", lambda svc, ms, cb: cb() if ms == 0 else None)
        later.start()
        self.addCleanup(later.stop)
        self.real_enqueue_preview = JsonService._enqueue_preview_path
        previews = patch.object(JsonService, "_enqueue_preview_path")
        previews.start()
        self.addCleanup(previews.stop)

    def make_service(self):
        service = JsonService(self.paths, PreviewService(self.paths), object(), QuietLog())
        self.addCleanup(service.close)
        service.setSource(2)
        return service

    def start_worker(self, regenerate, service=None, pause_at=1, before_clear=False):
        (self.root / "render-paused").unlink(missing_ok=True)
        (self.root / "render-resume").unlink(missing_ok=True)
        args = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", str(self.root)]
        args.extend(["--pause-at", str(pause_at)])
        if regenerate:
            args.append("--regenerate")
        if before_clear:
            args.append("--before-clear")
        if service is None:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            with patch.object(service, "_thumbnail_worker_enabled", return_value=True), \
                    patch("kfps_ui.json_service.worker_command", return_value=args):
                if regenerate:
                    service.regenerateLocalThumbnails()
                else:
                    service._start_thumbnail_worker()
            service._thumbnail_poll_timer.stop()
            proc = service._thumbnail_process
            self.assertIsNotNone(proc)
        self.addCleanup(self.stop_worker, proc)
        deadline = time.monotonic() + 20
        while not (self.root / "render-paused").exists():
            if proc.poll() is not None:
                self.fail(f"Worker exited before rendering: {proc.communicate()}")
            if time.monotonic() > deadline:
                self.fail("Worker did not reach render barrier")
            time.sleep(0.01)
        return proc

    @staticmethod
    def stop_worker(proc):
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=10)

    def finish_worker(self, proc):
        (self.root / "render-resume").touch()
        stdout, stderr = proc.communicate(timeout=30)
        self.assertEqual(0, proc.returncode, stderr)
        return stdout

    def test_warm_subprocess_cannot_overwrite_concurrent_inventory(self):
        self.assert_concurrent_inventory_preserved(False)

    def test_regenerate_subprocess_cannot_overwrite_concurrent_inventory(self):
        self.assert_concurrent_inventory_preserved(True)

    def assert_concurrent_inventory_preserved(self, regenerate):
        proc = self.start_worker(regenerate)
        added = self.paths.exported_root / "Concurrent Export.json"
        write_art(added, 2)
        build_startup_json_index_cache(self.paths, include_existing_previews=False)
        payload = json.loads(self.cache.read_text(encoding="utf-8"))
        payload["ownerRevision"] = "concurrent-export-and-rescan"
        write_index_cache_payload(self.cache, payload)
        expected = self.cache.read_bytes()
        self.finish_worker(proc)
        self.assertEqual(expected, self.cache.read_bytes(), "renderer rewrote inventory")
        self.assertTrue(added.is_file())

    def test_warm_service_preserves_export_rescan_and_changed_file(self):
        self.assert_service_concurrency(False, delete=False)

    def test_regenerate_service_preserves_export_rescan_and_changed_file(self):
        self.assert_service_concurrency(True, delete=False)

    def test_warm_service_preserves_export_rescan_and_deleted_file(self):
        self.assert_service_concurrency(False, delete=True)

    def test_regenerate_service_preserves_export_rescan_and_deleted_file(self):
        self.assert_service_concurrency(True, delete=True)

    def assert_service_concurrency(self, regenerate, delete):
        service = self.make_service()
        proc = self.start_worker(regenerate, service=service)
        imported = self.root / "inputs" / "Concurrent Export.json"
        write_art(imported, 2)

        class Desktop:
            def chooseJson(self):
                return str(imported)

        service.desktop = Desktop()
        service.browseManual()
        if delete:
            self.assertTrue(service.deleteEntry(str(self.target)))
        else:
            write_art(self.target, 3)
            service.refreshGameOutputs()
        service.selectPath(str(self.paths.exported_root / imported.name))
        selected = service.selectedPath
        current_index = service._source_index_cache[2]
        expected = [(row["path"], row["layers"], row["mtimeNs"], row["size"])
                    for row in current_index["rows"]]
        service._save_index_cache_async()
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertIs(current_index, service._source_index_cache[2])
        self.assertEqual(selected, service.selectedPath)
        self.assertEqual(expected, [(row["path"], row["layers"], row["mtimeNs"], row["size"])
                                    for row in current_index["rows"]])
        if not delete:
            original = current_index["rowsByKey"][service._preview_key(self.target)]
            self.assertEqual(3, original["layers"])
            self.assertEqual("", original["previewUrl"])
        service._save_index_cache_async()
        service.close()
        restarted = self.make_service()
        self.assertEqual({Path(row[0]).name for row in expected},
                         {row["name"] for row in restarted._source_index_cache[2]["rows"]})

    def test_merge_rejects_change_after_worker_finished_even_before_rescan(self):
        service = self.make_service()
        proc = self.start_worker(False)
        self.finish_worker(proc)
        write_art(self.target, 4)
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
        self.assertEqual("", service._source_index_cache[2]["rows"][0]["previewUrl"])

    def test_merge_rejects_deleted_file_even_before_rescan(self):
        service = self.make_service()
        proc = self.start_worker(False)
        self.finish_worker(proc)
        self.target.unlink()
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))

    def test_interrupted_regeneration_invalidates_only_its_missing_previews(self):
        preview = PreviewService(self.paths)
        old_url = preview.regenerate_preview_for_json(self.target, "exported")
        build_startup_json_index_cache(self.paths, preview=preview)
        service = self.make_service()
        self.assertEqual(old_url, service._source_index_cache[2]["rows"][0]["previewUrl"])
        proc = self.start_worker(True, service=service)
        added = self.paths.exported_root / "Newer.json"
        write_art(added)
        service.refreshGameOutputs()
        new_url = preview.regenerate_preview_for_json(added, "exported")
        service._update_preview_url(str(added), new_url)
        service._stop_thumbnail_worker()
        self.assertIsNotNone(proc.returncode)
        service._merge_preview_urls_from_cache(force=True)
        rows = service._source_index_cache[2]["rowsByKey"]
        self.assertEqual("", rows[service._preview_key(self.target)]["previewUrl"])
        self.assertEqual(new_url, rows[service._preview_key(added)]["previewUrl"])
        self.assertEqual("", next(row for row in service.fileModel.rows if row["path"] == str(self.target))["previewUrl"])
        service._save_index_cache_async()
        service.close()
        restarted = self.make_service()
        self.assertEqual(2, len(restarted._source_index_cache[2]["rows"]))
        resumed = self.start_worker(False, service=restarted)
        self.finish_worker(resumed)
        restarted._poll_thumbnail_worker()
        urls = [row["previewUrl"] for row in restarted._source_index_cache[2]["rows"]]
        self.assertTrue(all(urls))
        for url in urls:
            self.assertFalse(QImage(QUrl(url).toLocalFile()).isNull())

    def test_interrupted_warm_checkpoint_survives_restart(self):
        for index in range(26):
            write_art(self.paths.exported_root / f"Checkpoint-{index:02d}.json")
        build_startup_json_index_cache(self.paths, include_existing_previews=False)
        inventory = self.cache.read_bytes()
        proc = self.start_worker(False, pause_at=26)
        self.stop_worker(proc)
        self.assertEqual(inventory, self.cache.read_bytes())
        restarted = self.make_service()
        rows = restarted._source_index_cache[2]["rows"]
        self.assertEqual(27, len(rows))
        self.assertEqual(25, sum(bool(row["previewUrl"]) for row in rows))
        restarted._save_index_cache_async()
        proc = self.start_worker(False, service=restarted)
        self.finish_worker(proc)
        restarted._poll_thumbnail_worker()
        self.assertTrue(all(row["previewUrl"] for row in rows))

    def test_failed_regeneration_does_not_invalidate_later_repaired_preview(self):
        class FailingPreview(PreviewService):
            def regenerate_preview_for_json(self, path, source=""):
                return ""

        worker.regenerate_thumbnail_cache(self.paths, preview=FailingPreview(self.paths))
        service = self.make_service()
        url = service.preview.regenerate_preview_for_json(self.target, "exported")
        service._update_preview_url(str(self.target), url)
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
        self.assertEqual(url, service._source_index_cache[2]["rows"][0]["previewUrl"])

    def test_regeneration_before_clear_preserves_concurrent_new_preview(self):
        service = self.make_service()
        orphan = service.preview.cache / "unrelated-old-preview.png"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_bytes(b"outside-the-source-snapshot")
        proc = self.start_worker(True, service=service, before_clear=True)
        added = self.paths.exported_root / "Added after snapshot.json"
        write_art(added, 2)
        service.refreshGameOutputs()
        url = service.preview.regenerate_preview_for_json(added, "exported")
        png = Path(QUrl(url).toLocalFile())
        before = png.read_bytes()
        service._update_preview_url(str(added), url)
        service.selectPath(str(added))
        selected = service.selectedPath
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertTrue(png.is_file(), "regeneration deleted a preview outside its snapshot")
        self.assertEqual(before, png.read_bytes())
        self.assertEqual(b"outside-the-source-snapshot", orphan.read_bytes())
        self.assertFalse(QImage(str(png)).isNull())
        self.assertEqual(selected, service.selectedPath)
        self.assertEqual(2, len(service._source_index_cache[2]["rows"]))
        self.assertFalse(service._cache_has_missing_preview_urls())
        service._save_index_cache_async()
        service.close()
        restarted = self.make_service()
        row = restarted._source_index_cache[2]["rowsByKey"][service._preview_key(added)]
        self.assertEqual(url, row["previewUrl"])

    def test_regeneration_before_clear_preserves_changed_source_preview(self):
        service = self.make_service()
        proc = self.start_worker(True, service=service, before_clear=True)
        write_art(self.target, 3)
        service.refreshGameOutputs()
        url = service.preview.regenerate_preview_for_json(self.target, "exported")
        png = Path(QUrl(url).toLocalFile())
        before = png.read_bytes()
        source_before = self.target.read_bytes()
        service._update_preview_url(str(self.target), url)
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertTrue(png.is_file(), "cleanup followed a newer source revision")
        self.assertEqual(before, png.read_bytes())
        self.assertEqual(source_before, self.target.read_bytes())
        self.assertEqual(3, service._source_index_cache[2]["rows"][0]["layers"])
        self.assertEqual(url, service._source_index_cache[2]["rows"][0]["previewUrl"])

    def test_regeneration_before_clear_preserves_repaired_same_source_preview(self):
        preview = PreviewService(self.paths)
        url = preview.regenerate_preview_for_json(self.target, "exported")
        build_startup_json_index_cache(self.paths, preview=preview)
        service = self.make_service()
        proc = self.start_worker(True, service=service, before_clear=True)
        self.assertEqual(url, preview.regenerate_preview_for_json(self.target, "exported"))
        png = Path(QUrl(url).toLocalFile())
        repaired = worker.thumbnail_file_revision(png)
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertEqual(repaired, worker.thumbnail_file_revision(png),
                         "obsolete regeneration replaced a subsequently repaired preview")
        self.assertEqual(url, service._source_index_cache[2]["rows"][0]["previewUrl"])
        self.assertFalse(QImage(str(png)).isNull())

    def test_warm_recovers_missing_preview_for_running_owner(self):
        preview = PreviewService(self.paths)
        url = preview.regenerate_preview_for_json(self.target, "exported")
        build_startup_json_index_cache(self.paths, preview=preview)
        service = self.make_service()
        png = Path(QUrl(url).toLocalFile())
        png.unlink()
        self.assertTrue(service._cache_has_missing_preview_urls())
        proc = self.start_worker(False, service=service)
        self.assertEqual("", service._source_index_cache[2]["rows"][0]["previewUrl"])
        self.assertEqual("", service.fileModel.rows[0]["previewUrl"])
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertEqual(url, service._source_index_cache[2]["rows"][0]["previewUrl"])
        self.assertFalse(QImage(str(png)).isNull())
        self.assertFalse(service._cache_has_missing_preview_urls())

    def test_warm_subprocess_recovers_missing_preview_from_persisted_inventory(self):
        preview = PreviewService(self.paths)
        url = preview.regenerate_preview_for_json(self.target, "exported")
        build_startup_json_index_cache(self.paths, preview=preview)
        png = Path(QUrl(url).toLocalFile())
        png.unlink()
        inventory = self.cache.read_bytes()
        proc = self.start_worker(False)
        self.finish_worker(proc)
        self.assertEqual(inventory, self.cache.read_bytes())
        service = self.make_service()
        self.assertEqual(url, service._source_index_cache[2]["rows"][0]["previewUrl"])
        self.assertFalse(QImage(str(png)).isNull())

    def test_visible_preview_request_recovers_missing_file(self):
        preview = PreviewService(self.paths)
        url = preview.regenerate_preview_for_json(self.target, "exported")
        build_startup_json_index_cache(self.paths, preview=preview)
        service = self.make_service()
        png = Path(QUrl(url).toLocalFile())
        png.unlink()
        with patch.object(service, "_enqueue_preview_path", side_effect=lambda *a, **kw:
                          self.real_enqueue_preview(service, *a, **kw)):
            service.requestPreview(str(self.target))
        self.assertFalse(QImage(str(png)).isNull())
        self.assertEqual(url, service.fileModel.rows[0]["previewUrl"])

    def test_existing_and_non_file_preview_urls_do_not_trigger_repair(self):
        service = self.make_service()
        local = service.preview.regenerate_preview_for_json(self.target, "exported")
        for url in (local, "image://provided/preview", "data:image/png;base64,synthetic"):
            with self.subTest(url=url):
                service._update_preview_url(str(self.target), url)
                service._save_index_cache_async()
                self.assertFalse(service._cache_has_missing_preview_urls())
                with patch.object(service.preview, "preview_for_json", side_effect=AssertionError("unneeded repair")):
                    self.assertEqual(0, worker.warm_thumbnail_cache(self.paths, preview=service.preview))
                self.assertEqual(url, service.fileModel.rows[0]["previewUrl"])

    def test_warm_item_limit_and_custom_result_location(self):
        for index in range(4):
            write_art(self.paths.exported_root / f"Bounded-{index}.json")
        build_startup_json_index_cache(self.paths, include_existing_previews=False)
        custom = self.paths.runtime_root / "custom-index.json"
        custom.write_bytes(self.cache.read_bytes())
        original = custom.read_bytes()
        self.assertEqual(2, worker.warm_thumbnail_cache(self.paths, cache_file=custom, max_items=2))
        self.assertEqual(original, custom.read_bytes())
        results = json.loads(worker.thumbnail_results_file(custom).read_text(encoding="utf-8"))
        self.assertEqual(2, sum(len(source["rows"]) for source in results["sources"].values()))
        self.assertFalse(worker.thumbnail_results_file(self.cache).exists())

    def test_real_app_worker_command_preserves_stdout_and_inventory(self):
        before = self.cache.read_bytes()
        for regenerate in (False, True):
            command = worker.worker_command(self.paths, regenerate=regenerate)
            command.insert(1, "-B")
            result = subprocess.run(command, env=worker.worker_environment(self.paths),
                                    capture_output=True, text=True, timeout=30,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(0, result.returncode, result.stderr)
            if regenerate:
                summary = json.loads(result.stdout.strip().splitlines()[-1])
                self.assertEqual(1, summary["rendered"])
                self.assertEqual(1, summary["indexed"])
                self.assertEqual(0, summary["failed"])
            else:
                self.assertEqual("1", result.stdout.strip().splitlines()[-1])
            self.assertEqual(before, self.cache.read_bytes())
        restarted = self.make_service()
        url = restarted._source_index_cache[2]["rows"][0]["previewUrl"]
        self.assertFalse(QImage(QUrl(url).toLocalFile()).isNull())

    def test_owner_queued_writes_remain_ordered_during_worker_merge(self):
        service = self.make_service()
        proc = self.start_worker(True, service=service)
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def hold_writer_queue():
            entered.set()
            self.assertTrue(release.wait(10))

        blocker = service._index_executor.submit(hold_writer_queue)
        self.assertTrue(entered.wait(5))
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "test-native-writer-branch"}):
            service._save_index_cache_async()
        added = self.paths.exported_root / "Queued Export.json"
        write_art(added, 2)
        service.refreshGameOutputs()
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "test-native-writer-branch"}):
            service._save_index_cache_async()
        release.set()
        blocker.result(timeout=10)
        service._index_executor.submit(lambda: None).result(timeout=10)
        stored = json.loads(self.cache.read_text(encoding="utf-8"))["sources"]["2"]["rows"]
        self.assertEqual({"Original.json", "Queued Export.json"}, {row["name"] for row in stored})
        self.assertTrue(next(row for row in stored if row["name"] == "Original.json")["previewUrl"])

    def test_result_merge_is_idempotent_and_rejects_partial_sidecar(self):
        service = self.make_service()
        proc = self.start_worker(False)
        self.finish_worker(proc)
        result_file = worker.thumbnail_results_file(self.cache)
        completed = result_file.read_bytes()
        result_file.write_text('{"version":1,"sources":', encoding="utf-8")
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
        result_file.write_bytes(completed)
        with patch.object(service, "_schedule_index_cache_save") as save:
            self.assertEqual(1, service._merge_preview_urls_from_cache(force=True))
            self.assertEqual(0, service._merge_preview_urls_from_cache())
            self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
            save.assert_called_once()

    def test_regeneration_completion_does_not_reset_gallery_models(self):
        service = self.make_service()
        proc = self.start_worker(True, service=service)
        resets = []
        service.fileModel.modelReset.connect(lambda: resets.append("files"))
        service.explorerModel.modelReset.connect(lambda: resets.append("explorer"))
        self.finish_worker(proc)
        service._poll_thumbnail_worker()
        self.assertTrue(service._source_index_cache[2]["rows"][0]["previewUrl"])
        self.assertEqual([], resets)

    def test_results_do_not_insert_unknown_rows_or_cross_source_roots(self):
        service = self.make_service()
        proc = self.start_worker(False)
        self.finish_worker(proc)
        result_file = worker.thumbnail_results_file(self.cache)
        results = json.loads(result_file.read_text(encoding="utf-8"))
        results["sources"]["2"]["root"] = str(self.root / "other")
        write_index_cache_payload(result_file, results)
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
        results["sources"]["2"]["root"] = service._source_cache_key(2)
        service._source_index_cache[2] = service._empty_source_index(2)
        write_index_cache_payload(result_file, results)
        self.assertEqual(0, service._merge_preview_urls_from_cache(force=True))
        self.assertEqual([], service._source_index_cache[2]["rows"])

    def test_warm_time_limit_stops_at_render_boundary(self):
        for index in range(3):
            write_art(self.paths.exported_root / f"Time-{index}.json")
        build_startup_json_index_cache(self.paths, include_existing_previews=False)
        now = [0.0]

        class TimedPreview:
            def preview_for_json(self, path, source=""):
                now[0] += 2
                return "file:///time-limited.png"

        with patch.object(worker.time, "monotonic", side_effect=lambda: now[0]):
            self.assertEqual(1, worker.warm_thumbnail_cache(self.paths, max_seconds=1, preview=TimedPreview()))
        results = json.loads(worker.thumbnail_results_file(self.cache).read_text(encoding="utf-8"))
        self.assertEqual(1, sum(len(source["rows"]) for source in results["sources"].values()))


def child_main():
    root = Path(sys.argv[2])
    paths = make_paths(root)
    before_clear = "--before-clear" in sys.argv

    def barrier():
        (root / "render-paused").touch()
        deadline = time.monotonic() + 30
        while not (root / "render-resume").exists():
            if time.monotonic() > deadline:
                raise TimeoutError("render barrier timed out")
            time.sleep(0.01)

    publish = worker.write_index_cache_payload
    published = False

    def pause_after_snapshot(*args, **kwargs):
        nonlocal published
        publish(*args, **kwargs)
        if before_clear and not published:
            published = True
            barrier()

    class PausedPreview(PreviewService):
        paused = False
        calls = 0

        def pause_once(self):
            if before_clear:
                return
            self.calls += 1
            pause_at = int(sys.argv[sys.argv.index("--pause-at") + 1])
            if self.calls != pause_at:
                return
            if self.paused:
                return
            self.paused = True
            barrier()

        def preview_for_json(self, path, source=""):
            self.pause_once()
            return super().preview_for_json(path, source)

        def regenerate_preview_for_json(self, path, source=""):
            self.pause_once()
            return super().regenerate_preview_for_json(path, source)

    args = ["--app-root", str(root), "--ui-root", str(UI), "--runtime-root", str(paths.runtime_root)]
    if "--regenerate" in sys.argv:
        args.append("--regenerate")
    with patch.object(worker, "PreviewService", PausedPreview), \
            patch.object(worker, "write_index_cache_payload", side_effect=pause_after_snapshot):
        return worker.main(args)


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child_main())
    unittest.main()
