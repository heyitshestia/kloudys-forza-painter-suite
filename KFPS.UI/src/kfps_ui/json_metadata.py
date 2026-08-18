from __future__ import annotations

import json
import re
import time
from pathlib import Path


_COUNT_SUFFIX = re.compile(r"\.(\d+)v2\.json$", re.IGNORECASE)


def age_label(timestamp: float, now: float | None = None) -> str:
    seconds = max(0, int((time.time() if now is None else now) - timestamp))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def metadata_count_value(metadata: dict) -> int | None:
    for key in ("shape_count", "layer_count", "layers"):
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            if value is not None and str(value).strip():
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def json_count(path: str | Path) -> int:
    path = Path(path)
    match = _COUNT_SUFFIX.search(path.name)
    if match:
        return int(match.group(1))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("shapes", "layers", "items"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
    return 0


def json_summary(path: str | Path) -> tuple[dict, int, str]:
    path = Path(path)
    metadata: dict = {}
    layers: int | None = None
    manifest = path.with_suffix(".manifest.json")
    try:
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                metadata = dict(payload)
                layers = metadata_count_value(metadata)
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    if layers is None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                layers = len(payload)
            elif isinstance(payload, dict):
                if isinstance(payload.get("metadata"), dict):
                    metadata = dict(payload["metadata"])
                    layers = metadata_count_value(metadata)
                if layers is None:
                    for key in ("shapes", "layers", "items"):
                        if isinstance(payload.get(key), list):
                            layers = len(payload[key])
                            break
        except (OSError, UnicodeError, ValueError, TypeError):
            pass
    if layers is None:
        match = _COUNT_SUFFIX.search(path.name)
        layers = int(match.group(1)) if match else 0
    metadata.setdefault("layers", layers)
    metadata.setdefault("layer_count", layers)
    metadata.setdefault("shape_count", layers)
    name = metadata.get("display_name") or metadata.get("title")
    return metadata, int(layers), str(name) if name else path.name


def metadata_for_json(path: str | Path) -> dict:
    return json_summary(path)[0]


def metadata_count(metadata: dict, path: str | Path) -> int:
    value = metadata_count_value(metadata)
    return value if value is not None else json_count(path)


def count_detail_text(layers: int, metadata: dict) -> str:
    game = str(metadata.get("target_game") or metadata.get("game") or "").strip().lower()
    if game in {"fm", "fm8"}:
        return f"FM8  •  {int(layers)} shapes"
    return f"{int(layers)} layers"


def display_name_for_json(path: str | Path, metadata: dict | None = None) -> str:
    path = Path(path)
    metadata = metadata or metadata_for_json(path)
    name = metadata.get("display_name") or metadata.get("title")
    return str(name) if name else path.name
