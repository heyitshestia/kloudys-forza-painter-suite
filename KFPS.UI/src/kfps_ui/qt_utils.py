from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QUrl
from tools.kfps_update_status import is_remote_newer, version_tuple


def file_url(path: str | Path | None) -> str:
    if not path:
        return ""
    return QUrl.fromLocalFile(str(Path(path).resolve())).toString()


def safe_file_part(value: str, fallback: str = "item") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "")).strip(" .")
    return value or fallback


def open_path(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
