from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .json_thumbnail_worker import worker_command, worker_environment
from .log_service import LogService
from .models import DictListModel
from .preview_service import PreviewService
from .qt_utils import safe_file_part


FD6_FORMAT = "fd6.shapes"
KFPS_RECTANGLE_TYPE = 1048677
KFPS_ELLIPSE_TYPE = 1048678
KFPS_RECTANGLE_WORD = 0x0065
KFPS_ELLIPSE_WORD = 0x0066
FD6_RECTANGLE_DIVISOR = 127.0
FD6_ELLIPSE_DIVISOR = 63.0
JSON_INDEX_CACHE_VERSION = 1
OUTPUT_FOLDER_MARKER = ".kfps-output-folder"
OUTPUT_FOLDER_MARKER_FORMAT = "kfps-output-folder-v1"
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
OUTPUT_SORT_MODES = {"date-desc", "name-asc", "shapes-asc", "shapes-desc"}


class _StartupJsonIndexBuilder:
    def __init__(
        self,
        paths: AppPaths,
        preview: PreviewService | None = None,
        progress=None,
        include_existing_previews: bool = True,
    ):
        self.paths = paths
        self.preview = preview
        self.progress = progress
        self.include_existing_previews = bool(include_existing_previews)

    def source_roots(self):
        return [self.paths.generated_root, self.paths.editor_json_root, self.paths.exported_root, self.paths.library_root]

    def source_names(self):
        return ["generated", "editor", "exported", "library"]

    @staticmethod
    def source_label(source):
        labels = ["Generated finals", "Editor exports", "Game exports", "Library"]
        return labels[source] if 0 <= source < len(labels) else "Outputs"

    def cache_key(self, source):
        root = self.source_roots()[source]
        try:
            return str(root.resolve()).casefold()
        except Exception:
            return str(root).casefold()

    def report(self, message, done, total):
        if callable(self.progress):
            self.progress(message, done, total)

    def build_payload(self):
        sources = {}
        total_rows = 0
        roots = self.source_roots()
        for source, root in enumerate(roots):
            self.report(f"Politely interrogating {self.source_label(source)}...", source, len(roots))
            index = self.build_source(source, root)
            rows = index.get("rows", [])
            total_rows += len(rows)
            sources[str(source)] = self.source_payload(source, index)
            self.report(f"{self.source_label(source)} filed {len(rows)} JSONs without eating the clipboard.", source + 1, len(roots))
        return {"version": JSON_INDEX_CACHE_VERSION, "createdAt": time.time(), "sources": sources}, total_rows

    def build_source(self, source, root):
        root.mkdir(parents=True, exist_ok=True)
        groups = []
        if source == 0:
            root_files = [
                path for path in root.glob("*.json")
                if not any(token in path.name.casefold() for token in (".report.", "settings", "metadata", "backup", "session", "probe", "manifest"))
            ]
            if root_files:
                groups.append(self.group(root.name, root, root_files))
            for folder in root.iterdir():
                if folder.is_dir():
                    files = self.files(folder, generated=True)
                    if files:
                        groups.append(self.group(folder.name, folder, files))
                    if len(groups) % 25 == 0:
                        time.sleep(0)
        else:
            grouped = {}
            for path in self.files(root, generated=False):
                grouped.setdefault(path.parent, []).append(path)
            for index, (folder, files) in enumerate(grouped.items()):
                name = str(folder.relative_to(root)) if folder != root else root.name
                groups.append(self.group(name, folder, files))
                if index % 25 == 0:
                    time.sleep(0)
        groups.sort(key=lambda item: item["modified"], reverse=True)
        rows = [self.row_for_json(source, path) for path in self.sorted_visible_files(source, groups)]
        return {
            "root": self.cache_key(source),
            "groups": groups,
            "rows": rows,
            "source": source,
            "scannedAt": time.time(),
        }

    @staticmethod
    def files(root: Path, generated: bool):
        out = []
        for path in root.rglob("*.json"):
            low = path.name.lower()
            if any(token in low for token in (".report.","settings","metadata","backup","session","probe","manifest")):
                continue
            managed = any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
            if generated and not (path.parent.name.lower() == "finals" or managed):
                continue
            out.append(path)
        return out

    def group(self, name, folder, files):
        modified = max(path.stat().st_mtime for path in files)
        display_name = name
        detail_text = f"{len(files)} JSON" if len(files) == 1 else f"{len(files)} JSONs"
        if files:
            meta, layers, title = JsonService._json_summary(files[0])
            title = meta.get("display_name") or meta.get("title")
            if title:
                display_name = str(title)
            if isinstance(layers, int):
                detail_text = JsonService._count_detail_text(layers, meta)
        return {
            "name": name,
            "displayName": display_name,
            "detailText": detail_text,
            "path": str(folder),
            "files": sorted(files, key=lambda path: path.stat().st_mtime, reverse=True),
            "count": len(files),
            "modified": modified,
            "modifiedLabel": JsonService._age(modified),
        }

    def sorted_visible_files(self, source, groups):
        if source == 0:
            files = []
            root = self.source_roots()[source]
            for group in sorted(groups, key=lambda item: item["modified"], reverse=True):
                managed = [
                    path for path in group["files"]
                    if path.parent == root or any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
                ]
                generated = [path for path in group["files"] if path not in managed]
                files.extend(sorted(self.dedupe_generated_files(generated), key=lambda path: (JsonService._count(path), path.name.casefold())))
                files.extend(sorted(managed, key=lambda path: (JsonService._count(path), path.name.casefold())))
            return files
        files = [path for group in groups for path in group["files"]]
        return sorted(files, key=lambda path: (path.stat().st_mtime * -1, path.name.casefold()))

    @staticmethod
    def dedupe_generated_files(files):
        selected = {}
        for path in files:
            key = JsonService._count(path)
            previous = selected.get(key)
            if previous is None or path.stat().st_mtime >= previous.stat().st_mtime:
                selected[key] = path
        return list(selected.values())

    def row_for_json(self, source, path):
        stat = path.stat()
        modified_label = JsonService._age(stat.st_mtime)
        meta, layers, display_name = JsonService._json_summary(path)
        detail = JsonService._count_detail_text(layers, meta)
        return {
            "name": path.name,
            "displayName": display_name,
            "path": str(path),
            "layers": layers,
            "modifiedLabel": modified_label,
            "previewUrl": self.existing_preview(path, self.source_names()[source]),
            "countDetail": detail,
            "detailText": f"{detail}  •  {modified_label}",
            "folder": str(path.parent),
            "mtime": stat.st_mtime,
            "mtimeNs": stat.st_mtime_ns,
            "size": stat.st_size,
            "source": source,
        }

    def existing_preview(self, path, source_name):
        if not self.include_existing_previews:
            return ""
        existing = getattr(self.preview, "existing_preview_for_json", None)
        if callable(existing):
            try:
                return str(existing(path, source_name) or "")
            except Exception:
                return ""
        return ""

    def source_payload(self, source, index):
        return {
            "root": index.get("root") or self.cache_key(source),
            "scannedAt": index.get("scannedAt") or time.time(),
            "rows": [
                {
                    "name": row.get("name", ""),
                    "displayName": row.get("displayName", ""),
                    "path": row.get("path", ""),
                    "layers": int(row.get("layers") or 0),
                    "previewUrl": row.get("previewUrl", ""),
                    "countDetail": row.get("countDetail", ""),
                    "folder": row.get("folder", ""),
                    "mtimeNs": int(row.get("mtimeNs") or 0),
                    "size": int(row.get("size") or 0),
                }
                for row in index.get("rows", [])
            ],
            "groups": [
                {
                    "name": group.get("name", ""),
                    "displayName": group.get("displayName", ""),
                    "detailText": group.get("detailText", ""),
                    "path": group.get("path", ""),
                    "files": [str(path) for path in group.get("files", [])],
                }
                for group in index.get("groups", [])
            ],
        }


def build_startup_json_index_cache(
    paths: AppPaths,
    preview: PreviewService | None = None,
    progress=None,
    include_existing_previews: bool = True,
):
    builder = _StartupJsonIndexBuilder(
        paths,
        preview=preview,
        progress=progress,
        include_existing_previews=include_existing_previews,
    )
    payload, total_rows = builder.build_payload()
    JsonService._write_index_cache_payload(paths.runtime_root / "json-browser-index.v1.json", payload)
    return total_rows


