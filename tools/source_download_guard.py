from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


LATEST_RELEASE_URL = "https://github.com/heyitshestia/kloudys-forza-painter-suite/releases/latest"
ALLOW_ENV = "KFPS_ALLOW_SOURCE_DOWNLOAD"
ALLOW_FILES = (
    "ALLOW_SOURCE_DOWNLOAD.txt",
    "KFPS_ALLOW_SOURCE_DOWNLOAD.txt",
    ".kfps-allow-source-download",
)


@dataclass(frozen=True)
class SourceDownloadGuardStatus:
    blocked: bool
    latest_release_url: str = LATEST_RELEASE_URL
    reason: str = ""
    details: str = ""
    override_hint: str = (
        "Emergency bypass: create ALLOW_SOURCE_DOWNLOAD.txt next to VERSION, "
        "set KFPS_ALLOW_SOURCE_DOWNLOAD=1, or start with --allow-source-download."
    )


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "allow"}


def _has_allow_marker(app_root: Path) -> bool:
    return any((app_root / name).is_file() for name in ALLOW_FILES)


def _looks_like_release_layout(app_root: Path) -> bool:
    if app_root.name.lower() != "kloudysfh6painter":
        return False
    parent = app_root.parent
    return (parent / "KFPS.exe").is_file() and (parent / "Images").is_dir()


def _looks_like_source_archive(app_root: Path) -> bool:
    name = app_root.name.lower()
    source_name = name.endswith("-main") or name.endswith("-master") or "kloudys-forza-painter-suite" in name
    source_files = (
        (app_root / ".gitignore").is_file()
        and (app_root / "requirements.txt").is_file()
        and (app_root / "tools" / "native_launcher" / "KFPSLauncher.cs").is_file()
    )
    return source_name or source_files


def evaluate_source_download_guard(app_root: Path, *, allow: bool = False) -> SourceDownloadGuardStatus:
    app_root = Path(app_root).resolve()
    if allow or _truthy(os.environ.get(ALLOW_ENV)) or _has_allow_marker(app_root):
        return SourceDownloadGuardStatus(blocked=False)

    # Active developer checkouts are allowed. The block targets GitHub source
    # archives that users mistake for release zips, not local development trees.
    if (app_root / ".git").exists():
        return SourceDownloadGuardStatus(blocked=False)

    if _looks_like_release_layout(app_root):
        return SourceDownloadGuardStatus(blocked=False)

    if not _looks_like_source_archive(app_root):
        return SourceDownloadGuardStatus(blocked=False)

    details = [
        "This folder looks like the GitHub main/source download, not the KFPS release package.",
        "GitHub source downloads do not provide the supported release layout or a packaged Python runtime.",
        "Download the latest release instead, then choose the bundled zip with Python included.",
    ]
    return SourceDownloadGuardStatus(
        blocked=True,
        reason="GitHub main/source archive detected",
        details="\n".join(details),
    )
