from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .log_service import LogService
from .qt_utils import file_url


class SourceImageService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, desktop: DesktopService, log: LogService, parent=None):
        super().__init__(parent); self.paths = paths; self.desktop = desktop; self.log = log
        self._path = ""; self._paths = []; self._url = ""; self._title = "Source check"; self._message = "Choose an image to get a source check."; self._severity = "neutral"; self._metrics = "No source image selected."; self._heatmap = ""; self._revision = 0

    @Property(str, notify=changed)
    def path(self): return self._path
    @Property("QStringList", notify=changed)
    def queuedPaths(self): return self._paths
    @Property(int, notify=changed)
    def count(self): return len(self._paths)
    @Property(str, notify=changed)
    def summary(self):
        if not self._paths:
            return "No source selected"
        if len(self._paths) == 1:
            return self._path
        return f"{len(self._paths)} source images queued; first: {Path(self._path).name}"
    @Property(str, notify=changed)
    def url(self): return self._url
    @Property(int, notify=changed)
    def revision(self): return self._revision
    @Property(str, notify=changed)
    def reportTitle(self): return self._title
    @Property(str, notify=changed)
    def reportMessage(self): return self._message
    @Property(str, notify=changed)
    def severity(self): return self._severity
    @Property(str, notify=changed)
    def metrics(self): return self._metrics
    @Property(str, notify=changed)
    def heatmapUrl(self): return self._heatmap

    @Slot()
    def choose(self):
        paths = self.desktop.chooseImages()
        if paths:
            self.setPaths(paths)

    @Slot(str)
    def setPath(self, value):
        path = Path(value)
        if not path.is_file(): return
        self.setPaths([str(path)])

    @Slot("QStringList")
    def setPaths(self, values):
        paths = []
        for value in values or []:
            path = Path(value)
            if path.is_file():
                resolved = str(path.resolve())
                if resolved not in paths:
                    paths.append(resolved)
        if not paths:
            return
        first = Path(paths[0])
        self._paths = paths
        self._path = paths[0]
        self._url = file_url(first)
        self._heatmap = ""
        self._revision += 1
        self._analyze(first)
        if len(paths) == 1:
            self.log.append(f"Selected source image: {self._path}")
        else:
            self.log.append(f"Queued {len(paths)} source images for generation.")
        self.changed.emit()

    def _analyze(self, path: Path):
        try:
            from generator_backend import source_sanity_check
            report = source_sanity_check(path)
            metrics = report.get("metrics") or {}
            self._severity = {"ok": "green", "warn": "yellow", "bad": "red"}.get(str(report.get("severity")), "neutral")
            self._title = str(report.get("title") or "Source check")
            self._message = "\n".join(report.get("messages") or [])
            self._metrics = (
                f"File: {path.name}\n"
                f"Resolution: {metrics.get('width', '?')} × {metrics.get('height', '?')}\n"
                f"Megapixels: {float(metrics.get('megapixels') or 0):.2f} MP\n"
                f"Visible area: {float(metrics.get('alpha_coverage') or 0) * 100:.1f}%"
            )
        except Exception as exc:
            self._severity = "red"; self._title = "Source check unavailable"; self._message = str(exc); self._metrics = path.name

    @Slot()
    def buildHeatmap(self):
        if not self._path: return
        try:
            from detail_heatmap import detail_heatmap_preview_bytes
            target = self.paths.runtime_root / "qml-heatmaps" / (Path(self._path).stem + ".heatmap.png")
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(detail_heatmap_preview_bytes(self._path))
            self._heatmap = file_url(target); self.changed.emit(); self.log.append("Source detail heatmap created.")
        except Exception as exc: self.log.append(f"Heatmap preview failed: {exc}", "error")
