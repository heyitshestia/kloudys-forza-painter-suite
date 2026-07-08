from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .log_service import LogService
from .models import DictListModel
from .preview_service import PreviewService
from .qt_utils import safe_file_part


class JsonService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, preview: PreviewService, desktop: DesktopService, log: LogService, demo=False, parent=None):
        super().__init__(parent); self.paths = paths; self.preview = preview; self.desktop = desktop; self.log = log; self.demo = demo
        self._group_model = DictListModel(["name","displayName","detailText","path","count","modifiedLabel"])
        self._file_model = DictListModel(["name","displayName","path","layers","modifiedLabel","previewUrl","detailText","folder"])
        self._recent_model = DictListModel(["name","path","folder","age","source"])
        self._source = 0; self._selected_group = -1; self._selected_path = ""; self._selected_display_name = ""; self._preview_url = ""; self._layers = "—"; self._folder = "—"
        self._groups: list[dict] = []
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
        rows = [self._row_for_json(path) for path in self._sorted_visible_files(groups)]
        self._file_model.replace(rows)
        if self._selected_path and any(str(row["path"]) == self._selected_path for row in rows):
            self.selectPath(self._selected_path)
        elif rows:
            self.selectPath(str(rows[0]["path"]))
        else:
            self.clearSelection()

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
            layers = meta.get("layers")
            if title:
                display_name = str(title)
            if isinstance(layers, int):
                detail_text = f"{layers} layers"
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
        return {
            "name": path.name,
            "displayName": self._display_name_for_json(path),
            "path": str(path),
            "layers": layers,
            "modifiedLabel": modified_label,
            "previewUrl": self.preview.preview_for_json(path, self._source_names()[self._source]),
            "detailText": f"{layers} layers  •  {modified_label}",
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
                    return data
        except Exception:
            pass
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
                result = dict(data["metadata"])
                result.setdefault("layers", cls._count(path))
                return result
        except Exception:
            pass
        return {}

    @classmethod
    def _display_name_for_json(cls, path):
        meta = cls._metadata_for_json(path)
        name = meta.get("display_name") or meta.get("title")
        return str(name) if name else path.name

    @Slot(int)
    def selectFile(self,index):
        row=self._file_model.row(index)
        if row:self.selectPath(str(row["path"]))

    @Slot(str)
    def selectPath(self,value):
        path=Path(value)
        if not path.is_file():return
        source_name=self._source_names()[self._source]
        self._selected_path=str(path.resolve()); self._selected_display_name=self._display_name_for_json(path); self._layers=str(self._count(path)); self._folder=str(path.parent); self._preview_url=self.preview.preview_for_json(path, source_name); self.changed.emit(); self.log.append(f"Selected JSON: {self._selected_path}")

    @Slot()
    def clearSelection(self): self._selected_path=""; self._selected_display_name=""; self._preview_url=""; self._layers="—"; self._folder="—"; self.changed.emit()

    @Slot()
    def browseManual(self):
        src=self.desktop.chooseJson()
        if not src:return
        try:
            root=self.paths.exported_root; root.mkdir(parents=True,exist_ok=True); source=Path(src); target=root/source.name; n=2
            while target.exists(): target=root/f"{source.stem} ({n}){source.suffix}"; n+=1
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
