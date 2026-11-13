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
    ("app-runtime", "runtime/app-logs", None, r"app-\d+\.log(?:\.[12])?"),
    ("report-window", "runtime/support-reports", None, r"report-window\.log(?:\.[12])?"),
    ("editor-desktop", "runtime/fabric-editor", None, r"desktop\.log"),
    ("editor-server", "runtime/fabric-editor", None, r"server\.log(?:\.[12])?"),
    ("updater-legacy", "runtime/update-logs", None, r"update-" + RUN_NAME + r"\.log"),
    ("transfer-worker", "runtime/qml-transfer-logs", None, r"transfer-\d{8}-\d{6}\.log"),
    ("generator-bridge", "runtime/qml-generation-logs", None, r"generation-\d{8}-\d{6}\.log"),
    ("generator-worker", "imgs/generated", r"[^/\\]+", r"[A-Za-z0-9_-]+\.v2\.worker\.log"),
    ("upscale-worker", "runtime/upscaler/runs", RUN_NAME, r"native\.log"),
    ("background-worker", "runtime/background-remover/runs", RUN_NAME, r"worker\.log"),
    ("livery-worker", "runtime/experiments/full-livery/sessions", RUN_NAME, r"(?:stdout|stderr)\.log"),
    ("livery-viewer", "runtime/experiments/full-livery/sessions", "viewer-" + RUN_NAME, r"(?:stdout|stderr)\.log"),
)


def read_known_file(root: Path, path: Path, limit: int):
    """Snapshot one ordinary file; retry transient rotation/sharing races only."""
    if type(limit) is not int or limit < 0:
        raise ValueError("invalid read limit")
    for attempt in range(3):
        checked = False
        try:
            before = _safe(root, path)
            checked = True
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("unsafe_file")
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                current = _safe(root, path)
                if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
                    raise ValueError("changed_file")
                if opened.st_size > limit:
                    raise ValueError("oversized_file")
                raw = stream.read(opened.st_size)
                after = os.fstat(stream.fileno())
                if (len(raw) != opened.st_size or after.st_size < opened.st_size or after.st_nlink != 1
                        or (after.st_size == opened.st_size and after.st_mtime_ns != opened.st_mtime_ns)):
                    raise ValueError("changed_file")
            return raw, opened
        except (OSError, ValueError) as error:
            retry = (str(error) == "changed_file" or (checked and isinstance(error, FileNotFoundError))
                     or getattr(error, "winerror", 0) in (32, 33))
            if not retry or attempt == 2:
                raise
            time.sleep(.02 * (attempt + 1))


def updater_location(root: Path):
    # Same identity calculation as the native editor/updater. Never follow a path
    # supplied by a report or inspect another installation's updater history.
    from tools import fabric_editor_diagnostics  # installs the editor import root
    from kfps_editor.update_guard import updater_state_root
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local).resolve(), updater_state_root(root)) if local else None


