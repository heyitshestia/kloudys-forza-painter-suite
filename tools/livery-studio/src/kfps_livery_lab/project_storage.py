"""Car-organized ordinary project files and a read-only KFPS vinyl library."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from .model import MAX_BODY_BYTES, MAX_SHAPES, decode_json, ValidationError
from .recovery import MAX_PROJECT_BYTES, _project, _vehicle
from .storage_paths import SafeRoot, StorageError, relative_parts

PAGE_SIZE = 100
MAX_PROJECT_ENTRIES = 1024
MAX_PROJECT_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_CARS = 2048
MAX_DIRECTORY_ENTRIES = 20000
ID = re.compile(r"[a-f0-9]{32}\Z")
REVISION = re.compile(r"[a-f0-9]{64}\Z")
PROJECT_FILE = re.compile(r"[a-f0-9]{32}-[a-f0-9]{16}\.json\Z")
TEMP_FILE = re.compile(r"\.kfps-write-[a-f0-9]{32}\.tmp\Z")


def _offset(value):
    if type(value) is not int or not 0 <= value <= MAX_DIRECTORY_ENTRIES:
        raise StorageError(422, "Invalid page offset.")
    return value


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise StorageError(422, "Invalid project identifier.")
    return value


def _name(value):
    if not isinstance(value, str):
        raise StorageError(422, "Enter a project name of 1 to 80 characters.")
    value = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(value) <= 80 or any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value):
        raise StorageError(422, "Enter a single-line project name of 1 to 80 characters.")
    return value


def car_identity(vehicle):
    vehicle = _vehicle(vehicle)
    key = hashlib.sha256(json.dumps(vehicle, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    label = re.sub(r"[^a-z0-9]+", "-", vehicle["model_code"].lower()).strip("-")[:40].rstrip("-") or "car"
    return vehicle, key, f"{label}-{vehicle['car_id']}"


class ProjectStore:
    def __init__(self, root):
        self.safe = SafeRoot(root)
        self.root = self.safe.root
        self.path = self.root / "storage.sqlite3"

    @contextmanager
    def database(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            self.safe.check(Path(str(self.path) + suffix), directory=False, missing=True)
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA trusted_schema=OFF")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version not in (0, 1) or (version == 0 and tables) or (version == 1 and tables != {"cars", "projects", "files"}):
                raise StorageError(409, "The storage catalogue is unrelated or newer. It was not changed.")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS cars (key TEXT PRIMARY KEY, car_id INTEGER NOT NULL, "
                               "model_code TEXT NOT NULL, folder TEXT UNIQUE NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, car_key TEXT NOT NULL, "
                               "name TEXT NOT NULL, name_key TEXT NOT NULL, file_name TEXT NOT NULL, "
                               "revision TEXT NOT NULL, updated_at TEXT NOT NULL, bytes INTEGER NOT NULL, "
                               "UNIQUE(car_key,name_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS files (car_key TEXT NOT NULL, name TEXT NOT NULL, "
                               "PRIMARY KEY(car_key,name))")
            connection.execute("PRAGMA user_version=1")
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError) as exc:
            if connection:
                connection.rollback()
            raise StorageError(503, "The project catalogue is busy, unavailable or corrupt. No project was overwritten.") from exc
        except BaseException:
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()

    def car(self, db, vehicle, *, create=False):
        vehicle, key, folder = car_identity(vehicle)
        row = db.execute("SELECT * FROM cars WHERE key=?", (key,)).fetchone()
        if row is not None:
            if (row["car_id"] != vehicle["car_id"] or row["model_code"] != vehicle["model_code"]
                    or row["folder"] != folder):
                raise StorageError(409, "The car directory identity is inconsistent.")
            self.safe.check(self.root / folder, directory=True, missing=True)
            return row
        if not create:
            return None
        if db.execute("SELECT COUNT(*) FROM cars").fetchone()[0] >= MAX_CARS:
            raise StorageError(507, "The managed car directory limit is reached.")
        if db.execute("SELECT 1 FROM cars WHERE folder=?", (folder,)).fetchone():
            raise StorageError(409, "Another model identity already uses this car directory.")
        self.safe.mkdir(self.root / folder)
        db.execute("INSERT INTO cars VALUES(?,?,?,?)", (key, vehicle["car_id"], vehicle["model_code"], folder))
        return db.execute("SELECT * FROM cars WHERE key=?", (key,)).fetchone()

    @staticmethod
    def metadata(row):
        return {key: row[key] for key in ("id", "name", "file_name", "revision", "updated_at", "bytes")}

    def _listing(self, vehicle, entries, next_offset=None):
        _vehicle_value, _key, folder = car_identity(vehicle)
        return {"version": 1, "root_label": f"KFPS / imgs / livery-projects / {folder} / projects",
                "entries": entries, "next_offset": next_offset}

    def list(self, vehicle, offset=0):
        _offset(offset)
        vehicle = _vehicle(vehicle)
        with self.safe.lock(create=False) as exists:
            if not exists or self.safe.check(self.path, directory=False, missing=True) is None:
                return self._listing(vehicle, [])
            with self.database() as db:
                car = self.car(db, vehicle)
                rows = [] if car is None else db.execute(
                    "SELECT * FROM projects WHERE car_key=? ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                    (car["key"], PAGE_SIZE + 1, offset)).fetchall()
        return self._listing(vehicle, [self.metadata(row) for row in rows[:PAGE_SIZE]],
                             offset + PAGE_SIZE if len(rows) > PAGE_SIZE else None)

    def _file(self, car, row):
        if not isinstance(row["file_name"], str) or not PROJECT_FILE.fullmatch(row["file_name"]):
            raise StorageError(409, "The project file record is invalid.")
        return self.root / car["folder"] / "projects" / row["file_name"]

    def _read(self, car, row, vehicle):
        try:
            raw = self.safe.read(self._file(car, row), MAX_PROJECT_BYTES)
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["revision"]:
                raise ValueError("checksum")
            project = decode_json(raw)
            _project(project, vehicle)
            return project
        except (ValueError, TypeError) as exc:
            raise StorageError(409, "The saved project is missing, changed or corrupt. It was not overwritten.") from exc

    def open(self, vehicle, identifier):
        vehicle, identifier = _vehicle(vehicle), _identifier(identifier)
        with self.safe.lock(create=False) as exists:
            if not exists or self.safe.check(self.path, directory=False, missing=True) is None:
                raise StorageError(404, "This project is not available for the active car.")
            with self.database() as db:
                car = self.car(db, vehicle)
                row = None if car is None else db.execute("SELECT * FROM projects WHERE id=? AND car_key=?", (identifier, car["key"])).fetchone()
                if row is None:
                    raise StorageError(404, "This project is not available for the active car.")
                return {"version": 1, "entry": self.metadata(row), "project": self._read(car, row, vehicle)}

    def _cleanup(self, db, car):
        directory = self.root / car["folder"] / "projects"
        if self.safe.check(directory, directory=True, missing=True) is None:
            return
        keep = {row[0] for row in db.execute("SELECT file_name FROM projects WHERE car_key=?", (car["key"],))}
        owned = db.execute("SELECT name FROM files WHERE car_key=? LIMIT ?", (car["key"], MAX_DIRECTORY_ENTRIES + 1)).fetchall()
        if len(owned) > MAX_DIRECTORY_ENTRIES:
            raise StorageError(507, "The project file ledger exceeds its limit.")
        for row in owned:
            name = row[0]
            if not isinstance(name, str) or not (PROJECT_FILE.fullmatch(name) or TEMP_FILE.fullmatch(name)):
                raise StorageError(409, "The project file ledger is invalid.")
            if name not in keep:
                path = directory / name
                if self.safe.check(path, directory=False, missing=True) is not None:
                    path.unlink()
                db.execute("DELETE FROM files WHERE car_key=? AND name=?", (car["key"], name))

    def _publish(self, path, raw, temporary):
        self.safe.mkdir(path.parent)
        if self.safe.check(path, directory=False, missing=True) is not None:
            if self.safe.read(path, MAX_PROJECT_BYTES) != raw:
                raise StorageError(409, "The generated project filename is already occupied by different data.")
            return
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self.safe.check(path.parent, directory=True)
            self.safe.check(path, directory=False, missing=True)
            os.replace(temporary, path)
        except OSError as exc:
            raise StorageError(503, "The project could not be written. The previous save was not changed.") from exc
        finally:
            if temporary.exists():
                self.safe.check(temporary, directory=False)
                temporary.unlink()

    def save(self, vehicle, payload):
        vehicle = _vehicle(vehicle)
        if not isinstance(payload, dict) or set(payload) - {"name", "project", "id", "expected_revision"}:
            raise StorageError(422, "Invalid managed project save request.")
        name = _name(payload.get("name"))
        replacing = "id" in payload or "expected_revision" in payload
        identifier = _identifier(payload.get("id")) if replacing else uuid.uuid4().hex
        if replacing and (not isinstance(payload.get("expected_revision"), str) or not REVISION.fullmatch(payload["expected_revision"])):
            raise StorageError(422, "A replacement requires the current project revision.")
        raw = _project(payload.get("project"), vehicle)
        revision = hashlib.sha256(raw).hexdigest()
        with self.safe.lock():
            with self.database() as db:
                car = self.car(db, vehicle, create=True)
                old = db.execute("SELECT * FROM projects WHERE id=? AND car_key=?", (identifier, car["key"])).fetchone() if replacing else None
                collision = db.execute("SELECT * FROM projects WHERE car_key=? AND name_key=?", (car["key"], name.casefold())).fetchone()
                if replacing:
                    if old is None:
                        raise StorageError(404, "The project to replace is not available for this car.")
                    if old["revision"] != payload["expected_revision"]:
                        raise StorageError(409, "This project changed in another window. Review it before replacing.",
                                           code="project_changed", entry=self.metadata(old))
                    if old["name_key"] != name.casefold():
                        raise StorageError(422, "Omit the previous receipt to save under a new name.")
                    self._read(car, old, vehicle)
                if collision is not None and (not replacing or collision["id"] != identifier):
                    raise StorageError(409, "A project with this name already exists. Choose Replace or a new name.",
                                       code="project_exists", entry=self.metadata(collision))
                count, total = db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM projects").fetchone()
                if count + int(old is None) > MAX_PROJECT_ENTRIES or total - (old["bytes"] if old else 0) + len(raw) > MAX_PROJECT_TOTAL_BYTES:
                    raise StorageError(507, "Managed project storage is full. Existing projects were not removed.")
                self._cleanup(db, car)
                filename = identifier + "-" + revision[:16] + ".json"
                directory = self.root / car["folder"] / "projects"
                temporary = directory / (".kfps-write-" + uuid.uuid4().hex + ".tmp")
                existing = self.safe.check(directory / filename, directory=False, missing=True)
                if self.safe.check(temporary, directory=False, missing=True) is not None:
                    raise StorageError(409, "A temporary project filename is already occupied. It was not changed.")
                owned = db.execute("SELECT 1 FROM files WHERE car_key=? AND name=?", (car["key"], filename)).fetchone()
                if existing is not None and owned is None:
                    raise StorageError(409, "The generated filename is occupied by an unmanaged file. It was not changed.")
                db.executemany("INSERT OR IGNORE INTO files VALUES(?,?)", [(car["key"], filename), (car["key"], temporary.name)])
                # Persist file ownership before writing. Recovery cleanup must
                # never infer ownership from a filename pattern alone.
                db.commit()
                db.execute("BEGIN IMMEDIATE")
                self._publish(directory / filename, raw, temporary)
                db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "name=excluded.name,file_name=excluded.file_name,revision=excluded.revision,updated_at=excluded.updated_at,bytes=excluded.bytes",
                           (identifier, car["key"], name, name.casefold(), filename, revision,
                            datetime.now(timezone.utc).isoformat(timespec="microseconds"), len(raw)))
                entry = self.metadata(db.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())
            # Metadata commits after the immutable file is durable. An interrupted
            # write only leaves an unreferenced generated file, never a broken save.
            try:
                with self.database() as db:
                    self._cleanup(db, car)
            except (StorageError, OSError):
                pass  # A committed save remains successful; cleanup retries later.
        return {"version": 1, "root_label": self._listing(vehicle, [])["root_label"], "entry": entry}


def _vinyl_filename(name):
    lower = name.lower()
    return (lower.endswith(".json") and not any(part in lower for part in
            (".manifest.", ".report.", ".layout.", ".kfps-livery.", ".project."))
            and lower not in {"manifest.json", "report.json", "layout.json", "project.json", "package.json", "package-lock.json"})


class VinylLibrary:
    def __init__(self, root):
        self.safe = SafeRoot(root)
        self.root = self.safe.root

    def _path(self, relative, *, empty=False):
        parts = relative_parts(relative, empty=empty)
        if any(part.casefold() == "livery-projects" for part in parts):
            raise StorageError(404, "Project storage is not part of the vinyl library.")
        return self.root.joinpath(*parts)

    def list(self, path="", offset=0):
        _offset(offset)
        directory = self._path(path, empty=True)
        exists = self.safe.check(directory, directory=True, missing=not path)
        entries = []
        if exists is not None:
            try:
                with os.scandir(directory) as scan:
                    for index, item in enumerate(scan):
                        if index >= MAX_DIRECTORY_ENTRIES:
                            raise StorageError(413, "This folder contains too many entries. Choose a smaller folder.")
                        relative = (path + "/" if path else "") + item.name
                        try:
                            candidate = self._path(relative)
                            info = self.safe.check(candidate)
                            if item.is_dir(follow_symlinks=False):
                                entries.append({"name": item.name, "path": relative, "kind": "directory"})
                            elif _vinyl_filename(item.name) and info.st_size <= MAX_BODY_BYTES:
                                entries.append({"name": item.name, "path": relative, "kind": "file", "size": info.st_size})
                        except StorageError:
                            continue
            except OSError as exc:
                raise StorageError(503, "The vinyl library folder could not be read.") from exc
        entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold(), item["name"]))
        return {"version": 1, "path": path, "parent": path.rpartition("/")[0] if path else None,
                "entries": entries[offset:offset + PAGE_SIZE],
                "next_offset": offset + PAGE_SIZE if len(entries) > offset + PAGE_SIZE else None}

    def read(self, path):
        target = self._path(path)
        if not _vinyl_filename(target.name):
            raise StorageError(404, "Select a native vinyl JSON, not a report or project.")
        raw = self.safe.read(target, MAX_BODY_BYTES)
        try:
            value = decode_json(raw)
        except ValidationError as exc:
            raise StorageError(422, "The selected file is not valid vinyl JSON.") from exc
        shapes = value if isinstance(value, list) else value.get("shapes") if isinstance(value, dict) else None
        if (not isinstance(shapes, list) or not 1 <= len(shapes) <= MAX_SHAPES
                or any(not isinstance(shape, dict) for shape in shapes)
                or (isinstance(value, dict) and ("placements" in value or "vinyls" in value))):
            raise StorageError(422, "The selected JSON is not a native vinyl. Shape compatibility is checked during import.")
        return value
