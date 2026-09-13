"""Open the private handoff with the web default, not the .html association."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QDesktopServices

from .support_report import FORM_ORIGIN


def default_browser_executable() -> str:
    if sys.platform != "win32":
        return ""
    try:
        query = ctypes.WinDLL("shlwapi").AssocQueryStringW
        query.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
                          wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        query.restype = ctypes.c_long
        size = wintypes.DWORD(0)
        # ASSOCF_IS_PROTOCOL resolves this user's current default, not machine defaults.
        query(0x1000, 2, "https", "open", None, ctypes.byref(size))
        if not 1 < size.value <= 32768:
            return ""
        buffer = ctypes.create_unicode_buffer(size.value)
        if query(0x1000, 2, "https", "open", buffer, ctypes.byref(size)) != 0:
            return ""
        path = Path(buffer.value)
        if path.is_absolute() and path.suffix.lower() == ".exe" and path.is_file():
            return str(path)
    except (OSError, ValueError, AttributeError):
        pass
    return ""


def open_browser_url(url: QUrl) -> str:
    """Open an ordinary web URL in the existing default-browser profile.

    A started process/OS request is not proof that a tab appeared or login finished.
    Callers must retain a manual URL and wait for the authorization protocol.
    """
    if (not url.isValid() or url.scheme() not in {"https", "http"}
            or not url.host() or url.userName() or url.password()):
        return "failed"
    logger = logging.getLogger("kfps-report-window")
    executable = default_browser_executable()
    if executable:
        try:
            # No shell, browser-specific switches or temporary profile. The single
            # encoded argument cannot become command-line options or private data.
            started, _pid = QProcess.startDetached(executable, [url.toString(QUrl.ComponentFormattingOption.FullyEncoded)])
        except (OSError, RuntimeError):
            started = False
        logger.info("browser-launch route=default-executable started=%s", bool(started))
        if started:
            return "default-executable"
    try:
        started = QDesktopServices.openUrl(url)
    except (OSError, RuntimeError):
        started = False
    # Never log approval URLs, ticket IDs, paths or exception text here.
    logger.info("browser-launch route=system-handler started=%s", bool(started))
    return "system-handler" if started else "failed"


def open_support_handoff(handoff: str, *, paths=None) -> str:
    path = Path(handoff).resolve()
    if not path.is_file():
        return "failed"
    if paths is not None:
        from .support_window_launch import launch_review
        try:
            return launch_review(paths, path.parent.name)
        except (OSError, ValueError, RuntimeError):
            return "failed"
    executable = default_browser_executable()
    if executable:
        try:
            # Explicit argv keeps spaces/Unicode safe and the large draft off the command line.
            started, _pid = QProcess.startDetached(executable, [path.as_uri()])
            if started:
                return "prefilled"
        except (OSError, RuntimeError):
            pass
    # Packaged/custom handlers may not expose an executable. Still honor Windows'
    # HTTPS handler, but ask for the saved report instead of silently choosing Edge.
    return "manual" if QDesktopServices.openUrl(QUrl(FORM_ORIGIN)) else "failed"
