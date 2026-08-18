from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

from PySide6.QtQuick import QQuickWindow, QSGRendererInterface


_ALIASES = {
    "d3d": "d3d11",
    "direct3d": "d3d11",
    "direct3d11": "d3d11",
    "gl": "opengl",
    "default": "auto",
}
_SUPPORTED = {"auto", "opengl", "d3d11", "software"}


@dataclass(frozen=True)
class RendererPolicy:
    name: str
    source: str
    warning: str = ""

    @property
    def persistent_scene_graph(self) -> bool:
        return self.name != "software"


def select_renderer_policy(environment: Mapping[str, str]) -> RendererPolicy:
    requested = str(environment.get("KFPS_QML_GRAPHICS") or "").strip().lower()
    source = "KFPS_QML_GRAPHICS"
    if not requested:
        requested = str(environment.get("QSG_RHI_BACKEND") or "").strip().lower()
        source = "QSG_RHI_BACKEND"
    if not requested and str(environment.get("QT_QUICK_BACKEND") or "").strip().lower() == "software":
        requested = "software"
        source = "QT_QUICK_BACKEND"
    if not requested:
        return RendererPolicy("opengl", "KFPS default")

    normalized = _ALIASES.get(requested, requested)
    if normalized not in _SUPPORTED:
        return RendererPolicy(
            "opengl",
            source,
            f"Unsupported renderer '{requested}' from {source}; using OpenGL.",
        )
    return RendererPolicy(normalized, source)


def apply_renderer_policy(
    policy: RendererPolicy,
    environment: MutableMapping[str, str],
) -> None:
    if policy.name == "auto":
        return
    if policy.name == "software":
        environment["QT_QUICK_BACKEND"] = "software"
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        return
    if policy.name == "d3d11":
        environment["QSG_RHI_BACKEND"] = "d3d11"
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
        return
    environment["QSG_RHI_BACKEND"] = "opengl"
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
