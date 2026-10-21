"""Native JSON exports outside the installation retain usable, scoped IDs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from kfps_editor import server as module

EVIDENCE = ROOT / "runtime/test-runs/editor-export-ids"
PAYLOAD = {"shapes": [{"type": 1048677, "color": [70, 160, 210, 220],
                       "data": [2, -3, 1, .8, 17, .12, 0]}]}


class ExportIdTests(unittest.TestCase):
    def setUp(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=EVIDENCE)
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.app = self.base / "app"
        self.app.mkdir()
        self.runtime = self.base / "job"
        self.runtime.mkdir()
        self.paths = module.ServerPaths.for_runtime(self.app, self.runtime, exports=self.runtime / "exports")
        self.paths.exports.mkdir()
        for key, value in {"ROOT": self.app, "GENERATED_ROOT": self.app / "imgs/generated",
                           "EXPORTED_JSON_ROOT": self.app / "imgs/exported"}.items():
            setting = patch.object(module, key, value)
            setting.start()
            self.addCleanup(setting.stop)

    def write(self, relative="folder/Test % #.json", *, root=None):
        target = (root or self.paths.exports) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        return target

    def test_external_id_roundtrips_special_characters(self):
        target = self.write()
        identity = module._safe_relpath(target, paths=self.paths)
        self.assertEqual(identity, "@exports/folder/Test % #.json")
        self.assertEqual(module._resolve_browser_id(identity, paths=self.paths), target.resolve())

    def test_legacy_root_relative_ids_stay_byte_identical(self):
        target = self.write("imgs/editor/a/file.json", root=self.app)
        paths = self.paths._replace(exports=self.app / "imgs/editor")
        self.assertEqual(module._safe_relpath(target, paths=paths), "imgs/editor/a/file.json")
        self.assertEqual(module._safe_relpath(target), "imgs/editor/a/file.json")
        self.assertEqual(module._resolve_browser_id("imgs/editor/a/file.json", paths=paths), target.resolve())
        for source in ("generated", "exported"):
            target = self.write(f"imgs/{source}/file.json", root=self.app)
            self.assertEqual(module._resolve_browser_id(f"imgs/{source}/file.json", paths=paths), target.resolve())

    def test_unrelated_external_file_cannot_acquire_export_id(self):
        target = self.write("outside.json", root=self.base)
        with self.assertRaises(ValueError):
            module._safe_relpath(target, paths=self.paths)

    def test_namespace_is_locked_to_this_server_not_another_job(self):
        target = self.write("only-here.json")
        other = self.paths._replace(exports=self.base / "other-job/exports")
        with self.assertRaises(ValueError):
            module._resolve_browser_id("@exports/only-here.json", paths=other)
        self.assertEqual(target.read_text(), json.dumps(PAYLOAD))

    def test_traversal_absolute_unknown_namespace_and_unknown_files_rejected(self):
        self.write("valid.json")
        for identity in ("", "@exports", "@projects/valid.json", "@EXPORTS/valid.json",
                         "@exports/../outside.json", "@exports/a/../../outside.json",
                         "@exports//valid.json", "@exports/./valid.json", "@exports/valid.json/",
                         "@exports/C:/valid.json", "@exports/C:valid.json",
                         "@exports/\\server\\share\\valid.json", "@exports/..\\outside.json",
                         "@exports/valid.json:stream", "@exports/valid.json\x00",
                         "@exports/missing.json", "@exports/not-json.txt",
                         str(self.paths.exports / "valid.json")):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                module._resolve_browser_id(identity, paths=self.paths)

    def test_resolved_namespace_cannot_follow_a_link_outside_exports(self):
        target = self.write("outside.json", root=self.base)
        link = self.paths.exports / "escape.json"
        try:
            link.symlink_to(target)
        except OSError:
            if os.name != "nt":
                raise
            link = self.paths.exports / "redirect"
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "New-Item -ItemType Junction -Path $env:KFPS_TEST_LINK -Target $env:KFPS_TEST_LINK_TARGET -ErrorAction Stop | Out-Null"],
                           env={**os.environ, "KFPS_TEST_LINK": str(link), "KFPS_TEST_LINK_TARGET": str(target.parent)},
                           check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
            self.addCleanup(link.rmdir)
            identity = "@exports/redirect/outside.json"
        else:
            identity = "@exports/escape.json"
        with self.assertRaises(ValueError):
            module._resolve_browser_id(identity, paths=self.paths)

    def request(self, server, endpoint, data=None, *, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers[module.EDITOR_MUTATION_HEADER] = server.editor_session_token
        request = Request(f"http://127.0.0.1:{server.server_address[1]}{endpoint}",
                          data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            exc.add_note(exc.read().decode("utf-8", errors="replace"))
            exc.close()
            raise

    def exercise_http(self, *, legacy=False, cross_drive=False):
        if legacy:
            self.paths = self.paths._replace(exports=self.app / "imgs/editor")
        # No C-drive file is created/read. This exercises real Windows relative-path
        # semantics against a different-drive application root, writing only on E.
        root = Path("C:/KfpsSyntheticReadOnlyApplication") if cross_drive else self.app
        with patch.object(module, "ROOT", root), module.EditorServer(("127.0.0.1", 0), module.Handler, paths=self.paths) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                data = {"name": "Scoped % # export", "payload": PAYLOAD, "request_id": "a" * 32}
                status, _, raw = self.request(server, module.EDITOR_EXPORT_API, data)
                self.assertEqual(status, 200)
                result = json.loads(raw)
                identity = result["id"]
                self.assertEqual(identity.startswith("@exports/"), not legacy)
                target = module._resolve_browser_id(identity, paths=self.paths)
                self.assertTrue(target.is_relative_to(self.paths.exports))
                self.assertEqual(json.loads(target.read_bytes()), PAYLOAD)
                self.assertEqual(result["receipt"]["target_id"], target.relative_to(self.paths.exports).as_posix())

                _, _, raw = self.request(server, module.JSON_FILE_API + "?id=" + quote(identity, safe=""))
                loaded = json.loads(raw)
                self.assertEqual((loaded["id"], loaded["payload"]), (identity, PAYLOAD))
                _, _, raw = self.request(server, module.JSON_BROWSER_API + "?source=editor")
                entries = [entry for group in json.loads(raw)["groups"] for entry in group["entries"]]
                self.assertEqual([entry["id"] for entry in entries], [identity])
                _, headers, preview = self.request(server, entries[0]["preview_url"])
                self.assertEqual(headers.get_content_type(), "image/png")
                self.assertTrue(preview.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(preview), 100)

                _, _, raw = self.request(server, module.PROJECT_RECEIPT_API + "?kind=export&request_id=" + data["request_id"])
                receipt = json.loads(raw)
                self.assertEqual(receipt["id"], identity)
                self.assertEqual(receipt["receipt"], result["receipt"])
                query = "?kind=export&id=" + quote(result["receipt"]["target_id"], safe="")
                query += "&fingerprint=" + quote(result["receipt"]["fingerprint"], safe="")
                _, _, raw = self.request(server, module.PROJECT_RECEIPT_API + query)
                self.assertTrue(json.loads(raw)["current"])

                # An acknowledged export can be retried without a second file or
                # a different browser identity. Re-open the on-disk receipt too.
                before = sorted(self.paths.exports.rglob("*.json"))
                original = target.read_bytes()
                _, _, retry_raw = self.request(server, module.EDITOR_EXPORT_API, data)
                self.assertEqual(json.loads(retry_raw)["id"], identity)
                self.assertEqual(sorted(self.paths.exports.rglob("*.json")), before)
                self.assertEqual(target.read_bytes(), original)
                server._exports = None
                _, _, recovered_raw = self.request(server, module.PROJECT_RECEIPT_API + "?kind=export&request_id=" + data["request_id"])
                self.assertEqual(json.loads(recovered_raw)["id"], identity)
                receipt_file = self.runtime / "export-receipts" / (data["request_id"] + ".json")
                journal = json.loads(receipt_file.read_bytes())
                journal["write_stage"] = "prepared"
                receipt_file.write_text(json.dumps(journal), encoding="utf-8")
                _, _, recovered_raw = self.request(server, module.PROJECT_RECEIPT_API + "?kind=export&request_id=" + data["request_id"])
                recovered = json.loads(recovered_raw)
                self.assertEqual(recovered["id"], identity)
                self.assertEqual(recovered["receipt"]["write_stage"], "committed")
                self.assertTrue(recovered["current"])
                changed = {**data, "payload": {"shapes": []}}
                with self.assertRaises(HTTPError) as error:
                    self.request(server, module.EDITOR_EXPORT_API, changed)
                self.assertEqual(error.exception.code, 409)
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(sorted(self.paths.exports.rglob("*.json")), before)

                for bad in ("@exports/../outside.json", "@projects/file.json", "@exports/missing.json"):
                    for endpoint in (module.JSON_FILE_API, module.JSON_PREVIEW_API):
                        with self.subTest(bad=bad, endpoint=endpoint), self.assertRaises(HTTPError) as error:
                            self.request(server, endpoint + "?id=" + quote(bad, safe=""))
                        self.assertEqual(error.exception.code, 400)
                before = sorted(self.paths.exports.rglob("*.json"))
                with self.assertRaises(HTTPError) as error:
                    self.request(server, module.EDITOR_EXPORT_API, data, token=False)
                self.assertEqual(error.exception.code, 403)
                self.assertEqual(sorted(self.paths.exports.rglob("*.json")), before)
            finally:
                server.shutdown()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())

    def test_actual_http_export_list_preview_load_receipt_external_root(self):
        self.exercise_http()

    def test_actual_http_export_list_preview_load_receipt_legacy_root(self):
        self.exercise_http(legacy=True)

    def test_nested_groups_survive_http_export_reopen_and_receipt_recovery(self):
        shapes = [{**PAYLOAD["shapes"][0], "editor_group_id": "inner", "editor_group_name": "Inner",
                   "editor_group_path": [{"id": "outer", "name": "Outer"}, {"id": "inner", "name": "Inner"}]}]
        shapes.append({**PAYLOAD["shapes"][0], "editor_group_id": "outer", "editor_group_name": "Outer"})
        shapes.append(dict(PAYLOAD["shapes"][0]))
        with patch.dict(globals(), PAYLOAD={"shapes": shapes}):
            self.exercise_http()

    @unittest.skipUnless(os.name == "nt" and ROOT.drive.upper() == "E:", "Windows E/C path semantics")
    def test_actual_http_export_list_preview_load_receipt_cross_drive(self):
        self.exercise_http(cross_drive=True)


if __name__ == "__main__":
    unittest.main()
