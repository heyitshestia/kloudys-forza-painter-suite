from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService
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


class JsonService(QObject):
    changed = Signal()
    _previewReady = Signal(int, str, str)

    def __init__(self, paths: AppPaths, preview: PreviewService, desktop: DesktopService, log: LogService, demo=False, parent=None):
        super().__init__(parent); self.paths = paths; self.preview = preview; self.desktop = desktop; self.log = log; self.demo = demo
        self._group_model = DictListModel(["name","displayName","detailText","path","count","modifiedLabel"])
        self._file_model = DictListModel(["name","displayName","path","layers","modifiedLabel","previewUrl","detailText","folder"])
        self._recent_model = DictListModel(["name","path","folder","age","source"])
        self._source = 0; self._selected_group = -1; self._selected_path = ""; self._selected_display_name = ""; self._preview_url = ""; self._layers = "—"; self._folder = "—"
        self._search_query = ""
        self._all_file_rows: list[dict] = []
        self._visible_file_rows: list[dict] = []
        self._groups: list[dict] = []
        self._preview_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="json-preview")
        self._preview_queue: list[tuple[str, str]] = []
        self._preview_queued: set[str] = set()
        self._preview_running = False
        self._preview_generation = 0
        self._previewReady.connect(self._apply_preview_result)
        self._ensure_logo(); self.refresh(); self.refreshRecent()


    @Property(QObject, constant=True)
    def groupModel(self): return self._group_model
    @Property(QObject, constant=True)
    def fileModel(self): return self._file_model
    @Property(QObject, constant=True)
    def recentModel(self): return self._recent_model

    @Property(int, notify=changed)
    def sourceIndex(self): return self._source
    @Property(str, notify=changed)
    def selectedPath(self): return self._selected_path
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
    @Property(int, notify=changed)
    def outputCount(self): return len(self._all_file_rows)
    @Property(int, notify=changed)
    def visibleOutputCount(self): return len(self._visible_file_rows)
    @Property(str, notify=changed)
    def searchSummary(self):
        total = len(self._all_file_rows)
        visible = len(self._visible_file_rows)
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
    def setSource(self, index): self._source = max(0,min(len(self._source_roots()) - 1,index)); self._selected_group=-1; self.clearSelection(); self.refresh(); self.changed.emit()

    @Slot(str)
    def setSearchQuery(self, value):
        query = str(value or "").strip()
        if query == self._search_query:
            return
        self._search_query = query
        self._apply_search_filter()

    @Slot()
    def clearSearch(self): self.setSearchQuery("")

    @Slot()
    def refresh(self):
        root = self._root(); root.mkdir(parents=True, exist_ok=True)
        groups = []
        if self._source == 0:
            for folder in root.iterdir():
                if folder.is_dir():
                    files = self._files(folder, generated=True)
                    if files: groups.append(self._group(folder.name, folder, files))
        else:
            grouped = {}
            for path in self._files(root, generated=False): grouped.setdefault(path.parent, []).append(path)
            for folder, files in grouped.items(): groups.append(self._group(str(folder.relative_to(root)) if folder != root else root.name, folder, files))
        groups.sort(key=lambda g:g["modified"], reverse=True)
        self._groups=groups
        self._group_model.replace([{k:g[k] for k in ("name","displayName","detailText","path","count","modifiedLabel")} for g in groups])
        self._all_file_rows = [self._row_for_json(path) for path in self._sorted_visible_files(groups)]
        self._apply_search_filter()

    def _apply_search_filter(self):
        query = self._search_query.casefold()
        if query:
            rows = [row for row in self._all_file_rows if self._row_matches_search(row, query)]
        else:
            rows = list(self._all_file_rows)
        self._visible_file_rows = rows
        self._file_model.replace(rows)
        selected = self._selected_path
        if selected and any(self._same_path(row.get("path"), selected) for row in rows):
            self.changed.emit()
        elif rows:
            self._select_path(str(rows[0]["path"]), log=False, queue_preview=False)
        else:
            self.clearSelection()
        self._start_preview_queue(rows)

    @staticmethod
    def _same_path(left, right):
        try:
            return str(Path(str(left)).resolve()).casefold() == str(Path(str(right)).resolve()).casefold()
        except Exception:
            return str(left).casefold() == str(right).casefold()

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
            if generated and not (path.parent.name.lower()=="finals" and low.endswith("v2.json")): continue
            out.append(path)
        return out

    def _group(self,name,folder,files):
        modified=max(p.stat().st_mtime for p in files)
        display_name = name
        detail_text = f"{len(files)} JSON" if len(files) == 1 else f"{len(files)} JSONs"
        if files:
            meta = self._metadata_for_json(files[0])
            title = meta.get("display_name") or meta.get("title")
            layers = self._metadata_count(meta, files[0])
            if title:
                display_name = str(title)
            if isinstance(layers, int):
                detail_text = self._count_detail_text(layers, meta)
        return {"name":name,"displayName":display_name,"detailText":detail_text,"path":str(folder),"files":sorted(files,key=lambda p:p.stat().st_mtime,reverse=True),"count":len(files),"modified":modified,"modifiedLabel":self._age(modified)}

    def _sorted_visible_files(self, groups):
        if self._source == 0:
            files = []
            for group in sorted(groups, key=lambda item: item["modified"], reverse=True):
                files.extend(sorted(self._dedupe_generated_files(group["files"]), key=lambda path: (self._count(path), path.name.casefold())))
            return files
        files = [path for group in groups for path in group["files"]]
        return sorted(files, key=lambda path: (path.stat().st_mtime * -1, self._display_name_for_json(path).casefold(), self._count(path), path.name.casefold()))

    def _dedupe_generated_files(self, files):
        selected = {}
        for path in files:
            key = self._count(path)
            previous = selected.get(key)
            if previous is None or path.stat().st_mtime >= previous.stat().st_mtime:
                selected[key] = path
        return list(selected.values())

    def _row_for_json(self, path):
        layers = self._count(path)
        modified_label = self._age(path.stat().st_mtime)
        meta = self._metadata_for_json(path)
        detail = self._count_detail_text(layers, meta)
        return {
            "name": path.name,
            "displayName": self._display_name_for_json(path, meta),
            "path": str(path),
            "layers": layers,
            "modifiedLabel": modified_label,
            "previewUrl": self._existing_preview_for_json(path, self._source_names()[self._source]),
            "detailText": f"{detail}  •  {modified_label}",
            "folder": str(path.parent),
        }

    @staticmethod
    def _age(ts):
        import time
        seconds=max(0,int(time.time()-ts))
        if seconds<60:return "just now"
        if seconds<3600:return f"{seconds//60}m ago"
        if seconds<86400:return f"{seconds//3600}h ago"
        return f"{seconds//86400}d ago"

    @Slot(int)
    def selectGroup(self,index):
        if not 0<=index<len(self._groups): return
        self._selected_group=index; rows=[]
        for path in self._groups[index]["files"]:
            rows.append(self._row_for_json(path))
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
    def _metadata_for_json(cls, path):
        manifest = path.with_suffix(".manifest.json")
        try:
            if manifest.is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    result = dict(data)
                    result.setdefault("layers", cls._count(path))
                    result.setdefault("layer_count", result.get("layers"))
                    result.setdefault("shape_count", result.get("layers"))
                    return result
        except Exception:
            pass
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
                result = dict(data["metadata"])
                result.setdefault("layers", cls._count(path))
                result.setdefault("layer_count", result.get("layers"))
                result.setdefault("shape_count", result.get("layers"))
                return result
        except Exception:
            pass
        return {}

    @classmethod
    def _metadata_count(cls, meta, path):
        for key in ("shape_count", "layer_count", "layers"):
            value = meta.get(key)
            if isinstance(value, int):
                return value
            try:
                if value is not None and str(value).strip():
                    return int(value)
            except (TypeError, ValueError):
                pass
        return cls._count(path)

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

    def _select_path(self, value, log=True, queue_preview=True):
        path=Path(value)
        if not path.is_file():return
        source_name=self._source_names()[self._source]
        self._selected_path=str(path.resolve()); self._selected_display_name=self._display_name_for_json(path); self._layers=str(self._count(path)); self._folder=str(path.parent); self._preview_url=self._existing_preview_for_json(path, source_name); self.changed.emit()
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
        try:
            return str(Path(path).resolve()).casefold()
        except Exception:
            return str(path).casefold()

    def _start_preview_queue(self, rows):
        self._preview_generation += 1
        self._preview_queue = []
        self._preview_queued = set()
        source_name = self._source_names()[self._source]
        for row in rows:
            if row.get("previewUrl"):
                continue
            self._enqueue_preview_path(row.get("path"), source_name, priority=False, start=False, check_existing=False)
        self._pump_preview_queue()

    def _enqueue_preview_path(self, path, source_name=None, priority=False, start=True, check_existing=True):
        if not path:
            return
        path = Path(path)
        if not path.is_file():
            return
        source_name = source_name or self._source_names()[self._source]
        if check_existing:
            existing = self._existing_preview_for_json(path, source_name)
            if existing:
                self._update_preview_url(str(path), existing)
                return
        key = self._preview_key(path)
        if key in self._preview_queued:
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
        self._preview_queued.discard(self._preview_key(path))
        generation = self._preview_generation
        self._preview_running = True
        future = self._preview_executor.submit(self.preview.preview_for_json, path, source_name)
        future.add_done_callback(lambda done, gen=generation, item=path: self._previewReady.emit(gen, item, self._preview_result(done)))

    @staticmethod
    def _preview_result(future):
        try:
            return str(future.result() or "")
        except Exception:
            return ""

    @Slot(int, str, str)
    def _apply_preview_result(self, generation, path, preview_url):
        self._preview_running = False
        if generation == self._preview_generation and preview_url:
            self._update_preview_url(path, preview_url)
        QTimer.singleShot(180, self._pump_preview_queue)

    def _update_preview_url(self, path, preview_url):
        if not preview_url:
            return
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
        if self._selected_path and self._same_path(self._selected_path, path):
            self._preview_url = preview_url
            self.changed.emit()

    @Slot()
    def clearSelection(self): self._selected_path=""; self._selected_display_name=""; self._preview_url=""; self._layers="—"; self._folder="—"; self.changed.emit()

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
        rows=[]
        for source,root in (("Generated",self.paths.generated_root),("Editor",self.paths.editor_json_root),("Exported",self.paths.exported_root)):
            if not root.exists():continue
            for path in self._files(root, generated=source=="Generated"):
                try:rows.append({"name":path.name,"path":str(path),"folder":str(path.parent),"age":self._age(path.stat().st_mtime),"source":source,"mtime":path.stat().st_mtime})
                except OSError:pass
        rows.sort(key=lambda r:r["mtime"],reverse=True)
        if self.demo and not rows:
            rows=[
                {"name":"FH6_KS_2024_Supra.json","path":"D:/KFPS/projects/FH6/FH6_KS_2024_Supra.json","folder":"D:/KFPS/projects/FH6/","age":"2m ago","source":"Generated"},
                {"name":"FH5_M3_GTR_Livery.json","path":"D:/KFPS/projects/FH5/FH5_M3_GTR_Livery.json","folder":"D:/KFPS/projects/FH5/","age":"1h ago","source":"Exported"},
                {"name":"FM8_Porsche_911_GT3.json","path":"D:/KFPS/projects/FM8/FM8_Porsche_911_GT3.json","folder":"D:/KFPS/projects/FM8/","age":"Yesterday","source":"Editor"},
            ]
        self._recent_model.replace([{k:r[k] for k in ("name","path","folder","age","source")} for r in rows[:3]])
