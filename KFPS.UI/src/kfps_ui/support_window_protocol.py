"""Local-only report window inputs; never accept arbitrary file paths or URLs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

MAX_PACKAGE_BYTES = 9 * 1024 * 1024
CHUNK_BYTES = 192 * 1024


def report_id(value: str) -> str:
    parsed = str(uuid.UUID(value))
    if parsed != value:
        raise ValueError("Invalid report ID.")
    return parsed


def window_name(root: Path) -> str:
    identity = os.path.normcase(str(root.resolve())).encode("utf-8")
    return "kfps-report-" + hashlib.sha256(identity).hexdigest()[:32]


def read_source(root: Path, value: str) -> tuple[bytes, dict]:
    identifier = report_id(value)
    root = root.resolve()
    folder = root / "runtime" / "support-reports" / identifier
    for parent in (root / "runtime", folder.parent, folder):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked report folders are not supported.")
    package = folder / "report.kfps-report.json.gz"
    selected = package if package.exists() else folder / "report.json"
    mode = "package" if selected == package else "json"
    limit = MAX_PACKAGE_BYTES if mode == "package" else 49152
    info = selected.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Linked report files are not supported.")
    if not 0 < info.st_size <= limit:
        raise ValueError("The saved report exceeds its size limit.")
    with selected.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_ino, opened.st_dev, opened.st_size) != (info.st_ino, info.st_dev, info.st_size):
            raise ValueError("The saved report changed while opening.")
        data = stream.read(limit + 1)
    if len(data) != info.st_size:
        raise ValueError("The saved report changed while reading.")
    if mode == "json":
        summary = json.loads(data)
        if summary.get("schema") != "kfps-support-report/1" or summary.get("id") != identifier:
            raise ValueError("This is not the requested support report.")
    return data, {"id": identifier, "size": len(data), "mode": mode,
                  "sha256": hashlib.sha256(data).hexdigest()}
