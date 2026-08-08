"""Strict Xbox WGS container support for FH4 local vinyl groups.

The FH4 Microsoft Store build stores each user-created vinyl group as a WGS
container. This module owns that container format so the general C_group codec
and UI service do not need to understand opaque WGS filenames.

The implementation is intentionally conservative:

- existing metadata must parse and serialize byte-for-byte;
- imports create a new container instead of rewriting an existing vinyl;
- the complete WGS account slot is backed up before any save-file write;
- original files are fingerprinted and rechecked immediately before commit;
- the new logical files are reopened and verified after the atomic index swap;
- any failed verification restores the original index and removes the new entry.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


WGS_INDEX_VERSION = 0x0E
WGS_FILE_LIST_VERSION = 4
WGS_FILE_NAME_CHARS = 64
MAX_WGS_FOLDERS = 100_000
MAX_WGS_FILES = 4_096
MAX_WGS_STRING_CHARS = 4_096
WINDOWS_FILETIME_EPOCH = 116_444_736_000_000_000
WINDOWS_FILETIME_TICKS_PER_SECOND = 10_000_000
WGS_SLOT_PATTERN = re.compile(r"^[0-9A-Fa-f]{16}_[0-9A-Fa-f]{32}$")


class WgsFormatError(ValueError):
    """Raised when a WGS structure cannot be parsed without assumptions."""


class WgsConcurrentChangeError(RuntimeError):
    """Raised when Xbox or another process changes the save during staging."""


class _Reader:
    def __init__(self, data: bytes, source: Path | str):
        self.data = data
        self.source = str(source)
        self.pos = 0

    def _take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise WgsFormatError(
                f"{self.source} ended at 0x{self.pos:x} while reading {size} byte(s)"
            )
        value = self.data[self.pos : self.pos + size]
        self.pos += size
        return value

    def u8(self) -> int:
        return self._take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def guid_le(self) -> uuid.UUID:
        return uuid.UUID(bytes_le=self._take(16))

    def utf16(self) -> str:
        length = self.u32()
        if length > MAX_WGS_STRING_CHARS:
            raise WgsFormatError(
                f"{self.source} has an unreasonable UTF-16 length {length} at 0x{self.pos - 4:x}"
            )
        try:
            return self._take(length * 2).decode("utf-16le")
        except UnicodeDecodeError as exc:
            raise WgsFormatError(f"{self.source} contains invalid UTF-16 metadata") from exc

    def fixed_utf16(self, characters: int) -> str:
        try:
            return self._take(characters * 2).decode("utf-16le").rstrip("\x00")
        except UnicodeDecodeError as exc:
            raise WgsFormatError(f"{self.source} contains an invalid fixed UTF-16 name") from exc

    def finish(self) -> None:
        if self.pos != len(self.data):
            raise WgsFormatError(
                f"{self.source} has {len(self.data) - self.pos} unexplained trailing byte(s)"
            )


def _u8(value: int) -> bytes:
    return struct.pack("<B", int(value) & 0xFF)


def _u32(value: int) -> bytes:
    return struct.pack("<I", int(value) & 0xFFFFFFFF)


def _u64(value: int) -> bytes:
    return struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF)


def _utf16(value: str) -> bytes:
    text = str(value)
    if len(text) > MAX_WGS_STRING_CHARS:
        raise WgsFormatError(f"WGS metadata string is too long ({len(text)} characters)")
    return _u32(len(text)) + text.encode("utf-16le")


def _fixed_utf16(value: str, characters: int = WGS_FILE_NAME_CHARS) -> bytes:
    text = str(value)
    if len(text) > characters:
        raise WgsFormatError(f"WGS logical filename is too long: {text!r}")
    encoded = text.encode("utf-16le")
    return encoded + b"\x00" * (characters * 2 - len(encoded))


def datetime_to_filetime(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.astimezone()
    timestamp = value.astimezone(timezone.utc).timestamp()
    return int(timestamp * WINDOWS_FILETIME_TICKS_PER_SECOND) + WINDOWS_FILETIME_EPOCH


@dataclass(frozen=True)
class WgsFolderEntry:
    name: str
    repeated_name: str
    cloud_id: str
    sequence: int
    flags: int
    folder_guid: uuid.UUID
    modified_filetime: int
    unknown: int
    size: int

    @property
    def directory_name(self) -> str:
        return self.folder_guid.hex.upper()


@dataclass(frozen=True)
class WgsIndex:
    version: int
    flag1: int
    package_name: str
    modified_filetime: int
    flag2: int
    index_guid: str
    unknown: int
    folders: tuple[WgsFolderEntry, ...]


@dataclass(frozen=True)
class WgsFileEntry:
    name: str
    primary_guid: uuid.UUID
    secondary_guid: uuid.UUID
    actual_path: Path | None


@dataclass(frozen=True)
class WgsFileList:
    version: int
    sequence: int
    entries: tuple[WgsFileEntry, ...]
    path: Path


@dataclass(frozen=True)
class WgsLayerGroup:
    slot_path: Path
    folder: WgsFolderEntry
    file_list: WgsFileList

    @property
    def folder_path(self) -> Path:
        return self.slot_path / self.folder.directory_name

    def file(self, logical_name: str) -> Path | None:
        wanted = str(logical_name).casefold()
        for entry in self.file_list.entries:
            if entry.name.casefold() == wanted:
                return entry.actual_path
        return None

    @property
    def cgroup_path(self) -> Path | None:
        return self.file("C_group")

    @property
    def header_path(self) -> Path | None:
        return self.file("header")

    @property
    def thumbnail_path(self) -> Path | None:
        return self.file("thumb.png") or self.file("thumbnail")


@dataclass(frozen=True)
class WgsCreateResult:
    slot_path: Path
    folder_path: Path
    container_name: str
    cgroup_path: Path
    header_path: Path
    thumbnail_path: Path
    backup_path: Path


def parse_wgs_index_bytes(data: bytes, source: Path | str = "containers.index") -> WgsIndex:
    reader = _Reader(data, source)
    version = reader.u32()
    if version != WGS_INDEX_VERSION:
        raise WgsFormatError(
            f"{source} uses unsupported WGS index version {version}; expected {WGS_INDEX_VERSION}"
        )
    folder_count = reader.u32()
    if folder_count > MAX_WGS_FOLDERS:
        raise WgsFormatError(f"{source} declares an unreasonable folder count {folder_count}")
    flag1 = reader.u32()
    package_name = reader.utf16()
    modified_filetime = reader.u64()
    flag2 = reader.u32()
    index_guid = reader.utf16()
    unknown = reader.u64()
    folders: list[WgsFolderEntry] = []
    for _ in range(folder_count):
        name = reader.utf16()
        repeated_name = reader.utf16()
        if name != repeated_name:
            raise WgsFormatError(f"{source} has mismatched WGS folder names {name!r} and {repeated_name!r}")
        folders.append(
            WgsFolderEntry(
                name=name,
                repeated_name=repeated_name,
                cloud_id=reader.utf16(),
                sequence=reader.u8(),
                flags=reader.u32(),
                folder_guid=reader.guid_le(),
                modified_filetime=reader.u64(),
                unknown=reader.u64(),
                size=reader.u64(),
            )
        )
    reader.finish()
    return WgsIndex(
        version=version,
        flag1=flag1,
        package_name=package_name,
        modified_filetime=modified_filetime,
        flag2=flag2,
        index_guid=index_guid,
        unknown=unknown,
        folders=tuple(folders),
    )


def serialize_wgs_index(index: WgsIndex) -> bytes:
    if index.version != WGS_INDEX_VERSION:
        raise WgsFormatError(f"Unsupported WGS index version {index.version}")
    if len(index.folders) > MAX_WGS_FOLDERS:
        raise WgsFormatError(f"WGS index has too many folders: {len(index.folders)}")
    output = bytearray()
    output.extend(_u32(index.version))
    output.extend(_u32(len(index.folders)))
    output.extend(_u32(index.flag1))
    output.extend(_utf16(index.package_name))
    output.extend(_u64(index.modified_filetime))
    output.extend(_u32(index.flag2))
    output.extend(_utf16(index.index_guid))
    output.extend(_u64(index.unknown))
    for folder in index.folders:
        if folder.name != folder.repeated_name:
            raise WgsFormatError(f"WGS folder names do not match: {folder.name!r}")
        output.extend(_utf16(folder.name))
        output.extend(_utf16(folder.repeated_name))
        output.extend(_utf16(folder.cloud_id))
        output.extend(_u8(folder.sequence))
        output.extend(_u32(folder.flags))
        output.extend(folder.folder_guid.bytes_le)
        output.extend(_u64(folder.modified_filetime))
        output.extend(_u64(folder.unknown))
        output.extend(_u64(folder.size))
    return bytes(output)


def read_wgs_index(slot_path: Path | str) -> WgsIndex:
    slot = Path(slot_path)
    index_path = slot / "containers.index" if slot.is_dir() else slot
    return parse_wgs_index_bytes(index_path.read_bytes(), index_path)


def parse_wgs_file_list(path: Path | str, *, require_files: bool = True) -> WgsFileList:
    source = Path(path)
    match = re.fullmatch(r"container\.(\d+)", source.name, flags=re.IGNORECASE)
    if not match:
        raise WgsFormatError(f"WGS file list has an invalid name: {source.name}")
    sequence = int(match.group(1))
    reader = _Reader(source.read_bytes(), source)
    version = reader.u32()
    if version != WGS_FILE_LIST_VERSION:
        raise WgsFormatError(
            f"{source} uses unsupported WGS file-list version {version}; expected {WGS_FILE_LIST_VERSION}"
        )
    count = reader.u32()
    if count > MAX_WGS_FILES:
        raise WgsFormatError(f"{source} declares an unreasonable file count {count}")
    entries: list[WgsFileEntry] = []
    for _ in range(count):
        name = reader.fixed_utf16(WGS_FILE_NAME_CHARS)
        primary = reader.guid_le()
        secondary = reader.guid_le()
        primary_path = source.parent / primary.hex.upper()
        secondary_path = source.parent / secondary.hex.upper()
        actual = primary_path if primary_path.is_file() else secondary_path if secondary_path.is_file() else None
        if require_files and actual is None:
            raise WgsFormatError(f"{source} references a missing logical file {name!r}")
        entries.append(WgsFileEntry(name, primary, secondary, actual))
    reader.finish()
    return WgsFileList(version, sequence, tuple(entries), source)


def serialize_wgs_file_list(
    sequence: int,
    entries: Iterable[tuple[str, uuid.UUID, uuid.UUID | None]],
) -> bytes:
    items = list(entries)
    if len(items) > MAX_WGS_FILES:
        raise WgsFormatError(f"WGS file list has too many entries: {len(items)}")
    output = bytearray(_u32(WGS_FILE_LIST_VERSION) + _u32(len(items)))
    for name, primary, secondary in items:
        output.extend(_fixed_utf16(name))
        output.extend(primary.bytes_le)
        output.extend((secondary or primary).bytes_le)
    return bytes(output)


def find_wgs_slots(roots: Iterable[Path | str]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add(candidate: Path) -> None:
        if not candidate.is_dir() or not (candidate / "containers.index").is_file():
            return
        try:
            key = str(candidate.resolve()).casefold()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        found.append(candidate)

    for raw_root in roots:
        root = Path(raw_root)
        if root.is_file() and root.name.casefold() == "containers.index":
            add(root.parent)
            continue
        add(root)
        candidates = [root]
        package_wgs = root / "SystemAppData" / "wgs"
        if package_wgs.is_dir():
            candidates.append(package_wgs)
        if root.name.casefold() != "wgs" and (root / "wgs").is_dir():
            candidates.append(root / "wgs")
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            try:
                children = [item for item in candidate.iterdir() if item.is_dir()]
            except OSError:
                continue
            for child in children:
                if WGS_SLOT_PATTERN.fullmatch(child.name) or (child / "containers.index").is_file():
                    add(child)
    found.sort(
        key=lambda path: (path / "containers.index").stat().st_mtime if (path / "containers.index").is_file() else 0,
        reverse=True,
    )
    return found


def read_wgs_layer_groups(slot_path: Path | str) -> list[WgsLayerGroup]:
    slot = Path(slot_path)
    index = read_wgs_index(slot)
    groups: list[WgsLayerGroup] = []
    for folder in index.folders:
        if not folder.name.casefold().startswith("layergroup_"):
            continue
        file_list_path = slot / folder.directory_name / f"container.{folder.sequence}"
        if not file_list_path.is_file():
            continue
        try:
            file_list = parse_wgs_file_list(file_list_path)
        except (OSError, WgsFormatError):
            continue
        group = WgsLayerGroup(slot, folder, file_list)
        if group.cgroup_path and group.cgroup_path.is_file():
            groups.append(group)
    groups.sort(
        key=lambda group: group.cgroup_path.stat().st_mtime if group.cgroup_path and group.cgroup_path.is_file() else 0,
        reverse=True,
    )
    return groups


def find_wgs_layer_group_for_blob(path: Path | str) -> WgsLayerGroup | None:
    source = Path(path)
    try:
        source_key = str(source.resolve()).casefold()
    except OSError:
        return None
    folder = source.parent
    slot = folder.parent
    if not (slot / "containers.index").is_file():
        return None
    try:
        groups = read_wgs_layer_groups(slot)
    except (OSError, WgsFormatError):
        return None
    for group in groups:
        for entry in group.file_list.entries:
            if entry.actual_path is None:
                continue
            try:
                if str(entry.actual_path.resolve()).casefold() == source_key:
                    return group
            except OSError:
                continue
    return None


def logical_wgs_sibling(path: Path | str, logical_name: str) -> Path | None:
    group = find_wgs_layer_group_for_blob(path)
    return group.file(logical_name) if group else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slot_snapshot(slot: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(slot.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(slot)
        if any(".kfps" in part.casefold() for part in relative.parts):
            continue
        snapshot[relative.as_posix()] = (path.stat().st_size, _file_sha256(path))
    return snapshot


def _write_bytes_fsync(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_bytes_fsync(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.kfps-{uuid.uuid4().hex}.tmp")
    try:
        _write_bytes_fsync(temp, data)
        os.replace(temp, path)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def _unique_backup_path(backup_root: Path, slot: Path, now: datetime) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stem = f"{slot.name}-{now.strftime('%Y%m%d-%H%M%S')}"
    candidate = backup_root / stem
    suffix = 2
    while candidate.exists():
        candidate = backup_root / f"{stem}-{suffix}"
        suffix += 1
    return candidate


def _unique_container_name(index: WgsIndex, now: datetime) -> tuple[str, datetime]:
    existing = {folder.name.casefold() for folder in index.folders}
    candidate_time = now
    for _ in range(86_400):
        name = f"LayerGroup_0000_{candidate_time.strftime('%Y%m%d%H%M%S')}"
        if name.casefold() not in existing:
            return name, candidate_time
        candidate_time += timedelta(seconds=1)
    raise WgsFormatError("Could not allocate a unique FH4 LayerGroup name")


def create_wgs_layer_group(
    slot_path: Path | str,
    template: WgsLayerGroup,
    *,
    cgroup_data: bytes,
    header_data: bytes,
    thumbnail_data: bytes,
    backup_root: Path | str,
    now: datetime | None = None,
) -> WgsCreateResult:
    """Create and verify a new WGS layer-group container.

    The caller must ensure FH4 is closed before invoking this function.
    """

    slot = Path(slot_path).resolve()
    if not slot.is_dir() or not (slot / "containers.index").is_file():
        raise WgsFormatError(f"FH4 WGS slot is missing containers.index: {slot}")
    if template.slot_path.resolve() != slot:
        raise WgsFormatError("FH4 WGS template belongs to a different account slot")
    if not cgroup_data or not header_data or not thumbnail_data:
        raise WgsFormatError("FH4 WGS import requires C_group, header, and thumbnail data")

    index_path = slot / "containers.index"
    original_index_bytes = index_path.read_bytes()
    index = parse_wgs_index_bytes(original_index_bytes, index_path)
    roundtrip = serialize_wgs_index(index)
    if roundtrip != original_index_bytes:
        raise WgsFormatError("FH4 containers.index failed the byte-for-byte round-trip safety gate")
    template_folder = next(
        (folder for folder in index.folders if folder.folder_guid == template.folder.folder_guid),
        None,
    )
    if template_folder is None:
        raise WgsFormatError("FH4 template layer group is no longer present in containers.index")
    template_file_bytes = template.file_list.path.read_bytes()
    parsed_template_files = parse_wgs_file_list(template.file_list.path)
    if serialize_wgs_file_list(
        parsed_template_files.sequence,
        ((item.name, item.primary_guid, item.secondary_guid) for item in parsed_template_files.entries),
    ) != template_file_bytes:
        raise WgsFormatError("FH4 container file list failed the byte-for-byte round-trip safety gate")

    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.astimezone()
    container_name, container_time = _unique_container_name(index, moment)
    modified_filetime = datetime_to_filetime(container_time)
    existing_guids = {folder.folder_guid for folder in index.folders}
    folder_guid = uuid.uuid4()
    while folder_guid in existing_guids or (slot / folder_guid.hex.upper()).exists():
        folder_guid = uuid.uuid4()

    cgroup_guid = uuid.uuid4()
    header_guid = uuid.uuid4()
    thumbnail_guid = uuid.uuid4()
    sequence = int(template_folder.sequence)
    file_entries = (
        ("C_group", cgroup_guid, cgroup_guid),
        ("header", header_guid, header_guid),
        ("thumb.png", thumbnail_guid, thumbnail_guid),
    )
    file_list_bytes = serialize_wgs_file_list(sequence, file_entries)
    new_folder = WgsFolderEntry(
        name=container_name,
        repeated_name=container_name,
        cloud_id="",
        sequence=sequence,
        flags=5,
        folder_guid=folder_guid,
        modified_filetime=modified_filetime,
        unknown=0,
        size=len(cgroup_data) + len(header_data) + len(thumbnail_data),
    )
    new_index = replace(
        index,
        modified_filetime=modified_filetime,
        folders=index.folders + (new_folder,),
    )
    new_index_bytes = serialize_wgs_index(new_index)
    parsed_new_index = parse_wgs_index_bytes(new_index_bytes, "staged FH4 containers.index")
    if serialize_wgs_index(parsed_new_index) != new_index_bytes:
        raise WgsFormatError("Staged FH4 containers.index failed independent reserialization")

    original_snapshot = _slot_snapshot(slot)
    backup = _unique_backup_path(Path(backup_root), slot, moment)
    shutil.copytree(slot, backup)
    if _slot_snapshot(slot) != original_snapshot:
        raise WgsConcurrentChangeError("FH4 save changed while KFPS was making the safety backup; no import was written")

    final_folder = slot / folder_guid.hex.upper()
    staging_folder = slot / f".{folder_guid.hex.upper()}.kfps-{uuid.uuid4().hex}.tmp"
    index_replaced = False
    folder_committed = False
    try:
        staging_folder.mkdir()
        _write_bytes_fsync(staging_folder / cgroup_guid.hex.upper(), cgroup_data)
        _write_bytes_fsync(staging_folder / header_guid.hex.upper(), header_data)
        _write_bytes_fsync(staging_folder / thumbnail_guid.hex.upper(), thumbnail_data)
        _write_bytes_fsync(staging_folder / f"container.{sequence}", file_list_bytes)
        staged_list = parse_wgs_file_list(staging_folder / f"container.{sequence}")
        staged_files = {entry.name.casefold(): entry.actual_path for entry in staged_list.entries}
        expected_staged = {
            "c_group": cgroup_data,
            "header": header_data,
            "thumb.png": thumbnail_data,
        }
        for logical_name, expected_data in expected_staged.items():
            staged_path = staged_files.get(logical_name)
            if staged_path is None or staged_path.read_bytes() != expected_data:
                raise WgsFormatError(f"Staged FH4 logical file failed verification: {logical_name}")

        if _slot_snapshot(slot) != original_snapshot:
            raise WgsConcurrentChangeError("FH4 save changed while KFPS was staging the import; no import was committed")
        os.replace(staging_folder, final_folder)
        folder_committed = True
        _replace_bytes_fsync(index_path, new_index_bytes)
        index_replaced = True

        verified_index = read_wgs_index(slot)
        if len(verified_index.folders) != len(index.folders) + 1:
            raise WgsFormatError("FH4 containers.index did not retain the new layer group")
        verified_group = next(
            (group for group in read_wgs_layer_groups(slot) if group.folder.folder_guid == folder_guid),
            None,
        )
        if verified_group is None:
            raise WgsFormatError("FH4 WGS import could not reopen the new layer group")
        cgroup_path = verified_group.cgroup_path
        header_path = verified_group.header_path
        thumbnail_path = verified_group.thumbnail_path
        if not cgroup_path or cgroup_path.read_bytes() != cgroup_data:
            raise WgsFormatError("FH4 WGS import C_group verification failed")
        if not header_path or header_path.read_bytes() != header_data:
            raise WgsFormatError("FH4 WGS import header verification failed")
        if not thumbnail_path or thumbnail_path.read_bytes() != thumbnail_data:
            raise WgsFormatError("FH4 WGS import thumbnail verification failed")
        return WgsCreateResult(
            slot_path=slot,
            folder_path=final_folder,
            container_name=container_name,
            cgroup_path=cgroup_path,
            header_path=header_path,
            thumbnail_path=thumbnail_path,
            backup_path=backup,
        )
    except Exception:
        if index_replaced:
            try:
                _replace_bytes_fsync(index_path, original_index_bytes)
            except OSError:
                pass
        if folder_committed and final_folder.is_dir():
            shutil.rmtree(final_folder, ignore_errors=True)
        raise
    finally:
        if staging_folder.is_dir():
            shutil.rmtree(staging_folder, ignore_errors=True)
