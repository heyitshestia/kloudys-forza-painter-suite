"""Qt adapter for the shared offline release announcement."""
from PySide6.QtCore import QObject, Slot

from tools.kfps_release_announcement import ReleaseAnnouncement


class ReleaseAnnouncementService(QObject):
    def __init__(self, app_root, parent=None, *, provider=None):
        super().__init__(parent)
        self.provider = provider or ReleaseAnnouncement(app_root)

    @Slot("QVariantMap", result="QVariantMap")
    def dispatch(self, body):
        try:
            return self.provider.dispatch(body)
        except ValueError:
            return {"eligible": False, "acknowledged": False}

    @Slot(result="QVariantMap")
    def readStatus(self):
        return self.provider.read_status()

    def read_status(self):
        return self.provider.read_status()

    def close(self):
        self.provider.close()
