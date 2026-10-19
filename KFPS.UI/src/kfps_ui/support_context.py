"""Read-only, allowlisted startup and installation evidence for private reports."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time

import psutil

from .support_logs import _safe, discover_updater_files, read_known_file

MAX_STATE = 2 * 1024 * 1024
IDENTITY_FILES = {
    "editor-entry": "KFPS.Editor/editor.py",
    "editor-manifest": "KFPS.Editor/manifest.json",
    "editor-host": "KFPS.Editor/src/kfps_editor/host.py",
    "editor-startup": "KFPS.Editor/src/kfps_editor/startup.py",
    "editor-ipc": "KFPS.Editor/src/kfps_editor/ipc.py",
    "editor-lock": "KFPS.Editor/src/kfps_editor/instance_lock.py",
    "editor-page": "KFPS.Editor/web/index.html",
    "editor-script": "KFPS.Editor/web/editor.js",
    "editor-launcher": "KFPS Editor.exe",
    "editor-workspace": "KFPS.Editor/web/editor-workspace.js",
    "editor-docking": "KFPS.Editor/web/editor-docking.js",
    "editor-renderer": "KFPS.Editor/web/editor-renderer.js",
    "editor-themes": "KFPS.Editor/web/editor-themes.js",
    "editor-localization": "KFPS.Editor/web/editor-i18n.js",
    "editor-japanese": "KFPS.Editor/web/locales/ja.js",
    "app-settings": "KFPS.UI/src/kfps_ui/settings_service.py",
    "community-access": "KFPS.UI/src/kfps_ui/community_access.py",
    "theme-entitlement": "KFPS.UI/src/kfps_ui/supporter_service.py",
    "studio-launcher": "KFPSLiverySudio.exe",
    "studio-host": "tools/livery-studio/src/kfps_livery_lab/native_host.py",
    "studio-server": "tools/livery-studio/src/kfps_livery_lab/server.py",
    "studio-renderer": "tools/livery-studio/src/web/livery-scene.js",
    "studio-editor": "tools/livery-studio/src/web/livery-editor.mjs",
    "studio-storage": "tools/livery-studio/src/kfps_livery_lab/project_storage.py",
    "studio-source-return": "tools/livery-studio/src/kfps_livery_lab/source_editor.py",
    "release-notice": "tools/kfps_release_announcement.py",
    "activity-counter": "tools/kfps_activity.py",
}


def _fields(value, keys):
    from .support_report import redact
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in keys:
        item = value.get(key)
        if isinstance(item, str):
            result[key] = redact(item, 2000)
        elif type(item) in (bool, int, float) and abs(item) <= 2**53 - 1 and math.isfinite(item):
            result[key] = item
    return result


def _read(root, path, limit=MAX_STATE):
    try:
        info = _safe(root, path)
        raw, info = read_known_file(root, path, limit)
        return raw, {"status": "read", "bytes": info.st_size,
                     "age_seconds": max(0, round(time.time() - info.st_mtime, 1))}
    except FileNotFoundError:
        return None, {"status": "missing"}
    except (OSError, ValueError) as error:
        reason = str(error) if isinstance(error, ValueError) else "unreadable"
        result = {"status": reason if reason in {"oversized_file", "changed_file", "unsafe_file"} else "unreadable"}
        for key in ("errno", "winerror"):
            if type(getattr(error, key, None)) is int:
                result[key] = getattr(error, key)
        return None, result


def _json(root, path):
    raw, status = _read(root, path)
    if raw is None:
        return {}, status
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return data, status
    except (ValueError, UnicodeError, RecursionError):
        return {}, {**status, "status": "invalid"}


def _process(pid, root):
    if type(pid) is not int or not 0 < pid <= 2**32 - 1:
        return {"status": "invalid_pid"}
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            result = {"pid": pid, "status": process.status(), "created_at": process.create_time(),
                      "rss_bytes": process.memory_info().rss, "threads": process.num_threads()}
            # Inspect only the PID named by the marker; never attach a process list,
            # command line, executable path, hostname or window title.
            result["executable_in_installation"] = Path(process.exe()).resolve().is_relative_to(root)
        return result
    except psutil.NoSuchProcess:
        return {"pid": pid, "status": "not_running"}
    except (psutil.Error, OSError, ValueError):
        return {"pid": pid, "status": "unavailable"}


def _stored_object(value):
    if isinstance(value, str) and len(value) <= 128 * 1024:
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return {}
    return value if isinstance(value, dict) else {}


def collect_preferences(root: Path):
    """Describe compatibility-relevant settings, never custom names or bindings."""
    root = Path(root).resolve()
    ui, status = _json(root, root / "runtime/qml-shell-settings.json")
    options = {key: ui[key] for key in ("editorUseChrome", "liveryUseChrome",
        "reducedMotion", "ambientMotion", "glassEffects") if type(ui.get(key)) is bool}
    if ui.get("editorGraphics") in ("auto", "opengl", "d3d11"):
        options["editorGraphics"] = ui["editorGraphics"]
    from .theme_catalog import KNOWN_THEME_NAMES
    if isinstance(ui.get("theme"), str) and ui["theme"] in KNOWN_THEME_NAMES:
        options["theme"] = ui["theme"]
    elif "theme" in ui:
        options["theme_unrecognized"] = True
    geometry = _stored_object(ui.get("windowGeometry"))
    options["window"] = {key: geometry[key] for key in ("width", "height")
        if type(geometry.get(key)) is int and 0 < geometry[key] <= 32768}
    if type(geometry.get("maximized")) is bool:
        options["window"]["maximized"] = geometry["maximized"]
    result = {"app": {**status, "options": options}}
    preferences, status = _json(root, root / "runtime/fabric-editor/preferences.json")
    settings = _stored_object(preferences.get("settings"))
    editor = {"theme_selected": bool(isinstance(preferences.get("theme"), str)
        and preferences["theme"]), "saved_setting_count": len(settings)}
    if settings.get("kloudyFabricLanguage") in ("en", "ko", "ja"):
        editor["language"] = settings["kloudyFabricLanguage"]
    shortcuts = _stored_object(settings.get("kloudyFabricShortcuts"))
    editor["custom_shortcut_count"] = len(shortcuts)
    dock = _stored_object(settings.get("kloudyFabricDockState"))
    panels = _stored_object(dock.get("panels"))
    items = _stored_object(panels.get("items"))
    editor["panel_count"] = len(items)
    editor["panel_places"] = {place: sum(1 for item in items.values()
        if isinstance(item, dict) and item.get("place") == place)
        for place in ("home", "left", "floating", "hidden")}
    if type(panels.get("locked")) is bool:
        editor["panels_locked"] = panels["locked"]
    result["editor"] = {**status, "options": editor}
    # Only presence/size of fixed storage files. Never enumerate artwork,
    # recovery names, account credentials, projects or SQLite rows.
    result["storage"] = {}
    for label, relative in (("studio_projects", "imgs/livery-projects/storage.sqlite3"),
                            ("editor_recovery", "runtime/fabric-editor/autosave.json")):
        try:
            info = _safe(root, root / relative)
            import stat
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe_file")
            result["storage"][label] = {"status": "present", "bytes": info.st_size}
        except FileNotFoundError:
            result["storage"][label] = {"status": "missing"}
        except (OSError, ValueError):
            result["storage"][label] = {"status": "unavailable"}
    return result


def collect_context(root: Path):
    root = Path(root).resolve()
    runtime = root / "runtime/fabric-editor"
    result = {"schema": "kfps-diagnostic-context/1", "collected_at": time.time(),
              "scope": "this installation; observed state is not proof of lock ownership"}
    for label, filename, fields in (
        ("editor_state", "desktop.json", ("service", "pid", "state", "error", "started_at", "updated_at")),
        ("editor_startup_error", "desktop-startup-error.json", ("pid", "error")),
    ):
        value, observation = _json(root, runtime / filename)
        record = {**observation, "fields": _fields(value, fields)}
        if "pid" in value:
            record["process"] = _process(value["pid"], root)
            started = value.get("started_at")
            created = record["process"].get("created_at")
            if type(started) in (int, float) and math.isfinite(started) and created is not None:
                record["process_started_after_marker"] = created > started + 1
        result[label] = record
    for label, path in (("editor_lock", runtime / "desktop.lock"),
                        ("report_window_lock", root / "runtime/support-reports/window.lock")):
        raw, observation = _read(root, path, 8192)
        if raw is not None:
            try:
                pid = int(raw.splitlines()[0])
                observation["process"] = _process(pid, root)
            except (ValueError, IndexError):
                observation["status"] = "invalid"
        result[label] = observation
    from tools.fabric_editor_diagnostics import read_support_diagnostics
    result["editor_diagnostics"] = read_support_diagnostics(root)
    result["preferences"] = collect_preferences(root)
    from .support_studio import read_studio_snapshot
    result["studio_diagnostics"] = read_studio_snapshot(root)
    try:
        from tools.kfps_release_announcement import ReleaseAnnouncement
        result["release_announcement"] = ReleaseAnnouncement(root).read_status()
    except Exception:
        result["release_announcement"] = {"status": "unavailable"}
    try:
        from tools.kfps_activity import usage_status
        result["anonymous_activity"] = usage_status(root)
    except Exception:
        result["anonymous_activity"] = {"status": "state_unavailable"}
    locator, observation = _json(root, root / "runtime/live-memory/reports/latest.json")
    result["locator"] = {**observation,
        **_fields(locator, ("schema", "engine_version", "created_utc", "store_variant")),
        "request": _fields(locator.get("request"), ("game", "purpose", "layer_count")),
        "outcome": _fields(locator.get("outcome"), ("status", "reason", "authoritative", "failure_reason", "refusal_reason"))}
    installation = {}
    for label in ("VERSION", "BUILD_COMMIT"):
        raw, status = _read(root, root / label, 256)
        if raw is not None:
            text = raw.decode("utf-8", errors="replace").strip()
            if re.fullmatch(r"[0-9.a-zA-Z_-]{1,80}", text):
                # Group file hashes so the generic long-identifier privacy filter
                # does not erase these explicitly selected installation fingerprints.
                status["value_groups"] = [text[i:i+8] for i in range(0, len(text), 8)]
        installation[label.lower()] = status
    for label, relative in IDENTITY_FILES.items():
        raw, status = _read(root, root / relative, 4 * 1024 * 1024)
        if raw is not None:
            digest = hashlib.sha256(raw).hexdigest()
            status["sha256_groups"] = [digest[i:i+8] for i in range(0, 64, 8)]
        installation[label] = status
    baseline, baseline_status = _json(root, root / "KFPS.Editor/baseline.json")
    if baseline.get("schema") == "kfps-editor-baseline/1":
        baseline_status["engine"] = _fields(baseline.get("engine"), ("python", "bits", "pyside", "qt", "webengine", "chromium"))
        records = baseline.get("files")
        if isinstance(records, list):
            baseline_status["declared_files"] = len(records)
            expected = {item.get("path"): item for item in records if isinstance(item, dict) and isinstance(item.get("path"), str)}
            for label, relative in IDENTITY_FILES.items():
                record = expected.get(relative, {})
                digest = record.get("sha256")
                if isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest):
                    installation[label]["matches_recorded_baseline"] = (
                        "".join(installation[label].get("sha256_groups", [])) == digest)
    elif baseline_status["status"] == "read":
        baseline_status["status"] = "invalid"
    installation["baseline"] = baseline_status
    # No full runtime rehash on the report path. Startup verifies that already.
    for label, relative in (("managed_python", "python/python.exe"),):
        try:
            info = _safe(root, root / relative)
            installation[label] = {"status": "present", "bytes": info.st_size}
        except FileNotFoundError:
            installation[label] = {"status": "missing"}
        except (OSError, ValueError):
            installation[label] = {"status": "unreadable"}
    result["installation"] = installation
    try:
        disk = shutil.disk_usage(root)
        memory = psutil.virtual_memory()
        result["resources"] = {"disk_free_bytes": disk.free, "disk_total_bytes": disk.total,
                               "memory_available_bytes": memory.available, "memory_total_bytes": memory.total}
    except OSError:
        result["resources"] = {"status": "unavailable"}
    reports, warnings = discover_updater_files(root, "reports")
    result["updater_history"] = {"warnings": warnings, "runs": []}
    for anchor, path in reports:
        data, status = _json(anchor, path)
        fields = ("schema", "updater_version", "started_utc", "finished_utc", "status", "phase", "mode",
                  "from_version", "to_version", "sequence", "files_checked", "files_planned_replaced",
                  "files_planned_removed", "files_replaced", "files_removed", "bytes_downloaded",
                  "rollback", "rollback_success", "recovered_interrupted_transaction", "success", "error",
                  "handoff_exit_code")
        # Paths, change lists, installation IDs and raw payloads are not copied.
        result["updater_history"]["runs"].append({**status, "fields": _fields(data, fields)})
    return result
