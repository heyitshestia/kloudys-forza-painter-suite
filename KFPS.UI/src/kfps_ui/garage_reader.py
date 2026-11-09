"""On-demand local garage acquisition. Never writes to a selected source."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .garage_index import GarageError, MAX_BYTES, snapshot_records, parse_json, profile_identity

MAX_SOURCE = 128 * 1024 * 1024
READER_TIMEOUT = 45


def _reader_command():
    root = Path(__file__).resolve().parents[3]
    runtime = root / "python"
    python = runtime / "python.exe" if runtime.is_dir() else Path(sys.executable)
    script = root / "tools" / "garage-reader" / "reader.py"
    if not python.is_file() or not script.is_file():
        raise GarageError("Garage support files need repair. Run the KFPS Updater, then retry.")
    return [str(python), "-I", "-B", str(script), "--stdin"]


def check_cancel(cancel):
    if cancel.is_set():
        raise InterruptedError("Garage scan cancelled.")


def snapshot(path, cancel):
    check_cancel(cancel)
    with Path(path).open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not 0 < before.st_size <= MAX_SOURCE:
            raise GarageError("The selected garage save has an unsupported size.")
        data = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    current = Path(path).stat()
    stamps = [(s.st_size, s.st_mtime_ns, s.st_ino, s.st_dev) for s in (before, after, current)]
    if stamps[0] != stamps[1] or stamps[0] != stamps[2] or len(data) != before.st_size:
        raise GarageError("The save changed during the scan. Wait for saving to finish and refresh.")
    check_cancel(cancel)
    return data, hashlib.sha256(data).hexdigest()


def reader_records(source, data, config_path, cancel):
    if source.suffix.lower() == ".json":
        # Use the stable copy, not a second read of the selected path.
        return parse_json(data)
    check_cancel(cancel)
    command = _reader_command()
    # Retain this argument for callers; old machine-specific overrides are ignored.
    config_path = Path(config_path)
    if not 0 < len(data) <= MAX_SOURCE:
        raise GarageError("The selected garage save has an unsupported size.")
    # Delete-on-close handles are reclaimed by the OS even if KFPS terminates.
    # The child receives an inherited read handle, not a durable profile pathname.
    with tempfile.TemporaryFile(dir=config_path.parent) as copied, tempfile.TemporaryFile(dir=config_path.parent) as output:
        copied.write(data)
        copied.seek(0)
        try:
            process = subprocess.Popen(command,
                    stdin=copied, stdout=output, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), cwd=str(config_path.parent))
        except OSError:
            raise GarageError("Garage support could not start. Run the KFPS Updater, then retry.") from None
        try:
            deadline = time.monotonic() + READER_TIMEOUT
            while process.poll() is None:
                check_cancel(cancel)
                if time.monotonic() > deadline or os.fstat(output.fileno()).st_size > MAX_BYTES:
                    raise GarageError("The garage scan exceeded its resource limit.")
                cancel.wait(0.025)
            check_cancel(cancel)
            if process.returncode == 3:
                raise GarageError("Garage support files need repair. Run the KFPS Updater, then retry.")
            if process.returncode != 0:
                raise GarageError("This garage save could not be read. Try its last stable backup.")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        output.seek(0)
        try:
            return parse_json(output.read(min(os.fstat(output.fileno()).st_size, MAX_BYTES) + 1))
        except (ValueError, UnicodeError):
            raise GarageError("The garage reader returned invalid data. Refresh and try again.") from None


def scan(source, store, config_path, cancel, *, history=False, validate_source=None):
    started = time.perf_counter()
    source = Path(source).resolve(strict=True)
    data, source_hash = snapshot(source, cancel)
    ident = profile_identity(source)
    old = store.load(ident)
    reused = bool(old and old["sourceHash"] == source_hash)
    rows, scope = ((old["cars"], old["scope"]) if reused else
                   snapshot_records(reader_records(source, data, config_path, cancel)))
    del data
    check_cancel(cancel)
    _, current_hash = snapshot(source, cancel)
    if current_hash != source_hash:
        raise GarageError("The save changed during the scan. Wait for saving to finish and refresh.")
    check_cancel(cancel)
    def before_commit():
        check_cancel(cancel)
        if validate_source:
            validate_source()
        check_cancel(cancel)
    before_commit()
    # Do not retain full source contents in the durable index.
    if reused and (not old["history"] or history and scope):
        # Keep the original snapshot timestamp; an unchanged check needs no write.
        state = old
    else:
        state = store.publish(ident, source_hash, rows, history=history, scope=scope,
                              before_commit=before_commit)
    return {"state": state, "source": str(source), "reused": reused,
            "elapsedMs": round((time.perf_counter() - started) * 1000)}
