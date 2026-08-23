from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
OPERATIONS = {
    "link-game",
    "refresh-packages",
    "scan-saves",
    "open-package",
    "preview-source",
    "add-package",
    "migrate-package",
    "export-package",
    "install-package",
    "prepare-mesh",
    "clear-cache",
}


def new_request_id() -> str:
    return uuid.uuid4().hex


def write_json_atomic(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_request(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or int(value.get("protocol") or 0) != PROTOCOL_VERSION:
        raise ValueError("Unsupported full-livery worker request.")
    operation = str(value.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError(f"Unsupported full-livery worker operation: {operation or '<empty>'}")
    if not isinstance(value.get("paths"), dict) or not isinstance(value.get("payload"), dict):
        raise ValueError("The full-livery worker request is incomplete.")
    return value
