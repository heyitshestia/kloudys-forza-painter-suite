from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QObject, Property, Signal, Slot

from .app_paths import AppPaths
from .log_service import LogService
from .qt_utils import safe_file_part
from .theme_catalog import normalize_theme


class ReportService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, log: LogService, version, settings=None, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log
        self.version = version
        self.settings = settings
        self._preview = "Press Preview to build the local Markdown report."
        self._latest = ""

    @Property(str, notify=changed)
    def preview(self): return self._preview

    @Property(str, notify=changed)
    def latestPath(self): return self._latest

    def active_theme_name(self) -> str:
        if self.settings is None:
            return normalize_theme(None)
        return normalize_theme(getattr(self.settings, "theme", None))

    def build(self, kind, title, details, context, include_log, paths):
        title = title.strip() or "Untitled"
        details = details.strip() or "(No details entered.)"
        lines = [
            "# KFPS Report",
            "",
            f"Type: {kind}",
            f"Title: {title}",
            f"Created UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "",
            "## What happened",
            details,
        ]
        if context:
            lines += ["", "## App context", f"Version: {self.version.localVersion}", f"Theme: {self.active_theme_name()}"]
        if paths:
            lines += ["", "## Local paths", f"App root: {self.paths.app_root}"]
        if include_log:
            lines += ["", "## Visible runtime log", "```text", self.log.plainText, "```"]
        lines += ["", "## Privacy", "This report was created locally. KFPS does not upload it automatically."]
        return "\n".join(lines) + "\n"

    @Slot(str, str, str, bool, bool, bool, result=str)
    def previewReport(self, kind, title, details, context, include_log, paths):
        self._preview = self.build(kind, title, details, context, include_log, paths)
        self.changed.emit()
        self.log.append("Local report preview updated.")
        return self._preview

    @Slot(str, str, str, bool, bool, bool, result=str)
    def saveReport(self, kind, title, details, context, include_log, paths):
        root = self.paths.runtime_root / "bug-reports"
        root.mkdir(parents=True, exist_ok=True)
        target = root / (datetime.now().strftime("%Y%m%d-%H%M%S-") + safe_file_part(title, "kfps-report") + ".md")
        self._preview = self.build(kind, title, details, context, include_log, paths)
        target.write_text(self._preview, encoding="utf-8")
        self._latest = str(target)
        self.changed.emit()
        self.log.append(f"Saved local report: {target}")
        return self._latest
