"""Destroy the QML scene before its Python context objects leave scope."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QEvent


def dispose_qml_application(engine, shutdown: Callable[[], None] | None = None) -> None:
    try:
        if shutdown is not None:
            shutdown()
    finally:
        # The loop may have stopped or never started after an admission failure.
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)


def exec_qml_application(app, engine, shutdown: Callable[[], None] | None = None) -> int:
    try:
        return app.exec()
    finally:
        dispose_qml_application(engine, shutdown)
