"""Shared, read-only launch choice for the editor EXE and main-app launcher."""
import json
import os
from pathlib import Path


def _windows_local_appdata():
    # Environment isolation changes cache roots, not where Chrome is installed.
    if os.name != "nt":
        return None
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x1C, None, 0, buffer) == 0:
            return Path(buffer.value) if buffer.value else None
    except (AttributeError, OSError):
        pass
    return None


def find_chrome():
    """Use the same installed-Chrome discovery in Settings and the editor host."""
    roots = [os.environ.get(variable) for variable in ("LocalAppData", "ProgramFiles", "ProgramFiles(x86)")]
    roots.append(_windows_local_appdata())
    for root in roots:
        if root:
            path = Path(root) / "Google/Chrome/Application/chrome.exe"
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
    return None


def use_chrome(app_root):
    try:
        with (Path(app_root) / "runtime/qml-shell-settings.json").open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            return False
        payload = json.loads(data)
        return isinstance(payload, dict) and payload.get("editorUseChrome") is True
    except (OSError, ValueError):
        return False
