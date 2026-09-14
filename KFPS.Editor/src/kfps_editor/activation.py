"""Targeted Windows foreground handoff; no global focus permission or PID guessing."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


def grant_foreground(pid):
    if os.name != "nt" or type(pid) is not int or not 0 < pid < 0xFFFFFFFF:
        return False
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    return bool(user.AllowSetForegroundWindow(pid))


def grant_pipe_foreground(handle):
    if os.name != "nt":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    pid = wintypes.ULONG()
    if kernel.GetNamedPipeServerProcessId(int(handle), ctypes.byref(pid)):
        return grant_foreground(pid.value)
    return False


def process_running(pid):
    """False means verified exit; None means inaccessible/unknown, never stale."""
    if type(pid) is not int or not 0 < pid < 0xFFFFFFFF:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False if ctypes.get_last_error() == 87 else None
    try:
        code = wintypes.DWORD()
        return code.value == 259 if kernel.GetExitCodeProcess(handle, ctypes.byref(code)) else None
    finally:
        kernel.CloseHandle(handle)


def present(window, *, background=False):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    if not background and window._background:
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        window.setWindowFlag(Qt.WindowType.WindowStaysOnBottomHint, False)
        window._background = False
    window.showNormal() if window.isMinimized() else window.show()
    if background:
        return False
    modal = QApplication.activeModalWidget()
    target = modal if modal and window.isAncestorOf(modal) else window
    target.raise_()
    target.activateWindow()
    if QApplication.platformName() == "windows":
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.GetForegroundWindow.restype = wintypes.HWND
        user.SetForegroundWindow(int(target.winId()))
        focused = user.GetForegroundWindow() == int(target.winId())
        if not focused:
            QApplication.alert(window, 3000)
    else:
        focused = target.isActiveWindow()
    if focused and target is window and window._ready and window.view:
        window.view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    return focused
