from __future__ import annotations

from datetime import datetime, timezone
import concurrent.futures
import json
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices

from .app_paths import AppPaths
from .log_service import LogService
from .qt_utils import safe_file_part
from .theme_catalog import normalize_theme
from .support_report import DISCORD_URL, build_support_report, save_handoff, redact
from .support_browser import open_support_handoff
from .lifecycle import discard_queued_events


class ReportService(QObject):
    changed = Signal()
    _supportReady = Signal(object)

    def __init__(self, paths: AppPaths, log: LogService, version, settings=None, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log
        self.version = version
        self.settings = settings
        self._preview = "Press Preview to build the local Markdown report."
        self._latest = ""
        self._started = time.time()
        self._closed = False
        self._support_busy = False
        self._support_status = ""
        self._services = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="support-report")
        self._future = None
        self._supportReady.connect(self._apply_support)

    @Property(str, notify=changed)
    def preview(self): return self._preview

    @Property(str, notify=changed)
    def latestPath(self): return self._latest

    @Property(bool, notify=changed)
    def supportBusy(self): return self._support_busy

    @Property(str, notify=changed)
    def supportStatus(self): return self._support_status

    def bind_support_context(self, services):
        self._services = dict(services)

    @Slot(str)
    def openSupportForm(self, page):
        if self._closed or self._support_busy:
            return
        self._support_busy = True
        self._support_status = "Preparing report..."
        self.changed.emit()
        # Snapshot QObject properties on their owning thread; the worker receives plain data.
        context = {"page": page, "version": self.version.localVersion,
                   "theme": self.active_theme_name(), "log": self.log.plainText, "services": {}}
        context["retained_app_log"], context["app_log_writer"] = self.log.diagnostic_snapshot()
        fields = ("status", "running", "lastError", "activeGame", "selectedLayers", "selectedShapes",
                  "candidateCount", "exportedCount", "skippedCount", "viewerReady", "packageAddError",
                  "dependenciesText", "pythonText", "runtimeText", "selectedPresetIndex", "liveLog")
        for name, service in self._services.items():
            values = {}
            for field in fields:
                try:
                    value = getattr(service, field, None)
                except Exception:
                    continue
                if isinstance(value, (str, bool, int, float)):
                    values[field] = value
            context["services"][name] = values
        self._future = self._executor.submit(self._prepare_support, context)
        self._future.add_done_callback(self._emit_support)

    def _prepare_support(self, context):
        report = build_support_report(self.paths.app_root, context, since=self._started)
        from .support_log_bundle import collect_retained_log_bundle
        try:
            session_logs = {"app": context.get("retained_app_log", context.get("log", ""))}
            session_logs.update({name: values["liveLog"] for name, values in context.get("services", {}).items()
                                 if isinstance(values.get("liveLog"), str)})
            snapshot = {**report["technical"], "app_log_writer": context.get("app_log_writer", {})}
            attachment = collect_retained_log_bundle(self.paths.app_root, snapshot=snapshot, session_logs=session_logs)
        except Exception:
            attachment = None
            report["technical"]["collection_warning"] = "Application logs could not be prepared. Sending with technical details enabled is blocked. Reopen Report a Problem to retry, or explicitly turn technical details off to send without logs."
        if attachment is not None:
            report["private_logs"] = attachment[0]
        path, handoff = save_handoff(self.paths.app_root, report, log_attachment=attachment)
        return {"path": str(path), "handoff": str(handoff), "report": report}

    def _emit_support(self, future):
        if self._closed:
            return
        try:
            result = future.result()
        except Exception as exc:
            result = {"error": redact(exc)}
        if not self._closed:
            self._supportReady.emit(result)

    @Slot(object)
    def _apply_support(self, result):
        if self._closed:
            return
        self._support_busy = False
        if result.get("error"):
            self._support_status = "Could not prepare report: " + result["error"]
        else:
            self._latest = result["path"]
            self._preview = json.dumps(result["report"], indent=2)
            opened = open_support_handoff(result["handoff"], paths=self.paths)
            bundle_name = "report.kfps-report.json.gz" if result["report"].get("private_logs") else "report.json"
            self._support_status = {
                "review": ("KFPS report review opened with logs included. Nothing is sent until you press Send."
                           if result["report"].get("private_logs") else
                           "KFPS report review opened, but log collection failed. Sending with technical details enabled is blocked."),
                "prefilled": "Review opened in your default browser. Nothing is sent until you press Send.",
                "manual": f"Report saved. The form opened in your default browser. Use Reopen a saved report and choose {bundle_name} from Saved reports.",
                "failed": "Report saved. The KFPS report window could not open. Run KFPS-Updater.exe to repair the app, or find your report in Saved reports.",
            }.get(opened, "Report saved. Your report is available in Saved reports.")
        self.log.append(self._support_status, update_status=False)
        self.changed.emit()

    @Slot()
    def openDiscord(self):
        QDesktopServices.openUrl(QUrl(DISCORD_URL))

    @Slot()
    def openSupportReports(self):
        folder = self.paths.runtime_root / "support-reports"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                raise OSError("The reports folder could not be opened.")
        except OSError as exc:
            self._support_status = "Could not open reports folder: " + redact(exc)
            self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._future is not None:
            self._future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
        discard_queued_events(self)

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
