"""Bounded disposable viewer caches, never Studio project/recovery directories."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .prepare import LAB_ROOT, atomic_json
from .readonly_preview import ordinary_path

OWNER_FORMAT = 'kfps-readonly-viewer-cache-v1'
MAX_CACHE_BYTES = 2 * 1024**3
MAX_ENTRY_FILES = 4096
INVENTORY = 'viewer-owned.json'
LOCK_FILES = {'viewer.lock', 'backend.lock'}


def file_inventory(root):
    """Exact ordinary-file ownership; unknown content is never adopted by prune."""
    root = Path(root)
    result = {}
    for count, path in enumerate(root.rglob('*')):
        if count >= MAX_ENTRY_FILES:
            raise ValueError('Viewer cache contains too many entries.')
        ordinary_path(path, root)
        info = path.stat()
        if path.is_dir():
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Viewer cache contains a redirected or linked file.')
        name = path.relative_to(root).as_posix()
        if name not in LOCK_FILES | {INVENTORY}:
            result[name] = [info.st_size, info.st_mtime_ns]
    return result


def verify_inventory(root, *, create=False):
    root = Path(root)
    actual = file_inventory(root)
    directories = sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_dir())
    path = ordinary_path(root / INVENTORY, root)
    if not path.exists():
        if actual or directories or not create or any(root.iterdir()):
            raise ValueError('Untracked viewer cache files were preserved. Use a new cache location.')
        atomic_json(path, {'format': OWNER_FORMAT, 'files': {}, 'directories': []})
        return actual
    with path.open('rb') as stream:
        body = stream.read(1024**2 + 1)
    if len(body) > 1024**2:
        raise ValueError('Viewer cache ownership inventory is too large.')
    value = json.loads(body)
    if value != {'format': OWNER_FORMAT, 'files': actual, 'directories': directories}:
        raise ValueError('Unknown or modified viewer cache files were preserved.')
    return actual


def seal_inventory(root):
    # Called only by the producer while holding its cache lease, after its
    # previously recorded inventory was verified before any generation.
    root = Path(root)
    files = file_inventory(root)
    directories = sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_dir())
    atomic_json(root / INVENTORY, {'format': OWNER_FORMAT, 'files': files, 'directories': directories})


def _delete_owned(root, names):
    known = verify_inventory(root)
    for name in names:
        if name not in known:
            raise ValueError('Refusing to remove an unowned preview file.')
    for name in names:
        ordinary_path(Path(root) / name, root).unlink()
    for directory in sorted((p for p in Path(root).rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        ordinary_path(directory, root)
        if not any(directory.iterdir()):
            directory.rmdir()
    seal_inventory(root)


def _prune_artifacts(entry, *, target_bytes, protected_outputs=()):
    known = verify_inventory(entry)
    total = sum(value[0] for value in known.values())
    protected = {Path(path).absolute() for path in protected_outputs}
    groups = {}
    for name in known:
        parts = Path(name).parts
        if len(parts) >= 3 and parts[0] == 'saved-atlases':
            groups.setdefault(parts[1], []).append(name)
    removed = files = 0
    for key, names in sorted(groups.items(), key=lambda item: min(known[name][1] for name in item[1])):
        if total <= target_bytes and len(groups) <= 6:
            break
        output = entry / 'saved-atlases' / key
        touched = max(known[name][1] for name in names) / 1e9
        if output in protected or time.time() - touched < 60:
            continue
        prefix = 'saved-atlases/' + key + '/'
        for name in known:
            if re.fullmatch(r'readonly-[a-f0-9]{64}\.json', name):
                descriptor = json.loads((entry / name).read_text(encoding='utf-8'))
                if str(descriptor.get('files', {}).get('paint', '')).startswith(prefix):
                    names.append(name)
        size = sum(known[name][0] for name in names)
        _delete_owned(entry, names)
        removed += size
        files += len(names)
        total -= size
        groups.pop(key)
    return removed, files


def admit_artifact(kfps_root, reservation_bytes, *, protected=(), protected_outputs=()):
    """Reserve a bounded producer allowance before starting expensive work.

    Caller holds the installation-wide cache lease until publication. This
    serializes admission across KFPS instances without changing the renderer.
    """
    if type(reservation_bytes) is not int or not 0 <= reservation_bytes <= MAX_CACHE_BYTES:
        raise ValueError('Invalid viewer cache reservation.')
    result = prune_cache(kfps_root, protected=protected, protected_outputs=protected_outputs,
                         target_bytes=MAX_CACHE_BYTES - reservation_bytes)
    if result['bytes'] + reservation_bytes > MAX_CACHE_BYTES:
        raise ValueError('The viewer cache is full or in use. Close other previews or clear its cache, then retry.')
    return result


def enforce_budget(kfps_root, current_entry):
    """Fail publication and discard only recorded generated files on overshoot.

    The producer still holds both installation and car leases. A failed or
    unexpectedly large conversion cannot leave a successful over-budget cache.
    """
    if sum(row[2] for row in cache_entries(kfps_root)) > MAX_CACHE_BYTES:
        _delete_owned(current_entry, list(verify_inventory(current_entry)))
        raise ValueError('The generated preview exceeded the cache budget and was not published. No user files were removed.')


def cache_root(kfps_root, *, create=False):
    identity = os.path.normcase(str(Path(kfps_root).resolve()))
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    root = LAB_ROOT / 'runs/readonly-viewer' / key
    ordinary_path(root, LAB_ROOT)
    marker = root / 'owner.json'
    expected = {'format': OWNER_FORMAT, 'kfps_root': identity}
    if root.exists():
        ordinary_path(marker, root)
        try:
            value = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError('Viewer cache ownership is unavailable; it was not modified.') from error
        if value != expected:
            raise ValueError('Viewer cache belongs to another installation.')
    elif create:
        root.mkdir(parents=True)
        atomic_json(marker, expected)
    return root


@contextmanager
def cache_lease(root, *, wait_seconds=3):
    path = ordinary_path(Path(root) / 'viewer.lock', root)
    with path.open('a+b') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Viewer cache lock is not an ordinary file.')
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise ValueError('This viewer car cache is still in use.') from error
                time.sleep(.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def cache_entries(kfps_root):
    root = cache_root(kfps_root)
    cars = root / 'cars'
    if not cars.exists():
        return []
    ordinary_path(cars, root)
    entries = []
    for entry in cars.iterdir():
        if not re.fullmatch(r'[a-f0-9]{32}', entry.name):
            raise ValueError('Unexpected content in the disposable viewer cache.')
        ordinary_path(entry, root)
        if not entry.is_dir():
            raise ValueError('Invalid viewer cache directory.')
        if len(entries) >= 64:
            raise ValueError('Viewer cache has too many car entries.')
        known = verify_inventory(entry)
        size = sum(row[0] for row in known.values()) + (entry / INVENTORY).stat().st_size
        entries.append((entry.stat().st_mtime, entry, size, len(known) + 1))
    return entries


def prune_cache(kfps_root, *, protected=(), clear=False, protected_outputs=(), target_bytes=None):
    target_bytes = MAX_CACHE_BYTES if target_bytes is None else target_bytes
    entries = cache_entries(kfps_root)
    total = sum(row[2] for row in entries)
    removed = files = 0
    remaining = len(entries)
    protected = {Path(path).resolve() for path in protected}
    root = cache_root(kfps_root)
    for touched, entry, size, count in sorted(entries):
        if not clear and total <= target_bytes and remaining <= 6:
            break
        lease = cache_lease(entry, wait_seconds=3 if clear else 0)
        try:
            lease.__enter__()
        except ValueError:
            if clear:
                raise
            continue
        delete_entry = clear or entry.resolve() not in protected and time.time() - touched >= 60
        try:
            if not delete_entry:
                amount, count_removed = _prune_artifacts(entry, target_bytes=max(0, size - (total - target_bytes)),
                                                         protected_outputs=protected_outputs)
                total -= amount
                removed += amount
                files += count_removed
                continue
            known = verify_inventory(entry)
            _delete_owned(entry, list(known))
            (entry / INVENTORY).unlink()
            for name in LOCK_FILES - {'viewer.lock'}:
                (entry / name).unlink(missing_ok=True)
        finally:
            lease.__exit__(None, None, None)
        (entry / 'viewer.lock').unlink()
        entry.rmdir()
        total -= size
        remaining -= 1
        removed += size
        files += count
    total = sum(row[2] for row in cache_entries(kfps_root))
    return {'bytes': total, 'removed_bytes': removed, 'removed_files': files, 'budget_bytes': MAX_CACHE_BYTES}
