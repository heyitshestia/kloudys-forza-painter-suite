"""Destroy the QML scene before its Python context objects leave scope."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QEvent


def exec_qml_application(app, engine, shutdown: Callable[[], None] | None = None) -> int:
    try:
        return app.exec()
    finally:
        try:
            if shutdown is not None:
                shutdown()
        finally:
            # The main loop has stopped; deleteLater alone cannot release the scene.
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
