"""On-demand, read-only FH6 account discovery; no Garage decoding or workers.

Rows contain only id, label, directory, source and available. The id identifies
the canonical account directory, not a rotating save version. Unavailable primary
profiles have source="". Call resolve_account again before using a saved row.
Primary layouts are Profile/C_ProfileData and User_<verified-id>/C_ProfileData;
two primaries are ambiguous even if they share the same underlying file.
Cancellation raises InterruptedError and never returns a partial account list.
Display names are optional, bounded local metadata enrichment during discovery
or manual recognition only. They never participate in account/source validation.
"""
from __future__ import annotations

import hashlib
from itertools import islice
import os
from pathlib import Path
import stat
import unicodedata

from tools.cgroup.fh6_identity import ACCOUNT_NAME, USER_NAME, SaveAccount, read_account, resolve_creator

from .garage_index import GarageError


MAX_ROOTS = 32
MAX_POINTER_ENTRIES = 256
MAX_ROOT_ENTRIES = 512
MAX_CONTAINER_ENTRIES = 32768
MAX_CANDIDATES = 128
MAX_ACCOUNTS = 64
MAX_PROFILE_BYTES = 128 * 1024 * 1024
MAX_NAME_ENTRIES = 1024
MAX_NAME_LENGTH = 128
MAX_HEADER_BYTES = 65536
UNAVAILABLE = "The FH6 account or current primary profile is unavailable or ambiguous. Refresh accounts and try again."
_INVALID = (OSError, ValueError, TypeError, RuntimeError, OverflowError)


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Garage account discovery cancelled.")


def _children(directory, limit, cancel):
    _check_cancel(cancel)
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            _check_cancel(cancel)
            if index >= limit:
                raise ValueError("Directory limit exceeded.")
            yield Path(entry.path)
    _check_cancel(cancel)


class _AccountPath(type(Path())):
    """Keep the shared verifier's directory iteration streaming and cancelable.

    Python 3.12 with_segments propagates the budget to paths made by read_account;
    the shared verifier and its offline-transfer behavior remain unchanged.
    """

    def __init__(self, *segments, cancel=None):
        super().__init__(*segments)
        self._cancel = cancel

    def with_segments(self, *segments):
        return type(self)(*segments, cancel=self._cancel)

    def iterdir(self):
        for child in _children(self, MAX_CONTAINER_ENTRIES, self._cancel):
            yield self / child.name


def _absolute(value):
    path = Path(value)
    if (not path.is_absolute() or len(str(path)) > 32768
            or any(ord(char) < 32 for char in str(path))
            or ".." in path.parts or path.drive.startswith("\\\\")):
        raise ValueError("Unsupported local path.")
    return path


def _same_current(account):
    version = (account.directory / "current").resolve(strict=True)
    if (version != account.containers.parent
            or (version / "ContainersRoot").resolve(strict=True) != account.containers):
        raise ValueError("Current save changed.")


def _verified(directory, cancel=None):
    _check_cancel(cancel)
    directory = _absolute(directory)
    if (not ACCOUNT_NAME.fullmatch(directory.name)
            or directory.resolve(strict=True) != directory):
        raise ValueError("Unsupported account directory.")
    account = read_account(_AccountPath(directory, cancel=cancel))
    _check_cancel(cancel)
    account = SaveAccount(Path(account.directory), Path(account.containers),
                          account.user_id, account.manifest)
    _same_current(account)
    return account


def _primary_candidate(account, cancel):
    candidates = []
    for folder in _children(account.containers, MAX_CONTAINER_ENTRIES, cancel):
        user = USER_NAME.fullmatch(folder.name)
        if folder.name.casefold() != "profile" and not (user and int(user[1], 16) == account.user_id):
            continue
        if folder.resolve(strict=True) != folder or not folder.is_dir():
            raise ValueError("Primary profile container is redirected or unavailable.")
        source = folder / "C_ProfileData"
        try:
            source.lstat()
        except FileNotFoundError:
            continue
        # A broken link or inaccessible alternative must not silently select the
        # other layout. Count entries before testing their contents or usability.
        candidates.append(source)
        if len(candidates) > 1:
            raise ValueError("Ambiguous primary profiles.")
    if not candidates:
        raise ValueError("Primary profile is unavailable.")
    return candidates[0]


def _primary(account, cancel=None):
    _check_cancel(cancel)
    source = _primary_candidate(account, cancel)
    folder = source.parent
    if folder.resolve(strict=True) != folder or source.resolve(strict=True) != source:
        raise ValueError("Primary profile is redirected.")
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PROFILE_BYTES:
        raise ValueError("Unsupported primary profile.")
    # Opening without reading checks access. Never read/decode the profile here.
    with source.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PROFILE_BYTES:
            raise ValueError("Unsupported primary profile.")
    _check_cancel(cancel)
    _same_current(account)
    if folder.resolve(strict=True) != folder or source.resolve(strict=True) != source:
        raise ValueError("Primary profile changed.")
    return source


