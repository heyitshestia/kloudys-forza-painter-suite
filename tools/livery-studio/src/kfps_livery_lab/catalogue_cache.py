"""Bounded, on-demand installed catalogue acquisition. No game-file writes.

load_installed_catalogue returns database bytes (or None), status, provenance,
and path-free warning codes. Only provenance.current permits same-build use;
stale bytes are names-only reference material. Cancellation raises
InterruptedError, including when a usable older generation exists.

Each normalized source pathname owns two atomic receipt+SQLite envelopes and
one short-lived retry receipt. No paths, source bytes or reader configuration
are persisted. No in-process catalogue cache, polling, or cross-install pruning.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from .file_io import atomic_stream, io_path, logical_path
from .storage_paths import SafeRoot, StorageError

APP_ROOT = Path(__file__).resolve().parents[4]
READER_FORMAT = "kfps-catalogue-reader-v1"
CACHE_FORMAT = "kfps-catalogue-cache-v1"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_SCRIPT_BYTES = 4 * 1024 * 1024
MAX_READER_DEPENDENCIES = 8
MAX_RECEIPT_BYTES = 16 * 1024
MAX_PROVIDER_SECONDS = 45
MAX_LOCK_SECONDS = 5
MAX_VALIDATION_SECONDS = 5
MAX_PROGRESS_TICKS = 20000
MAX_BACKOFF_SECONDS = 30
SQLITE_MAGIC = b"SQLite format 3\0"
PART_TABLES = (
    "List_UpgradeCarBody", "List_UpgradeCarBodyChassisStiffness",
    "List_UpgradeCarBodyFrontBumper", "List_UpgradeCarBodyHood",
    "List_UpgradeCarBodyRearBumper", "List_UpgradeRearWing",
    "List_UpgradeCarBodySideSkirt",
)
REQUIRED_COLUMNS = {
    "VersionInfo": {"database_version"},
    "Data_Car": {"id", "medianame"},
    "Data_CarBody": {"id"},
    "List_PartManufacturer": {"id", "partmanufacturer"},
    "UpgradeTypes": {"id", "partname", "isexception", "name"},
    "Upgrades": {"id", "typeid", "level", "isexception", "name"},
    "Data_UpgradePart": {"id", "tablename", "categoryname", "partname", "hasrequiresgraphics"},
}
for _table in PART_TABLES:
    REQUIRED_COLUMNS[_table] = {"id", "level", "isstock", "manufacturerid"} | (
        {"ordinal"} if _table == "List_UpgradeRearWing" else {"carbodyid"})
REQUIRED_COLUMNS["List_UpgradeCarBody"].add("ordinal")
REQUIRED_COLUMNS["List_UpgradeCarBodyChassisStiffness"].add("requiresgraphics")
WARNING_CODES = frozenset({
    "source-unavailable", "source-size-invalid", "source-changed",
    "reader-unavailable", "reader-config-invalid", "reader-hash-mismatch",
    "reader-changed", "reader-failed", "reader-timeout", "reader-output-limit",
    "database-invalid", "database-schema-invalid", "database-identity-ambiguous",
    "database-validation-limit", "cache-invalid", "cache-unavailable", "retry-backoff",
})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}\Z")


class _Invalid(ValueError):
    pass


def _cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError("Catalogue acquisition cancelled.")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _stamp(info):
    return [info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino]


def _source_stat(path, maximum=MAX_SOURCE_BYTES):
    info = io_path(path).stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise _Invalid("source-size-invalid")
    return _stamp(info)


def _unchanged(path, expected):
    try:
        if _source_stat(path) != expected:
            raise _Invalid("source-changed")
    except OSError:
        raise _Invalid("source-changed") from None


def _snapshot(path, maximum, event=None):
    """Compare pathname and open-file identity on both sides of the read."""
    _cancel(event)
    before = _source_stat(path, maximum)
    with io_path(path).open("rb") as stream:
        if _stamp(os.fstat(stream.fileno())) != before:
            raise _Invalid("source-changed")
        data = bytearray()
        while len(data) <= maximum:
            _cancel(event)
            block = stream.read(min(1024 * 1024, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        after = _stamp(os.fstat(stream.fileno()))
    if (len(data) != before[0] or len(data) > maximum or after != before
            or _source_stat(path, maximum) != before):
        raise _Invalid("source-changed")
    return bytes(data), before


def _reader_configuration(value):
    try:
        if value is None:
            root = APP_ROOT / "tools/garage-reader"
            script = root / "catalogue.py"
            manifest, _ = _snapshot(root / "manifest.json", 1024 * 1024)
            inventory = json.loads(manifest)
            script_pin = inventory["files"]["catalogue.py"]["sha256"]
            runtime = APP_ROOT / "python"
            config = {"format": READER_FORMAT,
                      "python": str(runtime / "python.exe" if runtime.is_dir() else Path(sys.executable)),
                      "script": str(script), "script_sha256": script_pin,
                      "dependencies": [{"path": str(root / "manifest.json"), "sha256": _digest(manifest)}]}
            raw = _json(config)
        elif isinstance(value, dict):
            raw = _json(value)
            config = json.loads(raw)
        else:
            path = value
            raw, _ = _snapshot(path, MAX_RECEIPT_BYTES)
            config = json.loads(raw.decode("utf-8-sig"))
        if (len(raw) > MAX_RECEIPT_BYTES or not isinstance(config, dict)
                or config.get("format") != READER_FORMAT):
            raise _Invalid("reader-config-invalid")
        return config
    except _Invalid:
        raise
    except OSError:
        raise _Invalid("reader-unavailable") from None
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise _Invalid("reader-config-invalid") from None


def _reader(value):
    try:
        config = _reader_configuration(value)
        for key in ("python", "script"):
            if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
                raise _Invalid("reader-config-invalid")
        python, script = logical_path(config["python"]), logical_path(config["script"])
        dependencies = config.get("dependencies", [])
        if not isinstance(dependencies, list) or len(dependencies) > MAX_READER_DEPENDENCIES:
            raise _Invalid("reader-config-invalid")
        pins = [(config, "script_sha256")] if "script_sha256" in config else []
        for dependency in dependencies:
            if (not isinstance(dependency, dict) or not isinstance(dependency.get("path"), str)
                    or not Path(dependency["path"]).is_absolute()):
                raise _Invalid("reader-config-invalid")
            pins.append((dependency, "sha256"))
        for container, key in pins:
            if not isinstance(container.get(key), str) or not _HASH.fullmatch(container[key].lower()):
                raise _Invalid("reader-config-invalid")
        script_bytes, script_stamp = _snapshot(script, MAX_SCRIPT_BYTES)
        script_hash = _digest(script_bytes)
        if "script_sha256" in config:
            if config["script_sha256"].lower() != script_hash:
                raise _Invalid("reader-hash-mismatch")
        dependency_stamps = []
        for dependency in dependencies:
            path = logical_path(dependency["path"])
            info = io_path(path).lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise _Invalid("reader-config-invalid")
            content, stamp = _snapshot(path, MAX_SCRIPT_BYTES)
            digest = _digest(content)
            if digest != dependency["sha256"].lower():
                raise _Invalid("reader-hash-mismatch")
            dependency_stamps.append([stamp, digest])
        executable = io_path(python).stat()
        if not stat.S_ISREG(executable.st_mode):
            raise _Invalid("reader-config-invalid")
        fingerprint = _digest(_json({"protocol": READER_FORMAT, "config": config,
            "python_stamp": _stamp(executable), "script_stamp": script_stamp,
            "script_sha256": script_hash, "dependencies": dependency_stamps}))
        return {"python": python, "script": script, "fingerprint": fingerprint,
                "config_sha256": _digest(_json(config))}
    except _Invalid as exc:
        if str(exc).startswith("reader-"):
            raise
        raise _Invalid("reader-config-invalid") from None
    except OSError:
        raise _Invalid("reader-unavailable") from None
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise _Invalid("reader-config-invalid") from None


def _pipe_reader(stream):
    """Never block on stdout: the owner must remain able to kill and reap."""
    if os.name != "nt":
        os.set_blocking(stream.fileno(), False)

        def read():
            try:
                return os.read(stream.fileno(), 65536)
            except BlockingIOError:
                return None
        return read
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    peek = kernel.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                     ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    peek.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())

    def read():
        available = wintypes.DWORD()
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE
                return b""
            raise OSError("Reader pipe unavailable")
        if not available.value:
            return None
        return os.read(stream.fileno(), min(65536, available.value))
    return read


def _run_provider(reader, source, directory, event):
    _cancel(event)
    with tempfile.TemporaryFile(dir=io_path(directory)) as copied:
        copied.write(source)
        copied.seek(0)
        process = subprocess.Popen(
            [str(reader["python"]), "-I", "-B", str(reader["script"]), "--stdin"],
            stdin=copied, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, close_fds=True, bufsize=0, cwd=str(directory),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            read = _pipe_reader(process.stdout)
            deadline = time.monotonic() + MAX_PROVIDER_SECONDS
            output = bytearray()
            while True:
                _cancel(event)
                if time.monotonic() >= deadline:
                    raise _Invalid("reader-timeout")
                chunk = read()
                if chunk:
                    if len(output) + len(chunk) > MAX_DATABASE_BYTES:
                        raise _Invalid("reader-output-limit")
                    output.extend(chunk)
                    continue
                if process.poll() is not None:
                    # A second read closes the exit/last-write observation race.
                    chunk = read()
                    if chunk:
                        if len(output) + len(chunk) > MAX_DATABASE_BYTES:
                            raise _Invalid("reader-output-limit")
                        output.extend(chunk)
                        continue
                    if process.returncode != 0:
                        raise _Invalid("reader-failed")
                    _cancel(event)
                    return bytes(output)
                if event is None:
                    time.sleep(.025)
                else:
                    event.wait(.025)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def _validate(database, event=None):
    _cancel(event)
    if (not 100 <= len(database) <= MAX_DATABASE_BYTES
            or not database.startswith(SQLITE_MAGIC)):
        raise _Invalid("database-invalid")
    page_size = int.from_bytes(database[16:18], "big")
    page_size = 65536 if page_size == 1 else page_size
    if (page_size < 512 or page_size > 65536 or page_size & (page_size - 1)
            or len(database) % page_size or database[18:20] != b"\x01\x01"):
        raise _Invalid("database-invalid")
    deadline, ticks = time.monotonic() + MAX_VALIDATION_SECONDS, 0
    limited = False

    def progress():
        nonlocal ticks, limited
        ticks += 1
        limited = ticks > MAX_PROGRESS_TICKS or time.monotonic() >= deadline
        return limited or (event is not None and event.is_set())

    db = sqlite3.connect(":memory:")
    try:
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 65536)
        db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        db.set_progress_handler(progress, 1000)
        db.deserialize(database)
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA temp_store=MEMORY")
        schema = db.execute("SELECT name,type,sql FROM sqlite_schema LIMIT 2049").fetchall()
        if len(schema) > 2048:
            raise _Invalid("database-schema-invalid")
        tables = {}
        for name, kind, sql in schema:
            if isinstance(sql, str) and re.match(r"\s*CREATE\s+VIRTUAL\b", sql, re.I):
                raise _Invalid("database-schema-invalid")
            if kind == "table":
                tables[name.lower()] = name
        for table, required in REQUIRED_COLUMNS.items():
            if table.lower() not in tables:
                raise _Invalid("database-schema-invalid")
            columns = db.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
            if (any(row[6] != 0 for row in columns)
                    or not required.issubset({row[1].lower() for row in columns})):
                raise _Invalid("database-schema-invalid")
            if table != "VersionInfo":
                if db.execute(f'SELECT 1 FROM "{table}" WHERE typeof(Id) != \'integer\' LIMIT 1').fetchone():
                    raise _Invalid("database-identity-ambiguous")
                if db.execute(f'SELECT 1 FROM "{table}" GROUP BY Id HAVING count(*) > 1 LIMIT 1').fetchone():
                    raise _Invalid("database-identity-ambiguous")
        version = db.execute("SELECT database_version FROM VersionInfo LIMIT 2").fetchall()
        if len(version) != 1 or type(version[0][0]) is not int:
            raise _Invalid("database-schema-invalid")
        models = set()
        for _, model in db.execute("SELECT Id,MediaName FROM Data_Car LIMIT 16385"):
            if (not isinstance(model, str) or not _MODEL.fullmatch(model)
                    or model.lower() in models or len(models) >= 16384):
                raise _Invalid("database-identity-ambiguous")
            models.add(model.lower())
        if not models:
            raise _Invalid("database-schema-invalid")
        if db.execute("PRAGMA integrity_check(1)").fetchall() != [("ok",)]:
            raise _Invalid("database-invalid")
        _cancel(event)
        if time.monotonic() >= deadline:
            raise _Invalid("database-validation-limit")
        return version[0][0]
    except sqlite3.Error:
        _cancel(event)
        raise _Invalid("database-validation-limit" if limited else "database-invalid") from None
    finally:
        db.close()


@contextmanager
def _pin_windows_directories(store):
    """Disallow rename/junction replacement of cache ancestors during I/O."""
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handles = []
    try:
        for path in [*reversed(store.root.parents), store.root]:
            # OPEN_REPARSE_POINT prevents following an alias inserted after check.
            handle = create(str(io_path(path)), 0, 3, None, 3, 0x02200000, None)
            if handle == wintypes.HANDLE(-1).value:
                raise _Invalid("cache-unavailable")
            handles.append(handle)
            store.check(store.root, directory=True)
        yield
    finally:
        for handle in reversed(handles):
            close(handle)


@contextmanager
def _lock(store, event):
    """SafeRoot's OS-lock pattern, without translating cancellation to storage errors."""
    path = store.root / ".storage.lock"
    store.check(path, directory=False, missing=True)
    descriptor = os.open(io_path(path), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        current = store.check(path, directory=False)
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_size > 1
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
            raise _Invalid("cache-unavailable")
        if os.name == "nt":
            import msvcrt

            def acquire():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

            def release():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        deadline = time.monotonic() + MAX_LOCK_SECONDS
        while not acquired:
            _cancel(event)
            try:
                acquire()
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise _Invalid("cache-unavailable") from None
                if event is None:
                    time.sleep(.025)
                else:
                    event.wait(.025)
        store.check(store.root, directory=True)
        yield
    finally:
        try:
            if acquired:
                release()
        finally:
            os.close(descriptor)


def _cache_read(store, path, maximum):
    before = store.check(path, directory=False, missing=True)
    if before is None:
        return None
    data = store.read(path, maximum)
    after = store.check(path, directory=False)
    if _stamp(before) != _stamp(after) or len(data) != before.st_size:
        raise _Invalid("cache-invalid")
    return data


def _write(store, path, data, before_commit=None):
    store.check(path, directory=False, missing=True)
    with atomic_stream(path) as stream:
        stream.write(data)
        store.check(path, directory=False, missing=True)
        if before_commit is not None:
            before_commit()
    store.check(path, directory=False)


def _cached(store, identity, warnings, event):
    candidates = []
    for slot in (0, 1):
        _cancel(event)
        path = store.root / f"generation-{slot}.bin"
        try:
            raw = _cache_read(store, path, MAX_DATABASE_BYTES + MAX_RECEIPT_BYTES + 4)
            if raw is None:
                continue
            length = int.from_bytes(raw[:4], "little")
            if not 0 < length <= MAX_RECEIPT_BYTES or len(raw) < 4 + length:
                raise _Invalid("cache-invalid")
            receipt = json.loads(raw[4:4 + length])
            if (not isinstance(receipt, dict) or receipt.get("format") != CACHE_FORMAT
                    or receipt.get("source_identity") != identity
                    or type(receipt.get("generation")) is not int
                    or not 0 < receipt["generation"] < 2**63
                    or type(receipt.get("database_version")) is not int
                    or receipt.get("mode") not in ("sqlite", "provider")
                    or not isinstance(receipt.get("source_stamp"), list)
                    or len(receipt["source_stamp"]) != 4
                    or any(type(v) is not int or v < 0 for v in receipt["source_stamp"])
                    or not 0 < receipt["source_stamp"][0] <= MAX_SOURCE_BYTES
                    or any(not isinstance(receipt.get(k), str) or not _HASH.fullmatch(receipt[k])
                           for k in ("source_sha256", "database_sha256", "provider_sha256"))):
                raise _Invalid("cache-invalid")
            if ('reader_config_sha256' in receipt and (
                    not isinstance(receipt['reader_config_sha256'], str)
                    or not _HASH.fullmatch(receipt['reader_config_sha256']))):
                raise _Invalid('cache-invalid')
            data = raw[4 + length:]
            if _digest(data) != receipt["database_sha256"]:
                raise _Invalid("cache-invalid")
            candidates.append((receipt, data, slot))
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            warnings.append("cache-invalid")
    for receipt, data, slot in sorted(candidates, key=lambda item: item[0]["generation"], reverse=True):
        try:
            if _validate(data, event) != receipt["database_version"]:
                raise _Invalid("cache-invalid")
            return receipt, data, slot
        except _Invalid:
            warnings.append("cache-invalid")
    return None


def _retry(store, key):
    try:
        raw = _cache_read(store, store.root / "retry.json", MAX_RECEIPT_BYTES)
        value = json.loads(raw) if raw is not None else {}
        now = time.time()
        if (isinstance(value, dict) and value.get("key") == key
                and type(value.get("attempts")) is int and 1 <= value["attempts"] <= 5
                and type(value.get("after")) in (int, float)):
            return value["attempts"], now < value["after"] <= now + MAX_BACKOFF_SECONDS
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return 0, False


def _result(cached, status, warnings):
    receipt, database = cached[:2] if cached is not None else ({}, None)
    return {"database": database, "status": status,
            "provenance": {"source_sha256": receipt.get("source_sha256"),
                           "database_sha256": receipt.get("database_sha256"),
                           "database_version": receipt.get("database_version"),
                           "current": status in ("cached", "refreshed")},
            "warnings": list(dict.fromkeys(warnings))}


def load_installed_catalogue(game_root, *, cache_root=None, reader_config=None, cancel_event=None):
    """Return a validated installed catalogue; cancelled work raises InterruptedError.

    Default calls use app-owned support, ignoring legacy machine-local settings.
    An explicit reader_config is a JSON pathname or a dict with format, absolute python
    and script paths, optional strict script_sha256, and at most eight dependencies
    [{path: absolute, sha256: digest}]. Each dependency is bounded to 4 MiB and
    hash-verified on every use. Plain SQLite bypasses the provider configuration.
    Warm calls validate cache and rehash the stable source, never invoking an
    unchanged provider. Stale provenance describes the returned old bytes, not
    the newly observed source. Warnings are members of WARNING_CODES only.
    """
    _cancel(cancel_event)
    warnings, previous = [], None
    try:
        root = logical_path(game_root)
        source = (root if root.name.lower() == "media" else root / "media") / "stripped/gamedbRC.slt"
        identity = _digest(os.path.normcase(str(source)).encode("utf-8"))
        cache = logical_path(cache_root if cache_root is not None else APP_ROOT / "runtime/garage/catalogue")
        store = SafeRoot(cache / identity)
        store.mkdir(store.root)
        with _pin_windows_directories(store), _lock(store, cancel_event):
            _cancel(cancel_event)
            previous = _cached(store, identity, warnings, cancel_event)
            try:
                source_bytes, stamp = _snapshot(source, MAX_SOURCE_BYTES, cancel_event)
            except InterruptedError:
                raise
            except OSError:
                raise _Invalid("source-unavailable") from None
            source_hash = _digest(source_bytes)
            plain = source_bytes.startswith(SQLITE_MAGIC)
            try:
                reader = None if plain else _reader(reader_config)
            except _Invalid as exc:
                if (str(exc) == "reader-unavailable" and previous is not None
                        and previous[0]["source_stamp"] == stamp
                        and previous[0]["source_sha256"] == source_hash
                        and previous[0].get('reader_config_sha256') ==
                            _digest(_json(_reader_configuration(reader_config)))):
                    _cancel(cancel_event)
                    _unchanged(source, stamp)
                    return _result(previous, "cached", warnings + ["reader-unavailable"])
                raise
            provider_hash = _digest(b"plain-sqlite-v1") if plain else reader["fingerprint"]
            config_hash = provider_hash if plain else reader['config_sha256']
            if previous is not None:
                receipt = previous[0]
                if (receipt["source_stamp"] == stamp and receipt["source_sha256"] == source_hash
                        and receipt["provider_sha256"] == provider_hash
                        and receipt.get('reader_config_sha256') == config_hash):
                    _cancel(cancel_event)
                    _unchanged(source, stamp)
                    return _result(previous, "cached", warnings)
            key = _digest(_json([identity, stamp, source_hash, provider_hash]))
            attempts, waiting = _retry(store, key)
            if waiting:
                raise _Invalid("retry-backoff")
            try:
                data = source_bytes if plain else _run_provider(reader, source_bytes, store.root, cancel_event)
                version = _validate(data, cancel_event)
                _unchanged(source, stamp)
                if reader is not None and _reader(reader_config)["fingerprint"] != provider_hash:
                    raise _Invalid("reader-changed")
            except (_Invalid, OSError) as exc:
                if isinstance(exc, InterruptedError):
                    raise
                if isinstance(exc, _Invalid) and str(exc) in ("source-changed", "reader-changed"):
                    raise
                try:
                    _write(store, store.root / "retry.json", _json({"key": key,
                        "attempts": min(attempts + 1, 5),
                        "after": time.time() + min(2 ** (attempts + 1), MAX_BACKOFF_SECONDS)}))
                except (OSError, ValueError):
                    warnings.append("cache-unavailable")
                if isinstance(exc, _Invalid):
                    raise
                raise _Invalid("reader-failed") from None
            receipt = {"format": CACHE_FORMAT, "source_identity": identity,
                "generation": previous[0]["generation"] + 1 if previous else 1,
                "source_stamp": stamp, "source_sha256": source_hash,
                "database_sha256": _digest(data), "database_version": version,
                "reader_config_sha256": config_hash,
                "provider_sha256": provider_hash, "mode": "sqlite" if plain else "provider"}
            slot = 1 - previous[2] if previous else 0
            header = _json(receipt)

            def before_commit():
                _cancel(cancel_event)
                _unchanged(source, stamp)

            destination = store.root / f"generation-{slot}.bin"
            envelope = len(header).to_bytes(4, "little") + header + data
            _write(store, destination, envelope, before_commit)
            # Verify the durable artifact, not merely the writer's return code.
            if _cache_read(store, destination, len(envelope)) != envelope:
                raise _Invalid("cache-invalid")
            before_commit()
            return _result((receipt, data, slot), "refreshed", warnings)
    except InterruptedError:
        raise
    except _Invalid as exc:
        warnings.append(str(exc))
    except (OSError, ValueError, TypeError, StorageError):
        warnings.append("cache-unavailable")
    return _result(previous, "stale" if previous is not None else "unavailable", warnings)
