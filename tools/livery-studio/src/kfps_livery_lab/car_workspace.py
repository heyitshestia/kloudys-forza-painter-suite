"""Bounded session-local car preparation; no game/save/settings writes."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import traceback
import zipfile

import psutil

from .model import decode_json
from .prepare import LAB_ROOT, PREPARE_FORMAT, atomic_json, file_hash, within
from .file_io import io_path
from .garage_build import validate_build, resolve_prepared_build

ID = re.compile(r"[a-f0-9]{32}")
ARCHIVE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_ -]{0,150}\.zip", re.IGNORECASE)
MAX_CARS = 4096
MAX_DIRECTORY_ENTRIES = 16384
MAX_WORKSPACES = 3
MAX_RECORDS = 16
MAX_PREPARED_BYTES = 16 * 1024 * 1024


class CarError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def catalogue(game_root, *, model_code=None):
    game = Path(game_root).resolve(strict=True)
    root = within(game / "media/Cars", game)
    if root != game / "media/Cars" or not root.is_dir():
        raise CarError(400, "The configured car folder is unavailable.")
    from tools.livery.vehicle_assets import _car_clip_in_archive
    result = {}
    entries = []
    for path in root.iterdir():
        if len(entries) >= MAX_DIRECTORY_ENTRIES:
            raise CarError(400, "The configured car folder contains too many entries.")
        entries.append(path)
    for path in sorted(entries, key=lambda p: p.name.casefold()):
        if model_code is not None and path.stem != model_code:
            continue
        if not ARCHIVE.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        if path.resolve() != path or getattr(path, "is_junction", lambda: False)():
            continue
        info = path.stat()
        if not 0 < info.st_size <= 2 * 1024 ** 3:
            continue
        try:
            clip = _car_clip_in_archive(path)
        except (OSError, ValueError, zipfile.BadZipFile):
            continue
        if clip is None:
            continue
        key = hashlib.sha256(path.name.casefold().encode("ascii")).hexdigest()[:32]
        if key in result or len(result) >= MAX_CARS:
            raise CarError(400, "The configured car catalogue exceeds its safe bounds.")
        result[key] = {"id": key, "name": path.stem.replace("_", " "), "model_code": path.stem, "archive": path.name,
                       "car_id": clip[0], "_path": path, "_size": info.st_size, "_mtime": info.st_mtime_ns}
    return result


def public_car(row):
    return {key: row[key] for key in ("id", "name", "model_code", "archive", "car_id")}


def prepared_assets(prepared, root):
    files = prepared["files"]
    if not isinstance(files.get("masks"), list) or len(files["masks"]) != 3:
        raise ValueError("Exactly three mask pages are required.")
    assets = {"api/local-mesh": (files["mesh"], "model/gltf-binary"),
              "api/local-render/paint": (files["paint"], "image/png")}
    assets.update({f"api/local-render/mask/{index}": (name, "image/png") for index, name in enumerate(files["masks"])})
    if files.get("coverage"):
        assets["api/component-coverage"] = (files["coverage"], "application/json; charset=utf-8")
    textures = files.get("native_textures", {})
    if (not isinstance(textures, dict) or len(textures) > 32
            or any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) for key in textures)):
        raise ValueError("Invalid native texture registry.")
    assets.update({f"api/native-texture/{key}": (name, "image/png") for key, name in textures.items()})
    resolved = {}
    texture_bytes = 0
    for route, (name, mime) in assets.items():
        if (not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts
                or any(c in name for c in "\\:\x00")):
            raise ValueError("Invalid prepared asset path.")
        candidate = root / name
        for part in (candidate, *candidate.parents):
            native = io_path(part)
            if native.is_symlink() or native.is_junction():
                raise ValueError("Redirected prepared assets are not supported.")
            if part == root:
                break
        path = within(candidate, root)
        native = io_path(path)
        if path == root or not native.is_file() or native.stat().st_size == 0:
            raise ValueError("A prepared asset is missing.")
        if route.startswith("api/native-texture/"):
            texture_bytes += native.stat().st_size
            hashes = prepared.get("file_sha256", {})
            if (path.suffix.lower() != ".png" or native.stat().st_size > 80 * 1024**2
                    or texture_bytes > 128 * 1024**2 or not isinstance(hashes, dict)
                    or hashes.get(name) != file_hash(path)):
                raise ValueError("A native texture failed its integrity or size check.")
        resolved[route] = (path, mime)
    return resolved


def validate_prepared(root, car):
    with (root / "prepared.json").open("rb") as stream:
        body = stream.read(MAX_PREPARED_BYTES + 1)
    if len(body) > MAX_PREPARED_BYTES:
        raise ValueError("Prepared metadata is too large.")
    prepared = decode_json(body)
    vehicle = prepared["editor_config"]["vehicle"]
    if (prepared.get("format") != PREPARE_FORMAT or vehicle.get("archive_name") != car["archive"]
            or vehicle.get("car_id") != car["car_id"] or prepared["manifest"].get("vehicle") != vehicle
            or prepared["signature"].get("archive_sha256") != file_hash(car["_path"])):
        raise ValueError("Prepared car identity does not match.")
    assets = prepared_assets(prepared, root)
    hashes = prepared["file_sha256"]
    if not isinstance(hashes, dict) or len(hashes) > 48:
        raise ValueError("Invalid prepared asset hashes.")
    for path, _ in assets.values():
        if hashes.get(path.relative_to(root).as_posix()) != file_hash(path):
            raise ValueError("Prepared asset hash does not match.")
    if not prepared["editor_config"].get("sections"):
        raise ValueError("Prepared car has no editable sections.")
    return prepared, assets


class CarWorkspace:
    def __init__(self, session_root, kfps_root, game_root):
        self.session_root = within(Path(session_root).resolve(), LAB_ROOT / "runs")
        if self.session_root == (LAB_ROOT / "runs").resolve():
            raise ValueError("A named session workspace is required.")
        self.root = within(self.session_root / "cars", self.session_root)
        self.kfps_root = Path(kfps_root).resolve(strict=True)
        self.game_root = Path(game_root).resolve(strict=True)
        self.cars = catalogue(self.game_root)
        self.lock = threading.RLock()
        self.records = OrderedDict()
        self.owned = []
        self.active_root = None
        self.closed = False

    def list(self, current_archive):
        current = next((key for key, car in self.cars.items() if car["archive"] == current_archive), None)
        return {"enabled": True, "cars": [public_car(car) for car in self.cars.values()], "current": current}

    def _record(self, identifier):
        if not isinstance(identifier, str) or not ID.fullmatch(identifier):
            raise CarError(400, "Invalid car preparation identifier.")
        record = self.records.get(identifier)
        if record is None:
            raise CarError(404, "Car preparation was not found.")
        return record

    def _view(self, record):
        value = {"id": record["id"], "status": record["status"], "car": public_car(record["car"])}
        if record.get("error"):
            value["error"] = record["error"]
            value["error_code"] = record["error_code"]
        return value

    def poll(self, identifier):
        with self.lock:
            return self._view(self._record(identifier))

    def start(self, car_id, current_archive, *, garage_build=None, automatic_handoff=False):
        build = validate_build(garage_build) if garage_build is not None else None
        with self.lock:
            if self.closed:
                raise CarError(409, "The Studio is closing.")
            if not isinstance(car_id, str) or not ID.fullmatch(car_id):
                raise CarError(400, "Invalid car selection.")
            car = self.cars.get(car_id)
            if car is None:
                raise CarError(404, "Car selection was not found.")
            if car["archive"] == current_archive:
                raise CarError(409, "This car is already open.")
            if any(r["status"] in ("preparing", "ready", "cancelling") for r in self.records.values()):
                raise CarError(409, "Another car preparation is still active.")
            # Reuse only a completed, inactive directory witnessed by this live
            # session. A new job still runs the full preparation/verification path.
            root = next((r["root"] for r in reversed(self.records.values())
                         if r["car"]["id"] == car_id and r["status"] in ("committed", "cancelled")
                         and r.get("prepared") and r["root"] in self.owned
                         and r["root"] != self.active_root), None)
            if root is not None:
                if not self._check_inactive_owned(root, allow_missing=True):
                    self.owned.remove(root)
                    root = None
            # Only directories created and recorded by this live session may be removed.
            while root is None and len(self.owned) >= MAX_WORKSPACES:
                old = next((p for p in self.owned if p != self.active_root), None)
                if old is None:
                    raise CarError(409, "The car workspace is full.")
                self._remove(old)
                self.owned.remove(old)
            while len(self.records) >= MAX_RECORDS:
                self.records.popitem(last=False)
            identifier = secrets.token_hex(16)
            if root is None:
                root = within(self.root / identifier, self.root)
                root.mkdir(parents=True, exist_ok=False)
            else:
                self.owned.remove(root)
            self.owned.append(root)
            record = {"id": identifier, "status": "preparing", "car": car, "root": root,
                      "cancel": threading.Event(), "garage_build": build,
                      "automatic_handoff": automatic_handoff}
            thread = threading.Thread(target=self._run, args=(record,), name="KfpsCarPrepare-" + identifier, daemon=True)
            record["thread"] = thread
            self.records[identifier] = record
            try:
                thread.start()
            except (RuntimeError, OSError):
                record.update(thread=None, status="failed", error_code="containment-failed",
                              error="Car preparation could not start. Retry; your previous car is unchanged.")
            return self._view(record)

    def _check_inactive_owned(self, root, *, allow_missing=False):
        root = Path(root)
        if root not in self.owned or root == self.active_root or root.parent != self.root or not ID.fullmatch(root.name):
            raise ValueError("Not an inactive owned workspace.")
        if root.is_symlink() or getattr(root, "is_junction", lambda: False)() or root.resolve() != root:
            raise ValueError("Refusing a redirected workspace.")
        if allow_missing and not root.exists():
            return False
        if not root.is_dir():
            raise ValueError("The owned workspace is missing.")
        for directory, folders, files in os.walk(root, followlinks=False):
            for name in folders + files:
                path = Path(directory) / name
                if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()
                        or (path.is_file() and path.stat().st_nlink != 1)):
                    raise ValueError("Refusing a redirected workspace member.")
        return True

    def _remove(self, root):
        if self._check_inactive_owned(root, allow_missing=True):
            shutil.rmtree(root)

    def _prepare(self, record):
        from .converter_process import _execute
        car, root = record["car"], record["root"]
        detail = {}
        prioritized = set()

        def memory(pid):
            try:
                process = psutil.Process(pid)
                if pid not in prioritized:
                    process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    prioritized.add(pid)
                processes = [process, *process.children(recursive=True)]
            except psutil.NoSuchProcess:
                # A successful worker may exit between Popen.poll and this sample.
                return 0
            total = 0
            for item in processes:
                try:
                    total += item.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            return total

        command = [sys.executable, "-B", str(LAB_ROOT / "src/run_livery.py"), "--prepare-only",
                   "--kfps-root", str(self.kfps_root), "--game-root", str(self.game_root),
                   "--archive", car["archive"], "--workspace", str(root)]
        try:
            info = car["_path"].stat()
            if info.st_size != car["_size"] or info.st_mtime_ns != car["_mtime"] or car["_path"].resolve() != car["_path"]:
                raise ValueError("Car archive changed after catalogue creation.")
            _execute(command, root, detail, 300, 3 * 1024 ** 3, 4 * 1024 ** 2, record["cancel"], memory)
            result = validate_prepared(root, car)
            detail["status"] = "success"
            return result
        except Exception as exc:
            detail.update(status="cancelled" if record["cancel"].is_set() else "failed",
                          error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
            raise
        finally:
            atomic_json(root / "prepare-log.json", detail)

    def _run(self, record):
        stage = "preparation"
        try:
            prepared, assets = self._prepare(record)
            if record.get("garage_build") is not None and not record["cancel"].is_set():
                stage = "garage-build"
                resolve_prepared_build(record["garage_build"], prepared, assets)
            with self.lock:
                if record["cancel"].is_set() or self.closed:
                    record["status"] = "cancelled"
                else:
                    record.update(status="ready", prepared=prepared, assets=assets)
        except Exception as exc:
            with self.lock:
                record["status"] = "cancelled" if record["cancel"].is_set() else "failed"
                if record["status"] == "failed":
                    code = "garage-build-unavailable" if stage == "garage-build" else getattr(exc, "status", "preparation-failed")
                    messages = {
                        "timeout": "This car took too long to prepare. Try again or choose another car.",
                        "memory-limit": "This car exceeded the preparation memory limit. Choose another car.",
                        "output-limit": "Car preparation produced too much diagnostic output. Choose another car.",
                        "converter-failed": "This car could not be converted. Try again or choose another car.",
                        "containment-failed": "The safe preparation worker could not start. Restart Studio and retry.",
                        "garage-build-unavailable": "The saved body parts could not be matched to the prepared car. Refresh Garage and retry.",
                    }
                    record["error_code"] = code if code in messages else "preparation-failed"
                    record["error"] = messages.get(code, "This car could not be prepared or verified. Try again or choose another car.") + " Your previous car is unchanged."

    def cancel(self, identifier):
        with self.lock:
            record = self._record(identifier)
            if record["status"] == "committed":
                raise CarError(409, "This car is already open.")
            if record["status"] in ("preparing", "cancelling"):
                record["cancel"].set()
                record["status"] = "cancelling"
            elif record["status"] == "ready":
                record["cancel"].set()
                record["status"] = "cancelled"
            return self._view(record)

    def commit(self, identifier, activate):
        with self.lock:
            record = self._record(identifier)
            if record["status"] != "ready" or record["cancel"].is_set() or self.closed:
                raise CarError(409, "Car preparation is not ready to commit.")
            # Revalidate hashes just before publication; never publish partial/stale files.
            prepared, assets = validate_prepared(record["root"], record["car"])
            if record.get("garage_build") is not None:
                resolve_prepared_build(record["garage_build"], prepared, assets)
            url = activate(prepared, record["root"], assets)
            self.active_root = record["root"]
            record["status"] = "committed"
            return {**self._view(record), "url": url}

    def close(self):
        with self.lock:
            self.closed = True
            records = list(self.records.values())
            for record in records:
                record["cancel"].set()
        for record in records:
            thread = record.get("thread")
            if thread is None:
                continue
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("Car preparation did not shut down.")
