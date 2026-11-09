from __future__ import annotations

from pathlib import Path
from typing import Any


MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024


def source_grid_row(row: dict[str, Any]) -> dict[str, Any]:
    """Associate only the thumbnail belonging to this exact saved livery."""
    result = dict(row)
    result["thumbnailUrl"] = ""
    source = Path(str(row.get("path") or ""))
    try:
        result["available"] = source.name.casefold() == "c_livery" and source.is_file()
    except (OSError, ValueError):
        result["available"] = False
    if result["available"]:
        for name in ("bigThumb.webp", "BigThumb.webp"):
            thumbnail = source.parent / name
            try:
                stat = thumbnail.stat()
                if not thumbnail.is_file() or not 0 < stat.st_size <= MAX_THUMBNAIL_BYTES:
                    continue
                # Refresh independently of C_livery: the game can update its image
                # without changing the saved artwork record or catalog identity.
                result["thumbnailUrl"] = (
                    thumbnail.resolve().as_uri() + f"?v={stat.st_mtime_ns}-{stat.st_size}"
                )
                break
            except OSError:
                continue
    result["searchText"] = " ".join(str(row.get(key) or "") for key in (
        "title", "modelCode", "carId",
    ))
    return result