def discover_updater_files(root: Path, kind: str):
    if kind not in {"logs", "reports"}:
        raise ValueError("unsupported diagnostic kind")
    warnings = set()
    try:
        location = updater_location(root)
    except (OSError, ValueError, ImportError):
        location = None
    if location is None:
        warnings.add("Updater diagnostic location unavailable.")
    suffix = "log" if kind == "logs" else "json"
    entries = []
    deadline = time.monotonic() + 1.5

    def scan(anchor, folder):
        try:
            if time.monotonic() > deadline:
                warnings.add("Log discovery limit reached; some logs were not checked.")
                return
            if not stat.S_ISDIR(_safe(anchor, folder).st_mode):
                raise ValueError("unsafe_folder")
            with os.scandir(folder) as children:
                for count, child in enumerate(children):
                    if count >= MAX_ENTRIES or time.monotonic() > deadline:
                        warnings.add("Log discovery limit reached; some logs were not checked.")
                        break
                    if not re.fullmatch(r"update-" + RUN_NAME + r"\." + suffix, child.name):
                        continue
                    path = Path(child.path)
                    try:
                        info = _safe(anchor, path)
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise ValueError("unsafe_file")
                        entries.append((info.st_mtime, anchor, path))
                        entries.sort(key=lambda item: (item[0], str(item[2])), reverse=True)
                        if len(entries) > 40:
                            warnings.add("Retained log file limit reached; some logs were not included.")
                            del entries[40:]
                    except (OSError, ValueError):
                        warnings.add("Some log entries could not be read or were linked.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            warnings.add("Some log folders could not be read or were linked.")

    if location is not None:
        anchor, state = location
        scan(anchor, state / kind)
    if kind == "reports" and not entries:
        anchor = Path(root).resolve()
        scan(anchor, anchor / "runtime/update-reports")
    return [(anchor, path) for _, anchor, path in entries], sorted(warnings)


def _safe(root: Path, path: Path):
    """Reject links/junctions and nonregular files before opening a known log."""
    relative = path.relative_to(root)
    if ".." in relative.parts:
        raise ValueError("unsafe log path")
    if tuple(part.casefold() for part in relative.parts[:2]) == ("runtime", "garage"):
        raise ValueError("private application data is not a diagnostic log")
    current = root
    info = current.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("linked log path")
    for part in relative.parts:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked log path")
    if not path.resolve().is_relative_to(root):
        raise ValueError("log outside application")
    return info


def discover_worker_logs(root: Path, *, now: float, retained=False):
    root = Path(root).resolve()
    found, warnings = [], set()
    deadline = time.monotonic() + 1.5

    def scan(folder, pattern, directories=False):
        try:
            if time.monotonic() > deadline:
                warnings.add("Log discovery limit reached; some logs were not checked.")
                return
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
                        else:
                            warnings.add("Some log entries could not be read or were linked.")
                    except (OSError, ValueError):
                        warnings.add("Some log entries could not be read or were linked.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            warnings.add("Some log folders could not be read or were linked.")

    for source, relative, subdir, pattern in SOURCES:
        if time.monotonic() > deadline:
            warnings.add("Log discovery limit reached; some logs were not checked.")
            break
        folder = root / relative
        candidates = []
        folders = [folder]
        if subdir:
            folders = [path / "reports" if source == "generator-worker" else path
                       for path, _ in scan(folder, r"[^/\\]+" if source == "generator-worker" else subdir, True)]
        for directory in folders:
            if time.monotonic() > deadline:
                warnings.add("Log discovery limit reached; some logs were not checked.")
                break
            for path, info in scan(directory, pattern):
                if info.st_size and (retained or now - MAX_AGE <= info.st_mtime <= now + 5):
                    candidates.append((info.st_mtime, path))
                    limit = 256 if retained else 2
                    if retained and len(candidates) > limit:
                        warnings.add("Retained log file limit reached; some logs were not included.")
                    candidates = sorted(candidates, key=lambda item: (item[0], str(item[1])), reverse=True)[:limit]
        # Preserve stdout + stderr from the latest livery session, not unrelated runs.
        if not retained:
            if source.startswith("livery-") and candidates:
                newest_parent = candidates[0][1].parent
                candidates = [item for item in candidates if item[1].parent == newest_parent]
            else:
                candidates = candidates[:1]
        found.extend((source, path) for _, path in candidates)
    if retained and len(found) > 256:
        warnings.add("Retained log file limit reached; some logs were not included.")
        # Keep the newest evidence from every component before filling the
        # remaining slots; one busy worker must not hide all other components.
        from collections import defaultdict, deque
        groups = defaultdict(deque)
        for source, path in found:
            groups[source].append(path)
        found = []
        while len(found) < 256 and any(groups.values()):
            for source, paths in groups.items():
                if paths and len(found) < 256:
                    found.append((source, paths.popleft()))
    return found, sorted(warnings)


def collect_worker_logs(root: Path, *, since: float, now: float, redact):
    root = Path(root).resolve()
    candidates, discovery_warnings = discover_worker_logs(root, now=now)
    entries, warnings = [], set(discovery_warnings)
    for source, path in candidates:
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
