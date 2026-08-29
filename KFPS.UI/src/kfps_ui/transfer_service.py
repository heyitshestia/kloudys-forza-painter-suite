from __future__ import annotations

from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from game_adapters import LiveGameDetectionError, detect_single_running_game
from live_memory_locator.fh6_recovery import (
    FORCE_LOCAL_RECOVERY_ENV,
    force_local_recovery_requested,
)

from .app_paths import AppPaths
from .json_service import JsonService
from .log_service import LogService
from .lifecycle import discard_queued_events


class TransferService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, log: LogService, jsons: JsonService, parent=None):
        super().__init__(parent)
        self._closed = False
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
        self._force_fh6_recovery_pending = force_local_recovery_requested()
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read)
        self._process.finished.connect(self._finished)
        self._process.started.connect(self._process_started)
        self._process.errorOccurred.connect(self._process_error)
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(160)
        self._live_timer.timeout.connect(self._flush_live_log)
        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.setInterval(5000)
        self._startup_timer.timeout.connect(self._startup_timed_out)
        if self._force_fh6_recovery_pending:
            self.log.append(
                "FH6 local compatibility recovery test is armed for the first FH6 live transfer."
            )

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def liveLog(self):
        return self._live_log

    @Slot(str, int, bool)
    def importJson(self, path, layers, clear_unused):
        if not path or not Path(path).is_file():
            self.log.append("Select a JSON before importing.", "warning")
            return
        target = self._detect_live_target()
        if target is None:
            return
        adapter = target.adapter
        if not adapter.supports("live_import"):
            self.log.append(f"{adapter.short_label} online import is not supported.", "warning")
            return
        args = [
            "import",
            "--game",
            adapter.bridge_key,
            "--pid",
            str(target.pid),
            "--layer-count",
            str(layers),
            "--json",
            path,
        ]
        if clear_unused:
            args.append("--clear-unused")
        self._start(args, f"Importing JSON into {adapter.short_label}")

    @Slot(int)
    def exportJson(self, layers):
        target = self._detect_live_target()
        if target is None:
            return
        adapter = target.adapter
        if not adapter.supports("live_export"):
            self.log.append(f"{adapter.short_label} online export is not supported.", "warning")
            return
        self._start(
            [
                "export",
                "--game",
                adapter.bridge_key,
                "--pid",
                str(target.pid),
                "--layer-count",
                str(layers),
            ],
            f"Exporting current {adapter.short_label} group",
        )

    def _detect_live_target(self):
        try:
            return detect_single_running_game()
        except LiveGameDetectionError as exc:
            message = str(exc)
            self._status = "Live transfer blocked"
            self._live_log_lines = []
            self._pending_live_lines = []
            self._set_live_log([message])
            self.log.append(message, "warning")
            return None

    def _start(self, args, status):
        if self._closed:
            return
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

        env, forced_recovery_test = self._build_process_environment(args)
        if forced_recovery_test:
            message = "Forcing one FH6 local compatibility recovery test."
            self.log.append(message)
            self._set_live_log([message])
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(str(self.paths.app_root))
        self._process.start(self.paths.python_executable, ["-u", str(bridge), *args])
        self._startup_timer.start()

    @staticmethod
    def _game_argument(args):
        try:
            index = args.index("--game")
            return str(args[index + 1]).strip().casefold()
        except (AttributeError, IndexError, ValueError):
            return ""

    def _build_process_environment(self, args):
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("KFPS_APP_ROOT", str(self.paths.app_root))
        force_this_transfer = (
            self._force_fh6_recovery_pending and self._game_argument(args) == "fh6"
        )
        if force_this_transfer:
            env.insert(FORCE_LOCAL_RECOVERY_ENV, "1")
            self._force_fh6_recovery_pending = False
        else:
            env.remove(FORCE_LOCAL_RECOVERY_ENV)
        return env, force_this_transfer

    def _process_started(self):
        if not self._closed:
            self._startup_timer.stop()

    def _process_error(self, _error):
        if self._closed or not self._running or self._process.state() != QProcess.NotRunning:
            return
        self._fail_start("Import/export process did not start.")

    def _startup_timed_out(self):
        if self._closed or not self._running or self._process.state() != QProcess.Starting:
            return
        self._process.kill()
        self._fail_start("Import/export process did not start within five seconds.")

    def _fail_start(self, message):
        self._startup_timer.stop()
        self._running = False
        self._status = "Failed to start"
        self._close_full_transfer_log()
        self._live_timer.stop()
        self.changed.emit()
        self.log.append(message, "error")

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
        if self._closed:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        parts = self._buffer.split(b"\n")
        self._buffer = parts.pop() if parts else b""
        for raw in parts:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line.strip():
                self._handle_line(line)

    def _finished(self, code, _status):
        if self._closed:
            return
        self._startup_timer.stop()
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

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._startup_timer.stop()
        self._live_timer.stop()
        self._pending_live_lines.clear()
        self._close_full_transfer_log()
        try:
            process_id = int(self._process.processId())
        except Exception:
            process_id = 0
        if process_id:
            try:
                process = psutil.Process(process_id)
                for child in reversed(process.children(recursive=True)):
                    try:
                        child.kill()
                    except psutil.Error:
                        pass
                process.kill()
            except psutil.Error:
                pass
        try:
            if self._process.state() != QProcess.NotRunning:
                self._process.kill()
                self._process.waitForFinished(1500)
        except Exception:
            pass
        self._running = False
        discard_queued_events(self)
