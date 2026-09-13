"""Keep test windows behind the user's work unless focus is explicitly tested."""
from PySide6.QtCore import Qt


def keep_in_background(window):
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnBottomHint, True)
    window.raise_ = window.lower
    window.activateWindow = lambda: None
