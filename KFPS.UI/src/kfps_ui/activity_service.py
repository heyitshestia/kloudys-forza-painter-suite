"""Themed settings and real-window lifecycle for the shared activity counter."""
from PySide6.QtCore import QObject, Property, Signal, Slot

from tools.kfps_activity import PRIVACY_TEXT
from tools.kfps_activity_host import ActivityHost


class ActivityService(QObject):
    changed = Signal()

    def __init__(self, app_root, parent=None, *, counter=None):
        super().__init__(parent)
        self.counter = ActivityHost(app_root, counter=counter)
        self._enabled = self.counter.enabled()
        self._started = self._closed = False
        self._status = ''

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(str, constant=True)
    def privacyText(self):
        return PRIVACY_TEXT

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Slot()
    def refresh(self):
        value = self.counter.enabled()
        if value != self._enabled:
            self._enabled = value
            self.changed.emit()

    @Slot(bool, result=bool)
    def setEnabled(self, value):
        saved = self.counter.set_enabled(value)
        self._enabled = self.counter.enabled()
        self._status = '' if saved else 'Activity preference was not saved. Please try again.'
        self.changed.emit()
        return saved

    @Slot()
    def start(self):
        if not self._started and not self._closed:
            self._started = True
            self.counter.start()

    def close(self):
        if not self._closed:
            self._closed = True
            self.counter.stop()
