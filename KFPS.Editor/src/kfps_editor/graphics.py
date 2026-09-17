"""One graphics policy for both standalone and main-app editor launches."""
from __future__ import annotations

BACKEND = "opengl"
POLICY = "editor-opengl-v1"


def configure_environment(environment):
    # A parent app or shell must not silently select a different scene graph.
    for key in list(environment):
        if key.upper().startswith("QSG_") or key.upper() == "QT_QUICK_BACKEND":
            environment.pop(key)
    environment["QSG_RHI_BACKEND"] = BACKEND


def configure_qt():
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    return {"policy": POLICY, "requested_backend": BACKEND,
            "qt_graphics_api": QQuickWindow.graphicsApi().name}
