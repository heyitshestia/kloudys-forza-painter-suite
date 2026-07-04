from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from .app_paths import AppPaths
from .log_service import LogService
from .qt_utils import file_url


class GenerationService(QObject):
    changed = Signal()

    def __init__(self, paths: AppPaths, log: LogService, parent=None):
        super().__init__(parent); self.paths = paths; self.log = log
        self._process = QProcess(self); self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read); self._process.finished.connect(self._finished)
        self._running = False; self._status = "Ready"; self._run_dir = ""; self._preview = ""; self._preview_revision = 0; self._buffer = b""
        self._live_log_lines = []; self._live_log = "Live generation log appears here."
        self._full_log_path = ""; self._full_log_handle = None
        self._queue = []; self._queue_total = 0; self._queue_index = 0
        self._preview_timer = QTimer(self); self._preview_timer.setInterval(1000); self._preview_timer.timeout.connect(self.refreshPreview)
        self._presets = self._load_presets()
        self._selected_preset_index = 0 if self._presets else -1

    def _load_presets(self):
        fallback = ["1. Shaded Character Art", "2. Flat Colors", "3. Smooth Gradients"]
        try:
            from generator_backend import load_settings
            rows = load_settings()
            labels = [str(item.get("label") or item.get("name")) for item in rows if item.get("label") or item.get("name")]
            return labels or fallback
        except Exception:
            return fallback

    @Property("QStringList", constant=True)
    def presets(self): return self._presets
    @Property(int, notify=changed)
    def selectedPresetIndex(self): return self._selected_preset_index
    @Property(bool, notify=changed)
    def running(self): return self._running
    @Property(str, notify=changed)
    def status(self): return self._status
    @Property(str, notify=changed)
    def runDirectory(self): return self._run_dir
    @Property(str, notify=changed)
    def previewUrl(self): return self._preview
    @Property(int, notify=changed)
    def previewRevision(self): return self._preview_revision
    @Property(str, notify=changed)
    def liveLog(self): return self._live_log
    @Property(int, notify=changed)
    def queueRemaining(self): return len(self._queue)
    @Property(str, notify=changed)
    def queueStatus(self):
        if self._queue_total <= 1:
            return ""
        current = min(self._queue_index + 1, self._queue_total)
        return f"Queue {current}/{self._queue_total}"

    @Slot(str, int, str, str, bool, bool, bool, bool, bool, str, str, str, int)
    def start(self, image, preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed):
        self.startQueue([image], preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed)

    @Slot("QStringList", int, str, str, bool, bool, bool, bool, bool, str, str, str, int)
    def startQueue(self, images, preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed):
        if self._running: self.log.append("Generation is already running."); return
        valid_images = []
        for image in images or []:
            if image and Path(image).is_file():
                resolved = str(Path(image).resolve())
                if resolved not in valid_images:
                    valid_images.append(resolved)
        if not valid_images: self.log.append("Choose a source image before generating.", "warning"); return
        self._queue_total = len(valid_images); self._queue_index = 0
        self._queue = [
            (image, preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed)
            for image in valid_images[1:]
        ]
        if self._queue_total > 1:
            self.log.append(f"Starting queued generation: {self._queue_total} images.")
        self._start_single(valid_images[0], preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed)

    def _start_single(self, image, preset, layers, save_at, luma, detail, repair, boost, manual, max_res, random_samples, mutated_samples, seed):
        bridge = self.paths.ui_root / "bridges" / "generation_bridge.py"
        preset_index = preset if 0 <= int(preset) < len(self._presets) else self._selected_preset_index
        args = ["-u", str(bridge), "--image", image, "--preset-index", str(max(0, preset_index)), "--layers", layers or "2000", "--save-at", save_at or layers or "2000", "--seed", str(max(0, seed))]
        if luma: args += ["--luma-prep"]
        if detail: args += ["--detail-heatmap"]
        if repair: args += ["--edge-repair"]
        if boost: args += ["--sample-boost"]
        if manual:
            if max_res.strip(): args += ["--max-resolution", max_res.strip()]
            if random_samples.strip(): args += ["--random-samples", random_samples.strip()]
            if mutated_samples.strip(): args += ["--mutated-samples", mutated_samples.strip()]
        self._open_full_generation_log()
        prefix = f" ({self.queueStatus})" if self.queueStatus else ""
        self._run_dir = ""; self._set_preview(file_url(image)); self._buffer = b""; self._live_log_lines = []; self._live_log = "Starting generation" + prefix; self._running = True; self._status = "Starting generation" + prefix; self.changed.emit()
        self.log.append(f"Starting generation for: {image}")
        if self._full_log_path:
            self.log.append(f"Full generation log: {self._full_log_path}")
        env = QProcessEnvironment.systemEnvironment(); env.insert("PYTHONUTF8", "1"); env.insert("KFPS_APP_ROOT", str(self.paths.app_root)); self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(str(self.paths.app_root)); self._process.start(self.paths.python_executable, args)
        if not self._process.waitForStarted(5000):
            self._close_full_generation_log()
            self._running = False; self._status = "Failed to start"; self.changed.emit(); self.log.append("Generation process did not start.", "error")
        else: self._preview_timer.start()

    def _open_full_generation_log(self):
        self._close_full_generation_log()
        try:
            folder = self.paths.runtime_root / "qml-generation-logs"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"generation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            self._full_log_handle = path.open("w", encoding="utf-8", errors="replace")
            self._full_log_path = str(path)
        except Exception:
            self._full_log_handle = None
            self._full_log_path = ""

    def _write_full_generation_log(self, line):
        handle = self._full_log_handle
        if not handle:
            return
        try:
            handle.write(str(line).rstrip("\r\n") + "\n")
        except Exception:
            self._close_full_generation_log()

    def _close_full_generation_log(self):
        handle = self._full_log_handle
        self._full_log_handle = None
        if handle:
            try:
                handle.close()
            except Exception:
                pass

    def _set_preview(self, value):
        value = str(value or "")
        if value == self._preview:
            return False
        self._preview = value
        self._preview_revision += 1
        return True

    @Slot()
    def clearPreview(self):
        if self._set_preview(""):
            self.changed.emit()

    def _append_live_log(self, line):
        text = str(line or "").strip()
        if not text:
            return
        self._live_log_lines.append(text)
        self._live_log = "\n".join(self._live_log_lines)

    @staticmethod
    def _stream_live_generation_line(line):
        text = str(line or "").strip()
        if not text:
            return False
        lower = text.lower()
        if re.search(r"\b\d+(?:\.\d+)?\s*ms\b", lower):
            return True
        if any(token in lower for token in (
            "error", "failed", "traceback", "exception", "missing", "out of resources",
            "exited with code", "stop requested", "complete", "finalizing import json",
            "finalize scoring", "selected kloudy preset", "target template layers",
            "finalize at layers", "preset effort", "seed:", "detail heatmap:", "luma prep:",
        )):
            return True
        return False

    @Slot(int)
    def setSelectedPresetIndex(self, index):
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
        if self._presets:
            index = max(0, min(index, len(self._presets) - 1))
        else:
            index = -1
        if index != self._selected_preset_index:
            self._selected_preset_index = index
            self.changed.emit()

    @Slot(str)
    def autoSelectPresetForImage(self, image):
        if not image or not Path(image).is_file():
            return
        try:
            key = self._auto_preset_key(image)
            index = self._find_preset_index(key)
            if index < 0:
                index = self._find_preset_index("shaded")
            self.setSelectedPresetIndex(index)
            self.log.append(f"Auto preset: {self._preset_name_for_key(key)}.")
        except Exception as exc:
            index = self._find_preset_index("shaded")
            self.setSelectedPresetIndex(index if index >= 0 else 0)
            self.log.append(f"Auto preset detection unavailable, using Shaded Character Art: {exc}", "warning")

    def _find_preset_index(self, key):
        for index, text in enumerate(self._presets):
            lower = str(text).lower()
            if key == "flat" and "flat" in lower:
                return index
            if key == "gradient" and "gradient" in lower:
                return index
            if key == "shaded" and ("shaded" in lower or "character" in lower):
                return index
        return 0 if key == "shaded" and self._presets else -1

    @staticmethod
    def _preset_name_for_key(key):
        return {
            "flat": "Flat Colors",
            "gradient": "Smooth Gradients",
        }.get(key, "Shaded Character Art")

    @staticmethod
    def _auto_preset_key(image):
        from PIL import Image
        import numpy as np

        with Image.open(image) as source:
            source.thumbnail((384, 384), Image.Resampling.LANCZOS)
            rgba = source.convert("RGBA")

        pixels = np.asarray(rgba, dtype=np.uint8)
        if pixels.size == 0:
            return "shaded"
        alpha = pixels[:, :, 3]
        visible = alpha > 24
        if int(visible.sum()) < 32:
            return "shaded"

        rgb = pixels[:, :, :3].astype(np.int32)
        gray = ((rgb[:, :, 0] * 54 + rgb[:, :, 1] * 183 + rgb[:, :, 2] * 19) >> 8).astype(np.int32)
        left = np.roll(gray, 1, axis=1)
        right = np.roll(gray, -1, axis=1)
        up = np.roll(gray, 1, axis=0)
        down = np.roll(gray, -1, axis=0)
        left[:, 0] = gray[:, 0]
        right[:, -1] = gray[:, -1]
        up[0, :] = gray[0, :]
        down[-1, :] = gray[-1, :]
        edge = np.abs(right - left) + np.abs(down - up)
        visible_gray = gray[visible]
        edge_density = float(np.mean(edge[visible] > 80))

        coords = np.flatnonzero(visible.reshape(-1))
        sample_step = max(1, int(len(coords) / 20000))
        sampled = pixels.reshape(-1, 4)[coords[::sample_step], :3]
        bins = sampled // 24
        color_bin_count = int(len({(int(r) << 16) | (int(g) << 8) | int(b) for r, g, b in bins}))
        color_ratio = color_bin_count / float(max(1, len(sampled)))

        blur = (
            left + right + up + down + gray
            + np.roll(up, 1, axis=1) + np.roll(up, -1, axis=1)
            + np.roll(down, 1, axis=1) + np.roll(down, -1, axis=1)
        ) / 9.0
        local_detail = float(np.mean(np.abs(gray[visible] - blur[visible])))
        luma_std = float(np.std(visible_gray))

        if color_bin_count <= 90 and color_ratio < 0.030 and edge_density >= 0.045:
            return "flat"
        if edge_density < 0.070 and color_bin_count >= 140 and local_detail < 12.0 and luma_std >= 28.0:
            return "gradient"
        return "shaded"

    def _read(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        parts = self._buffer.split(b"\n"); self._buffer = parts.pop() if parts else b""
        for raw in parts:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            self._write_full_generation_log(line)
            if line.startswith("KFPS_RUN_DIR:") or line.startswith("WPF_RUN_DIR:"):
                self._run_dir = line.split(":",1)[1].strip(); self.changed.emit()
            elif line.startswith("KFPS_PREVIEW:") or line.startswith("WPF_PREVIEW:"):
                path = line.split(":",1)[1].strip(); self._set_preview(file_url(path)); self.changed.emit()
            elif self._stream_live_generation_line(line):
                self._append_live_log(line)
                self.log.append(line, update_status=False)
                self._status = line[:100]
                self.changed.emit()

    def _finished(self, code, _status):
        if self._buffer:
            buffered = self._buffer.decode("utf-8", "replace")
            for line in buffered.splitlines():
                self._write_full_generation_log(line)
                if self._stream_live_generation_line(line):
                    self._append_live_log(line)
                    self.log.append(line, update_status=False)
            self._buffer = b""
        self._close_full_generation_log()
        self._preview_timer.stop(); self.refreshPreview()
        self.log.append("Generation finished." if code == 0 else f"Generation exited with code {code}.", "info" if code == 0 else "error")
        if self._queue:
            self._queue_index += 1
            next_args = self._queue.pop(0)
            self._status = f"Starting next queued image ({self.queueStatus})"
            self.changed.emit()
            self._start_single(*next_args)
            return
        self._queue_index = 0; self._queue_total = 0
        self._running = False; self._status = "Complete" if code == 0 else f"Failed (exit {code})"; self.changed.emit()

    @Slot()
    def refreshPreview(self):
        root = Path(self._run_dir) if self._run_dir else None
        if not root or not root.is_dir(): return
        candidates = []
        for folder in [root / "previews", root / "finals", root]:
            if folder.is_dir(): candidates += list(folder.glob("*.png"))
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime_ns)
            url = file_url(latest)
            if self._set_preview(url): self.changed.emit()

    @Slot()
    def gracefulStop(self):
        if not self._running: self.log.append("No generation is running."); return
        if self._run_dir:
            try: (Path(self._run_dir) / ".v2-stop").write_text("stop\n", encoding="utf-8"); self._status = "Stop requested"; self.changed.emit(); self.log.append("Graceful stop requested. The current saved point will finish first.")
            except Exception as exc: self.log.append(f"Could not request graceful stop: {exc}", "error")
        else: self.log.append("The run folder is not known yet; use Force Stop only if necessary.", "warning")

    @Slot()
    def forceStop(self):
        if not self._running: return
        self._queue = []; self._queue_total = 0; self._queue_index = 0
        pid = int(self._process.processId())
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.kill()
                except psutil.Error: pass
            parent.kill(); self.log.append("Generation process tree was force-stopped.", "warning")
        except Exception:
            self._process.kill()
