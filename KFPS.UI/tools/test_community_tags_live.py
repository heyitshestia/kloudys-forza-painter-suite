"""Opt-in live tag test using an existing session, with owner-scoped cleanup."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
import uuid

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]

from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient, CommunityApiError, build_query
from kfps_ui.community_credentials import CommunityCredentialStore
from kfps_ui.community_service import CommunityService, SCOPE_VALUES, configured_community_api_url


class QuietLog:
    def append(self, message, level="info"):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-live-writes", required=True, action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "results.json").exists():
        raise RuntimeError("Use a fresh output directory so an earlier cleanup record cannot be overwritten.")
    app = QCoreApplication.instance() or QCoreApplication([])
    base = configured_community_api_url(ROOT)
    store = CommunityCredentialStore(args.session_root.resolve() / "runtime", base)
    token = store.load_token()
    if not token:
        raise RuntimeError("No saved Community session at the supplied installation.")
    credential_hash = hashlib.sha256(store.session_file.read_bytes()).hexdigest()
    client = CommunityApiClient(base, token)
    public = CommunityApiClient(base)
    real_json = CommunityApiClient.json
    session = real_json(client, "session", authenticated=True)
    username = session["user"]["username"]
    run_id = uuid.uuid4().hex
    title = "KFPS synthetic tag test - delete - " + run_id[:12]
    marker = "tagtest-" + run_id[:12]
    korean = "\ud55c\uae00\ud0dc\uadf8"
    description = "Automated synthetic tag-bank verification, not real artwork. This listing will be deleted after testing."
    results = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "account": username,
        "title": title, "marker": marker, "created_id": "", "creation_attempted": False,
        "removed": False, "cases": [], "errors": [], "writes": [],
    }

    def save():
        temporary = out / "results.tmp"
        temporary.write_text(json.dumps(results, indent=2, ensure_ascii=True), encoding="utf-8")
        temporary.replace(out / "results.json")

    def own_rows():
        rows = []
        page = 1
        while True:
            data = real_json(client, build_query("artworks", {"scope": "mine", "page": page, "limit": 60}), authenticated=True)
            rows.extend(data["items"])
            if page >= data["page_count"]:
                return rows
            page += 1

    def snapshot():
        keys = ("id", "title", "description", "tags", "status", "current_revision", "content_sha256", "preview_sha256")
        return {row["id"]: {key: row.get(key) for key in keys} for row in own_rows()}

    baseline = snapshot()
    results["existing_uploads"] = len(baseline)
    save()
    paths = AppPaths(ROOT, UI, UI / "qml", UI / "assets", out / "profile", Path(sys.executable))
    service = CommunityService(paths, object(), QuietLog(), app_version=(ROOT / "VERSION").read_text().strip())
    for timer in (service._activation_timer, service._supporter_timer, service._authentication_timer):
        timer.stop()
    service._token = token
    service._client = client
    service._session_user = session["user"]
    service._connected = True
    service._scope = "mine"
    service._config = real_json(client, "config")

    def wait_ready(predicate=lambda: True):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            app.processEvents()
            if not service.busy and not service._filter_timer.isActive():
                if service.errorMessage:
                    raise AssertionError(service.errorMessage)
                if predicate():
                    return
            time.sleep(0.015)
        raise TimeoutError("Community operation did not finish: " + service.statusMessage)

    def record(case):
        results["cases"].append(case)
        save()
        print(case, flush=True)

    def guard(instance, endpoint, method="GET", payload=None, **kwargs):
        if method != "GET":
            if method == "POST" and endpoint == "artworks":
                assert not results["creation_attempted"] and payload["title"] == title
                assert marker in payload["tags"] and payload["description"] == description
                results["creation_attempted"] = True
                save()
            else:
                assert results["created_id"] and results["created_id"] not in baseline
                allowed = {(f"artworks/{results['created_id']}", "PATCH"),
                           (f"artworks/{results['created_id']}/revisions", "POST"),
                           (f"artworks/{results['created_id']}", "DELETE")}
                assert (endpoint, method) in allowed, "Blocked a write outside this test upload"
            results["writes"].append({"endpoint": endpoint, "method": method})
            save()
        response = real_json(instance, endpoint, method, payload, **kwargs)
        if method == "POST" and endpoint == "artworks":
            artwork = response["artwork"]
            results["created_id"] = artwork["id"]
            save()
            assert artwork["title"] == title and artwork["creator"]["username"] == username
            assert artwork["id"] not in baseline
        if method == "DELETE":
            results["removed"] = response.get("removed") is True
            save()
        return response

    def fixture(name, count):
        offset = int(run_id[:6], 16)
        shapes = [{"type": 16, "color": [(offset + i * 57) % 256, (offset // 256 + i * 89) % 256, 170, 255],
                   "data": [140 + (i % 4) * 230, 180 + (i // 4) * 230, 130 + i * 2, 70 + i,
                            ((offset + i * 317) % 360000) / 1000]}
                  for i in range(count)]
        path = out / name
        path.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
        return path

    def inspect(path):
        service.selectUploadJson(str(path))
        wait_ready(lambda: service.uploadReady)

    def select_test():
        service.setScopeIndex(SCOPE_VALUES.index("mine"))
        service.setSearchQuery(marker)
        service.refresh()
        wait_ready(lambda: service.selectedArtwork.get("id") == results["created_id"])
        assert service.selectedOwned and service.selectedMetadataEditable

    def detail():
        return real_json(public, f"artworks/{results['created_id']}")["artwork"]

    def searched(query):
        data = real_json(public, build_query("artworks", {"scope": "browse", "search": query, "creator": username, "limit": 60}))
        return {row["id"] for row in data["items"]}

    try:
        with patch.object(CommunityApiClient, "json", new=guard):
            inspect(fixture("synthetic-source.json", 12))
            prepared = service.prepareTags([], f"anime, racing, {marker}, {korean}, ANIME")
            assert not prepared["error"] and len(prepared["tags"]) == 4
            service.submitUpload(title, description, "Other", ", ".join(prepared["tags"]), "toolmade",
                                 "kfps-community-share-v1", False, True, True)
            wait_ready(lambda: bool(results["created_id"]))
            assert detail()["tags"] == prepared["tags"]
            assert detail()["status"] == "published"
            record("Actual CommunityService upload published; broad/custom/Korean tags and deduplication survived the server")

            assert results["created_id"] in searched(marker)
            assert results["created_id"] in searched(marker.upper())
            assert results["created_id"] in searched(korean)
            record("Anonymous public searches find the new upload by its custom tag, uppercase spelling and Korean tag")

            select_test()
            updated = service.prepareTags([], f"anime, {marker}, {korean}, retro, gaming, patterns, logos, portrait, space, stripes")
            assert not updated["error"] and len(updated["tags"]) == 10
            service.updateSelectedTags(", ".join(updated["tags"]))
            wait_ready()
            assert detail()["tags"] == updated["tags"]
            assert results["created_id"] in searched("retro")
            assert results["created_id"] not in searched("racing")
            record("Owner tag editing saved all ten tags; added tags became searchable and the removed tag stopped matching")

            select_test()
            inspect(fixture("synthetic-revision.json", 14))
            service.submitRevision(title, description, "Other", ", ".join(updated["tags"]), "toolmade",
                                   "kfps-community-share-v1", False, True, True, "Synthetic revision for tag verification")
            wait_ready()
            revision = detail()
            assert revision["current_revision"] == 2 and revision["shape_count"] == 14
            assert revision["tags"] == updated["tags"]
            record("A real replacement revision published with all ten tags preserved")

            select_test()
            service.removeSelectedUpload()
            wait_ready()
            assert results["removed"]
            record("Normal owner Remove Upload completed successfully")
    except Exception:
        results["errors"].append(traceback.format_exc())
        save()
    finally:
        service.close()
        try:
            # Recover a successful creation whose HTTP response was interrupted, without replaying POST.
            if results["creation_attempted"] and not results["created_id"]:
                candidates = [row for row in own_rows() if row["title"] == title and row["id"] not in baseline]
                assert len(candidates) <= 1
                if candidates:
                    results["created_id"] = candidates[0]["id"]
                    save()
            if results["created_id"] and not results["removed"]:
                assert results["created_id"] not in baseline
                response = real_json(client, f"artworks/{results['created_id']}", "DELETE", authenticated=True)
                results["removed"] = response.get("removed") is True
                save()
            if results["created_id"]:
                try:
                    detail()
                except CommunityApiError as exc:
                    assert exc.status == 404
                else:
                    raise AssertionError("Deleted test artwork still accessible")
                assert results["created_id"] not in searched(marker)
                results["cleanup_verified"] = True
            assert snapshot() == baseline, "Existing upload metadata/content changed during the test"
            assert hashlib.sha256(store.session_file.read_bytes()).hexdigest() == credential_hash
            results["existing_uploads_unchanged"] = True
            results["original_session_file_unchanged"] = True
        except Exception:
            results["errors"].append("CLEANUP OR PRESERVATION CHECK: " + traceback.format_exc())
        save()
    print(json.dumps(results, indent=2, ensure_ascii=True))
    return int(bool(results["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
