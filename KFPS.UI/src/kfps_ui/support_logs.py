"""Read bounded tails from known KFPS workers, only while preparing a report."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import time
from datetime import datetime, timezone


MAX_TAIL_BYTES = 16 * 1024
MAX_ENTRIES = 4096
MAX_AGE = 7 * 86400
RUN_NAME = r"\d{8}-\d{6}(?:-[0-9a-f]+)?"
# Deliberately not a recursive *.log search. Never read project/report JSON files.
SOURCES = (
    ("editor-desktop", "runtime/fabric-editor", None, r"desktop\.log"),
    ("transfer-worker", "runtime/qml-transfer-logs", None, r"transfer-\d{8}-\d{6}\.log"),
    ("generator-bridge", "runtime/qml-generation-logs", None, r"generation-\d{8}-\d{6}\.log"),
    ("generator-worker", "imgs/generated", r"[^/\\]+", r"[A-Za-z0-9_-]+\.v2\.worker\.log"),
    ("upscale-worker", "runtime/upscaler/runs", RUN_NAME, r"native\.log"),
    ("background-worker", "runtime/background-remover/runs", RUN_NAME, r"worker\.log"),
    ("livery-worker", "runtime/experiments/full-livery/sessions", RUN_NAME, r"(?:stdout|stderr)\.log"),
    ("livery-viewer", "runtime/experiments/full-livery/sessions", "viewer-" + RUN_NAME, r"(?:stdout|stderr)\.log"),
)


def _safe(root: Path, path: Path):
    """Reject links/junctions and nonregular files before opening a known log."""
    relative = path.relative_to(root)
    current = root
    info = current.lstat()
    for part in relative.parts:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked log path")
    if not path.resolve().is_relative_to(root):
        raise ValueError("log outside application")
    return info


def collect_worker_logs(root: Path, *, since: float, now: float, redact):
    root = Path(root).resolve()
    entries, warnings = [], set()
    deadline = time.monotonic() + 1.5

    def scan(folder, pattern, directories=False):
        try:
            if not stat.S_ISDIR(_safe(root, folder).st_mode):
                return
            with os.scandir(folder) as children:
                for count, child in enumerate(children):
                    if count >= MAX_ENTRIES or time.monotonic() > deadline:
                        warnings.add("Log discovery limit reached; some logs were not checked.")
                        break
                    if not re.fullmatch(pattern, child.name):
                        continue
                    path = Path(child.path)
                    try:
                        info = _safe(root, path)
                        if (stat.S_ISDIR(info.st_mode) if directories else stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
                            yield path, info
                    except (OSError, ValueError):
                        warnings.add("Some log entries could not be read or were linked.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            warnings.add("Some log folders could not be read or were linked.")

    for source, relative, subdir, pattern in SOURCES:
        folder = root / relative
        candidates = []
        folders = [folder]
        if subdir:
            folders = [path / "reports" if source == "generator-worker" else path
                       for path, _ in scan(folder, r"[^/\\]+" if source == "generator-worker" else subdir, True)]
        for directory in folders:
            for path, info in scan(directory, pattern):
                if now - MAX_AGE <= info.st_mtime <= now + 5 and info.st_size:
                    candidates.append((info.st_mtime, path))
                    # Keep the two latest files, not a directory-sized list of contents.
                    candidates = sorted(candidates, key=lambda item: (item[0], str(item[1])), reverse=True)[:2]
        # Preserve stdout + stderr from the latest livery session, not unrelated runs.
        if source.startswith("livery-") and candidates:
            newest_parent = candidates[0][1].parent
            candidates = [item for item in candidates if item[1].parent == newest_parent]
        else:
            candidates = candidates[:1]
        for _, path in candidates:
            try:
                before = _safe(root, path)
                with path.open("rb") as handle:
                    info = os.fstat(handle.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)):
                        raise ValueError("log changed while opening")
                    start = max(0, info.st_size - MAX_TAIL_BYTES)
                    handle.seek(start)
                    raw = handle.read(MAX_TAIL_BYTES)
                # Drop an incomplete leading line: it may start inside a credential/blob.
                if start:
                    raw = raw.partition(b"\n")[2]
                lines = raw.decode("utf-8", errors="replace").replace("\r", "\n").splitlines()
                cleaned = redact("\n".join(lines), MAX_TAIL_BYTES)
                tail = "\n".join(cleaned.splitlines()[-60:])[-2400:]
                label = source + ("-stderr" if path.name == "stderr.log" else "")
                entries.append({"source": label, "text": tail,
                                "modified_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                                "age_seconds": max(0, int(now - info.st_mtime)),
                                "previous_session": info.st_mtime < since,
                                "truncated": bool(start or tail != cleaned),
                                "bytes": info.st_size})
            except (OSError, ValueError, OverflowError):
                warnings.add("Some logs could not be read; the report is still usable.")
    return entries, sorted(warnings)
