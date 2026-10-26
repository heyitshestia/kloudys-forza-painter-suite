"""Read-only FH3 acquisition using KFPS's existing strict WGS metadata parser.

Only registered current blobs are read; no save registration or writing APIs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .fh3_files import MAX_CONTAINER, _read, _check_cancel
from .xbox_wgs import parse_wgs_index_bytes, parse_wgs_file_list


def _digest(path: Path) -> str:
    return hashlib.sha256(_read(path, MAX_CONTAINER)).hexdigest()


@dataclass(frozen=True)
class Fh3Source:
    payload: Path
    header: Path | None
    fingerprints: tuple[tuple[Path, str], ...]

    @property
    def cache_key(self) -> str:
        contents = tuple((str(p), digest) for p, digest in self.fingerprints
                         if p == self.payload or p == self.header)
        identity = str(self.payload.resolve()).casefold() + repr(contents)
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def verify(self) -> None:
        for path, digest in self.fingerprints:
            if _digest(path) != digest:
                raise ValueError("FH3 save changed while reading. Wait for cloud sync, then scan again.")


def _source(payload: Path, header: Path | None, metadata=()) -> Fh3Source:
    files = [payload] + ([header] if header is not None else [])
    return Fh3Source(payload, header, tuple(metadata) + tuple((p, _digest(p)) for p in files))


def discover_sources(roots, cancel=None) -> tuple[list[Fh3Source], list[str]]:
    """Scan bounded selected/known trees, reporting damaged slots individually."""
    sources, errors = [], []
    seen, visited = set(), set()
    queue = [(Path(root), 0) for root in roots]
    while queue:
        _check_cancel(cancel)
        root, depth = queue.pop()
        try:
            key = str(root.resolve()).casefold()
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > 10000:
                errors.append("Folder scan limit reached; choose the FH3 wgs folder directly.")
                break
            if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
                continue
            index_path = root / "containers.index"
            if index_path.is_file():
                raw = _read(index_path, MAX_CONTAINER)
                index = parse_wgs_index_bytes(raw, index_path)
                package = index.package_name.casefold()
                if "microsoft.opuspg" not in package and "forzahorizon3" not in package:
                    raise ValueError("This WGS profile is not identified as Forza Horizon 3.")
                index_snapshot = (index_path, hashlib.sha256(raw).hexdigest())
                for folder in index.folders:
                    _check_cancel(cancel)
                    if not folder.name.casefold().startswith("layergroup_"):
                        continue
                    try:
                        directory = root / folder.directory_name
                        if directory.resolve().parent != root.resolve():
                            raise ValueError("WGS container points outside the selected profile.")
                        descriptor = directory / f"container.{folder.sequence}"
                        descriptor_digest = _digest(descriptor)
                        listing = parse_wgs_file_list(descriptor, require_files=False)
                        # WGS's second GUID is the current blob. Never read an older
                        # primary GUID just because that stale file still exists.
                        files = {entry.name.casefold(): directory / entry.secondary_guid.hex.upper()
                                 for entry in listing.entries}
                        if "c_group" not in files or "header" not in files:
                            raise ValueError("Registered vinyl is missing C_group or header.")
                        for path in (files["c_group"], files["header"]):
                            if path.resolve().parent != directory.resolve():
                                raise ValueError("WGS blob points outside its container.")
                        source = _source(files["c_group"], files["header"],
                                         (index_snapshot, (descriptor, descriptor_digest)))
                        source.verify()
                        source_key = str(source.payload.resolve()).casefold()
                        if source_key not in seen:
                            sources.append(source)
                            seen.add(source_key)
                    except (OSError, ValueError) as exc:
                        errors.append(f"{directory}: {exc}")
                # Do not salvage unregistered blobs or stale descriptors by walking
                # beneath a profile. The index is the authority for active entries.
                continue
            if any(root.glob("container.*")):
                errors.append(f"{root}: choose the parent profile containing containers.index.")
                continue
            payload = root / "C_group"
            if payload.is_file():
                header = root / "header"
                source = _source(payload, header if header.is_file() else None)
                if str(payload.resolve()).casefold() not in seen:
                    sources.append(source)
                    seen.add(str(payload.resolve()).casefold())
                continue
            if depth >= 6:
                errors.append(f"{root}: folder depth limit reached; choose a closer save folder.")
                continue
            queue.extend((child, depth + 1) for child in root.iterdir()
                         if child.is_dir() and child.name.casefold() not in
                         {"t", ".git", ".fls-wgs-backups", "node_modules", "python"})
        except (OSError, ValueError) as exc:
            errors.append(f"{root}: {exc}")
    return sources, errors