def _name_stat(path):
    info = path.lstat()
    # Reject reparse points before resolving, including junctions to remote paths.
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or path.resolve(strict=True) != path):
        raise ValueError("Creator metadata is redirected.")
    return info


def _name_headers(account, cancel):
    for folder in _children(account.containers, MAX_NAME_ENTRIES, cancel):
        if not folder.name.casefold().startswith("layergroup_"):
            continue
        _check_cancel(cancel)
        if not stat.S_ISDIR(_name_stat(folder).st_mode):
            raise ValueError("Creator metadata container is unavailable.")
        path = folder / "header"
        before = _name_stat(path)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_HEADER_BYTES:
            raise ValueError("Unsupported creator metadata.")
        _check_cancel(cancel)
        yield path
        _check_cancel(cancel)
        _name_stat(folder)
        after = _name_stat(path)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("Creator metadata changed.")


def _display_name(account, cancel):
    try:
        name = resolve_creator(account, header_paths=_name_headers(account, cancel)).name
        _check_cancel(cancel)
        # The picker is PlainText, but shared hover tooltips can auto-detect rich
        # text. Reject markup as well as invisible controls and filler characters.
        if any(char in name for char in "<>&"):
            return ""
        if any(unicodedata.category(char).startswith("C")
               or unicodedata.category(char) in ("Zl", "Zp")
               or char in "\u034f\u115f\u1160\u17b4\u17b5\u2800\u3164\uffa0"
               or "\ufe00" <= char <= "\ufe0f" or "\U000e0100" <= char <= "\U000e01ef"
               for char in name):
            return ""
        name = name.strip()
        return name if 0 < len(name) <= MAX_NAME_LENGTH else ""
    except InterruptedError:
        raise
    except _INVALID:
        _check_cancel(cancel)
        return ""


def _row(account, cancel=None, *, source=None):
    if source is None:
        try:
            source = str(_primary(account, cancel))
        except InterruptedError:
            raise
        except _INVALID:
            source = ""
    name = _display_name(account, cancel)
    _check_cancel(cancel)
    _same_current(account)
    _check_cancel(cancel)
    identity = hashlib.sha256(os.path.normcase(str(account.directory)).encode("utf-8")).hexdigest()
    # A directory-derived suffix also distinguishes the same user on two drives.
    prefix = f"{name} -" if name else "FH6 account"
    return {"id": identity, "label": f"{prefix} {str(account.user_id)[-6:]} ({identity[:8]})",
            "directory": str(account.directory), "source": source, "available": bool(source)}


def resolve_account(directory: str | Path) -> Path:
    """Reverify an account and return its exact current primary profile.

    Missing, oversized, redirected, backup-only and changing saves fail closed.
    The generic error deliberately contains neither a source path nor an ID.
    """
    try:
        return _primary(_verified(directory))
    except _INVALID:
        raise GarageError(UNAVAILABLE) from None


def account_for_source(source, cancel=None) -> dict | None:
    """Recognize an exact current primary in either verified profile layout.

    Both the current alias and its active numbered target are accepted. A copied
    file, unrelated symlink, backup, old version, folder or export is not adopted.
    """
    try:
        _check_cancel(cancel)
        path = _absolute(source)
        user = USER_NAME.fullmatch(path.parent.name)
        if (path.name.casefold() != "c_profiledata"
                or (path.parent.name.casefold() != "profile" and not user)
                or path.parent.parent.name.casefold() != "containersroot"):
            return None
        version = path.parents[2]
        directory = version.parent
        if version.name.casefold() != "current" and not version.name.isdecimal():
            return None
        account = _verified(directory, cancel)
        if user and int(user[1], 16) != account.user_id:
            return None
        if version not in (directory / "current", account.containers.parent):
            return None
        primary = _primary(account, cancel)
        if path.resolve(strict=True) != primary:
            return None
        return _row(account, cancel, source=str(primary))
    except InterruptedError:
        raise
    except _INVALID:
        return None


def _drive_type(drive):
    if os.name != "nt":
        return 0
    import ctypes
    get_type = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
    get_type.argtypes = [ctypes.c_wchar_p]
    get_type.restype = ctypes.c_uint
    return get_type(str(drive))


def _default_roots():
    # Check the drive type before any path probe: mapped letters can be remote.
    try:
        drives = os.listdrives() if hasattr(os, "listdrives") else ("C:/",)
    except OSError:
        drives = ("C:/",)
    for drive in islice(drives, MAX_ROOTS):
        try:
            if _drive_type(drive) not in (2, 3):  # DRIVE_REMOVABLE, DRIVE_FIXED
                continue
        except (OSError, ValueError):
            continue
        yield Path(drive) / "XboxGames" / "GameSave"


