"""Fail-open, once-per-host lifecycle boundary around optional activity counts."""
import threading

from tools.kfps_activity import ActivityCounter


class ActivityHost:
    def __init__(self, app_root, *, counter=None):
        self._mutex = threading.Lock()
        self._started = self._closed = False
        try:
            self.counter = counter if counter is not None else ActivityCounter(app_root)
        except Exception:
            self.counter = None

    def enabled(self):
        try:
            return self.counter is not None and self.counter.enabled() is True
        except Exception:
            return False

    def set_enabled(self, value):
        try:
            return type(value) is bool and self.counter is not None and self.counter.set_enabled(value) is True
        except Exception:
            return False

    def start(self):
        with self._mutex:
            if self._closed or self.counter is None:
                return False
            if self._started:
                return True
            try:
                self.counter.start()
                self._started = True
                return True
            except Exception:
                return False

    def stop(self):
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            try:
                if self.counter is not None:
                    self.counter.stop()
            except Exception:
                pass
