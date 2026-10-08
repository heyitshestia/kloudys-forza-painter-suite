"""Shared, read-only launch choice for the editor EXE and main-app launcher."""
import json
import os
from pathlib import Path


def find_chrome():
    """Use the same installed-Chrome discovery in Settings and the editor host."""
    for variable in ("LocalAppData", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
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
