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
        self._group_model = DictListModel(["name","path","count","modifiedLabel"])
        self._file_model = DictListModel(["name","path","layers","modifiedLabel"])
        self._recent_model = DictListModel(["name","path","folder","age","source"])
        self._source = 0; self._selected_group = -1; self._selected_path = ""; self._preview_url = ""; self._layers = "—"; self._folder = "—"
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
    def selectedName(self): return Path(self._selected_path).name if self._selected_path else "—"
    @Property(str, notify=changed)
    def selectedLayers(self): return self._layers
    @Property(str, notify=changed)
    def selectedFolder(self): return self._folder

    def _root(self): return [self.paths.generated_root, self.paths.editor_json_root, self.paths.exported_root][self._source]

    def _ensure_logo(self):
        src = self.paths.app_root / "assets" / "app" / "KFPS Logo.json"
        if not src.is_file(): return
        for dest in [self.paths.generated_root / "KFPS Logo" / "finals" / "KFPS Logo.3000v2.json", self.paths.editor_json_root / "KFPS Logo" / "KFPS Logo.json", self.paths.exported_root / "KFPS Logo.json"]:
            try: dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest)
            except Exception: pass

    @Slot(int)
    def setSource(self, index): self._source = max(0,min(2,index)); self._selected_group=-1; self.clearSelection(); self.refresh(); self.changed.emit()

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
        self._groups=groups; self._group_model.replace([{k:g[k] for k in ("name","path","count","modifiedLabel")} for g in groups]); self._file_model.replace([])
        if groups: self.selectGroup(0)

    def _files(self, root: Path, generated: bool):
        out=[]
        for path in root.rglob("*.json"):
            low=path.name.lower()
            if any(token in low for token in (".report.","settings","metadata","backup","session","probe","manifest")): continue
            if generated and not ("v2" in low or path.parent.name.lower()=="finals"): continue
            out.append(path)
        return out

    def _group(self,name,folder,files):
        modified=max(p.stat().st_mtime for p in files)
        return {"name":name,"path":str(folder),"files":sorted(files,key=lambda p:p.stat().st_mtime,reverse=True),"count":len(files),"modified":modified,"modifiedLabel":self._age(modified)}

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
            rows.append({"name":path.name,"path":str(path),"layers":self._count(path),"modifiedLabel":self._age(path.stat().st_mtime)})
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

    @Slot(int)
    def selectFile(self,index):
        row=self._file_model.row(index)
        if row:self.selectPath(str(row["path"]))

    @Slot(str)
    def selectPath(self,value):
        path=Path(value)
        if not path.is_file():return
        source_name=["generated","editor","exported"][self._source]
        self._selected_path=str(path.resolve()); self._layers=str(self._count(path)); self._folder=str(path.parent); self._preview_url=self.preview.preview_for_json(path, source_name); self.changed.emit(); self.log.append(f"Selected JSON: {self._selected_path}")

    @Slot()
    def clearSelection(self): self._selected_path=""; self._preview_url=""; self._layers="—"; self._folder="—"; self.changed.emit()

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
