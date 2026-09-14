"""On-demand, privacy-filtered copies of allowlisted retained application logs."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import time

from .support_logs import discover_worker_logs, discover_updater_files, read_known_file

SCHEMA = "kfps-private-editor-logs/1"
APP_SCHEMA = "kfps-private-app-logs/2"
PACKAGE_SCHEMA = "kfps-support-package/1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
NAMES = ("performance.2.jsonl", "performance.1.jsonl", "performance.jsonl",
         "desktop.log.2", "desktop.log.1", "desktop.log")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def clean_record(value):
    from tools.fabric_editor_diagnostics import clean_fields, clean_packet, SCHEMA as EVENT_SCHEMA
    if not isinstance(value, dict) or value.get("schema") != EVENT_SCHEMA:
        raise ValueError("unsupported_record")
    session, utc, serial = value.get("session"), value.get("utc"), value.get("serial")
    if not isinstance(session, str) or not re.fullmatch(r"[a-f0-9]{32}", session):
        raise ValueError("unsupported_record")
    if not isinstance(utc, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT[0-9:.+Z-]{8,30}", utc):
        raise ValueError("unsupported_record")
    if type(serial) is not int or not 0 <= serial <= 2**53-1:
        raise ValueError("unsupported_record")
    result = {"schema": EVENT_SCHEMA, "session": session, "utc": utc, "serial": serial}
    if value.get("kind") == "sample":
        packet = clean_packet({**value, "schema": 1})
        result.update(kind="sample", **packet)
    else:
        fields = clean_fields(value)
        if not fields.get("kind"):
            raise ValueError("unsupported_record")
        result.update(fields)
    return result


def collect_retained_log_bundle(root: Path, *, snapshot=None, session_logs=None):
    return _collect_log_bundle(root, include_workers=True, snapshot=snapshot, session_logs=session_logs)


def collect_editor_log_bundle(root: Path):
    """Keep the editor-only collection contract for existing integrations."""
    return _collect_log_bundle(root, include_workers=False)


def _collect_log_bundle(root: Path, *, include_workers, snapshot=None, session_logs=None):
    from .support_report import redact
    root = Path(root).resolve()
    files, warnings, total, inventory = [], [], 0, []
    # Reserve room for the checklist/warnings and JSON envelope, rather than
    # filling the archive with log bodies and losing it all at final serialization.
    log_budget = max(0, MAX_RAW_BYTES - 256 * 1024)

    def add_generated(name, value):
        nonlocal total
        text = "\n".join(redact(line, 60000) for line in
                         json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).splitlines()) + "\n"
        size = len(text.encode("utf-8"))
        if size > MAX_FILE_BYTES:
            raise ValueError("Current session diagnostics exceed the attachment safety limit.")
        entry = {"name": name, "modified_utc": datetime.now(timezone.utc).isoformat(),
                 "source_bytes": size, "omitted_lines": 0, "text": text}
        total += len(compact(entry).encode("utf-8"))
        files.append(entry)
    if snapshot is not None:
        # Only the already allowlisted report context is supplied here, never raw
        # QObject state or project data. Refilter each line for the archive contract.
        add_generated("app-status-0000.log", snapshot)
    if session_logs:
        # Preserve the current in-memory history as well as disk logs, including
        # events queued to the UI/disk writer immediately before Report was clicked.
        safe = {key: str(value) for key, value in session_logs.items()
                if key in {"app", "generator", "transfer", "editor", "liveries", "community",
                           "updater", "upscaler", "background_remover"} and isinstance(value, str)}
        add_generated("app-session-0000.log", {key: value.splitlines() for key, value in safe.items()})
    if include_workers:
        from .support_context import collect_context
        add_generated("diagnostic-context-0000.log", collect_context(root))
    paths = [(name, root, root / "runtime/fabric-editor" / name) for name in NAMES]
    if include_workers:
        found, discovery_warnings = discover_worker_logs(root, now=time.time(), retained=True)
        warnings.extend(discovery_warnings)
        for index, (source, path) in enumerate(found, 1):
            if source == "editor-desktop":
                continue
            label = source + ("-stderr" if path.name == "stderr.log" else "")
            paths.append((f"{label}-{index:04}.log", root, path))
        updater, discovery_warnings = discover_updater_files(root, "logs")
        warnings.extend(discovery_warnings)
        paths.extend((f"updater-worker-{index:04}.log", anchor, path)
                     for index, (anchor, path) in enumerate(updater, 1))
        from collections import defaultdict, deque
        groups = defaultdict(deque)
        # Current desktop/performance logs first, then newest runs per source;
        # distribute remaining capacity across components instead of one archive hog.
        current = {"desktop.log", "performance.jsonl"}
        paths.sort(key=lambda item: item[0] not in current)
        for item in paths:
            name = item[0]
            source = "performance" if name.startswith("performance") else (
                "desktop" if name.startswith("desktop.") else name.rsplit("-", 1)[0])
            groups[source].append(item)
        paths = []
        while any(groups.values()):
            paths.extend(items.popleft() for items in groups.values() if items)
    for name, anchor, path in paths:
        try:
            raw, opened = read_known_file(anchor, path, MAX_FILE_BYTES)
            lines, omitted = [], 0
            for line in raw.decode("utf-8", errors="replace").splitlines():
                if name.startswith("performance"):
                    try:
                        lines.append(compact(clean_record(json.loads(line))))
                    except (ValueError, TypeError, KeyError, OverflowError):
                        omitted += 1
                else:
                    # Never split an oversized line inside a secret or encoded blob.
                    if len(line) > 60000:
                        lines.append("[oversized log line removed]")
                        omitted += 1
                    else:
                        lines.append(redact(line, 60000))
            entry = {"name": name, "modified_utc": datetime.fromtimestamp(opened.st_mtime, timezone.utc).isoformat(),
                     "source_bytes": len(raw), "omitted_lines": omitted, "text": "\n".join(lines) + ("\n" if lines else "")}
            entry_bytes = len(compact(entry).encode("utf-8"))
            if total + entry_bytes > log_budget:
                raise ValueError("oversized_file")
            total += entry_bytes
            files.append(entry)
            if omitted:
                warnings.append(f"{name}: incomplete or unsupported lines omitted ({omitted}).")
            inventory.append({"file": name, "status": "included", "bytes": len(raw), "omitted_lines": omitted})
        except FileNotFoundError:
            inventory.append({"file": name, "status": "missing"})
            continue
        except (OSError, ValueError) as error:
            warnings.append(f"{name}: could not copy the complete retained log.")
            reason = str(error) if isinstance(error, ValueError) else "unreadable"
            entry = {"file": name, "status": reason if reason in {"oversized_file", "changed_file", "unsafe_file"} else "unreadable"}
            for key in ("errno", "winerror"):
                if type(getattr(error, key, None)) is int:
                    entry[key] = getattr(error, key)
            inventory.append(entry)
    if include_workers:
        from .support_logs import SOURCES
        add_generated("collection-index-0000.log", {
            "scope": "known diagnostic files from this installation, at report preparation time",
            "sources_checked": [item[0] for item in SOURCES] + ["editor-performance", "updater-worker"],
            "files": inventory, "discovery_warnings": sorted(set(warnings)),
            "limits": {"file_bytes": MAX_FILE_BYTES, "raw_bytes": MAX_RAW_BYTES, "archive_bytes": MAX_ARCHIVE_BYTES}})
    if not files and not warnings:
        return None
    schema = APP_SCHEMA if include_workers else SCHEMA
    value = {"schema": schema, "created_at": datetime.now(timezone.utc).isoformat(), "files": files, "warnings": warnings}
    raw = compact(value).encode("utf-8")
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("Complete application logs exceed the attachment safety limit. No log attachment was prepared.")
    blob = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(blob) > MAX_ARCHIVE_BYTES:
        raise ValueError("Complete application logs exceed the upload safety limit. No log attachment was prepared.")
    metadata = {"schema": schema, "sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob),
                "raw_size": len(raw), "files": len(files), "warnings": warnings}
    return metadata, blob


def package_report(report, attachment):
    _, blob = attachment
    value = {"schema": PACKAGE_SCHEMA, "report": report, "logs_base64": base64.b64encode(blob).decode("ascii")}
    return gzip.compress(compact(value).encode("utf-8"), compresslevel=6, mtime=0)
