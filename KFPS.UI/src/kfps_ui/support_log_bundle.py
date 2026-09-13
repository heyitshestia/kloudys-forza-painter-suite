"""On-demand, privacy-filtered copies of allowlisted retained application logs."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .support_logs import _safe, discover_worker_logs

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


def collect_retained_log_bundle(root: Path, *, snapshot=None):
    return _collect_log_bundle(root, include_workers=True, snapshot=snapshot)


def collect_editor_log_bundle(root: Path):
    """Keep the editor-only collection contract for existing integrations."""
    return _collect_log_bundle(root, include_workers=False)


def _collect_log_bundle(root: Path, *, include_workers, snapshot=None):
    from .support_report import redact
    root = Path(root).resolve()
    files, warnings, total = [], [], 0
    if snapshot is not None:
        # Only the already allowlisted report context is supplied here, never raw
        # QObject state or project data. Refilter each line for the archive contract.
        text = "\n".join(redact(line, 60000) for line in
                         json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False).splitlines()) + "\n"
        total = len(text.encode("utf-8"))
        if total > MAX_FILE_BYTES:
            raise ValueError("Current session diagnostics exceed the attachment safety limit.")
        files.append({"name": "app-status-0000.log", "modified_utc": datetime.now(timezone.utc).isoformat(),
                      "source_bytes": total, "omitted_lines": 0, "text": text})
    paths = [(name, root / "runtime/fabric-editor" / name) for name in NAMES]
    if include_workers:
        found, discovery_warnings = discover_worker_logs(root, now=time.time(), retained=True)
        warnings.extend(discovery_warnings)
        for index, (source, path) in enumerate(found, 1):
            if source == "editor-desktop":
                continue
            label = source + ("-stderr" if path.name == "stderr.log" else "")
            paths.append((f"{label}-{index:04}.log", path))
    for name, path in paths:
        try:
            before = _safe(root, path)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("unsafe_file")
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_nlink != 1:
                    raise ValueError("changed_file")
                if opened.st_size > MAX_FILE_BYTES or total + opened.st_size > MAX_RAW_BYTES:
                    raise ValueError("oversized_file")
                raw = stream.read(opened.st_size)
                if len(raw) != opened.st_size:
                    raise ValueError("changed_file")
            total += len(raw)
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
            files.append({"name": name, "modified_utc": datetime.fromtimestamp(opened.st_mtime, timezone.utc).isoformat(),
                          "source_bytes": len(raw), "omitted_lines": omitted, "text": "\n".join(lines) + ("\n" if lines else "")})
            if omitted:
                warnings.append(f"{name}: incomplete or unsupported lines omitted ({omitted}).")
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            warnings.append(f"{name}: could not copy the complete retained log.")
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
