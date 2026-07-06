from __future__ import annotations

from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from .app_paths import AppPaths
from .json_service import JsonService
from .log_service import LogService


class TransferService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, log: LogService, jsons: JsonService, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log
        self.jsons = jsons
        self._running = False
        self._status = "Ready"
        self._buffer = b""
        self._live_log_lines: list[str] = []
        self._pending_live_lines: list[str] = []
        self._live_log = "Import/export log appears here."
        self._full_log_path = ""
        self._full_log_handle = None
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read)
        self._process.finished.connect(self._finished)
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(160)
        self._live_timer.timeout.connect(self._flush_live_log)

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def liveLog(self):
        return self._live_log

    @Slot(str, str, int, bool)
    def importJson(self, game, path, layers, clear_unused):
        if not path or not Path(path).is_file():
            self.log.append("Select a JSON before importing.", "warning")
            return
        args = ["import", "--game", self._game(game), "--layer-count", str(layers), "--json", path]
        if clear_unused:
            args.append("--clear-unused")
        self._start(args, "Importing JSON into game")

    @Slot(str, int)
    def exportJson(self, game, layers):
        self._start(["export", "--game", self._game(game), "--layer-count", str(layers)], "Exporting current game group")

    @staticmethod
    def _game(value):
        value = str(value or "").lower()
        return "fm" if value.startswith("fm") else value

    def _start(self, args, status):
        if self._running:
            self.log.append("A transfer job is already running.")
            return
        bridge = self.paths.ui_root / "bridges" / "transfer_bridge.py"
        self._open_full_transfer_log()
        self._running = True
        self._status = status
        self._buffer = b""
        self._live_log_lines = []
        self._pending_live_lines = []
        self._set_live_log([status + "..."])
        self.changed.emit()
        self.log.append(status + "...")
        if self._full_log_path:
            self.log.append(f"Full import/export log: {self._full_log_path}")

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("KFPS_APP_ROOT", str(self.paths.app_root))
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(str(self.paths.app_root))
        self._process.start(self.paths.python_executable, ["-u", str(bridge), *args])
        if not self._process.waitForStarted(5000):
            self._running = False
            self._status = "Failed to start"
            self._close_full_transfer_log()
            self._live_timer.stop()
            self.changed.emit()
            self.log.append("Import/export process did not start.", "error")

    def _open_full_transfer_log(self):
        self._close_full_transfer_log()
        try:
            folder = self.paths.runtime_root / "qml-transfer-logs"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"transfer-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            self._full_log_handle = path.open("w", encoding="utf-8", errors="replace")
            self._full_log_path = str(path)
        except Exception:
            self._full_log_handle = None
            self._full_log_path = ""

    def _write_full_transfer_log(self, line):
        handle = self._full_log_handle
        if not handle:
            return
        try:
            handle.write(str(line).rstrip("\r\n") + "\n")
        except Exception:
            self._close_full_transfer_log()

    def _close_full_transfer_log(self):
        handle = self._full_log_handle
        self._full_log_handle = None
        if handle:
            try:
                handle.close()
            except Exception:
                pass

    @staticmethod
    def _stream_live_transfer_line(line):
        text = str(line or "").strip()
        if not text:
            return False
        lower = text.lower()
        if lower.startswith("wrote target ") or lower.startswith("cleared unused layer "):
            return False
        important_tokens = (
            "error", "failed", "traceback", "exception", "timed out", "time limit",
            "complete", "located", "validated", "fallback", "warning", "refused",
            "run folder", "target game", "visible shapes", "fast-locating", "finding current",
            "process:", "detected", "writing json", "reading current", "imported ",
            "exported ", "trimming", "report:", "backup:", "selected exported json",
            "no safe", "missing", "unsupported", "permission", "administrator",
        )
        if any(token in lower for token in important_tokens):
            return True
        if "scan" in lower and ("candidate" in lower or "checked" in lower or "hits" in lower):
            return True
        return False

    def _queue_live_log(self, lines):
        clean = [str(line or "").strip() for line in lines if str(line or "").strip()]
        if not clean:
            return
        self._pending_live_lines.extend(clean)
        if not self._live_timer.isActive():
            self._live_timer.start()

    def _flush_live_log(self):
        if not self._pending_live_lines:
            self._live_timer.stop()
            return
        batch = self._pending_live_lines[:80]
        del self._pending_live_lines[:80]
        self._set_live_log(batch)
        if not self._pending_live_lines:
            self._live_timer.stop()

    def _set_live_log(self, lines):
        clean = [str(line or "").strip() for line in lines if str(line or "").strip()]
        if not clean:
            return
        self._live_log_lines.extend(clean)
        if len(self._live_log_lines) > 220:
            del self._live_log_lines[: len(self._live_log_lines) - 220]
        self._live_log = "\n".join(self._live_log_lines)
        self.changed.emit()

    def _handle_line(self, line):
        self._write_full_transfer_log(line)
        if line.startswith("KFPS_SELECTED_JSON:") or line.startswith("WPF_SELECTED_JSON:"):
            selected = line.split(":", 1)[1].strip()
            self.jsons.setSource(2)
            self.jsons.refresh()
            self.jsons.selectPath(selected)
            self._queue_live_log([f"Selected exported JSON: {Path(selected).name}"])
            return
        if self._stream_live_transfer_line(line):
            self.log.append(line, update_status=False)
            self._queue_live_log([line])

    def _read(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        parts = self._buffer.split(b"\n")
        self._buffer = parts.pop() if parts else b""
        for raw in parts:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line.strip():
                self._handle_line(line)

    def _finished(self, code, _status):
        if self._buffer:
            buffered = self._buffer.decode("utf-8", "replace")
            for line in buffered.splitlines():
                if line.strip():
                    self._handle_line(line.rstrip("\r"))
            self._buffer = b""
        final_line = "Transfer finished." if code == 0 else f"Transfer failed with exit code {code}."
        self._queue_live_log([final_line])
        self._flush_live_log()
        self._close_full_transfer_log()
        self._running = False
        self._status = "Complete" if code == 0 else f"Failed (exit {code})"
        self.changed.emit()
        self.jsons.refresh()
        self.jsons.refreshRecent()
        self.log.append(final_line, "info" if code == 0 else "error")

    @Slot()
    def forceStop(self):
        if not self._running:
            return
        try:
            process_id = int(self._process.processId())
            p = psutil.Process(process_id)
            for child in p.children(recursive=True):
                child.kill()
            p.kill()
        except Exception:
            self._process.kill()
