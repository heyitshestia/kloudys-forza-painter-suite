"""Once-per-process cinematic eligibility and non-blocking startup readiness."""
from __future__ import annotations

import concurrent.futures
import time
import threading

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from fh6_rtti_registry import refresh_runtime_registry
from .lifecycle import discard_queued_events


class StartupFrameProvider(QQuickImageProvider):
    """One decoded frame, not a growing cache; works with every QML renderer."""
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._lock = threading.Lock()
        self._image = QImage(1, 1, QImage.Format_RGB32)
        self._image.fill(0)

    def set_frame(self, image):
        with self._lock:
            self._image = image

    def clear(self):
        image = QImage(1, 1, QImage.Format_RGB32)
        image.fill(0)
        self.set_frame(image)

    def requestImage(self, _identifier, size, requestedSize):
        with self._lock:
            image = QImage(self._image)
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class StartupSequenceService(QObject):
    changed = Signal()
    frameChanged = Signal()
    playbackChanged = Signal()
    mediaEnded = Signal()
    playbackError = Signal(str)
    _registryResult = Signal(object)

    def __init__(self, paths, jsons, runtime, logs, *, enabled=False,
                 refresh_registry=False, muted=False, parent=None):
        super().__init__(parent)
        self._paths, self._jsons, self._runtime, self._logs = paths, jsons, runtime, logs
        self._closed = self._claimed = self._started = self._ready = False
        self._ready_elapsed = None
        self._refresh_registry = refresh_registry
        self._forced_muted = self._muted = bool(muted)
        self._player = self._audio = self._sink = None
        self._frame_revision = 0
        self._playing = False
        self.frame_provider = StartupFrameProvider()
        self._executor = self._future = None
        candidates = (paths.runtime_root / "theme-assets/ps2/startup.mp4",
                      paths.asset_root / "themes/ps2/startup.mp4")
        media = None
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    media = candidate
                    break
            except OSError:
                continue
        self._source = QUrl.fromLocalFile(str(media)).toString() if media else ""
        self._enabled = bool(enabled and media)
        if enabled and not media:
            logs.append("PS2 startup media unavailable; opening the menu directly.", "warning")
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._check_ready)
        self._registryResult.connect(self._record_registry_result)

    @Property(str, constant=True)
    def source(self): return self._source

    @Property(bool, constant=True)
    def enabled(self): return self._enabled

    @Property(bool, notify=playbackChanged)
    def muted(self): return self._muted

    @Property(bool, notify=changed)
    def ready(self): return self._ready

    @Property(str, notify=frameChanged)
    def frameSource(self): return f"image://ps2-startup/frame-{self._frame_revision}"

    @Property(int, notify=playbackChanged)
    def position(self): return self._player.position() if self._player else 0

    @Slot()
    def play(self):
        if self._closed or not self._claimed or not self._enabled:
            return
        if self._player is None:
            # A CPU video sink avoids Qt VideoOutput's black software-renderer path.
            # QML receives a normal image, without changing the scene-graph backend.
            try:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
            except ImportError as exc:
                self.playbackError.emit(str(exc))
                return
            self._audio = QAudioOutput(self)
            self._audio.setMuted(self._muted)
            self._sink = QVideoSink(self)
            self._sink.videoFrameChanged.connect(self._receive_frame)
            self._player = QMediaPlayer(self)
            self._player.setObjectName("Ps2StartupPlayer")
            self._player.setAudioOutput(self._audio)
            self._player.setVideoSink(self._sink)
            self._player.positionChanged.connect(self.playbackChanged)
            self._player.mediaStatusChanged.connect(self._media_status)
            self._player.errorOccurred.connect(self._playback_error)
        if self._player.source().isEmpty():
            self._player.setSource(QUrl(self._source))
        self._playing = True
        self._player.play()

    def _receive_frame(self, frame):
        if self._closed or not self._playing or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            self.playbackError.emit("The video decoder returned an empty frame.")
            return
        self.frame_provider.set_frame(image)
        self._frame_revision += 1
        self.frameChanged.emit()

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if not self._closed and status == QMediaPlayer.EndOfMedia:
            self.mediaEnded.emit()

    def _playback_error(self, _error, message):
        if not self._closed:
            self.playbackError.emit(message)

    @Slot()
    def pause(self):
        if self._player is not None:
            self._player.pause()

    @Slot()
    def stop(self):
        self._playing = False
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        self.frame_provider.clear()

    @Slot(bool)
    def setMuted(self, value):
        if self._closed:
            return
        muted = self._forced_muted or bool(value)
        if self._muted == muted:
            return
        self._muted = muted
        if self._audio is not None:
            self._audio.setMuted(muted)
        self.playbackChanged.emit()

    @Slot(result=bool)
    def claim(self):
        if self._closed or self._claimed:
            return False
        self._claimed = True
        return self._enabled

    @Slot()
    def beginLoading(self):
        if self._closed or self._started:
            return
        self._started = True
        self._started_at = time.monotonic()
        # JsonService owns scans and thumbnail warming; do not create a second writer.
        self._jsons.warmIndex()
        if self._refresh_registry:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="startup-registry")
            self._future = self._executor.submit(refresh_runtime_registry, self._paths.app_root)
            self._future.add_done_callback(self._emit_registry_result)
        self._timer.start()
        self._check_ready()

    def _emit_registry_result(self, future):
        if self._closed:
            return
        try:
            result = future.result()
        except Exception as exc:
            result = {"result": "error", "error": str(exc)}
        if not self._closed:
            self._registryResult.emit(result)

    @Slot(object)
    def _record_registry_result(self, result):
        if not self._closed:
            self._logs.append("Startup registry refresh: " + str(result.get("result", "complete")))

    @Slot()
    def _check_ready(self):
        if self._closed or not self._started or self._ready:
            return
        elapsed = time.monotonic() - self._started_at
        busy = self._jsons.indexing or self._runtime.checking
        # A disconnected output drive must not trap the user in a cinematic.
        if busy and elapsed < 30:
            return
        self._ready = True
        self._ready_elapsed = elapsed
        self._timer.stop()
        message = f"PS2 startup ready after {elapsed:.2f}s"
        if busy:
            message += "; output indexing continues in the background"
        self._logs.append(message + ".")
        self.changed.emit()

    @Slot(str)
    def recordPlaybackError(self, message):
        if not self._closed:
            self._logs.append("PS2 startup playback unavailable: " + str(message)[:300], "warning")

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop()
        self._timer.stop()
        if self._future is not None:
            self._future.cancel()
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
        discard_queued_events(self)
