"""Bounded disposable viewer caches, never Studio project/recovery directories."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .prepare import LAB_ROOT, atomic_json, viewer_cache_base
from .file_io import io_path, logical_path, resolved_path
from .readonly_preview import ordinary_path

OWNER_FORMAT = 'kfps-readonly-viewer-cache-v1'
MAX_CACHE_BYTES = 2 * 1024**3
MAX_ENTRY_FILES = 4096
INVENTORY = 'viewer-owned.json'
LOCK_FILES = {'viewer.lock', 'backend.lock'}


def file_inventory(root):
    """Exact ordinary-file ownership; unknown content is never adopted by prune."""
    root = logical_path(root)
    result = {}
    for count, native in enumerate(io_path(root).rglob('*')):
        path = logical_path(native)
        if count >= MAX_ENTRY_FILES:
            raise ValueError('Viewer cache contains too many entries.')
        ordinary_path(path, root)
        info = native.stat()
        if native.is_dir():
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Viewer cache contains a redirected or linked file.')
        name = path.relative_to(root).as_posix()
        if name not in LOCK_FILES | {INVENTORY}:
            result[name] = [info.st_size, info.st_mtime_ns]
    return result


def verify_inventory(root, *, create=False):
    root = logical_path(root)
    actual = file_inventory(root)
    directories = sorted(logical_path(path).relative_to(root).as_posix()
                         for path in io_path(root).rglob('*') if path.is_dir())
    path = ordinary_path(root / INVENTORY, root)
    if not io_path(path).exists():
        if actual or directories or not create or any(io_path(root).iterdir()):
            raise ValueError('Untracked viewer cache files were preserved. Use a new cache location.')
        atomic_json(path, {'format': OWNER_FORMAT, 'files': {}, 'directories': []})
        return actual
    with io_path(path).open('rb') as stream:
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
    root = logical_path(root)
    files = file_inventory(root)
    directories = sorted(logical_path(path).relative_to(root).as_posix()
                         for path in io_path(root).rglob('*') if path.is_dir())
    atomic_json(root / INVENTORY, {'format': OWNER_FORMAT, 'files': files, 'directories': directories})


def _delete_owned(root, names):
    known = verify_inventory(root)
    for name in names:
        if name not in known:
            raise ValueError('Refusing to remove an unowned preview file.')
    for name in names:
        io_path(ordinary_path(Path(root) / name, root)).unlink()
    for directory in sorted((p for p in io_path(root).rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        ordinary_path(directory, root)
        if not any(directory.iterdir()):
            directory.rmdir()
    seal_inventory(root)


def _prune_artifacts(entry, *, target_bytes, protected_outputs=()):
    known = verify_inventory(entry)
    total = sum(value[0] for value in known.values())
    protected = {logical_path(path) for path in protected_outputs}
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
                descriptor = json.loads(io_path(entry / name).read_text(encoding='utf-8'))
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


def _cache_root(kfps_root, *, legacy=False, create=False):
    identity = os.path.normcase(str(resolved_path(kfps_root)))
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    if legacy:
        root, boundary = LAB_ROOT / 'runs/readonly-viewer' / key, LAB_ROOT
    elif LAB_ROOT.name == 'livery-studio' and LAB_ROOT.parent.name == 'tools':
        root, boundary = viewer_cache_base() / key, LAB_ROOT.parents[1]
    else:
        root, boundary = viewer_cache_base() / key, LAB_ROOT
    root = ordinary_path(root, boundary)
    marker = root / 'owner.json'
    expected = {'format': OWNER_FORMAT, 'kfps_root': identity}
    native = io_path(root)
    if create and not native.exists():
        try:
            native.mkdir(parents=True)
        except FileExistsError:
            pass
        else:
            atomic_json(marker, expected)
    if native.exists():
        deadline = time.monotonic() + (1 if create else 0)
        while True:
            ordinary_path(marker, root)
            try:
                info = io_path(marker).stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
                    raise ValueError('Invalid ownership marker.')
                value = json.loads(io_path(marker).read_text(encoding='utf-8'))
                break
            except FileNotFoundError as error:
                if time.monotonic() < deadline:
                    time.sleep(.02)
                    continue
                raise ValueError('Viewer cache ownership is unavailable; it was not modified.') from error
            except (OSError, ValueError) as error:
                raise ValueError('Viewer cache ownership is unavailable; it was not modified.') from error
        if value != expected:
            raise ValueError('Viewer cache belongs to another installation.')
    return root


def cache_root(kfps_root, *, create=False):
    return _cache_root(kfps_root, create=create)


def cache_roots(kfps_root):
    """Both generations count toward the same budget; unknown files stay guarded."""
    return [cache_root(kfps_root), _cache_root(kfps_root, legacy=True)]


@contextmanager
def installation_cache_lease(kfps_root, *, create=False):
    # Keep the old installation lock first so an already-running older viewer
    # producer cannot race new preparation or cache cleanup.
    with ExitStack() as stack:
        for legacy in (True, False):
            root = _cache_root(kfps_root, legacy=legacy, create=create)
            if io_path(root).exists():
                stack.enter_context(cache_lease(root))
        yield


@contextmanager
def cache_lease(root, *, wait_seconds=3):
    path = ordinary_path(Path(root) / 'viewer.lock', root)
    with io_path(path).open('a+b') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Viewer cache lock is not an ordinary file.')
        if io_path(path).stat().st_size == 0:
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
    entries = []
    for root in cache_roots(kfps_root):
        cars = root / 'cars'
        if not io_path(cars).exists():
            continue
        ordinary_path(cars, root)
        for native in io_path(cars).iterdir():
            entry = logical_path(native)
            if not re.fullmatch(r'[a-f0-9]{32}', entry.name):
                raise ValueError('Unexpected content in the disposable viewer cache.')
            ordinary_path(entry, root)
            if not native.is_dir():
                raise ValueError('Invalid viewer cache directory.')
            if len(entries) >= 64:
                raise ValueError('Viewer cache has too many car entries.')
            known = verify_inventory(entry)
            size = sum(row[0] for row in known.values()) + io_path(entry / INVENTORY).stat().st_size
            entries.append((native.stat().st_mtime, entry, size, len(known) + 1))
    return entries


def prune_cache(kfps_root, *, protected=(), clear=False, protected_outputs=(), target_bytes=None):
    target_bytes = MAX_CACHE_BYTES if target_bytes is None else target_bytes
    entries = cache_entries(kfps_root)
    total = sum(row[2] for row in entries)
    removed = files = 0
    remaining = len(entries)
    protected = {resolved_path(path) for path in protected}
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
        delete_entry = clear or resolved_path(entry) not in protected and time.time() - touched >= 60
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
            io_path(entry / INVENTORY).unlink()
            for name in LOCK_FILES - {'viewer.lock'}:
                io_path(entry / name).unlink(missing_ok=True)
        finally:
            lease.__exit__(None, None, None)
        io_path(entry / 'viewer.lock').unlink()
        io_path(entry).rmdir()
        total -= size
        remaining -= 1
        removed += size
        files += count
    total = sum(row[2] for row in cache_entries(kfps_root))
    return {'bytes': total, 'removed_bytes': removed, 'removed_files': files, 'budget_bytes': MAX_CACHE_BYTES}
