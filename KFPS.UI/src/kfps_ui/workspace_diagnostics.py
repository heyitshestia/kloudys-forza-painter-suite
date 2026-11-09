"""Allowlisted lifecycle evidence for the existing app log and support reports."""
from __future__ import annotations

import math
import re
import time
import uuid

SCHEMA = "kfps-workspace-diagnostic/1"
COMPONENT_REVISION = "workspace-integration-r1"
MAX_EVENTS = 128
REPORT_EVENTS = 32
EVENTS = frozenset({
    "app.startup", "app.shutdown", "startup.index", "startup.registry", "startup.playback",
    "workspace.connection", "workspace.surface", "workspace.selection", "workspace.close",
    "workspace.owner", "workspace.shutdown", "handoff.editor", "handoff.studio", "handoff.source",
    "handoff.marker", "session.read", "session.persist", "session.restore", "session.snapshot",
    "cache.clear", "cache.catalog", "studio.backend",
})
OUTCOMES = frozenset({"started", "ready", "completed", "failed", "cancelled", "timeout",
                      "blocked", "fallback", "reused", "discarded", "deferred", "missing", "recovery", "busy"})
ENUMS = {
    "surface": {"KFPS", "Editor", "Studio", "Source", "other"},
    "mode": {"unified", "standalone", "native", "chrome"},
    "stage": {"qml", "workspace", "registry", "index", "prepare", "commit", "cleanup",
              "read", "persist", "restore", "load", "navigation", "request", "launch", "close", "lock", "ipc"},
    "error_type": {"OSError", "ValueError", "TypeError", "RuntimeError", "TimeoutError", "Exception"},
}
COUNTS = {"owner_count", "file_count", "byte_count", "cache_hits", "row_count", "errno", "winerror"}
FLAGS = {"whole", "busy", "restoring"}


def operation():
    return "c" + uuid.uuid4().hex[:15], time.monotonic()


def surface(name):
    if isinstance(name, str) and name.startswith("Source "):
        return "Source"
    return name if isinstance(name, str) and name in ENUMS["surface"] else "other"


def clean_event(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    if (not isinstance(value.get("event"), str) or value["event"] not in EVENTS
            or not isinstance(value.get("outcome"), str) or value["outcome"] not in OUTCOMES):
        return None
    result = {"schema": SCHEMA, "event": value["event"], "outcome": value["outcome"]}
    for key in ("session", "operation"):
        item = value.get(key)
        if isinstance(item, str) and re.fullmatch(r"[a-f0-9]{16}", item):
            result[key] = item
    utc = value.get("utc")
    if isinstance(utc, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", utc):
        result["utc"] = utc
    version = value.get("version")
    if isinstance(version, str) and re.fullmatch(r"\d{1,4}(?:\.\d{1,5}){1,3}", version):
        result["version"] = version
    if value.get("component_revision") == COMPONENT_REVISION:
        result["component_revision"] = COMPONENT_REVISION
    for key, choices in ENUMS.items():
        item = value.get(key)
        if isinstance(item, str) and item in choices:
            result[key] = item
    for key in COUNTS | {"serial"}:
        item = value.get(key)
        if type(item) is int and 0 <= item <= 2**53 - 1:
            result[key] = item
    for key in FLAGS:
        if type(value.get(key)) is bool:
            result[key] = value[key]
    for key in ("elapsed_ms", "verification_ms"):
        elapsed = value.get(key)
        if type(elapsed) in (int, float) and 0 <= elapsed <= 604800000 and math.isfinite(elapsed):
            result[key] = round(elapsed, 3)
    return result


def clean_identity(value):
    if not isinstance(value, dict):
        return {}
    event = clean_event({**{key: value.get(key) for key in ("version", "mode", "session", "component_revision")},
                         "schema": SCHEMA, "event": "app.startup", "outcome": "started"})
    return {key: event[key] for key in ("version", "mode", "session", "component_revision") if key in event}


def clean_snapshot(value):
    if not isinstance(value, (list, tuple)):
        return []
    return [event for item in value[-REPORT_EVENTS:] if (event := clean_event(item)) is not None]


def record(log, event, outcome, *, op=None, error=None, **fields):
    """Diagnostics must never change lifecycle outcomes or serialize exceptions."""
    emit = getattr(log, "diagnostic", None)
    if not callable(emit):
        return
    try:
        if op is not None:
            fields.update(operation=op[0], elapsed_ms=(time.monotonic() - op[1]) * 1000)
        if error is not None:
            fields["error_type"] = next((cls.__name__ for cls in
                (TimeoutError, OSError, ValueError, TypeError, RuntimeError) if isinstance(error, cls)), "Exception")
            for key in ("errno", "winerror"):
                fields[key] = getattr(error, key, None)
        emit(event, outcome, **fields)
    except Exception:
        pass
