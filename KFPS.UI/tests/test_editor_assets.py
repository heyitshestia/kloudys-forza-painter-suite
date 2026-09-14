import copy
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from test_fabric_editor_server import RunningEditorServer, fabric_server, post_json


API = fabric_server.EDITOR_ASSETS_API
SHAPE = {"type": 1048677, "type_word": 101, "data": [0, 0, 1, 1, 0, 0, 0], "color": [12, 34, 56, 255], "editor_group_id": "group-a", "editor_group_name": "Original group", "mask": False}


def save(server, **overrides):
    payload = {"format": fabric_server.EDITOR_ASSET_FORMAT, "name": "Test asset", "shapes": [copy.deepcopy(SHAPE)]}
    payload.update(overrides)
    return post_json(server, API, {"action": "save", "payload": payload})[1]["entry"]


def get(server, query=""):
    with urllib.request.urlopen(f"{server}{API}{query}") as response:
        return json.load(response)


class EditorAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "assets"
        self.patch = patch.object(fabric_server, "EDITOR_ASSET_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_save_restart_rename_delete_preserves_shapes(self):
        with RunningEditorServer() as server:
            entry = save(server, name="My grouped asset")
            self.assertEqual(1, entry["layer_count"])
            original = get(server, "?id=" + entry["id"])["payload"]
        with RunningEditorServer() as server:
            self.assertEqual([entry], get(server)["entries"])
            renamed = post_json(server, API, {"action": "rename", "id": entry["id"], "revision": 1, "name": "New name"})[1]["entry"]
            self.assertEqual(2, renamed["revision"])
            self.assertEqual(original["shapes"], get(server, "?id=" + entry["id"])["payload"]["shapes"])
            with self.assertRaises(urllib.error.HTTPError) as error:
                post_json(server, API, {"action": "delete", "id": entry["id"], "revision": 1})
            self.assertEqual(409, error.exception.code)
            post_json(server, API, {"action": "delete", "id": entry["id"], "revision": 2})
            self.assertEqual([], get(server)["entries"])

    def test_invalid_files_and_authorization(self):
        with RunningEditorServer() as server:
            entry = save(server)
            initial = next(self.root.glob("*.json")).read_bytes()
            invalid = [{"shapes": []}, {"name": ""}, {"shapes": [dict(SHAPE, color=[300, 0, 0, 0])]}, {"shapes": [dict(SHAPE, data=[float("nan")] * 7)]}, {"shapes": [dict(SHAPE, source_path="private")]}, {"shapes": [dict(SHAPE, resource_index={})]}]
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(urllib.error.HTTPError):
                    save(server, **payload)
            with self.assertRaises(urllib.error.HTTPError) as error:
                post_json(server, API, {"action": "delete", "id": entry["id"], "revision": 1}, token=False)
            self.assertEqual(403, error.exception.code)
            for value in ("../elsewhere", "x", entry["id"] + "/"):
                with self.assertRaises(urllib.error.HTTPError):
                    get(server, "?id=" + value)
            self.assertEqual(initial, next(self.root.glob("*.json")).read_bytes())

    def test_corruption_is_reported_not_removed(self):
        self.root.mkdir()
        broken = self.root / ("a" * 32 + ".asset.json")
        broken.write_text("broken", encoding="utf-8")
        with RunningEditorServer() as server:
            save(server)
            result = get(server)
            self.assertEqual(1, len(result["entries"]))
            self.assertEqual(1, len(result["unavailable"]))
            self.assertEqual("broken", broken.read_text())

    def test_nested_groups_survive_asset_save_and_restart(self):
        nested = dict(SHAPE, editor_group_path=[
            {"id": "outer", "name": "Added project"},
            {"id": "group-a", "name": "Original group"},
        ])
        with RunningEditorServer() as server:
            entry = save(server, shapes=[nested])
        with RunningEditorServer() as server:
            self.assertEqual(nested, get(server, "?id=" + entry["id"])["payload"]["shapes"][0])
            for path in ([], "bad", [{"id": "wrong", "name": "Wrong leaf"}],
                         [{"id": "group-a", "name": "A"}] * 2,
                         [{"id": "group-a", "name": "A", "source_path": "private"}],
                         [{"id": str(i), "name": "Group"} for i in range(65)]):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError):
                    save(server, shapes=[dict(nested, editor_group_path=path)])

    def test_failed_atomic_rename_retains_previous_document(self):
        with RunningEditorServer() as server:
            entry = save(server)
            file = self.root / (entry["id"] + ".asset.json")
            before = file.read_bytes()
            with patch.object(fabric_server.os, "replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(urllib.error.HTTPError):
                    post_json(server, API, {"action": "rename", "id": entry["id"], "revision": 1, "name": "Not saved"})
            self.assertEqual(before, file.read_bytes())
            self.assertEqual([file], list(self.root.iterdir()))

    def test_import_gets_fresh_id_and_does_not_overwrite(self):
        with RunningEditorServer() as server:
            entry = save(server)
            payload = get(server, "?id=" + entry["id"])["payload"]
            imported = post_json(server, API, {"action": "save", "payload": payload})[1]["entry"]
            self.assertNotEqual(entry["id"], imported["id"])
            self.assertEqual(2, len(get(server)["entries"]))

    def test_preview_cache_and_bounds(self):
        with RunningEditorServer() as server:
            entry = save(server)
            with patch.object(fabric_server, "render_editor_asset_preview", return_value=b"png-preview") as render:
                for _ in range(2):
                    with urllib.request.urlopen(str(server) + entry["preview_url"]) as response:
                        self.assertEqual(b"png-preview", response.read())
                self.assertEqual(1, render.call_count)
            with patch.object(fabric_server, "EDITOR_ASSET_MAX_BYTES", 10):
                with self.assertRaises(urllib.error.HTTPError):
                    get(server, "?id=" + entry["id"])

    def test_preview_revalidation_avoids_rerender_after_lru_eviction(self):
        with RunningEditorServer() as server:
            entry = save(server)
            url = str(server) + entry["preview_url"]
            with patch.object(fabric_server, "render_editor_asset_preview", return_value=b"preview") as render:
                with urllib.request.urlopen(url) as response:
                    etag = response.headers["ETag"]
                    self.assertEqual("private, no-cache", response.headers["Cache-Control"])
                    self.assertEqual(b"preview", response.read())
                server.httpd.asset_previews.clear()
                request = urllib.request.Request(url, headers={"If-None-Match": etag})
                with self.assertRaises(urllib.error.HTTPError) as unchanged:
                    urllib.request.urlopen(request)
                self.assertEqual(304, unchanged.exception.code)
                self.assertEqual(1, render.call_count)
                post_json(server, API, {"action": "rename", "id": entry["id"], "revision": 1, "name": "Changed asset"})
                with urllib.request.urlopen(request) as changed:
                    self.assertNotEqual(etag, changed.headers["ETag"])
                    changed.read()
                self.assertEqual(2, render.call_count)

    def test_preview_tag_changes_when_source_or_server_changes(self):
        self.root.mkdir()
        source = self.root / "source.json"
        preview = self.root / "source.png"
        source.write_text("{}", encoding="utf-8")
        preview.write_bytes(b"preview")
        with RunningEditorServer() as server:
            handler = object.__new__(fabric_server.Handler)
            handler.server = server.httpd
            first = handler._preview_etag(source, preview)
            source.write_text('{"shapes":[]}', encoding="utf-8")
            second = handler._preview_etag(source, preview)
            self.assertNotEqual(first, second)
            preview.write_bytes(b"new preview")
            third = handler._preview_etag(source, preview)
            self.assertNotEqual(second, third)
        with RunningEditorServer() as server:
            handler.server = server.httpd
            self.assertNotEqual(third, handler._preview_etag(source, preview))

    def test_json_preview_revalidation_checks_file_before_cached_response(self):
        self.root.mkdir()
        source = self.root / "source.json"
        source.write_text(json.dumps({"shapes": [SHAPE]}), encoding="utf-8")
        with patch.object(fabric_server, "ROOT", self.root), \
                patch.object(fabric_server, "EXPORTED_JSON_ROOT", self.root), \
                patch.object(fabric_server, "_render_json_preview", return_value=b"preview") as render, \
                RunningEditorServer() as server:
            url = str(server) + fabric_server.JSON_PREVIEW_API + "?id=source.json"
            with urllib.request.urlopen(url) as response:
                etag = response.headers["ETag"]
                self.assertEqual(b"preview", response.read())
            request = urllib.request.Request(url, headers={"If-None-Match": etag})
            with self.assertRaises(urllib.error.HTTPError) as unchanged:
                urllib.request.urlopen(request)
            self.assertEqual(304, unchanged.exception.code)
            self.assertEqual(1, render.call_count)
            source.write_text(json.dumps({"shapes": [SHAPE, SHAPE]}), encoding="utf-8")
            with urllib.request.urlopen(request) as changed:
                self.assertNotEqual(etag, changed.headers["ETag"])
                changed.read()
            self.assertEqual(2, render.call_count)
            source.unlink()
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(request)
            self.assertEqual(400, missing.exception.code)
            self.assertEqual(2, render.call_count)

    def test_thumbnail_preserves_gradient_and_ignores_hidden_shapes(self):
        from PIL import Image
        gradient = dict(SHAPE, type=1048787, type_word=211, resource_family="Gradient_Shapes", resource_index=11, color=[240, 100, 180, 255])
        plain = fabric_server.render_editor_asset_preview([gradient])
        self.assertTrue(plain)
        with Image.open(io.BytesIO(plain)) as image:
            self.assertGreater(len(image.convert("RGB").getcolors(100000)), 20)
        hidden = dict(SHAPE, editor_hidden=True, data=[9999, 9999, 20, 20, 0, 0, 0])
        self.assertEqual(plain, fabric_server.render_editor_asset_preview([gradient, hidden]))
        self.assertIsNone(fabric_server.render_editor_asset_preview([hidden]))

    def test_preview_cache_has_a_fixed_entry_bound(self):
        with RunningEditorServer() as server, patch.object(fabric_server, "render_editor_asset_preview", return_value=b"preview"):
            for index in range(35):
                entry = save(server, name=f"Asset {index}")
                with urllib.request.urlopen(str(server) + entry["preview_url"]) as response:
                    response.read()
            self.assertEqual(32, len(server.httpd.asset_previews))
