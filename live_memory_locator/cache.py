from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from .contracts import CACHE_SCHEMA, ENGINE_VERSION


MAX_USER_ADDRESS = 0x800000000000
MAX_ALLOCATOR_WINDOW = 0x100000000


def normalize_allocator_windows(values: Any, limit: int | None = 8) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for value in values or []:
        try:
            start, end = (int(item) for item in value)
        except (TypeError, ValueError):
            continue
        if start < 0x10000 or end <= start or end > MAX_USER_ADDRESS:
            continue
        if end - start > MAX_ALLOCATOR_WINDOW:
            continue
        windows.append((start, end))
    windows.sort()
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged if limit is None else merged[: max(0, int(limit))]


def allocator_window_for_address(address: int, size: int = 0x10000000) -> tuple[int, int]:
    if size <= 0 or size & (size - 1):
        raise ValueError("allocator window size must be a positive power of two")
    start = int(address) & ~(size - 1)
    return start, start + size


def _empty_cache() -> dict[str, Any]:
    return {
        "schema": CACHE_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "profiles": {},
        "sessions": {},
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class LocatorCache:
    """Persistent locator hints. Raw live pointers are deliberately never cached."""

    def __init__(self, path: str | Path, *, legacy_path: str | Path | None = None) -> None:
        self.path = Path(path).resolve()
        self.legacy_path = Path(legacy_path).resolve() if legacy_path else None

    def _load(self) -> dict[str, Any]:
        raw = _read_json(self.path)
        if raw.get("schema") == CACHE_SCHEMA:
            raw.setdefault("profiles", {})
            raw.setdefault("sessions", {})
            return raw

        legacy = raw
        if legacy.get("format") != "kfps_fh6_allocator_cache_v2" and self.legacy_path and self.legacy_path != self.path:
            legacy = _read_json(self.legacy_path)
        if legacy.get("format") == "kfps_fh6_allocator_cache_v2":
            migrated = _empty_cache()
            for profile_id, profile in (legacy.get("profiles") or {}).items():
                if not isinstance(profile, dict):
                    continue
                migrated["profiles"][str(profile_id)] = {
                    "game": "fh6",
                    "allocator_windows": [
                        [start, end]
                        for start, end in normalize_allocator_windows(profile.get("allocator_windows"))
                    ],
                    "updated": float(profile.get("updated") or 0.0),
                }
            return migrated
        return _empty_cache()

    def allocator_windows(self, profile_id: str) -> list[tuple[int, int]]:
        profile = (self._load().get("profiles") or {}).get(str(profile_id))
        return normalize_allocator_windows(
            profile.get("allocator_windows") if isinstance(profile, dict) else []
        )

    def all_allocator_windows(self, game: str) -> list[tuple[int, int]]:
        game = str(game or "").lower()
        windows = []
        for profile in (self._load().get("profiles") or {}).values():
            if not isinstance(profile, dict) or str(profile.get("game") or "").lower() != game:
                continue
            windows.extend(profile.get("allocator_windows") or [])
        return normalize_allocator_windows(windows)

    def update_allocator_windows(self, game: str, profile_id: str, windows: Any) -> None:
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            return
        raw = self._load()
        profiles = raw.setdefault("profiles", {})
        profiles[profile_id] = {
            "game": str(game or "").lower(),
            "allocator_windows": [
                [start, end] for start, end in normalize_allocator_windows(windows)
            ],
            "updated": time.time(),
        }
        if len(profiles) > 32:
            ordered = sorted(
                profiles.items(),
                key=lambda item: float(item[1].get("updated") or 0.0),
                reverse=True,
            )
            raw["profiles"] = dict(ordered[:32])
        _atomic_write(self.path, raw)

    @staticmethod
    def session_key(game: str, profile_id: str, process_started: float, purpose: str) -> str:
        return ":".join(
            (
                str(game).lower(),
                str(profile_id or "unmatched"),
                f"{float(process_started):.6f}",
                str(purpose).lower(),
            )
        )

    def previous_session(self, key: str) -> dict[str, Any] | None:
        value = (self._load().get("sessions") or {}).get(str(key))
        return dict(value) if isinstance(value, dict) else None

    def record_session(self, key: str, summary: Mapping[str, Any]) -> None:
        forbidden = ("address", "pointer", "table", "group")

        def reject_live_fields(value: Any, trail: str = "session") -> None:
            if isinstance(value, Mapping):
                for name, child in value.items():
                    field = str(name)
                    if any(token in field.casefold() for token in forbidden):
                        raise ValueError(
                            f"live address field cannot be persisted in locator cache: {trail}.{field}"
                        )
                    reject_live_fields(child, f"{trail}.{field}")
            elif isinstance(value, (list, tuple)):
                for index, child in enumerate(value):
                    reject_live_fields(child, f"{trail}[{index}]")

        reject_live_fields(summary)
        raw = self._load()
        sessions = raw.setdefault("sessions", {})
        sessions[str(key)] = {**dict(summary), "updated": time.time()}
        if len(sessions) > 64:
            ordered = sorted(
                sessions.items(),
                key=lambda item: float(item[1].get("updated") or 0.0),
                reverse=True,
            )
            raw["sessions"] = dict(ordered[:64])
        _atomic_write(self.path, raw)