def _pointer_selections(local, cancel):
    bases = (local / "ForzaHorizon6", local / "Packages"
             / "Microsoft.ForteBaseGame_8wekyb3d8bbwe" / "LocalCache" / "Local")
    for base in bases:
        _check_cancel(cancel)
        try:
            if base.resolve(strict=True) != base:
                continue
            for metadata in _children(base, MAX_POINTER_ENTRIES, cancel):
                if not metadata.name.startswith("SaveFolderMetadata_"):
                    continue
                try:
                    ident = metadata.name.removeprefix("SaveFolderMetadata_")
                    if not ident or len(ident) > 16 or any(c not in "0123456789abcdefABCDEF" for c in ident):
                        continue
                    pointer = metadata / "LastSaveFolderLocation"
                    if metadata.resolve(strict=True) != metadata or pointer.resolve(strict=True) != pointer:
                        continue
                    if not stat.S_ISREG(pointer.stat().st_mode):
                        continue
                    _check_cancel(cancel)
                    with pointer.open("rb") as stream:
                        raw = stream.read(4097)
                    _check_cancel(cancel)
                    if len(raw) > 4096:
                        continue
                    selected = _absolute(raw.decode("utf-8-sig").strip().rstrip("\x00"))
                    directory = next((p for p in (selected, *selected.parents)
                                      if ACCOUNT_NAME.fullmatch(p.name)), None)
                    if directory is not None:
                        yield directory, selected, int(ident, 16)
                except InterruptedError:
                    raise
                except _INVALID:
                    continue
        except InterruptedError:
            raise
        except _INVALID:
            continue


def _root_candidates(root, cancel):
    root = _absolute(root)
    if root.resolve(strict=True) != root:
        return
    if ACCOUNT_NAME.fullmatch(root.name):
        yield root
        return
    if root.name.casefold() == "xboxgames":
        root = root / "GameSave"
    for base in (root, root / "pgs"):
        _check_cancel(cancel)
        try:
            if base.resolve(strict=True) != base:
                continue
            for child in _children(base, MAX_ROOT_ENTRIES, cancel):
                if ACCOUNT_NAME.fullmatch(child.name):
                    yield child
        except InterruptedError:
            raise
        except _INVALID:
            continue


def discover_accounts(cancel, *, roots=None, local_app_data=None) -> list[dict]:
    """List verified FH6 accounts from both pointers and shallow fallback roots.

    roots overrides the local fixed/removable XboxGames defaults (an empty
    iterable disables fallback). Default probes exclude mapped network drives.
    Each root may be XboxGames, GameSave, pgs, or an account directory. None for
    local_app_data uses LOCALAPPDATA. Invalid/stale pointers do not suppress other
    verified accounts. No numbered versions are enumerated. Filesystem calls are
    synchronous; cancellation is checked between bounded reads/iteration steps.
    """
    _check_cancel(cancel)
    found = {}
    attempted = set()

    def accept(directory, selected=None, user_id=None):
        _check_cancel(cancel)
        if len(attempted) >= MAX_CANDIDATES or len(found) >= MAX_ACCOUNTS:
            return
        key = (directory, selected, user_id)
        if key in attempted or str(directory) in found:
            return
        attempted.add(key)
        try:
            account = _verified(directory, cancel)
            if selected is not None:
                allowed = (directory, directory / "current", directory / "current" / "ContainersRoot",
                           account.containers.parent, account.containers)
                if selected not in allowed or account.user_id != user_id:
                    return
            found[str(account.directory)] = _row(account, cancel)
        except InterruptedError:
            raise
        except _INVALID:
            return

    local = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
    if local:
        try:
            for directory, selected, user_id in _pointer_selections(_absolute(local), cancel):
                accept(directory, selected, user_id)
                if len(attempted) >= MAX_CANDIDATES or len(found) >= MAX_ACCOUNTS:
                    break
        except InterruptedError:
            raise
        except _INVALID:
            pass
    if roots is None:
        roots = _default_roots()
    for root in islice(roots, MAX_ROOTS):
        _check_cancel(cancel)
        if len(attempted) >= MAX_CANDIDATES or len(found) >= MAX_ACCOUNTS:
            break
        try:
            for directory in _root_candidates(root, cancel):
                accept(directory)
                if len(attempted) >= MAX_CANDIDATES or len(found) >= MAX_ACCOUNTS:
                    break
        except InterruptedError:
            raise
        except _INVALID:
            continue
    _check_cancel(cancel)
    return sorted(found.values(), key=lambda row: (row["label"], row["id"]))