class JsonService(QObject):
    changed = Signal()
    _previewReady = Signal(str, str, str)
    _indexReady = Signal(int, int, object, str)

    def __init__(self, paths: AppPaths, preview: PreviewService, desktop: DesktopService, log: LogService, demo=False, parent=None):
        super().__init__(parent); self.paths = paths; self.preview = preview; self.desktop = desktop; self.log = log; self.demo = demo
        self._group_model = DictListModel(["name","displayName","detailText","path","count","modifiedLabel"])
        self._file_model = DictListModel(["name","displayName","path","layers","modifiedLabel","previewUrl","detailText","folder"])
        self._explorer_model = DictListModel(["name","displayName","path","entryKind","isFolder","sourceIndex","layers","modifiedLabel","previewUrl","detailText","folder","selected"])
        self._folder_model = DictListModel(["displayName","path","depth","sourceIndex"])
        self._move_folder_model = DictListModel(["displayName","path","depth","sourceIndex"])
        self._recent_model = DictListModel(["name","path","folder","age","source"])
        self._source = 0; self._selected_group = -1; self._selected_path = ""; self._selected_display_name = ""; self._preview_url = ""; self._layers = "—"; self._folder = "—"
        self._search_query = ""
        self._sort_mode = "date-desc"
        self._explorer_selection: list[str] = []
        self._explorer_selection_keys: set[str] = set()
        self._explorer_index_by_key: dict[str, int] = {}
        self._explorer_operable_keys: set[str] = set()
        self._explorer_json_keys: set[str] = set()
        self._operation_selection_count = 0
        self._operation_selection_json_count = 0
        self._selection_anchor_path = ""
        self._selection_revision = 0
        self._management_status = ""
        self._current_folder = ""
        self._explorer_rows: list[dict] = []
        self._back_history: list[str] = []
        self._forward_history: list[str] = []
        self._clipboard_paths: list[str] = []
        self._clipboard_cut = False
        self._all_file_rows: list[dict] = []
        self._visible_file_rows: list[dict] = []
        self._groups: list[dict] = []
        self._source_index_cache: dict[int, dict] = {}
        self._source_scan_generation: dict[int, int] = {}
        self._indexing_sources: set[int] = set()
        self._index_status = "Output index idle"
        self._cache_save_pending = False
        self._thumbnail_process = None
        self._thumbnail_cache_mtime_ns = 0
        self._thumbnail_warm_pending = False
        self._thumbnail_status = ""
        self._thumbnail_active = False
        self._thumbnail_regenerating = False
        self._thumbnail_poll_timer = QTimer(self)
        self._thumbnail_poll_timer.setInterval(900)
        self._thumbnail_poll_timer.timeout.connect(self._poll_thumbnail_worker)
        self._index_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="json-index")
        self._preview_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="json-preview")
        self._preview_queue: list[tuple[str, str]] = []
        self._preview_queued: set[str] = set()
        self._preview_empty: set[str] = set()
        self._preview_running = False
        self._previewReady.connect(self._apply_preview_result)
        self._indexReady.connect(self._apply_source_index_result)
        self._ensure_logo(); self._load_index_cache(); self._load_source(force=False); self.refreshRecent(); QTimer.singleShot(150, self.warmIndex); QTimer.singleShot(1800, self._schedule_thumbnail_warm)


    @Property(QObject, constant=True)
    def groupModel(self): return self._group_model
    @Property(QObject, constant=True)
    def fileModel(self): return self._file_model
    @Property(QObject, constant=True)
    def explorerModel(self): return self._explorer_model
    @Property(QObject, constant=True)
    def folderModel(self): return self._folder_model
    @Property(QObject, constant=True)
    def moveFolderModel(self): return self._move_folder_model
    @Property(QObject, constant=True)
    def recentModel(self): return self._recent_model

    @Property(int, notify=changed)
    def sourceIndex(self): return self._source
    @Property(str, notify=changed)
    def selectedPath(self): return self._selected_path
    @Property(bool, notify=changed)
    def selectedIsGameLibraryItem(self):
        if not self._selected_path:
            return False
        selected = Path(self._selected_path)
        if not self._path_is_within(selected, self.paths.library_root):
            return False
        return not self._path_is_within(selected, self.paths.library_root / "Community")
    @Property(str, notify=changed)
    def previewUrl(self): return self._preview_url
    @Property(str, notify=changed)
    def selectedName(self): return self._selected_display_name or (Path(self._selected_path).name if self._selected_path else "—")
    @Property(str, notify=changed)
    def selectedLayers(self): return self._layers
    @Property(str, notify=changed)
    def selectedFolder(self): return self._folder
    @Property(str, notify=changed)
    def searchQuery(self): return self._search_query
    @Property(str, notify=changed)
    def sortMode(self): return self._sort_mode
    @Property(int, notify=changed)
    def explorerSelectionCount(self): return len(self._explorer_selection)
    @Property(str, notify=changed)
    def explorerSelectionName(self):
        if len(self._explorer_selection) != 1:
            return ""
        selected_key = self._preview_key(self._explorer_selection[0])
        index = self._explorer_index_by_key.get(selected_key, -1)
        row = self._explorer_rows[index] if 0 <= index < len(self._explorer_rows) else None
        return str(row.get("displayName") or row.get("name") or "") if row else Path(self._explorer_selection[0]).name
    @Property(int, notify=changed)
    def explorerSelectionRevision(self): return self._selection_revision
    @Property(str, notify=changed)
    def managementStatus(self): return self._management_status

    @Slot()
    def clearManagementStatus(self):
        if not self._management_status:
            return
        self._management_status = ""
        self.changed.emit()

    @Property(str, notify=changed)
    def currentFolder(self): return self._current_folder
    @Property(str, notify=changed)
    def currentFolderDisplay(self):
        if not self._current_folder:
            return "Outputs"
        root = self._root()
        current = Path(self._current_folder)
        try:
            current.resolve().relative_to(root.resolve())
            suffix = "" if self._same_path(current, root) else f" / {self._folder_display_path(current, root)}"
        except (OSError, ValueError):
            suffix = ""
        return f"{self._explorer_source_label(self._source)}{suffix}"
    @Property(int, notify=changed)
    def currentFolderIndex(self):
        for index, row in enumerate(self._folder_model.rows):
            if str(row.get("path") or "") == self._current_folder or self._same_path(row.get("path"), self._current_folder):
                return index
        return 0
    @Property(bool, notify=changed)
    def canGoBack(self): return bool(self._back_history)
    @Property(bool, notify=changed)
    def canGoForward(self): return bool(self._forward_history)
    @Property(bool, notify=changed)
    def canGoUp(self): return bool(self._current_folder)
    @Property(int, notify=changed)
    def clipboardCount(self): return len(self._clipboard_paths)
    @Property(bool, notify=changed)
    def clipboardCut(self): return self._clipboard_cut and bool(self._clipboard_paths)
    @Property(bool, notify=changed)
    def canPaste(self): return bool(self._clipboard_paths)
    @Property(int, notify=changed)
    def fileOperationSelectionCount(self):
        return self._operation_selection_count
    @Property(bool, notify=changed)
    def canMoveJsonSelection(self):
        return self._operation_selection_count > 0 and self._operation_selection_json_count == self._operation_selection_count
    @Property(str, notify=changed)
    def explorerSummary(self):
        folders = sum(1 for row in self._explorer_rows if row.get("isFolder"))
        jsons = len(self._explorer_rows) - folders
        if not self._current_folder:
            noun = "folder" if folders == 1 else "folders"
            return f"{folders} output {noun}"
        if self._search_query:
            return self.searchSummary
        folder_label = "folder" if folders == 1 else "folders"
        json_label = "JSON" if jsons == 1 else "JSONs"
        return f"{folders} {folder_label} • {jsons} {json_label}"
    @Property(bool, notify=changed)
    def indexing(self): return bool(self._indexing_sources)
    @Property(bool, notify=changed)
    def currentSourceIndexing(self): return self._source in self._indexing_sources
    @Property(str, notify=changed)
    def indexStatus(self): return self._index_status
    @Property(str, notify=changed)
    def thumbnailStatus(self): return self._thumbnail_status
    @Property(bool, notify=changed)
    def thumbnailActive(self): return self._thumbnail_active
    @Property(bool, notify=changed)
    def thumbnailRegenerating(self): return self._thumbnail_regenerating
    @Property(int, notify=changed)
    def outputCount(self): return len(self._all_file_rows)
    @Property(int, notify=changed)
    def visibleOutputCount(self): return len(self._visible_file_rows)
    @Property(str, notify=changed)
    def searchSummary(self):
        total = len(self._all_file_rows)
        visible = len(self._visible_file_rows)
        if total == 0 and self.currentSourceIndexing:
            return "Indexing..."
        if self._search_query:
            noun = "match" if visible == 1 else "matches"
            return f"{visible} of {total} {noun}"
        noun = "vinyl" if total == 1 else "vinyls"
        return f"{total} {noun}"

    def _source_roots(self):
        return [self.paths.generated_root, self.paths.editor_json_root, self.paths.exported_root, self.paths.library_root]

    def _source_names(self):
        return ["generated", "editor", "exported", "library"]

    def _root(self): return self._source_roots()[self._source]

    def _source_label(self, source):
        labels = ["Generated finals", "Editor exports", "Game exports", "Library"]
        return labels[source] if 0 <= source < len(labels) else "Outputs"

    @staticmethod
    def _explorer_source_label(source):
        labels = ["Generated JSONs", "Editor JSONs", "Game Exports", "Library"]
        return labels[source] if 0 <= source < len(labels) else "Outputs"

    def _source_cache_key(self, source):
        root = self._source_roots()[source]
        try:
            return str(root.resolve()).casefold()
        except Exception:
            return str(root).casefold()

    def _empty_source_index(self, source):
        return {"root": self._source_cache_key(source), "groups": [], "rows": [], "rowsByKey": {}, "source": source}

    def _current_source_index(self):
        return self._source_index_cache.get(self._source) or self._empty_source_index(self._source)

    def _build_source_index(self, source, root, cache_key):
        root.mkdir(parents=True, exist_ok=True)
        retained_previews = self._retained_preview_urls(source)
        groups = []
        if source == 0:
            root_files = [path for path in root.glob("*.json") if self._explorer_json_visible(path)]
            if root_files:
                groups.append(self._group(root.name, root, root_files))
            for folder in root.iterdir():
                if folder.is_dir():
                    files = self._files(folder, generated=True)
                    if files: groups.append(self._group(folder.name, folder, files))
                    if len(groups) % 25 == 0:
                        time.sleep(0)
        else:
            grouped = {}
            for path in self._files(root, generated=False): grouped.setdefault(path.parent, []).append(path)
            for index, (folder, files) in enumerate(grouped.items()):
                groups.append(self._group(str(folder.relative_to(root)) if folder != root else root.name, folder, files))
                if index % 25 == 0:
                    time.sleep(0)
        groups.sort(key=lambda g:g["modified"], reverse=True)
        rows = [self._row_for_json(source, path, retained_previews=retained_previews) for path in self._sorted_visible_files(source, groups)]
        rows_by_key = {self._preview_key(row["path"]): row for row in rows}
        return {"root": cache_key, "groups": groups, "rows": rows, "rowsByKey": rows_by_key, "source": source, "scannedAt": time.time()}

    def _retained_preview_urls(self, source):
        retained = {}
        cached = self._source_index_cache.get(source, {})
        rows_by_key = cached.get("rowsByKey", {}) if isinstance(cached, dict) else {}
        for key, row in list(rows_by_key.items()):
            if not isinstance(row, dict):
                continue
            preview_url = str(row.get("previewUrl") or "")
            if not preview_url:
                continue
            retained[key] = (
                int(row.get("mtimeNs") or -1),
                int(row.get("size") or -1),
                preview_url,
            )
        return retained

    def _load_source(self, force=False):
        if force:
            self._request_source_scan(self._source, force=True)
        elif self._source not in self._source_index_cache:
            self._request_source_scan(self._source, force=False)
        cached = self._current_source_index()
        groups = cached.get("groups", [])
        self._groups = groups
        self._group_model.replace([{k:g[k] for k in ("name","displayName","detailText","path","count","modifiedLabel")} for g in groups])
        self._all_file_rows = list(cached.get("rows", []))
        self._apply_search_filter()

    def _explorer_json_visible(self, path):
        path = Path(path)
        if path.suffix.casefold() != ".json":
            return False
        low = path.name.casefold()
        return not any(token in low for token in (".report.", "settings", "metadata", "backup", "session", "probe", "manifest"))

    @staticmethod
    def _folder_marker(path):
        return Path(path) / OUTPUT_FOLDER_MARKER

    def _folder_display_name(self, path):
        path = Path(path)
        try:
            payload = json.loads(self._folder_marker(path).read_text(encoding="utf-8"))
            name = str(payload.get("displayName") or "").strip() if isinstance(payload, dict) else ""
            if name and not self._name_error(name):
                return name
        except (OSError, ValueError, TypeError):
            pass
        return path.name

    def _write_folder_marker(self, path, display_name):
        payload = {"format": OUTPUT_FOLDER_MARKER_FORMAT, "displayName": str(display_name).strip()}
        self._folder_marker(path).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    def _is_managed_folder(self, path):
        path = Path(path)
        return path.is_dir() and not path.is_symlink() and self._folder_marker(path).is_file()

    def _is_accessible_managed_folder(self, path, source=None):
        path = Path(path)
        source = self._managed_source_for_path(path) if source is None else int(source)
        if source < 0:
            return False
        root = self._source_roots()[source]
        current = path
        if self._same_path(current, root):
            return False
        while self._path_is_within(current, root) and not self._same_path(current, root):
            if not self._is_managed_folder(current):
                return False
            current = current.parent
        return self._same_path(current, root)

    def _path_in_managed_folder(self, path, source=None):
        return self._path_in_managed_folder_with_keys(path, source=source)

    @staticmethod
    def _fast_path_key(path):
        try:
            return os.path.normcase(os.path.abspath(os.fspath(path)))
        except (OSError, TypeError, ValueError):
            return os.path.normcase(str(path or ""))

    def _managed_folder_keys(self, source=None):
        source = self._source if source is None else int(source)
        root = self._source_roots()[source]
        root_key = self._fast_path_key(root)
        return {
            self._fast_path_key(row.get("path"))
            for row in self._folder_model.rows
            if int(row.get("sourceIndex", -1)) == source
            and row.get("path")
            and self._fast_path_key(row.get("path")) != root_key
        }

    def _path_in_managed_folder_with_keys(self, path, source=None, managed_keys=None):
        source = self._source if source is None else int(source)
        root = self._source_roots()[source]
        root_key = self._fast_path_key(root)
        path_key = self._fast_path_key(path)
        try:
            if os.path.commonpath((path_key, root_key)) != root_key:
                return False
        except ValueError:
            return False
        managed = self._managed_folder_keys(source) if managed_keys is None else managed_keys
        current = Path(path).parent
        while True:
            current_key = self._fast_path_key(current)
            if current_key == root_key:
                return False
            if current_key in managed:
                return True
            parent = current.parent
            if parent == current:
                return False
            current = parent

    def _managed_child_folders(self, parent):
        try:
            with os.scandir(parent) as entries:
                folders = [
                    Path(entry.path)
                    for entry in entries
                    if entry.is_dir(follow_symlinks=False)
                    and self._folder_marker(entry.path).is_file()
                ]
            return sorted(folders, key=lambda item: self._folder_display_name(item).casefold())
        except OSError:
            return []

    def _managed_descendant_folders(self, root):
        folders = []

        def visit(parent):
            for child in self._managed_child_folders(parent):
                folders.append(child)
                visit(child)

        visit(Path(root))
        return folders

    def _folder_display_name_exists(self, parent, display_name, exclude=None):
        requested = str(display_name).strip().casefold()
        return any(
            (exclude is None or not self._same_path(child, exclude))
            and self._folder_display_name(child).casefold() == requested
            for child in self._managed_child_folders(parent)
        )

    def _unique_folder_display_name(self, parent, display_name, exclude=None):
        display_name = str(display_name).strip()
        if not self._folder_display_name_exists(parent, display_name, exclude=exclude):
            return display_name
        candidate = f"{display_name} - Copy"
        index = 2
        while self._folder_display_name_exists(parent, candidate, exclude=exclude):
            candidate = f"{display_name} - Copy ({index})"
            index += 1
        return candidate

    def _folder_storage_target(self, parent, display_name, exclude=None):
        parent = Path(parent)
        candidate = parent / str(display_name).strip()
        if (exclude is not None and self._same_path(candidate, exclude)) or not candidate.exists():
            return candidate
        candidate = parent / f"{str(display_name).strip()}.kfps-folder"
        index = 2
        while candidate.exists() and (exclude is None or not self._same_path(candidate, exclude)):
            candidate = parent / f"{str(display_name).strip()}.kfps-folder-{index}"
            index += 1
        return candidate

    def _folder_display_path(self, path, root):
        current = Path(root)
        parts = []
        for part in Path(path).relative_to(root).parts:
            current /= part
            parts.append(self._folder_display_name(current))
        return " / ".join(parts)

    def _source_entry_row(self, source):
        cached = self._source_index_cache.get(source, {})
        json_count = sum(1 for row in cached.get("rows", []) if row.get("path"))
        folder_count = sum(
            1 for row in self._folder_model.rows
            if int(row.get("sourceIndex", -1)) == source and int(row.get("depth", 0)) > 1
        )
        parts = [f"{json_count} JSON" if json_count == 1 else f"{json_count} JSONs"]
        if folder_count:
            parts.append(f"{folder_count} folder" if folder_count == 1 else f"{folder_count} folders")
        root = self._source_roots()[source]
        return {
            "name": self._explorer_source_label(source),
            "displayName": self._explorer_source_label(source),
            "path": str(root),
            "entryKind": "source",
            "isFolder": True,
            "sourceIndex": source,
            "layers": -1,
            "modifiedLabel": "",
            "previewUrl": "",
            "detailText": " • ".join(parts),
            "folder": "",
        }

    def _folder_entry_row(self, path, json_counts=None, folder_counts=None):
        path = Path(path)
        source = self._managed_source_for_path(path)
        display_name = self._folder_display_name(path)
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        path_key = self._fast_path_key(path)
        folders = int((folder_counts or {}).get(path_key, 0))
        jsons = int((json_counts or {}).get(path_key, 0))
        parts = []
        if folders:
            parts.append(f"{folders} folder" if folders == 1 else f"{folders} folders")
        if jsons:
            parts.append(f"{jsons} JSON" if jsons == 1 else f"{jsons} JSONs")
        return {
            "name": display_name,
            "displayName": display_name,
            "path": str(path),
            "entryKind": "folder",
            "isFolder": True,
            "sourceIndex": source,
            "layers": -1,
            "modifiedLabel": self._age(modified) if modified else "",
            "previewUrl": "",
            "detailText": " • ".join(parts) if parts else "Empty folder",
            "folder": str(path.parent),
        }

    def _explorer_json_row(self, path, cached_rows=None):
        path = Path(path)
        key = self._preview_key(path)
        row = dict((cached_rows or {}).get(key) or self._row_for_json(self._source, path))
        row["entryKind"] = "json"
        row["isFolder"] = False
        row["sourceIndex"] = self._source
        return row

    @staticmethod
    def _natural_text_key(value):
        return tuple(
            (1, int(part)) if part.isdigit() else (0, part.casefold())
            for part in re.split(r"(\d+)", str(value or ""))
            if part
        )

    def _sort_json_rows(self, rows):
        def name_key(row):
            return (
                self._natural_text_key(row.get("displayName") or row.get("name")),
                str(row.get("path") or "").casefold(),
            )

        if self._sort_mode == "name-asc":
            return sorted(rows, key=name_key)
        if self._sort_mode in {"shapes-asc", "shapes-desc"}:
            def shape_key(row):
                try:
                    layers = int(row.get("layers", -1))
                except (TypeError, ValueError):
                    layers = -1
                unknown = layers < 0
                ordered_layers = layers if self._sort_mode == "shapes-asc" else -layers
                return (unknown, ordered_layers if not unknown else 0, *name_key(row))
            return sorted(rows, key=shape_key)
        return sorted(
            rows,
            key=lambda row: (
                -int(row.get("mtimeNs") or 0),
                *name_key(row),
            ),
        )

    def _refresh_explorer(self):
        self._refresh_folder_model()
        rows = []
        if not self._current_folder:
            rows = [self._source_entry_row(source) for source in range(len(self._source_roots()))]
        else:
            root = self._root()
            root.mkdir(parents=True, exist_ok=True)
            current = Path(self._current_folder)
            valid_folder = self._same_path(current, root) or self._is_accessible_managed_folder(current, self._source)
            if not current.is_dir() or not self._path_is_within(current, root) or not valid_folder:
                self._current_folder = ""
                self._back_history.clear()
                self._forward_history.clear()
                self._search_query = ""
                self._refresh_folder_model(force=True)
                self._refresh_explorer()
                return
            current_index = self._current_source_index()
            cached_rows = current_index.get("rowsByKey", {})
            indexed_rows = current_index.get("rows", [])
            json_counts = {}
            for indexed_row in indexed_rows:
                folder_key = self._fast_path_key(indexed_row.get("folder") or Path(indexed_row["path"]).parent)
                json_counts[folder_key] = json_counts.get(folder_key, 0) + 1
            folder_counts = {}
            for folder_row in self._folder_model.rows:
                folder_path = folder_row.get("path")
                if not folder_path or int(folder_row.get("sourceIndex", -1)) != self._source:
                    continue
                parent_key = self._fast_path_key(Path(folder_path).parent)
                folder_counts[parent_key] = folder_counts.get(parent_key, 0) + 1
            if self._search_query:
                rows = [
                    self._explorer_json_row(row["path"], cached_rows)
                    for row in self._visible_file_rows
                    if row.get("path")
                ]
            elif self._same_path(current, root):
                rows.extend(
                    self._folder_entry_row(path, json_counts, folder_counts)
                    for path in self._managed_child_folders(root)
                )
                managed_keys = self._managed_folder_keys(self._source)
                rows.extend(
                    self._explorer_json_row(row["path"], cached_rows)
                    for row in self._visible_file_rows
                    if row.get("path")
                    and not self._path_in_managed_folder_with_keys(
                        row["path"],
                        managed_keys=managed_keys,
                    )
                )
            else:
                rows.extend(
                    self._folder_entry_row(path, json_counts, folder_counts)
                    for path in self._managed_child_folders(current)
                )
                current_key = self._fast_path_key(current)
                direct_rows = [
                    row for row in self._visible_file_rows
                    if row.get("path")
                    and self._fast_path_key(row.get("folder") or Path(row["path"]).parent) == current_key
                ]
                direct_rows = self._sort_json_rows(direct_rows)
                rows.extend(self._explorer_json_row(row["path"], cached_rows) for row in direct_rows)
        self._explorer_index_by_key = {}
        self._explorer_operable_keys = set()
        self._explorer_json_keys = set()
        for index, row in enumerate(rows):
            key = self._preview_key(row.get("path"))
            selected = key in self._explorer_selection_keys
            row["selected"] = selected
            self._explorer_index_by_key[key] = index
            if row.get("entryKind") != "source":
                self._explorer_operable_keys.add(key)
            if row.get("entryKind") == "json":
                self._explorer_json_keys.add(key)
        self._update_operation_selection_counts()
        self._explorer_rows = rows
        self._explorer_model.replace(rows)

    def _update_operation_selection_counts(self):
        selected_operable = self._explorer_selection_keys & self._explorer_operable_keys
        self._operation_selection_count = len(selected_operable)
        self._operation_selection_json_count = len(selected_operable & self._explorer_json_keys)

    def _sync_explorer_selection_model(self, previous_keys):
        current_keys = self._explorer_selection_keys
        for key in previous_keys.symmetric_difference(current_keys):
            index = self._explorer_index_by_key.get(key, -1)
            if not 0 <= index < len(self._explorer_rows):
                continue
            selected = key in current_keys
            self._explorer_rows[index]["selected"] = selected
            self._explorer_model.set_row_value(index, "selected", selected)
        self._update_operation_selection_counts()

    def _refresh_folder_model(self, force=False):
        if self._folder_model.rows and not force:
            return
        rows = []
        if not self._current_folder:
            rows.append({"displayName": "Outputs", "path": "", "depth": 0, "sourceIndex": -1})
            scopes = [(source, self._source_roots()[source], 1) for source in range(len(self._source_roots()))]
        else:
            current = Path(self._current_folder)
            source = self._managed_source_for_path(current)
            if source < 0:
                rows.append({"displayName": "Outputs", "path": "", "depth": 0, "sourceIndex": -1})
                scopes = []
            else:
                scopes = [(source, current, 0)]

        for source, scope_root, base_depth in scopes:
            source_root = self._source_roots()[source]
            source_root.mkdir(parents=True, exist_ok=True)
            label = self._explorer_source_label(source)
            if self._same_path(scope_root, source_root):
                scope_label = label
            else:
                scope_label = f"{label} / {self._folder_display_path(scope_root, source_root)}"
            rows.append({"displayName": scope_label, "path": str(scope_root), "depth": base_depth, "sourceIndex": source})
            for path in self._managed_descendant_folders(scope_root):
                relative_depth = len(path.relative_to(scope_root).parts)
                rows.append({
                    "displayName": f"{label} / {self._folder_display_path(path, source_root)}",
                    "path": str(path),
                    "depth": base_depth + relative_depth,
                    "sourceIndex": source,
                })
        self._folder_model.replace(rows)
        self._refresh_move_folder_model()

    def _refresh_move_folder_model(self):
        rows = []
        for source in range(len(self._source_roots())):
            source_root = self._source_roots()[source]
            source_root.mkdir(parents=True, exist_ok=True)
            label = self._explorer_source_label(source)
            rows.append({"displayName": label, "path": str(source_root), "depth": 0, "sourceIndex": source})
            for path in self._managed_descendant_folders(source_root):
                rows.append({
                    "displayName": f"{label} / {self._folder_display_path(path, source_root)}",
                    "path": str(path),
                    "depth": len(path.relative_to(source_root).parts),
                    "sourceIndex": source,
                })
        self._move_folder_model.replace(rows)

    @Slot()
    def warmIndex(self):
        for source in range(len(self._source_roots())):
            self._request_source_scan(source, force=False)

    def _request_source_scan(self, source, force=False):
        if not 0 <= source < len(self._source_roots()):
            return
        if not force and source in self._indexing_sources:
            return
        if not force and self._source_index_cache.get(source, {}).get("backgroundFresh"):
            return
        generation = self._source_scan_generation.get(source, 0) + 1
        self._source_scan_generation[source] = generation
        self._indexing_sources.add(source)
        self._index_status = f"Indexing {self._source_label(source)}..."
        self.changed.emit()
        root = self._source_roots()[source]
        cache_key = self._source_cache_key(source)
        future = self._index_executor.submit(self._build_source_index, source, root, cache_key)
        future.add_done_callback(lambda done, item=source, gen=generation: self._emit_source_index_result(item, gen, done))

    def _emit_source_index_result(self, source, generation, future):
        try:
            index = future.result()
            error = ""
        except Exception as exc:
            index = None
            error = str(exc)
        self._indexReady.emit(source, generation, index, error)

    @Slot(int, int, object, str)
    def _apply_source_index_result(self, source, generation, index, error):
        if generation != self._source_scan_generation.get(source):
            return
        self._indexing_sources.discard(source)
        if index and not error:
            old_rows = list(self._all_file_rows) if source == self._source else []
            index["backgroundFresh"] = True
            self._source_index_cache[source] = index
            self._index_status = f"Indexed {self._source_label(source)} ({len(index.get('rows', []))} JSONs)"
            if source == self._source:
                new_rows = index.get("rows", [])
                if not old_rows or self._row_path_signature(old_rows) != self._row_path_signature(new_rows):
                    self._load_source(force=False)
                else:
                    self._refresh_explorer()
            self._refresh_recent_from_cache()
            self._schedule_index_cache_save()
        else:
            self._index_status = f"{self._source_label(source)} index failed"
            if error:
                self.log.append(f"{self._source_label(source)} index failed: {error}", "error")
        if not self._indexing_sources and not error:
            self._index_status = "Output index ready"
            self._cache_save_pending = False
            self._save_index_cache_async()
            self._schedule_thumbnail_warm(1200)
        self.changed.emit()

    @staticmethod
    def _row_path_signature(rows):
        return tuple(str(row.get("path") or "") for row in rows)

    def _index_cache_file(self):
        return self.paths.runtime_root / "json-browser-index.v1.json"

    def _load_index_cache(self):
        cache_file = self._index_cache_file()
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict) or payload.get("version") != JSON_INDEX_CACHE_VERSION:
            return
        sources = payload.get("sources")
        if not isinstance(sources, dict):
            return
        loaded = 0
        for source in range(len(self._source_roots())):
            index = self._source_index_from_cache(source, sources.get(str(source)))
            if index:
                self._source_index_cache[source] = index
                loaded += len(index.get("rows", []))
        if loaded:
            self._index_status = f"Loaded cached output index ({loaded} JSONs)"
        try:
            self._thumbnail_cache_mtime_ns = cache_file.stat().st_mtime_ns
        except OSError:
            self._thumbnail_cache_mtime_ns = 0

    def _source_index_from_cache(self, source, payload):
        if not isinstance(payload, dict):
            return None
        cache_key = self._source_cache_key(source)
        if payload.get("root") != cache_key:
            return None
        valid_rows = []
        valid_keys = set()
        for raw in payload.get("rows", []):
            if not isinstance(raw, dict):
                continue
            path = Path(str(raw.get("path") or ""))
            try:
                stat = path.stat()
            except OSError:
                continue
            if int(raw.get("mtimeNs") or -1) != stat.st_mtime_ns or int(raw.get("size") or -1) != stat.st_size:
                continue
            modified_label = self._age(stat.st_mtime)
            count_detail = str(raw.get("countDetail") or "").strip() or f"{int(raw.get('layers') or 0)} layers"
            row = {
                "name": str(raw.get("name") or path.name),
                "displayName": str(raw.get("displayName") or path.name),
                "path": str(path),
                "layers": int(raw.get("layers") or 0),
                "modifiedLabel": modified_label,
                "previewUrl": str(raw.get("previewUrl") or ""),
                "countDetail": count_detail,
                "detailText": f"{count_detail}  •  {modified_label}",
                "folder": str(raw.get("folder") or path.parent),
                "mtime": stat.st_mtime,
                "mtimeNs": stat.st_mtime_ns,
                "size": stat.st_size,
                "source": source,
            }
            valid_rows.append(row)
            valid_keys.add(self._preview_key(path))
        if not valid_rows:
            return None
        try:
            scanned_at = float(payload.get("scannedAt") or 0)
        except (TypeError, ValueError):
            scanned_at = 0.0
        groups = []
        row_by_key = {self._preview_key(row["path"]): row for row in valid_rows}
        for raw in payload.get("groups", []):
            if not isinstance(raw, dict):
                continue
            files = []
            for item in raw.get("files", []):
                path = Path(str(item))
                if self._preview_key(path) in valid_keys:
                    files.append(path)
            if not files:
                continue
            modified = max((row_by_key[self._preview_key(path)].get("mtime", 0) for path in files), default=0)
            groups.append({
                "name": str(raw.get("name") or Path(str(raw.get("path") or "")).name),
                "displayName": str(raw.get("displayName") or raw.get("name") or "JSONs"),
                "detailText": str(raw.get("detailText") or f"{len(files)} JSONs"),
                "path": str(raw.get("path") or files[0].parent),
                "files": sorted(files, key=lambda p: row_by_key[self._preview_key(p)].get("mtime", 0), reverse=True),
                "count": len(files),
                "modified": modified,
                "modifiedLabel": self._age(modified),
            })
        rows_by_key = {self._preview_key(row["path"]): row for row in valid_rows}
        return {
            "root": cache_key,
            "groups": groups,
            "rows": valid_rows,
            "rowsByKey": rows_by_key,
            "source": source,
            "loadedFromDisk": True,
            "scannedAt": scanned_at,
            "backgroundFresh": bool(scanned_at and time.time() - scanned_at < 300),
        }

    def _index_cache_payload(self):
        sources = {}
        for source, index in self._source_index_cache.items():
            rows = []
            for row in index.get("rows", []):
                rows.append({
                    "name": row.get("name", ""),
                    "displayName": row.get("displayName", ""),
                    "path": row.get("path", ""),
                    "layers": int(row.get("layers") or 0),
                    "previewUrl": row.get("previewUrl", ""),
                    "countDetail": row.get("countDetail", ""),
                    "folder": row.get("folder", ""),
                    "mtimeNs": int(row.get("mtimeNs") or 0),
                    "size": int(row.get("size") or 0),
                })
            groups = []
            for group in index.get("groups", []):
                groups.append({
                    "name": group.get("name", ""),
                    "displayName": group.get("displayName", ""),
                    "detailText": group.get("detailText", ""),
                    "path": group.get("path", ""),
                    "files": [str(path) for path in group.get("files", [])],
                })
            sources[str(source)] = {
                "root": index.get("root") or self._source_cache_key(source),
                "scannedAt": index.get("scannedAt") or time.time(),
                "rows": rows,
                "groups": groups,
            }
        return {"version": JSON_INDEX_CACHE_VERSION, "createdAt": time.time(), "sources": sources}

    def _schedule_index_cache_save(self):
        if self._cache_save_pending:
            return
        self._cache_save_pending = True
        QTimer.singleShot(700, self._save_index_cache_async)

    def _save_index_cache_async(self):
        self._cache_save_pending = False
        payload = self._index_cache_payload()
        target = self._index_cache_file()
        try:
            self._index_executor.submit(self._write_index_cache_payload, target, payload)
        except RuntimeError:
            # A delayed Qt callback can arrive while the app is shutting down.
            return

    @staticmethod
    def _write_index_cache_payload(target, payload):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            tmp.replace(target)
        except Exception:
            pass

    def _thumbnail_worker_enabled(self):
        if self.demo:
            return False
        if os.environ.get("KFPS_SKIP_BACKGROUND_THUMBNAILS", "").strip() == "1":
            return False
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return False
        return True

    def _set_thumbnail_status(self, message="", active=False):
        message = str(message or "")
        active = bool(active)
        if self._thumbnail_status == message and self._thumbnail_active == active:
            return
        self._thumbnail_status = message
        self._thumbnail_active = active
        self.changed.emit()

    @staticmethod
    def _env_float(name, default, minimum=0.0, maximum=300.0):
        try:
            value = float(os.environ.get(name, default))
        except (TypeError, ValueError):
            value = float(default)
        return max(minimum, min(maximum, value))

    @staticmethod
    def _env_int(name, default, minimum=0, maximum=1000):
        try:
            value = int(os.environ.get(name, default))
        except (TypeError, ValueError):
            value = int(default)
        return max(minimum, min(maximum, value))

    def _stop_thumbnail_worker(self):
        proc = self._thumbnail_process
        if not proc or proc.poll() is not None:
            self._thumbnail_process = None
            return
        try:
            proc.terminate()
            proc.communicate(timeout=0.8)
        except Exception:
            try:
                proc.kill()
                proc.communicate(timeout=0.8)
            except Exception:
                pass
        self._thumbnail_process = None

    @Slot()
    def regenerateLocalThumbnails(self):
        if self._thumbnail_regenerating:
            return
        if not self._thumbnail_worker_enabled():
            self._set_thumbnail_status("Local thumbnail regeneration is unavailable in this session.", False)
            return
        self._thumbnail_warm_pending = False
        self._thumbnail_poll_timer.stop()
        self._stop_thumbnail_worker()
        self._preview_queue.clear()
        self._preview_queued.clear()
        self._preview_empty.clear()
        self._thumbnail_regenerating = True
        self._set_thumbnail_status("Clearing and replacing every local thumbnail...", True)
        self._start_thumbnail_worker(regenerate=True)

    @Slot()
    def _schedule_thumbnail_warm(self, delay_ms=0):
        if not self._thumbnail_worker_enabled() or self._thumbnail_warm_pending:
            return
        self._thumbnail_warm_pending = True
        QTimer.singleShot(max(0, int(delay_ms or 0)), self._start_thumbnail_worker)

    def _start_thumbnail_worker(self, regenerate=False):
        self._thumbnail_warm_pending = False
        if not self._thumbnail_worker_enabled():
            if regenerate:
                self._thumbnail_regenerating = False
                self._set_thumbnail_status("Local thumbnail regeneration is unavailable in this session.", False)
            return
        if self._thumbnail_process and self._thumbnail_process.poll() is None:
            if not self._thumbnail_poll_timer.isActive():
                self._thumbnail_poll_timer.start()
            return
        cache_file = self._index_cache_file()
        if not regenerate and not cache_file.is_file():
            self._set_thumbnail_status("Thumbnail cache is waiting for the output index.", False)
            return
        if not regenerate and not self._cache_source_has_missing_preview_urls(self._source):
            self._set_thumbnail_status(f"{self._source_label(self._source)} thumbnails are ready.", False)
            if not self._cache_has_missing_preview_urls():
                return
        if not regenerate and not self._cache_has_missing_preview_urls():
            return
        seconds = 0.0 if regenerate else self._env_float("KFPS_BACKGROUND_THUMBNAIL_SECONDS", 5.0, 1.0, 120.0)
        max_items = 0 if regenerate else self._env_int("KFPS_BACKGROUND_THUMBNAIL_ITEMS", 40, 1, 500)
        cmd = worker_command(
            paths=self.paths,
            cache_file=cache_file,
            max_seconds=seconds,
            max_items=max_items,
            app_executable=sys.executable,
            preferred_source=None if regenerate else self._source,
            regenerate=bool(regenerate),
        )
        kwargs = {
            "cwd": str(self.paths.ui_root),
            "env": worker_environment(self.paths),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
        }
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS"):
            flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
        if flags:
            kwargs["creationflags"] = flags
        try:
            self._thumbnail_process = subprocess.Popen(cmd, **kwargs)
            message = "Replacing every local thumbnail..." if regenerate else f"Warming {self._source_label(self._source)} thumbnails..."
            self._set_thumbnail_status(message, True)
            self._thumbnail_poll_timer.start()
        except Exception as exc:
            self._thumbnail_process = None
            if regenerate:
                self._thumbnail_regenerating = False
            self._set_thumbnail_status(f"{self._source_label(self._source)} thumbnail worker failed to start.", False)
            self.log.append(f"Output thumbnail worker failed to start: {exc}", "warning")

    def _cache_has_missing_preview_urls(self):
        return self._cache_source_has_missing_preview_urls(None)

    def _cache_source_has_missing_preview_urls(self, wanted_source):
        try:
            payload = json.loads(self._index_cache_file().read_text(encoding="utf-8"))
        except Exception:
            return False
        sources = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(sources, dict):
            return False
        for source_key, source in sources.items():
            if wanted_source is not None and str(source_key) != str(int(wanted_source)):
                continue
            rows = source.get("rows") if isinstance(source, dict) else None
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                path = Path(str(row.get("path") or ""))
                if row.get("previewUrl"):
                    if str(source_key) != "0":
                        continue
                    checker = getattr(self.preview, "generated_preview_needs_persistence", None)
                    if not callable(checker) or not checker(path):
                        continue
                if path.is_file():
                    return True
        return False

    def _restart_thumbnail_warm_for_current_source(self):
        if self._thumbnail_regenerating:
            return
        if not self._thumbnail_worker_enabled() or not self._cache_source_has_missing_preview_urls(self._source):
            if self._thumbnail_worker_enabled():
                self._set_thumbnail_status(f"{self._source_label(self._source)} thumbnails are ready.", False)
            return
        self._stop_thumbnail_worker()
        self._merge_preview_urls_from_cache(force=True)
        self._schedule_thumbnail_warm(100)

    def _poll_thumbnail_worker(self):
        self._merge_preview_urls_from_cache()
        proc = self._thumbnail_process
        if not proc:
            self._thumbnail_poll_timer.stop()
            return
        if proc.poll() is None:
            return
        try:
            stdout, stderr = proc.communicate(timeout=0.2)
        except Exception:
            stdout, stderr = "", ""
        self._thumbnail_process = None
        count = 0
        summary = {}
        try:
            final_line = (stdout or "0").strip().splitlines()[-1]
            if final_line.startswith("{"):
                parsed = json.loads(final_line)
                summary = parsed if isinstance(parsed, dict) else {}
                count = max(0, int(summary.get("rendered") or 0))
            else:
                count = max(0, int(final_line))
        except (IndexError, TypeError, ValueError):
            count = 0
        merged = self._merge_preview_urls_from_cache(force=True)
        label = self._source_label(self._source)
        if proc.returncode != 0:
            self._thumbnail_regenerating = False
            self._set_thumbnail_status(f"{label} thumbnail worker exited with code {proc.returncode}.", False)
            self.log.append(f"{label} thumbnail worker exited with code {proc.returncode}.", "warning")
            self._thumbnail_poll_timer.stop()
            return
        if self._thumbnail_regenerating:
            self._thumbnail_regenerating = False
            self._reload_regenerated_thumbnail_index()
            indexed = max(count, int(summary.get("indexed") or count))
            failed = max(0, int(summary.get("failed") or (indexed - count)))
            if indexed == 0:
                message = "No local JSON thumbnails were found to regenerate."
                level = "warning"
            elif failed:
                message = f"Regenerated {count} of {indexed} local thumbnails ({failed} failed)."
                level = "warning"
            else:
                noun = "thumbnail" if indexed == 1 else "thumbnails"
                message = f"Regenerated all {indexed} local {noun}."
                level = "success"
            self._set_thumbnail_status(message, False)
            self.log.append(message, level)
            self._thumbnail_poll_timer.stop()
            return
        if count > 0 or merged > 0:
            shown = max(count, merged)
            noun = "thumbnail" if shown == 1 else "thumbnails"
            self._set_thumbnail_status(f"Warmed {shown} {label} {noun}.", False)
        else:
            self._set_thumbnail_status(f"No new {label} thumbnails this pass.", False)
        if proc.returncode == 0 and count > 0 and self._cache_has_missing_preview_urls():
            self._schedule_thumbnail_warm(1600)
            return
        self._thumbnail_poll_timer.stop()

    def _reload_regenerated_thumbnail_index(self):
        self._source_index_cache.clear()
        self._thumbnail_cache_mtime_ns = 0
        self._load_index_cache()
        self._load_source(force=False)
        self._refresh_recent_from_cache()
        self._preview_url = ""
        if self._selected_path:
            for row in self._all_file_rows:
                if self._same_path(row.get("path"), self._selected_path):
                    self._preview_url = str(row.get("previewUrl") or "")
                    break
        self.changed.emit()

    def _merge_preview_urls_from_cache(self, force=False):
        cache_file = self._index_cache_file()
        try:
            stat = cache_file.stat()
        except OSError:
            return 0
        if not force and self._thumbnail_cache_mtime_ns == stat.st_mtime_ns:
            return 0
        self._thumbnail_cache_mtime_ns = stat.st_mtime_ns
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return 0
        sources = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(sources, dict):
            return 0
        previews_by_key = {}
        for source, cached in self._source_index_cache.items():
            source_payload = sources.get(str(source))
            rows = source_payload.get("rows") if isinstance(source_payload, dict) else None
            if not isinstance(rows, list):
                continue
            rows_by_key = cached.get("rowsByKey", {})
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                preview_url = str(raw.get("previewUrl") or "")
                if not preview_url:
                    continue
                path = Path(str(raw.get("path") or ""))
                key = self._preview_key(path)
                row = rows_by_key.get(key)
                if not row or row.get("previewUrl") == preview_url:
                    continue
                if int(raw.get("mtimeNs") or -1) != int(row.get("mtimeNs") or -2):
                    continue
                if int(raw.get("size") or -1) != int(row.get("size") or -2):
                    continue
                row["previewUrl"] = preview_url
                previews_by_key[key] = preview_url
                self._preview_empty.discard(key)
        if not previews_by_key:
            return 0
        for row in self._all_file_rows:
            key = self._preview_key(row.get("path"))
            if key in previews_by_key:
                row["previewUrl"] = previews_by_key[key]
        for index, row in enumerate(self._visible_file_rows):
            key = self._preview_key(row.get("path"))
            preview_url = previews_by_key.get(key)
            if preview_url:
                row["previewUrl"] = preview_url
                self._file_model.set_row_value(index, "previewUrl", preview_url)
        for key, preview_url in previews_by_key.items():
            self._set_explorer_preview_url(key, preview_url)
        if self._selected_path:
            selected_key = self._preview_key(self._selected_path)
            if selected_key in previews_by_key:
                self._preview_url = previews_by_key[selected_key]
        self.changed.emit()
        return len(previews_by_key)

    def _ensure_logo(self):
        src = self.paths.app_root / "assets" / "app" / "KFPS Logo.json"
        if not src.is_file(): return
        for dest in [self.paths.generated_root / "KFPS Logo" / "finals" / "KFPS Logo.3000v2.json", self.paths.editor_json_root / "KFPS Logo" / "KFPS Logo.json", self.paths.exported_root / "KFPS Logo.json"]:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_file() and dest.read_bytes() == src.read_bytes():
                    continue
                shutil.copy2(src, dest)
            except Exception: pass

    @Slot(int)
    def setSource(self, index):
        self._source = max(0,min(len(self._source_roots()) - 1,index))
        self._selected_group=-1
        self._current_folder = str(self._root())
        self._back_history.clear()
        self._forward_history.clear()
        self._clear_explorer_selection(emit=False)
        self.clearSelection()
        self._refresh_folder_model(force=True)
        self._load_source(force=False)
        self._restart_thumbnail_warm_for_current_source()
        self.changed.emit()

    @Slot(str)
    def setSearchQuery(self, value):
        query = str(value or "").strip()
        if query == self._search_query:
            return
        self._search_query = query
        self._clear_explorer_selection(emit=False)
        self._apply_search_filter()

    @Slot(str)
    def setSortMode(self, value):
        mode = str(value or "").strip().casefold()
        if mode not in OUTPUT_SORT_MODES or mode == self._sort_mode:
            return
        self._sort_mode = mode
        self._apply_search_filter()

    @Slot()
    def clearSearch(self): self.setSearchQuery("")

    @Slot()
    def refresh(self):
        self._refresh_folder_model(force=True)
        self._load_source(force=True)

    def _navigate_to_folder(self, value, record_history=True):
        requested = str(value or "")
        source = self._source
        target = ""
        if requested:
            candidate = Path(requested)
            source = self._managed_source_for_path(candidate)
            if source < 0:
                self._management_status = "That folder is outside the available KFPS output categories."
                self.changed.emit()
                return False
            root = self._source_roots()[source]
            valid_folder = self._same_path(candidate, root) or self._is_accessible_managed_folder(candidate, source)
            if not candidate.is_dir() or not self._path_is_within(candidate, root) or not valid_folder:
                self._management_status = "Only an output category or a folder created in KFPS can be opened here."
                self.changed.emit()
                return False
            target = str(candidate.resolve())
        if target == self._current_folder or (target and self._same_path(target, self._current_folder)):
            return True
        if record_history:
            self._back_history.append(self._current_folder)
            self._forward_history.clear()
        source_changed = bool(target) and source != self._source
        self._source = source
        self._current_folder = target
        self._refresh_folder_model(force=True)
        self._selected_group = -1
        self._management_status = ""
        self._clear_explorer_selection(emit=False)
        self.clearSelection()
        had_search = bool(self._search_query)
        if had_search:
            self._search_query = ""
        if source_changed:
            self._load_source(force=False)
            self._restart_thumbnail_warm_for_current_source()
        else:
            if had_search:
                self._apply_search_filter()
            else:
                self._refresh_explorer()
        self.changed.emit()
        return True

    @Slot(str)
    def openExplorerFolder(self, value):
        self._navigate_to_folder(value, record_history=True)

    @Slot(str)
    def jumpToFolder(self, value):
        self._navigate_to_folder(value, record_history=True)

    @Slot()
    def goBack(self):
        if not self._back_history:
            return
        target = self._back_history.pop()
        self._forward_history.append(self._current_folder)
        if not self._navigate_to_folder(target, record_history=False):
            self._forward_history.pop()

    @Slot()
    def goForward(self):
        if not self._forward_history:
            return
        target = self._forward_history.pop()
        self._back_history.append(self._current_folder)
        if not self._navigate_to_folder(target, record_history=False):
            self._back_history.pop()

    @Slot()
    def goUp(self):
        if not self._current_folder:
            return
        if self._same_path(self._current_folder, self._root()):
            self._navigate_to_folder("", record_history=True)
        else:
            self._navigate_to_folder(str(Path(self._current_folder).parent), record_history=True)

    @Slot(int, bool, bool)
    def selectExplorerEntry(self, index, control, shift):
        if not 0 <= index < len(self._explorer_rows):
            return
        row = self._explorer_rows[index]
        path = str(row.get("path") or "")
        if not path:
            return
        key = self._preview_key(path)
        previous_keys = set(self._explorer_selection_keys)

        if shift and self._selection_anchor_path:
            anchor_key = self._preview_key(self._selection_anchor_path)
            anchor_index = next(
                (position for position, candidate in enumerate(self._explorer_rows)
                 if self._preview_key(candidate.get("path")) == anchor_key),
                index,
            )
            start, end = sorted((anchor_index, index))
            range_paths = [
                str(candidate.get("path") or "")
                for candidate in self._explorer_rows[start:end + 1]
                if candidate.get("path")
            ]
            if not control:
                self._explorer_selection = []
                self._explorer_selection_keys.clear()
            for candidate in range_paths:
                candidate_key = self._preview_key(candidate)
                if candidate_key not in self._explorer_selection_keys:
                    self._explorer_selection.append(candidate)
                    self._explorer_selection_keys.add(candidate_key)
        elif control:
            if key in self._explorer_selection_keys:
                self._explorer_selection_keys.remove(key)
                self._explorer_selection = [
                    candidate for candidate in self._explorer_selection
                    if self._preview_key(candidate) != key
                ]
            else:
                self._explorer_selection.append(path)
                self._explorer_selection_keys.add(key)
            self._selection_anchor_path = path
        else:
            self._explorer_selection = [path]
            self._explorer_selection_keys = {key}
            self._selection_anchor_path = path

        selected = key in self._explorer_selection_keys
        if selected and not row.get("isFolder"):
            self._select_path(path, queue_preview=not (control or shift), emit=False)
        elif self._selected_path and self._preview_key(self._selected_path) not in self._explorer_selection_keys:
            self._clear_selection(emit=False)
        self._sync_explorer_selection_model(previous_keys)
        self._selection_revision += 1
        self.changed.emit()

    @Slot(str, result=bool)
    def isExplorerEntrySelected(self, value):
        return self._preview_key(value) in self._explorer_selection_keys

    def _managed_source_for_path(self, value):
        path_key = self._fast_path_key(value)
        for source, root in enumerate(self._source_roots()):
            root_key = self._fast_path_key(root)
            try:
                if os.path.commonpath((path_key, root_key)) == root_key:
                    return source
            except ValueError:
                continue
        return -1

    def _entry_allowed_for_operation(self, value):
        path = Path(str(value or ""))
        source = self._managed_source_for_path(path)
        if source < 0 or not path.exists() or path.is_symlink() or self._same_path(path, self._source_roots()[source]):
            return False
        return self._is_accessible_managed_folder(path, source) or (path.is_file() and self._explorer_json_visible(path))

    @staticmethod
    def _name_error(value):
        name = str(value or "").strip()
        if not name:
            return "Enter a name first."
        if name in {".", ".."} or any(character in name for character in '<>:"/\\|?*'):
            return "That name contains characters Windows does not allow."
        if name.endswith((" ", ".")):
            return "Windows folder and file names cannot end with a space or period."
        if name.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            return "That name is reserved by Windows."
        return ""

    def _operation_selection(self):
        values = []
        seen = set()
        selected_values = list(self._explorer_selection)
        if not selected_values and self._selected_path:
            selected_values = [self._selected_path]
        for value in selected_values:
            if not self._entry_allowed_for_operation(value):
                continue
            path = Path(value)
            key = self._preview_key(path)
            if key in seen:
                continue
            seen.add(key)
            values.append(path)

        values.sort(key=lambda path: len(path.parts))
        collapsed = []
        selected_folders = []
        for path in values:
            if any(self._path_is_within(path, parent) for parent in selected_folders):
                continue
            collapsed.append(path)
            if path.is_dir():
                selected_folders.append(path)
        return [str(path) for path in collapsed]

    def _stage_clipboard(self, values, cut, validated=False):
        paths = []
        seen = set()
        for value in values:
            if not validated and not self._entry_allowed_for_operation(value):
                continue
            path = str(Path(value))
            key = self._preview_key(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
        if not paths:
            self._management_status = "Select a JSON or use a folder's right-click menu first."
            self.changed.emit()
            return
        self._clipboard_paths = paths
        self._clipboard_cut = bool(cut)
        published_to_windows = not cut and self._publish_system_clipboard(paths)
        action = "Cut" if cut else "Copied"
        noun = "item" if len(paths) == 1 else "items"
        if published_to_windows:
            self._management_status = (
                f"{action} {len(paths)} {noun}. Paste in KFPS or Windows File Explorer when ready."
            )
        else:
            self._management_status = f"{action} {len(paths)} {noun}. Choose a folder and paste when ready."
        self.changed.emit()

    @staticmethod
    def _system_clipboard_mime(paths):
        resolved = []
        for value in paths:
            path = Path(value)
            if path.exists():
                resolved.append(path.resolve())
        if not resolved:
            return None
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in resolved])
        mime.setText(os.linesep.join(str(path) for path in resolved))
        return mime

    def _publish_system_clipboard(self, paths):
        try:
            app = QGuiApplication.instance()
            if not isinstance(app, QGuiApplication):
                return False
            mime = JsonService._system_clipboard_mime(paths)
            clipboard = app.clipboard()
            if mime is None or clipboard is None:
                return False
            clipboard.setMimeData(mime)
            return True
        except Exception as exc:
            self.log.append(f"Could not copy output files to the Windows clipboard: {exc}", "warning")
            return False

    @Slot()
    def copySelection(self):
        self._stage_clipboard(self._operation_selection(), cut=False, validated=True)

    @Slot()
    def cutSelection(self):
        self._stage_clipboard(self._operation_selection(), cut=True, validated=True)

    @Slot(str, result=int)
    def moveSelectedJsonsToFolder(self, value):
        destination = Path(str(value or ""))
        destination_source = self._managed_source_for_path(destination)
        destination_root = self._source_roots()[destination_source] if destination_source >= 0 else None
        valid_destination = destination_source >= 0 and (
            self._same_path(destination, destination_root)
            or self._is_accessible_managed_folder(destination, destination_source)
        )
        if not destination.is_dir() or not valid_destination:
            self._management_status = "Choose a KFPS output folder as the move destination."
            self.changed.emit()
            return 0

        sources = [Path(path) for path in self._operation_selection()]
        if not sources or any(not path.is_file() or path.suffix.casefold() != ".json" for path in sources):
            self._management_status = "Move to folder is available only when the selection contains JSON files."
            self.changed.emit()
            return 0

        succeeded = []
        preview_urls = {}
        failed = []
        affected = [destination]
        for source in sources:
            target = destination / source.name
            if self._same_path(source.parent, destination):
                failed.append(f"{source.name} is already in that folder")
                continue
            if target.exists():
                failed.append(f"{source.name} already exists there")
                continue
            source_index = self._managed_source_for_path(source)
            preview_transfers = self._prepare_preview_transfers(source, source_index)
            try:
                shutil.move(str(source), str(target))
                succeeded.append((str(source), str(target)))
                preview_urls.update(self._complete_preview_transfers(
                    preview_transfers,
                    source,
                    target,
                    self._source_names()[destination_source],
                    move=True,
                ))
                affected.extend((source, target))
            except OSError as exc:
                failed.append(source.name)
                self.log.append(f"Could not move {source} into {destination}: {exc}", "error")

        if succeeded:
            moved_keys = {self._preview_key(source) for source, target in succeeded}
            if self._selected_path and self._preview_key(self._selected_path) in moved_keys:
                self._clear_selection(emit=False)
            self._clear_explorer_selection(emit=False)
            self._remap_entry_references_batch(succeeded)
            self._remap_cached_output_rows(succeeded, preview_urls, copy=False)

        if succeeded and not failed:
            noun = "JSON" if len(succeeded) == 1 else "JSONs"
            self._management_status = f"Moved {len(succeeded)} {noun} into {self._folder_display_name(destination)}."
        elif succeeded:
            self._management_status = f"Moved {len(succeeded)} JSON(s); {len(failed)} could not be moved."
        elif failed:
            self._management_status = f"Nothing was moved: {failed[0]}."
        else:
            self._management_status = "Nothing was moved."
        self._refresh_after_file_operations(affected)
        return len(succeeded)

    @Slot(str)
    def copyEntry(self, value):
        self._stage_clipboard([value], cut=False)

    @Slot(str)
    def cutEntry(self, value):
        self._stage_clipboard([value], cut=True)

    @Slot(str, result=bool)
    def createFolder(self, value):
        return self._create_folder_in(self._current_folder, value)

    @Slot(str, str, result=bool)
    def createFolderIn(self, parent_value, value):
        return self._create_folder_in(parent_value, value)

    def _create_folder_in(self, parent_value, value):
        display_name = str(value or "").strip()
        error = self._name_error(display_name)
        current = Path(str(parent_value or self._current_folder))
        if error:
            self._management_status = error
            self.changed.emit()
            return False
        source = self._managed_source_for_path(current)
        root = self._source_roots()[source] if source >= 0 else None
        valid_parent = source >= 0 and (self._same_path(current, root) or self._is_accessible_managed_folder(current, source))
        if not current.is_dir() or not valid_parent:
            self._management_status = "Open an output category or a folder created in KFPS first."
            self.changed.emit()
            return False
        if self._folder_display_name_exists(current, display_name):
            self._management_status = f"A folder named {display_name} already exists here."
            self.changed.emit()
            return False
        target = self._folder_storage_target(current, display_name)
        try:
            target.mkdir()
            self._write_folder_marker(target, display_name)
        except OSError as exc:
            try:
                target.rmdir()
            except OSError:
                pass
            self._management_status = f"Could not create {target.name}: {exc}"
            self.log.append(self._management_status, "error")
            self.changed.emit()
            return False
        self._management_status = f"Created folder {display_name}."
        self._refresh_folder_model(force=True)
        self._refresh_explorer()
        self.changed.emit()
        return True

    @staticmethod
    def _remap_path_reference(value, source, target):
        if not value:
            return value
        try:
            path = os.path.abspath(os.fspath(value))
            source_path = os.path.abspath(os.fspath(source))
            target_path = os.path.abspath(os.fspath(target))
            path_key = os.path.normcase(path)
            source_key = os.path.normcase(source_path)
            if path_key == source_key:
                return target_path
            if path_key.startswith(source_key.rstrip(os.sep) + os.sep):
                return os.path.normpath(os.path.join(target_path, os.path.relpath(path, source_path)))
            return value
        except (OSError, TypeError, ValueError):
            return value

    def _remap_entry_references(self, source, target):
        self._remap_entry_references_batch([(source, target)])

    def _prepare_preview_transfers(self, source, source_index):
        prepare = getattr(self.preview, "prepare_managed_preview_transfer", None)
        if not callable(prepare):
            return []
        source = Path(source)
        source_name = self._source_names()[source_index]
        if source.is_file():
            candidates = [source]
        else:
            source_key = self._fast_path_key(source)
            candidates = [
                Path(str(row.get("path") or ""))
                for cached in self._source_index_cache.values()
                for row in cached.get("rows", [])
                if row.get("path")
                and (
                    self._fast_path_key(row.get("path")) == source_key
                    or self._fast_path_key(row.get("path")).startswith(source_key + os.sep)
                )
            ]
        transfers = []
        for json_path in candidates:
            try:
                state = prepare(json_path, source_name)
            except Exception as exc:
                self.log.append(f"Could not preserve the thumbnail cache for {json_path}: {exc}", "warning")
                continue
            if state:
                transfers.append((str(json_path), state))
        return transfers

    def _complete_preview_transfers(self, transfers, source, target, target_source, move):
        complete = getattr(self.preview, "complete_managed_preview_transfer", None)
        if not callable(complete):
            return {}
        preview_urls = {}
        for old_json, state in transfers:
            new_json = self._remap_path_reference(old_json, source, target)
            try:
                preview_url = complete(state, new_json, target_source, move=move)
            except Exception as exc:
                self.log.append(f"Could not transfer the cached thumbnail for {new_json}: {exc}", "warning")
                continue
            if preview_url:
                preview_urls[self._preview_key(new_json)] = str(preview_url)
        return preview_urls

    def _remap_cached_output_rows(self, mappings, preview_urls, copy):
        additions = {}
        for source_index, cached in self._source_index_cache.items():
            retained = []
            for row in cached.get("rows", []):
                old_path = str(row.get("path") or "")
                new_path = old_path
                for source, target in mappings:
                    candidate = self._remap_path_reference(old_path, source, target)
                    if candidate != old_path:
                        new_path = candidate
                        break
                if new_path == old_path:
                    retained.append(row)
                    continue
                if copy:
                    retained.append(row)
                target_path = Path(new_path)
                target_source = self._managed_source_for_path(target_path)
                try:
                    stat = target_path.stat()
                except OSError:
                    continue
                new_row = dict(row)
                new_row.update({
                    "name": target_path.name,
                    "path": str(target_path),
                    "folder": str(target_path.parent),
                    "mtime": stat.st_mtime,
                    "mtimeNs": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "source": target_source,
                    "previewUrl": str(preview_urls.get(self._preview_key(target_path)) or ""),
                })
                additions.setdefault(target_source, []).append(new_row)
            cached["rows"] = retained

        for source_index, rows in additions.items():
            if source_index < 0:
                continue
            cached = self._source_index_cache.setdefault(source_index, self._empty_source_index(source_index))
            by_key = {self._preview_key(row.get("path")): row for row in cached.get("rows", [])}
            for row in rows:
                by_key[self._preview_key(row.get("path"))] = row
            cached["rows"] = list(by_key.values())

        for cached in self._source_index_cache.values():
            cached["rowsByKey"] = {
                self._preview_key(row.get("path")): row
                for row in cached.get("rows", [])
            }
        current_rows = list(self._current_source_index().get("rows", []))
        self._all_file_rows = current_rows
        query = self._search_query.casefold()
        self._visible_file_rows = self._sort_json_rows([
            row for row in current_rows
            if not query or self._row_matches_search(row, query)
        ])
        self._file_model.replace(self._visible_file_rows)

    def _remap_entry_references_batch(self, mappings):
        mappings = list(mappings)

        def remap(value):
            result = value
            for source, target in mappings:
                updated = self._remap_path_reference(result, source, target)
                if updated != result:
                    return updated
            return result

        self._current_folder = remap(self._current_folder)
        self._back_history = [remap(value) for value in self._back_history]
        self._forward_history = [remap(value) for value in self._forward_history]
        self._clipboard_paths = [remap(value) for value in self._clipboard_paths]
        self._explorer_selection = [remap(value) for value in self._explorer_selection]
        self._explorer_selection_keys = {self._preview_key(value) for value in self._explorer_selection}
        self._selection_anchor_path = remap(self._selection_anchor_path)
        selected = remap(self._selected_path)
        if selected != self._selected_path:
            self._selected_path = selected
            if Path(selected).is_file():
                self._select_path(selected, log=False, queue_preview=False)
            else:
                self.clearSelection()
        self._selection_revision += 1

    @staticmethod
    def _rename_path_with_retry(source, target):
        last_error = None
        for attempt in range(5):
            try:
                source.rename(target)
                return
            except PermissionError as exc:
                last_error = exc
                if attempt == 4:
                    break
                time.sleep(0.025 * (attempt + 1))
        raise last_error

    @Slot(str, str, result=bool)
    def renameEntry(self, value, requested_name):
        source = Path(str(value or ""))
        if not self._entry_allowed_for_operation(source):
            self._management_status = "That item cannot be renamed from Outputs."
            self.changed.emit()
            return False
        is_folder = source.is_dir()
        source_index = self._managed_source_for_path(source)
        preview_transfers = self._prepare_preview_transfers(source, source_index)
        old_display_name = self._folder_display_name(source) if is_folder else source.name
        name = str(requested_name or "").strip()
        if not is_folder and not name.casefold().endswith(".json"):
            name += ".json"
        error = self._name_error(name)
        if error:
            self._management_status = error
            self.changed.emit()
            return False
        if is_folder:
            if old_display_name == name:
                self._management_status = "The name is unchanged."
                self.changed.emit()
                return False
            if self._folder_display_name_exists(source.parent, name, exclude=source):
                self._management_status = f"A folder named {name} already exists here."
                self.changed.emit()
                return False
            target = self._folder_storage_target(source.parent, name, exclude=source)
        else:
            target = source.with_name(name)
        same_location = os.path.normcase(str(source.absolute())) == os.path.normcase(str(target.absolute()))
        if not is_folder and same_location and source.name == target.name:
            self._management_status = "The name is unchanged."
            self.changed.emit()
            return False
        if target.exists() and not same_location:
            self._management_status = f"{target.name} already exists in this folder."
            self.changed.emit()
            return False
        moved = False
        try:
            if same_location:
                if source.name != target.name:
                    temporary = source.with_name(f".kfps-rename-{time.time_ns()}")
                    self._rename_path_with_retry(source, temporary)
                    self._rename_path_with_retry(temporary, target)
                    moved = True
            else:
                self._rename_path_with_retry(source, target)
                moved = True
            if is_folder:
                self._write_folder_marker(target, name)
        except OSError as exc:
            if moved and target.exists() and not source.exists():
                try:
                    self._rename_path_with_retry(target, source)
                except OSError:
                    pass
            self._management_status = f"Could not rename {old_display_name}: {exc}"
            self.log.append(self._management_status, "error")
            self.changed.emit()
            return False
        if moved:
            target_source = self._managed_source_for_path(target)
            preview_urls = self._complete_preview_transfers(
                preview_transfers,
                source,
                target,
                self._source_names()[target_source],
                move=True,
            )
            self._remap_cached_output_rows([(str(source), str(target))], preview_urls, copy=False)
            self._remap_entry_references(source, target)
        self._management_status = f"Renamed {old_display_name} to {name}."
        self._refresh_after_file_operations([source, target])
        return True

    @Slot(str, result=bool)
    def deleteEntry(self, value):
        return self._delete_output_entries([value]) > 0

    def _delete_output_entries(self, values):
        requested = []
        seen = set()
        for value in values:
            if not self._entry_allowed_for_operation(value):
                continue
            path = Path(value)
            key = self._preview_key(path)
            if key in seen:
                continue
            seen.add(key)
            requested.append(path)
        requested.sort(key=lambda path: len(path.parts))
        targets = []
        target_folders = []
        for path in requested:
            if any(self._path_is_within(path, parent) for parent in target_folders):
                continue
            targets.append(path)
            if path.is_dir():
                target_folders.append(path)

        if not targets:
            self._management_status = "That item cannot be deleted from Outputs."
            self.changed.emit()
            return 0

        deleted = []
        failures = []
        deleted_jsons = []
        affected = []
        remove_preview = getattr(self.preview, "remove_managed_preview_for_json", None)

        for source in targets:
            source_index = self._managed_source_for_path(source)
            source_name = self._source_names()[source_index]
            is_folder = source.is_dir()
            display_name = self._folder_display_name(source) if is_folder else source.name
            if is_folder:
                try:
                    json_paths = [path for path in source.rglob("*.json") if path.is_file()]
                except OSError:
                    json_paths = []
            else:
                json_paths = [source]
            try:
                if is_folder:
                    shutil.rmtree(source)
                else:
                    source.unlink()
            except OSError as exc:
                failures.append(display_name)
                self.log.append(f"Could not delete {display_name}: {exc}", "error")
                continue

            deleted.append((source, is_folder, display_name, source_index))
            deleted_jsons.extend((json_path, source_name) for json_path in json_paths)
            affected.extend((source, source.parent))

        for json_path, source_name in deleted_jsons:
            if not callable(remove_preview):
                break
            try:
                remove_preview(json_path, source_name)
            except Exception as exc:
                self.log.append(f"Could not remove the managed thumbnail for {json_path}: {exc}", "warning")

        def was_deleted(path_value):
            if not path_value:
                return False
            return any(
                self._same_path(path_value, source)
                or (is_folder and self._path_is_within(path_value, source))
                for source, is_folder, display_name, source_index in deleted
            )

        if was_deleted(self._current_folder):
            deleted_parent = next(
                source.parent for source, is_folder, display_name, source_index in deleted
                if self._same_path(self._current_folder, source)
                or (is_folder and self._path_is_within(self._current_folder, source))
            )
            self._current_folder = str(deleted_parent.resolve())
        self._back_history = [path for path in self._back_history if not was_deleted(path)]
        self._forward_history = [path for path in self._forward_history if not was_deleted(path)]
        self._clipboard_paths = [path for path in self._clipboard_paths if not was_deleted(path)]
        if not self._clipboard_paths:
            self._clipboard_cut = False
        previous_selection_keys = set(self._explorer_selection_keys)
        self._explorer_selection = [path for path in self._explorer_selection if not was_deleted(path)]
        self._explorer_selection_keys = {self._preview_key(path) for path in self._explorer_selection}
        self._sync_explorer_selection_model(previous_selection_keys)
        if was_deleted(self._selection_anchor_path):
            self._selection_anchor_path = ""
        if was_deleted(self._selected_path):
            self.clearSelection()

        deleted_keys = {self._preview_key(path) for path, source_name in deleted_jsons}
        self._preview_queue = [item for item in self._preview_queue if not was_deleted(item[0])]
        self._preview_queued.difference_update(deleted_keys)
        self._preview_empty.difference_update(deleted_keys)
        for source_index in {item[3] for item in deleted}:
            cached = self._source_index_cache.get(source_index, {})
            cached_rows = [row for row in cached.get("rows", []) if not was_deleted(row.get("path"))]
            cached["rows"] = cached_rows
            cached["rowsByKey"] = {self._preview_key(row.get("path")): row for row in cached_rows}
        if any(source_index == self._source for source, is_folder, display_name, source_index in deleted):
            self._all_file_rows = [row for row in self._all_file_rows if not was_deleted(row.get("path"))]
            self._apply_search_filter()

        deleted_count = len(deleted)
        if deleted_count and not failures:
            if deleted_count == 1:
                source, is_folder, display_name, source_index = deleted[0]
                self._management_status = f"Deleted {'folder' if is_folder else 'JSON'} {display_name}."
            else:
                self._management_status = f"Deleted {deleted_count} items."
        elif deleted_count:
            self._management_status = f"Deleted {deleted_count}; {len(failures)} could not be deleted."
        else:
            self._management_status = f"No items were deleted. {len(failures)} could not be deleted."
        self._selection_revision += 1
        self._refresh_after_file_operations(affected or targets)
        return deleted_count

    @staticmethod
    def _unique_copy_target(folder, name):
        folder = Path(folder)
        candidate = folder / name
        if not candidate.exists():
            return candidate
        original = Path(name)
        stem = original.stem if original.suffix else original.name
        suffix = original.suffix
        candidate = folder / f"{stem} - Copy{suffix}"
        index = 2
        while candidate.exists():
            candidate = folder / f"{stem} - Copy ({index}){suffix}"
            index += 1
        return candidate

    @Slot()
    def pasteIntoCurrentFolder(self):
        self.pasteIntoFolder(self._current_folder)

    @Slot(str)
    def pasteIntoFolder(self, value):
        destination = Path(str(value or self._current_folder))
        destination_source = self._managed_source_for_path(destination)
        if not self._clipboard_paths:
            self._management_status = "Nothing has been copied or cut yet."
            self.changed.emit()
            return
        destination_root = self._source_roots()[destination_source] if destination_source >= 0 else None
        valid_destination = destination_source >= 0 and (
            self._same_path(destination, destination_root) or self._is_accessible_managed_folder(destination, destination_source)
        )
        if not destination.is_dir() or not valid_destination:
            self._management_status = "Choose an output category or a folder created in KFPS before pasting."
            self.changed.emit()
            return

        was_cut = self._clipboard_cut
        succeeded = []
        preview_urls = {}
        failed = []
        affected = [destination]
        for raw_source in list(self._clipboard_paths):
            source = Path(raw_source)
            if not self._entry_allowed_for_operation(source):
                failed.append(source.name or raw_source)
                continue
            if source.is_dir() and (self._same_path(source, destination) or self._path_is_within(destination, source)):
                failed.append(source.name)
                continue
            if was_cut and self._same_path(source.parent, destination):
                failed.append(source.name)
                continue
            is_folder = source.is_dir()
            source_index = self._managed_source_for_path(source)
            preview_transfers = self._prepare_preview_transfers(source, source_index)
            if is_folder:
                display_name = self._unique_folder_display_name(destination, self._folder_display_name(source))
                target = self._folder_storage_target(destination, display_name)
            else:
                display_name = source.name
                target = self._unique_copy_target(destination, source.name)
            try:
                if was_cut:
                    shutil.move(str(source), str(target))
                elif is_folder:
                    shutil.copytree(source, target, symlinks=True)
                else:
                    shutil.copy2(source, target)
                if is_folder:
                    self._write_folder_marker(target, display_name)
                succeeded.append((str(source), str(target)))
                preview_urls.update(self._complete_preview_transfers(
                    preview_transfers,
                    source,
                    target,
                    self._source_names()[destination_source],
                    move=was_cut,
                ))
                affected.extend((source, target))
            except OSError as exc:
                failed.append(display_name)
                if is_folder and target.exists():
                    try:
                        if was_cut and not source.exists():
                            shutil.move(str(target), str(source))
                        elif not was_cut:
                            shutil.rmtree(target)
                    except OSError:
                        pass
                self.log.append(f"Could not paste {source} into {destination}: {exc}", "error")

        if was_cut:
            moved_keys = {self._preview_key(source) for source, target in succeeded}
            self._clipboard_paths = [path for path in self._clipboard_paths if self._preview_key(path) not in moved_keys]
            if not self._clipboard_paths:
                self._clipboard_cut = False
            self._clear_explorer_selection(emit=False)
            if self._selected_path and self._preview_key(self._selected_path) in moved_keys:
                self.clearSelection()
            self._remap_entry_references_batch(succeeded)
        if succeeded:
            self._remap_cached_output_rows(succeeded, preview_urls, copy=not was_cut)
        action = "Moved" if was_cut else "Copied"
        if succeeded and not failed:
            noun = "item" if len(succeeded) == 1 else "items"
            self._management_status = f"{action} {len(succeeded)} {noun} into {destination.name}."
        elif succeeded:
            self._management_status = f"{action} {len(succeeded)}; {len(failed)} could not be pasted."
        else:
            self._management_status = f"Nothing was pasted. {len(failed)} item(s) could not be moved or copied."
        self._refresh_after_file_operations(affected)

    def _refresh_after_file_operations(self, paths):
        missing_paths = [Path(path) for path in paths if path and not Path(path).exists()]
        if missing_paths:
            missing_keys = tuple(self._fast_path_key(path) for path in missing_paths)

            def remains_available(row):
                row_path = row.get("path")
                if not row_path:
                    return False
                row_key = self._fast_path_key(row_path)
                return not any(
                    row_key == missing_key
                    or row_key.startswith(missing_key + os.sep)
                    for missing_key in missing_keys
                )

            for source, cached in self._source_index_cache.items():
                cached_rows = [row for row in cached.get("rows", []) if remains_available(row)]
                cached["rows"] = cached_rows
                cached["rowsByKey"] = {
                    self._preview_key(row.get("path")): row
                    for row in cached_rows
                }
            self._all_file_rows = [row for row in self._all_file_rows if remains_available(row)]
            self._visible_file_rows = [row for row in self._visible_file_rows if remains_available(row)]
            self._file_model.replace(self._visible_file_rows)
        affected_sources = {self._managed_source_for_path(path) for path in paths}
        affected_sources.discard(-1)
        self._refresh_folder_model(force=True)
        self._refresh_explorer()
        for source in affected_sources:
            self._request_source_scan(source, force=True)
        self.log.append(self._management_status, "warning" if "could not" in self._management_status.casefold() else "info")
        self.changed.emit()

    def _clear_explorer_selection(self, emit=True):
        had_selection = bool(self._explorer_selection or self._selection_anchor_path)
        previous_keys = set(self._explorer_selection_keys)
        self._explorer_selection = []
        self._explorer_selection_keys.clear()
        self._selection_anchor_path = ""
        self._sync_explorer_selection_model(previous_keys)
        if had_selection:
            self._selection_revision += 1
            if emit:
                self.changed.emit()

    @Slot()
    def clearExplorerSelection(self):
        self._clear_explorer_selection()

    @Slot()
    def selectAllExplorerEntries(self):
        previous_keys = set(self._explorer_selection_keys)
        self._explorer_selection = [str(row.get("path") or "") for row in self._explorer_rows if row.get("path")]
        self._explorer_selection_keys = {self._preview_key(path) for path in self._explorer_selection}
        self._selection_anchor_path = self._explorer_selection[-1] if self._explorer_selection else ""
        self._sync_explorer_selection_model(previous_keys)
        self._selection_revision += 1
        self.changed.emit()

    @Slot()
    def deleteSelectedEntries(self):
        self._delete_output_entries(self._operation_selection())

    def _apply_search_filter(self):
        query = self._search_query.casefold()
        if query:
            rows = [row for row in self._all_file_rows if self._row_matches_search(row, query)]
        else:
            rows = list(self._all_file_rows)
        self._visible_file_rows = self._sort_json_rows(rows)
        self._file_model.replace(self._visible_file_rows)
        self._refresh_explorer()
        if not self._current_folder:
            if self._selected_path:
                self.clearSelection()
            else:
                self.changed.emit()
            return
        selected = self._selected_path
        if selected and any(self._same_path(row.get("path"), selected) for row in self._visible_file_rows):
            self.changed.emit()
        elif self._visible_file_rows:
            self._select_path(str(self._visible_file_rows[0]["path"]), log=False, queue_preview=False)
        else:
            self.clearSelection()

    @staticmethod
    def _same_path(left, right):
        try:
            return str(Path(str(left)).resolve()).casefold() == str(Path(str(right)).resolve()).casefold()
        except Exception:
            return str(left).casefold() == str(right).casefold()

    @staticmethod
    def _path_is_within(path, root):
        try:
            resolved_path = os.path.normcase(str(Path(path).resolve()))
            resolved_root = os.path.normcase(str(Path(root).resolve()))
            return os.path.commonpath([resolved_path, resolved_root]) == resolved_root
        except (OSError, ValueError):
            return False

    @staticmethod
    def _row_matches_search(row, query):
        terms = [term for term in re.split(r"\s+", query) if term]
        name = str(row.get("displayName") or "")
        file_name = str(row.get("name") or "")
        stem = Path(file_name).stem
        haystack = " ".join([name, file_name, stem]).casefold()
        return all(term in haystack for term in terms)

    def _files(self, root: Path, generated: bool):
        out=[]
        for path in root.rglob("*.json"):
            low=path.name.lower()
            if any(token in low for token in (".report.","settings","metadata","backup","session","probe","manifest")): continue
            managed = any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
            if generated and not (path.parent.name.lower()=="finals" or managed): continue
            out.append(path)
        return out

    def _group(self,name,folder,files):
        modified=max(p.stat().st_mtime for p in files)
        display_name = name
        detail_text = f"{len(files)} JSON" if len(files) == 1 else f"{len(files)} JSONs"
        if files:
            meta, layers, title = self._json_summary(files[0])
            title = meta.get("display_name") or meta.get("title")
            if title:
                display_name = str(title)
            if isinstance(layers, int):
                detail_text = self._count_detail_text(layers, meta)
        return {"name":name,"displayName":display_name,"detailText":detail_text,"path":str(folder),"files":sorted(files,key=lambda p:p.stat().st_mtime,reverse=True),"count":len(files),"modified":modified,"modifiedLabel":self._age(modified)}

    def _sorted_visible_files(self, source, groups):
        if source == 0:
            files = []
            root = self._source_roots()[source]
            for group in sorted(groups, key=lambda item: item["modified"], reverse=True):
                managed = [
                    path for path in group["files"]
                    if path.parent == root or any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
                ]
                generated = [path for path in group["files"] if path not in managed]
                files.extend(sorted(self._dedupe_generated_files(generated), key=lambda path: (self._count(path), path.name.casefold())))
                files.extend(sorted(managed, key=lambda path: (self._count(path), path.name.casefold())))
            return files
        files = [path for group in groups for path in group["files"]]
        return sorted(files, key=lambda path: (path.stat().st_mtime * -1, path.name.casefold()))

    def _dedupe_generated_files(self, files):
        selected = {}
        for path in files:
            key = self._count(path)
            previous = selected.get(key)
            if previous is None or path.stat().st_mtime >= previous.stat().st_mtime:
                selected[key] = path
        return list(selected.values())

    def _row_for_json(self, source, path, retained_previews=None):
        stat = path.stat()
        modified_label = self._age(stat.st_mtime)
        meta, layers, display_name = self._json_summary(path)
        detail = self._count_detail_text(layers, meta)
        preview_url = ""
        if retained_previews:
            cached = retained_previews.get(self._preview_key(path))
            if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                preview_url = cached[2]
        return {
            "name": path.name,
            "displayName": display_name,
            "path": str(path),
            "layers": layers,
            "modifiedLabel": modified_label,
            "previewUrl": preview_url,
            "countDetail": detail,
            "detailText": f"{detail}  •  {modified_label}",
            "folder": str(path.parent),
            "mtime": stat.st_mtime,
            "mtimeNs": stat.st_mtime_ns,
            "size": stat.st_size,
            "source": source,
        }

    @staticmethod
    def _age(ts):
        seconds=max(0,int(time.time()-ts))
        if seconds<60:return "just now"
        if seconds<3600:return f"{seconds//60}m ago"
        if seconds<86400:return f"{seconds//3600}h ago"
        return f"{seconds//86400}d ago"

    @Slot(int)
    def selectGroup(self,index):
        if not 0<=index<len(self._groups): return
        self._selected_group=index; rows=[]
        cached = self._source_index_cache.get(self._source, {})
        rows_by_key = cached.get("rowsByKey", {})
        for path in self._groups[index]["files"]:
            row = rows_by_key.get(self._preview_key(path))
            rows.append(row if row else self._row_for_json(self._source, path))
        self._file_model.replace(rows)
        if rows:
            self.selectPath(str(rows[0]["path"]))
        else:
            self.clearSelection()
        self.changed.emit()

    @staticmethod
    def _count(path):
        match=re.search(r"\.(\d+)v2\.json$",path.name.lower())
        if match:return int(match.group(1))
        try:
            data=json.loads(path.read_text(encoding="utf-8"));
            if isinstance(data,list):return len(data)
            for key in ("shapes","layers","items"):
                if isinstance(data.get(key),list):return len(data[key])
        except Exception: pass
        return 0

    @classmethod
    def _metadata_count_value(cls, meta):
        for key in ("shape_count", "layer_count", "layers"):
            value = meta.get(key)
            if isinstance(value, int):
                return value
            try:
                if value is not None and str(value).strip():
                    return int(value)
            except (TypeError, ValueError):
                pass
        return None

    @classmethod
    def _json_summary(cls, path):
        meta = {}
        layers = None
        manifest = path.with_suffix(".manifest.json")
        try:
            if manifest.is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    meta = dict(data)
                    layers = cls._metadata_count_value(meta)
        except Exception:
            pass
        if layers is None:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    layers = len(data)
                elif isinstance(data, dict):
                    if isinstance(data.get("metadata"), dict):
                        meta = dict(data["metadata"])
                        layers = cls._metadata_count_value(meta)
                    if layers is None:
                        for key in ("shapes","layers","items"):
                            if isinstance(data.get(key),list):
                                layers = len(data[key])
                                break
            except Exception:
                pass
        if layers is None:
            match = re.search(r"\.(\d+)v2\.json$",path.name.lower())
            layers = int(match.group(1)) if match else 0
        meta.setdefault("layers", layers)
        meta.setdefault("layer_count", layers)
        meta.setdefault("shape_count", layers)
        name = meta.get("display_name") or meta.get("title")
        return meta, int(layers), (str(name) if name else path.name)

    @classmethod
    def _metadata_for_json(cls, path):
        return cls._json_summary(path)[0]

    @classmethod
    def _metadata_count(cls, meta, path):
        value = cls._metadata_count_value(meta)
        return value if value is not None else cls._count(path)

    @staticmethod
    def _count_detail_text(layers, meta):
        game = str(meta.get("target_game") or meta.get("game") or "").strip().lower()
        if game in {"fm", "fm8"}:
            return f"FM8  •  {int(layers)} shapes"
        return f"{int(layers)} layers"

    @classmethod
    def _display_name_for_json(cls, path, meta=None):
        meta = meta or cls._metadata_for_json(path)
        name = meta.get("display_name") or meta.get("title")
        return str(name) if name else path.name

    @Slot(int)
    def selectFile(self,index):
        row=self._file_model.row(index)
        if row:self.selectPath(str(row["path"]))

    @Slot(str)
    def selectPath(self,value):
        self._select_path(value, log=True)

    def _select_path(self, value, log=True, queue_preview=True, emit=True):
        path=Path(value)
        if not path.is_file():return
        source_name,row=self._source_name_for_preview_path(path)
        self._selected_path=str(path.resolve())
        self._selected_display_name=str(row.get("displayName") if row else self._display_name_for_json(path))
        self._layers=str(row.get("layers") if row else self._count(path))
        self._folder=str(row.get("folder") if row else path.parent)
        self._preview_url=str(row.get("previewUrl") if row and row.get("previewUrl") else self._existing_preview_for_json(path, source_name))
        if emit:
            self.changed.emit()
        if queue_preview and not self._preview_url:
            self._enqueue_preview_path(path, source_name, priority=True)
        if log:
            self.log.append(f"Selected JSON: {self._selected_path}")

    def _existing_preview_for_json(self, path, source_name):
        existing = getattr(self.preview, "existing_preview_for_json", None)
        if callable(existing):
            return existing(path, source_name)
        return ""

    @staticmethod
    def _preview_key(path):
        return JsonService._fast_path_key(path)

    def _source_name_for_preview_path(self, path):
        key = self._preview_key(path)
        for source, cached in self._source_index_cache.items():
            row = cached.get("rowsByKey", {}).get(key)
            if row:
                return self._source_names()[source], row
        return self._source_names()[self._source], None

    @Slot(str)
    def requestPreview(self, value):
        if not value:
            return
        path = Path(value)
        if not path.is_file():
            return
        key = self._preview_key(path)
        if key in self._preview_empty:
            return
        source_name, row = self._source_name_for_preview_path(path)
        if row and row.get("previewUrl"):
            return
        self._enqueue_preview_path(path, source_name, priority=False, start=True, check_existing=True)

    def _enqueue_preview_path(self, path, source_name=None, priority=False, start=True, check_existing=True):
        if not path:
            return
        path = Path(path)
        if not path.is_file():
            return
        key = self._preview_key(path)
        if key in self._preview_empty and not priority:
            return
        source_name = source_name or self._source_names()[self._source]
        if check_existing:
            existing = self._existing_preview_for_json(path, source_name)
            if existing:
                self._update_preview_url(str(path), existing)
                return
        if key in self._preview_queued:
            return
        if not priority and len(self._preview_queue) >= 48:
            return
        item = (str(path), source_name)
        if priority:
            self._preview_queue.insert(0, item)
        else:
            self._preview_queue.append(item)
        self._preview_queued.add(key)
        if start:
            self._pump_preview_queue()

    def _pump_preview_queue(self):
        if self._preview_running or not self._preview_queue:
            return
        path, source_name = self._preview_queue.pop(0)
        self._preview_running = True
        future = self._preview_executor.submit(self.preview.preview_for_json, path, source_name)
        future.add_done_callback(lambda done, item=path, source=source_name: self._previewReady.emit(item, source, self._preview_result(done)))

    @staticmethod
    def _preview_result(future):
        try:
            return str(future.result() or "")
        except Exception:
            return ""

    @Slot(str, str, str)
    def _apply_preview_result(self, path, source_name, preview_url):
        self._preview_running = False
        self._preview_queued.discard(self._preview_key(path))
        if preview_url:
            self._update_preview_url(path, preview_url)
        else:
            self._preview_empty.add(self._preview_key(path))
        QTimer.singleShot(180, self._pump_preview_queue)

    def _update_preview_url(self, path, preview_url):
        if not preview_url:
            return
        preview_key = self._preview_key(path)
        for cached in self._source_index_cache.values():
            for row in cached.get("rows", []):
                if self._same_path(row.get("path"), path):
                    row["previewUrl"] = preview_url
        for row in self._all_file_rows:
            if self._same_path(row.get("path"), path):
                row["previewUrl"] = preview_url
        visible_index = -1
        for index, row in enumerate(self._visible_file_rows):
            if self._same_path(row.get("path"), path):
                row["previewUrl"] = preview_url
                visible_index = index
        if visible_index >= 0:
            self._file_model.set_row_value(visible_index, "previewUrl", preview_url)
        self._set_explorer_preview_url(preview_key, preview_url)
        if self._selected_path and self._same_path(self._selected_path, path):
            self._preview_url = preview_url
            self.changed.emit()

    def _set_explorer_preview_url(self, preview_key, preview_url):
        index = self._explorer_index_by_key.get(preview_key, -1)
        if not 0 <= index < len(self._explorer_rows):
            return
        row = self._explorer_rows[index]
        if row.get("isFolder") or row.get("previewUrl") == preview_url:
            return
        row["previewUrl"] = preview_url
        self._explorer_model.set_row_value(index, "previewUrl", preview_url)

    def _clear_selection(self, emit=True):
        self._selected_path = ""
        self._selected_display_name = ""
        self._preview_url = ""
        self._layers = "—"
        self._folder = "—"
        if emit:
            self.changed.emit()

    @Slot()
    def clearSelection(self):
        self._clear_selection(emit=True)

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if value is None or isinstance(value, bool):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_fd6_payload(payload):
        return isinstance(payload, dict) and str(payload.get("format") or "").strip().lower() == FD6_FORMAT

    @staticmethod
    def _fd6_color(value):
        if isinstance(value, dict):
            raw = [value.get("r"), value.get("g"), value.get("b"), value.get("a", 255)]
        elif isinstance(value, (list, tuple)):
            raw = list(value[:4])
            if len(raw) == 3:
                raw.append(255)
        else:
            return None
        if len(raw) != 4:
            return None
        try:
            nums = [float(item) for item in raw]
        except (TypeError, ValueError):
            return None
        if all(0.0 <= item <= 1.0 for item in nums):
            nums = [item * 255.0 for item in nums]
        return [max(0, min(255, int(round(item)))) for item in nums]

    @classmethod
    def _fd6_shape_bounds(cls, shape):
        if not isinstance(shape, dict):
            return None
        kind = str(shape.get("type") or "").strip().lower()
        x = cls._safe_float(shape.get("x"), None)
        y = cls._safe_float(shape.get("y"), None)
        if x is None or y is None:
            return None
        if kind == "circle":
            r = abs(cls._safe_float(shape.get("r"), 0.0))
            return x - r, y - r, x + r, y + r
        if kind in {"ellipse", "rotated_ellipse"}:
            rx = abs(cls._safe_float(shape.get("rx"), 0.0))
            ry = abs(cls._safe_float(shape.get("ry"), 0.0))
            radius = max(rx, ry) if kind == "rotated_ellipse" else None
            return (x - radius, y - radius, x + radius, y + radius) if radius else (x - rx, y - ry, x + rx, y + ry)
        if kind in {"rectangle", "rotated_rectangle"}:
            hw = abs(cls._safe_float(shape.get("hw"), 0.0))
            hh = abs(cls._safe_float(shape.get("hh"), 0.0))
            radius = (hw * hw + hh * hh) ** 0.5 if kind == "rotated_rectangle" else None
            return (x - radius, y - radius, x + radius, y + radius) if radius else (x - hw, y - hh, x + hw, y + hh)
        return None

    @classmethod
    def _fd6_conversion_center(cls, payload, shapes):
        size = payload.get("image_size") if isinstance(payload, dict) else None
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            width = cls._safe_float(size[0], 0.0)
            height = cls._safe_float(size[1], 0.0)
            if width > 0 and height > 0:
                return width / 2.0, height / 2.0, "image_center"
        bounds = [item for item in (cls._fd6_shape_bounds(shape) for shape in shapes) if item]
        if bounds:
            min_x = min(item[0] for item in bounds); min_y = min(item[1] for item in bounds)
            max_x = max(item[2] for item in bounds); max_y = max(item[3] for item in bounds)
            return (min_x + max_x) / 2.0, (min_y + max_y) / 2.0, "bounds_center"
        return 0.0, 0.0, "zero"

    @staticmethod
    def _round_fd6(value):
        rounded = round(float(value), 6)
        return 0.0 if rounded == -0.0 else rounded

    @classmethod
    def _convert_fd6_payload(cls, payload, source):
        shapes = payload.get("shapes") if isinstance(payload, dict) else None
        if not isinstance(shapes, list) or not shapes:
            raise ValueError("FD6 JSON must contain a non-empty shapes list.")
        center_x, center_y, origin = cls._fd6_conversion_center(payload, shapes)
        converted = []
        skipped = 0
        for index, shape in enumerate(shapes):
            if not isinstance(shape, dict):
                skipped += 1
                continue
            kind = str(shape.get("type") or "").strip().lower()
            color = cls._fd6_color(shape.get("color"))
            if not color or color[3] <= 0:
                skipped += 1
                continue
            x = cls._safe_float(shape.get("x"), None)
            y = cls._safe_float(shape.get("y"), None)
            angle = cls._safe_float(shape.get("angle"), 0.0)
            type_code = None
            type_word = None
            scale_x = None
            scale_y = None
            resource_index = None
            if kind == "circle":
                radius = abs(cls._safe_float(shape.get("r"), 0.0))
                scale_x = radius / FD6_ELLIPSE_DIVISOR
                scale_y = radius / FD6_ELLIPSE_DIVISOR
                type_code = KFPS_ELLIPSE_TYPE
                type_word = KFPS_ELLIPSE_WORD
                resource_index = 2
            elif kind in {"ellipse", "rotated_ellipse"}:
                scale_x = abs(cls._safe_float(shape.get("rx"), 0.0)) / FD6_ELLIPSE_DIVISOR
                scale_y = abs(cls._safe_float(shape.get("ry"), 0.0)) / FD6_ELLIPSE_DIVISOR
                type_code = KFPS_ELLIPSE_TYPE
                type_word = KFPS_ELLIPSE_WORD
                resource_index = 2
            elif kind in {"rectangle", "rotated_rectangle"}:
                scale_x = abs(cls._safe_float(shape.get("hw"), 0.0)) * 2.0 / FD6_RECTANGLE_DIVISOR
                scale_y = abs(cls._safe_float(shape.get("hh"), 0.0)) * 2.0 / FD6_RECTANGLE_DIVISOR
                type_code = KFPS_RECTANGLE_TYPE
                type_word = KFPS_RECTANGLE_WORD
                resource_index = 1
            if x is None or y is None or type_code is None or not scale_x or not scale_y:
                skipped += 1
                continue
            converted.append({
                "type": type_code,
                "type_word": type_word,
                "data": [
                    cls._round_fd6(x - center_x),
                    cls._round_fd6(-(y - center_y)),
                    cls._round_fd6(scale_x),
                    cls._round_fd6(scale_y),
                    cls._round_fd6((360.0 - angle) % 360.0),
                    0,
                    0,
                ],
                "color": color,
                "resource_family": "Primitives",
                "resource_index": resource_index,
                "source_format": FD6_FORMAT,
                "fd6_type": kind,
                "fd6_source_index": index,
            })
        if not converted:
            raise ValueError("FD6 JSON did not contain any supported visible shapes.")
        display_name = f"{Path(source).stem} (FD6 converted)"
        metadata = {
            "title": display_name,
            "display_name": display_name,
            "source_format": FD6_FORMAT,
            "source_file": Path(source).name,
            "fd6_source_image": payload.get("source_image") or "",
            "fd6_profile": payload.get("profile") or "",
            "fd6_generated_at": payload.get("generated_at") or "",
            "fd6_sticker_mode": bool(payload.get("sticker_mode", False)),
            "fd6_origin": origin,
            "fd6_offset": [cls._round_fd6(center_x), cls._round_fd6(center_y)],
            "conversion": "fd6.shapes->kfps.typecode.v1",
            "target_game": "fh6",
            "layers": len(converted),
            "layer_count": len(converted),
            "shape_count": len(converted),
            "skipped_shapes": skipped,
        }
        return {"format": "kfps.fd6.converted.v1", "metadata": metadata, "shapes": converted}, len(converted), skipped

    @staticmethod
    def _unique_json_target(root, name):
        stem = safe_file_part(Path(name).stem, "manual-json")
        suffix = Path(name).suffix or ".json"
        target = root / f"{stem}{suffix}"
        n = 2
        while target.exists():
            target = root / f"{stem} ({n}){suffix}"
            n += 1
        return target

    @Slot()
    def browseManual(self):
        src=self.desktop.chooseJson()
        if not src:return
        try:
            root=self.paths.exported_root; root.mkdir(parents=True,exist_ok=True); source=Path(src)
            payload = None
            try:
                payload = json.loads(source.read_text(encoding="utf-8-sig"))
            except Exception:
                payload = None
            if self._is_fd6_payload(payload):
                converted, count, skipped = self._convert_fd6_payload(payload, source)
                target = self._unique_json_target(root, f"{source.stem}.fd6-converted.json")
                target.write_text(json.dumps(converted, indent=2) + "\n", encoding="utf-8")
                self.setSource(2); self.refresh(); self.selectPath(str(target))
                suffix = f"; skipped {skipped}" if skipped else ""
                self.log.append(f"Converted FD6 JSON to KFPS Exported: {target} ({count} shapes{suffix})")
            else:
                target=self._unique_json_target(root, source.name)
                shutil.copy2(source,target); self.setSource(2); self.refresh(); self.selectPath(str(target)); self.log.append(f"Copied manual JSON to Exported: {target}")
        except Exception as exc:self.log.append(f"Manual JSON copy failed: {exc}","error")

    @Slot()
    def refreshRecent(self):
        self._refresh_recent_from_cache()
        self.warmIndex()

    def _refresh_recent_from_cache(self):
        rows=[]
        for source, label in ((0, "Generated"), (1, "Editor"), (2, "Exported")):
            index = self._source_index_cache.get(source)
            if not index:
                continue
            for row in index.get("rows", []):
                rows.append({
                    "name": row.get("displayName") or row.get("name") or Path(str(row.get("path") or "")).name,
                    "path": row.get("path", ""),
                    "folder": row.get("folder", ""),
                    "age": self._age(float(row.get("mtime") or 0)),
                    "source": label,
                    "mtime": float(row.get("mtime") or 0),
                })
        rows.sort(key=lambda r:r["mtime"],reverse=True)
        if self.demo and not rows:
            rows=[
                {"name":"FH6_KS_2024_Supra.json","path":"D:/KFPS/projects/FH6/FH6_KS_2024_Supra.json","folder":"D:/KFPS/projects/FH6/","age":"2m ago","source":"Generated"},
                {"name":"FH5_M3_GTR_Livery.json","path":"D:/KFPS/projects/FH5/FH5_M3_GTR_Livery.json","folder":"D:/KFPS/projects/FH5/","age":"1h ago","source":"Exported"},
                {"name":"FM8_Porsche_911_GT3.json","path":"D:/KFPS/projects/FM8/FM8_Porsche_911_GT3.json","folder":"D:/KFPS/projects/FM8/","age":"Yesterday","source":"Editor"},
            ]
        self._recent_model.replace([{k:r[k] for k in ("name","path","folder","age","source")} for r in rows[:3]])
