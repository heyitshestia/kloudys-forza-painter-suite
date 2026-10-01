"""One graphics policy for both standalone and main-app editor launches."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

BACKEND = "opengl"
POLICY = "editor-graphics-v2"
MODES = ("auto", "opengl", "d3d11")
SETTINGS_KEY = "editorGraphics"
# Frozen report d82882: PCI board identity, not a marketing name or adapter index.
KNOWN_FAULTY = (0x1002, 0x744C, 0x53051849, "32.0.31041.1004")


@dataclass(frozen=True)
class Selection:
    mode: str = "auto"
    backend: str = BACKEND
    reason: str = "default"
    settings_status: str = "missing"
    adapters: tuple = ()
    probe_status: str = "not-needed"


def read_preference(app_root):
    path = Path(app_root) / "runtime" / "qml-shell-settings.json"
    try:
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            return "auto", "oversized"
        payload = json.loads(data)
        if not isinstance(payload, dict):
            return "auto", "invalid"
        value = payload.get(SETTINGS_KEY, "auto")
        if not isinstance(value, str) or value not in MODES:
            return "auto", "invalid"
        return value, "loaded"
    except FileNotFoundError:
        return "auto", "missing"
    except (OSError, ValueError):
        return "auto", "unreadable"


def select_policy(app_root, *, probe=None):
    mode, status = read_preference(app_root)
    if mode != "auto":
        return Selection(mode, mode, "user-choice", status)
    try:
        if probe is None:
            from .graphics_probe import present_adapters
            probe = present_adapters
        adapters = tuple(probe())
    except (OSError, ValueError, ImportError) as exc:
        return Selection(settings_status=status, reason="detection-unavailable",
                         probe_status=type(exc).__name__)
    # A present second adapter (including virtual/unknown) makes the rendering
    # device ambiguous. Do not guess from the primary monitor or list order.
    if len(adapters) != 1:
        return Selection(settings_status=status, adapters=adapters,
                         reason="ambiguous-adapters" if adapters else "no-adapter",
                         probe_status="ok")
    adapter = adapters[0]
    identity = (adapter.vendor, adapter.device, adapter.subsystem, adapter.driver)
    matched = identity == KNOWN_FAULTY
    return Selection(backend="d3d11" if matched else BACKEND,
                     reason="known-driver-workaround" if matched else "no-known-match",
                     settings_status=status, adapters=adapters, probe_status="ok")


def configure_environment(environment, selection=None):
    backend = (selection or Selection()).backend
    if backend not in ("opengl", "d3d11"):
        raise ValueError("Unsupported editor graphics backend")
    # A parent app or shell must not silently select a different scene graph.
    for key in list(environment):
        if key.upper().startswith("QSG_") or key.upper() == "QT_QUICK_BACKEND":
            environment.pop(key)
    environment["QSG_RHI_BACKEND"] = backend


def configure_qt(selection=None):
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

    selection = selection or Selection()
    api = {"opengl": QSGRendererInterface.GraphicsApi.OpenGL,
           "d3d11": QSGRendererInterface.GraphicsApi.Direct3D11}[selection.backend]
    QQuickWindow.setGraphicsApi(api)
    return {"policy": POLICY, **asdict(selection), "requested_backend": selection.backend,
            "qt_graphics_api": QQuickWindow.graphicsApi().name}
