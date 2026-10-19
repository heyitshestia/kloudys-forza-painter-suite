"""Transactional recovery for layout v1 (not a game-save format).

HTTP adapter contract (the session server supplies its current vehicle):
  GET recovery -> {version: 1, entries: [metadata], limits: {...}}
  POST recovery {document_id, kind: auto|checkpoint, name?, project}
      -> {version: 1, entry: metadata}
  POST recovery/<entry_id>/restore {document_id, current_project}
      -> {version: 1, entry: metadata, retained: metadata, project: layout}
RecoveryError.status/message map to HTTP status/{error: message}. The adapter
must retain its Host/Origin/token checks and cap bodies at MAX_REQUEST_BYTES.
No filesystem paths, session tokens, host settings or credentials are accepted.
Default legacy roots remain workspace-only. A trusted managed-storage caller can
supply an explicit root boundary; legacy reads use SQLite read-only connections.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from .model import ValidationError, decode_json, validate_shapes

LAB_ROOT = Path(__file__).resolve().parents[2]
MAX_PROJECT_BYTES = 32 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_PROJECT_BYTES + 4096
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 128
MAX_PROTECTED = 64
AUTO_PER_DOCUMENT = 5
MAX_AUTO = 32
ID = re.compile(r"[a-f0-9]{32}\Z")
SECTIONS = frozenset(("Front", "Back", "Top", "Left", "Right", "Spoiler",
                      "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow"))
FORMAT = "kfps-livery-layout-v1"


class RecoveryError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _text(value, maximum, label):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise RecoveryError(422, f"Invalid {label}.")
    return value


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise RecoveryError(422, "Invalid recovery identifier.")
    return value


def _vehicle(value):
    if (not isinstance(value, dict) or type(value.get("car_id")) is not int
            or not 0 < value["car_id"] <= 0x7fffffff):
        raise RecoveryError(422, "Invalid recovery car.")
    return {"car_id": value["car_id"], "model_code": _text(value.get("model_code"), 160, "car model")}


def _number(value, low, high, label):
    if (type(value) not in (float, int) or not low <= value <= high
            or not math.isfinite(value)):
        raise RecoveryError(422, f"Invalid {label}.")
    return value


def _authoring(value, placements):
    if (not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1
            or set(value) - {"version", "groups", "locked", "links"}):
        raise RecoveryError(422, "Invalid recovery authoring metadata.")
    groups, locks, links = value.get("groups", []), value.get("locked", []), value.get("links", [])
    if (not isinstance(groups, list) or len(groups) > 100 or not isinstance(locks, list) or len(locks) > 200
            or not isinstance(links, list) or len(links) > 100):
        raise RecoveryError(422, "Recovery authoring metadata exceeds its limits.")
    by_id = {p["id"]: p for p in placements}
    group_ids, members, locked, link_ids, endpoints = set(), set(), set(), set(), set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"id", "name", "placements"}:
            raise RecoveryError(422, "Invalid recovery group.")
        group_id = _text(group["id"], 100, "group ID")
        _text(group["name"], 160, "group name")
        selected = group["placements"]
        if group_id in group_ids or not isinstance(selected, list) or not 2 <= len(selected) <= 200:
            raise RecoveryError(422, "Invalid or duplicate recovery group.")
        group_ids.add(group_id)
        section = None
        for pid in selected:
            _text(pid, 100, "group placement")
            if pid not in by_id or pid in members or (section is not None and by_id[pid]["section"] != section):
                raise RecoveryError(422, "Missing, overlapping or cross-section recovery group.")
            members.add(pid)
            section = by_id[pid]["section"]
    for pid in locks:
        _text(pid, 100, "locked placement")
        if pid not in by_id or pid in locked:
            raise RecoveryError(422, "Missing or duplicate locked recovery placement.")
        locked.add(pid)
    for link in links:
        if not isinstance(link, dict) or set(link) != {"id", "a", "b", "sectionA", "sectionB", "mode", "calibration"}:
            raise RecoveryError(422, "Invalid recovery mirror link.")
        for key in ("id", "a", "b"):
            _text(link[key], 100, "mirror identifier")
        a, b = link["a"], link["b"]
        if (link["id"] in link_ids or a == b or a in endpoints or b in endpoints or a not in by_id or b not in by_id
                or link["sectionA"] != by_id[a]["section"] or link["sectionB"] != by_id[b]["section"]
                or (link["sectionA"], link["sectionB"]) not in (("Left", "Right"), ("Right", "Left"), ("LeftWindow", "RightWindow"), ("RightWindow", "LeftWindow"))
                or link["mode"] not in ("mirror-artwork", "readable-lettering")):
            raise RecoveryError(422, "Missing, overlapping or incompatible recovery mirror link.")
        calibration = link["calibration"]
        if not isinstance(calibration, dict) or set(calibration) != {"kind", "aToB"} or calibration["kind"] != "user-aligned-pair-v1":
            raise RecoveryError(422, "Invalid recovery mirror calibration.")
        matrix = calibration["aToB"]
        if not isinstance(matrix, list) or len(matrix) != 6:
            raise RecoveryError(422, "Invalid recovery mirror matrix.")
        for v in matrix:
            _number(v, -1e9, 1e9, "mirror matrix coefficient")
        if matrix[0] * matrix[3] - matrix[1] * matrix[2] >= -1e-12:
            raise RecoveryError(422, "Recovery mirror calibration is not a nonsingular reflection.")
        link_ids.add(link["id"])
        endpoints.update((a, b))
    return value


def _project(value, vehicle):
    if (not isinstance(value, dict) or value.get("format") != FORMAT
            or set(value) - {"format", "vehicle", "vinyls", "placements", "vehicle_parts", "authoring"}):
        raise RecoveryError(422, "Expected a layout v1 project, not application settings.")
    if _vehicle(value.get("vehicle")) != vehicle:
        raise RecoveryError(422, "Recovery belongs to a different car.")
    vinyls, placements = value.get("vinyls"), value.get("placements")
    if (not isinstance(vinyls, list) or len(vinyls) > 16
            or not isinstance(placements, list) or len(placements) > 200):
        raise RecoveryError(422, "Recovery exceeds the layout authoring limits.")
    ids, placement_ids, sources, items = set(), set(), [], []
    for source in vinyls:
        if not isinstance(source, dict) or set(source) != {"id", "name", "shapes"}:
            raise RecoveryError(422, "Invalid recovery vinyl source.")
        source_id = _text(source.get("id"), 100, "source ID")
        if source_id in ids:
            raise RecoveryError(422, "Duplicate recovery source ID.")
        ids.add(source_id)
        _text(source.get("name"), 160, "source name")
        try:
            # Structural validation only; exact native assets are checked by the
            # normal atomic project loader at restore, not guessed by recovery.
            validate_shapes({"shapes": source.get("shapes")}, lambda _kind: True)
        except ValidationError as exc:
            raise RecoveryError(422, str(exc)) from exc
        sources.append(source)
    limits = {"x": (-4096, 4096), "y": (-4096, 4096), "scaleX": (.01, 8),
              "scaleY": (.01, 8), "rotation": (-3600, 3600), "opacity": (0, 1)}
    for placement in placements:
        if (not isinstance(placement, dict)
                or set(placement) - {"id", "vinylId", "section", "visible", "skew", *limits}
                or not isinstance(placement.get("vinylId"), str) or placement["vinylId"] not in ids
                or not isinstance(placement.get("section"), str) or placement["section"] not in SECTIONS
                or type(placement.get("visible")) is not bool):
            raise RecoveryError(422, "Invalid recovery placement.")
        pid = _text(placement.get("id"), 100, "placement ID")
        if pid in placement_ids:
            raise RecoveryError(422, "Duplicate recovery placement ID.")
        placement_ids.add(pid)
        for key, bounds in limits.items():
            _number(placement.get(key), *bounds, key)
        if "skew" in placement:
            _number(placement["skew"], -4, 4, "skew")
        items.append(placement)
    result = {"format": FORMAT, "vehicle": vehicle, "vinyls": sources, "placements": items}
    if "authoring" in value:
        result["authoring"] = _authoring(value["authoring"], items)
    if "vehicle_parts" in value:
        parts = value["vehicle_parts"]
        if not isinstance(parts, dict) or len(parts) > 128:
            raise RecoveryError(422, "Invalid recovery component map.")
        for part, option in parts.items():
            _text(part, 128, "component type")
            if option is not None and (type(option) is not int or abs(option) > 2**53 - 1):
                raise RecoveryError(422, "Invalid recovery component option.")
        result["vehicle_parts"] = parts
    try:
        raw = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise RecoveryError(422, "Recovery must contain finite JSON data.") from exc
    if len(raw) > MAX_PROJECT_BYTES:
        raise RecoveryError(413, "Recovery layout exceeds 32 MiB.")
    return raw


class RecoveryStore:
    def __init__(self, root, *, allowed_root=None, readonly=False, limits=None):
        self.root = Path(root).absolute()
        self.path = self.root / "recovery.sqlite3"
        self.allowed_root = Path(allowed_root or LAB_ROOT).absolute()
        self.readonly = bool(readonly)
        self.limits = dict(limits or {})
        self._check_paths()

    def _check_paths(self):
        try:
            from .storage_paths import SafeRoot
            SafeRoot(self.allowed_root).check(self.root, directory=True, missing=True)
            relative = self.root.relative_to(self.allowed_root)
            if not relative.parts:
                raise ValueError()
            current = self.allowed_root
            for segment in (*relative.parts, "recovery.sqlite3"):
                current /= segment
                if current.exists() or current.is_symlink():
                    info = current.lstat()
                    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                            or (stat.S_ISREG(info.st_mode) and info.st_nlink > 1)):
                        raise ValueError()
            self.root.resolve().relative_to(self.allowed_root.resolve())
            for suffix in ("-journal", "-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                try:
                    info = sidecar.lstat()
                except FileNotFoundError:
                    # Another connection can remove its journal after commit.
                    # Inspect once; an exists()/lstat() pair races that cleanup.
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1 or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError()
        except (ValueError, OSError) as exc:
            raise RecoveryError(500, "Recovery storage must be an ordinary directory inside the isolated workspace.") from exc

    @contextmanager
    def _database(self):
        self._check_paths()
        connection = None
        try:
            if not self.readonly:
                self.root.mkdir(parents=True, exist_ok=True)
            connection = (sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
                          if self.readonly else sqlite3.connect(self.path, timeout=5))
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA trusted_schema=OFF")
            # Inspect before changing any on-disk pragmas on an unfamiliar DB.
            # One read transaction keeps version/table checks consistent while
            # another host initializes this same store for the first time.
            connection.execute("BEGIN")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RecoveryError(409, "Recovery was created by a newer version. Existing data was not changed.")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if (version == 0 and tables) or (version == 1 and tables != {"entries"}):
                raise RecoveryError(409, "The recovery database is unrelated or incompatible. It was not replaced.")
            if self.readonly:
                # A refused first write can leave SQLite's empty version-zero
                # container after rollback. It is empty, not corrupt or owned.
                yield connection if version == 1 else None
                connection.rollback()
                return
            connection.commit()
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA auto_vacuum=FULL")
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RecoveryError(409, "Recovery was created by a newer version. Existing data was not changed.")
            if version == 0 and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                raise RecoveryError(409, "The recovery location contains an unrelated database. It was not replaced.")
            connection.execute("CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, "
                               "car_id INTEGER NOT NULL, model_code TEXT NOT NULL, document_id TEXT NOT NULL, "
                               "kind TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL, "
                               "bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, sources INTEGER NOT NULL, "
                               "placements INTEGER NOT NULL, project BLOB NOT NULL)")
            connection.execute("PRAGMA user_version=1")
            yield connection
            connection.commit()
        except RecoveryError:
            if connection:
                connection.rollback()
            raise
        except (sqlite3.Error, OSError) as exc:
            if connection:
                connection.rollback()
            raise RecoveryError(503, "Recovery storage is unavailable, busy or corrupt. Existing entries were not replaced.") from exc
        finally:
            if connection:
                connection.close()

    @staticmethod
    def _metadata(row):
        return {key: row[key] for key in ("id", "document_id", "kind", "name", "created_at", "bytes", "sources", "placements")}

    def list(self, vehicle):
        vehicle = _vehicle(vehicle)
        if self.readonly and not self.path.exists():
            return {"version": 1, "entries": [], "limits": self._limit_info()}
        with self._database() as db:
            rows = [] if db is None else db.execute("SELECT id,document_id,kind,name,created_at,bytes,sources,placements FROM entries "
                              "WHERE car_id=? AND model_code=? ORDER BY seq DESC",
                              (vehicle["car_id"], vehicle["model_code"])).fetchall()
        return {"version": 1, "entries": [self._metadata(row) for row in rows], "limits": self._limit_info()}

    @staticmethod
    def _limit_info():
        return {"project_bytes": MAX_PROJECT_BYTES, "total_bytes": MAX_TOTAL_BYTES,
                "auto_per_document": AUTO_PER_DOCUMENT, "protected_entries": MAX_PROTECTED}

    def usage(self):
        if self.readonly and not self.path.exists():
            return {"entries": 0, "bytes": 0, "auto": 0, "protected": 0}
        with self._database() as db:
            if db is None:
                return {"entries": 0, "bytes": 0, "auto": 0, "protected": 0}
            row = db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0),COALESCE(SUM(kind='auto'),0),"
                             "COALESCE(SUM(kind!='auto'),0) FROM entries").fetchone()
        if any(type(value) is not int or value < 0 for value in row):
            raise RecoveryError(409, "Recovery storage usage is inconsistent.")
        return dict(zip(("entries", "bytes", "auto", "protected"), row))

    def _read_row(self, db, vehicle, entry_id):
        if db is None:
            raise RecoveryError(404, "This recovery entry is no longer available for this car.")
        row = db.execute("SELECT id,document_id,kind,name,created_at,bytes,sha256,sources,placements, "
                         "CASE WHEN length(project)<=? THEN project ELSE NULL END AS project "
                         "FROM entries WHERE id=? AND car_id=? AND model_code=?",
                         (MAX_PROJECT_BYTES, entry_id, vehicle["car_id"], vehicle["model_code"])).fetchone()
        if row is None:
            raise RecoveryError(404, "This recovery entry is no longer available for this car.")
        raw = row["project"]
        try:
            if (not isinstance(raw, bytes) or len(raw) > MAX_PROJECT_BYTES or len(raw) != row["bytes"]
                    or hashlib.sha256(raw).hexdigest() != row["sha256"]):
                raise ValueError()
            project = decode_json(raw)
            _project(project, vehicle)
        except (ValueError, TypeError) as exc:
            raise RecoveryError(409, "This recovery entry is corrupt or incompatible. The current layout was not changed.") from exc
        return row, project

    def read(self, vehicle, entry_id):
        vehicle, entry_id = _vehicle(vehicle), _id(entry_id)
        if self.readonly and not self.path.exists():
            raise RecoveryError(404, "This recovery entry is no longer available for this car.")
        with self._database() as db:
            row, project = self._read_row(db, vehicle, entry_id)
        return {"version": 1, "entry": self._metadata(row), "project": project}

    def _insert(self, db, vehicle, document_id, kind, name, raw):
        if self.readonly:
            raise RecoveryError(405, "The legacy recovery store is read-only.")
        maximum_auto = self.limits.get("auto", MAX_AUTO)
        maximum_protected = self.limits.get("protected", MAX_PROTECTED)
        maximum_entries = self.limits.get("entries", MAX_ENTRIES)
        maximum_bytes = self.limits.get("bytes", MAX_TOTAL_BYTES)
        digest = hashlib.sha256(raw).hexdigest()
        if kind == "auto":
            previous = db.execute("SELECT id,document_id,kind,name,created_at,bytes,sha256,sources,placements, "
                                  "CASE WHEN length(project)<=? THEN project ELSE NULL END AS project "
                                  "FROM entries WHERE car_id=? AND model_code=? AND document_id=? "
                                  "AND kind='auto' ORDER BY seq DESC LIMIT 1",
                                  (MAX_PROJECT_BYTES, vehicle["car_id"], vehicle["model_code"], document_id)).fetchone()
            if (previous and previous["sha256"] == digest and isinstance(previous["project"], bytes)
                    and len(previous["project"]) == previous["bytes"]
                    and hashlib.sha256(previous["project"]).hexdigest() == digest):
                return self._metadata(previous)
        elif db.execute("SELECT COUNT(*) FROM entries WHERE kind!='auto'").fetchone()[0] >= maximum_protected:
            raise RecoveryError(507, "The protected recovery/checkpoint limit is reached. Save the layout to a file; no checkpoint was removed.")
        if kind == "auto":
            if maximum_auto <= 0:
                raise RecoveryError(507, "Other cars use the automatic recovery budget. No other car's snapshots were removed.")
            old = db.execute("SELECT id FROM entries WHERE car_id=? AND model_code=? AND document_id=? AND kind='auto' "
                             "ORDER BY seq DESC LIMIT -1 OFFSET ?",
                             (vehicle["car_id"], vehicle["model_code"], document_id, AUTO_PER_DOCUMENT - 1)).fetchall()
            db.executemany("DELETE FROM entries WHERE id=?", [(row[0],) for row in old])
            old = db.execute("SELECT id FROM entries WHERE kind='auto' ORDER BY seq DESC LIMIT -1 OFFSET ?", (maximum_auto - 1,)).fetchall()
            db.executemany("DELETE FROM entries WHERE id=?", [(row[0],) for row in old])
        while True:
            count, size = db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM entries").fetchone()
            if count < maximum_entries and size + len(raw) <= maximum_bytes:
                break
            oldest = db.execute("SELECT id FROM entries WHERE kind='auto' ORDER BY seq LIMIT 1").fetchone()
            if not oldest:
                raise RecoveryError(507, "Recovery storage is full. Save the layout to a file; protected checkpoints were not removed.")
            db.execute("DELETE FROM entries WHERE id=?", (oldest[0],))
        project = decode_json(raw)
        entry_id = uuid.uuid4().hex
        db.execute("INSERT INTO entries(id,car_id,model_code,document_id,kind,name,created_at,bytes,sha256,sources,placements,project) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (entry_id, vehicle["car_id"], vehicle["model_code"], document_id, kind, name,
                    datetime.now(timezone.utc).isoformat(timespec="milliseconds"), len(raw), digest,
                    len(project["vinyls"]), len(project["placements"]), raw))
        return self._metadata(db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone())

    def save(self, vehicle, payload):
        vehicle = _vehicle(vehicle)
        if not isinstance(payload, dict) or set(payload) - {"document_id", "kind", "name", "project"}:
            raise RecoveryError(422, "Invalid recovery request.")
        document_id = _id(payload.get("document_id"))
        kind = payload.get("kind")
        if kind not in ("auto", "checkpoint"):
            raise RecoveryError(422, "Choose an automatic snapshot or named checkpoint.")
        name = _text(payload.get("name"), 80, "checkpoint name").strip() if kind == "checkpoint" else "Automatic recovery"
        raw = _project(payload.get("project"), vehicle)
        with self._database() as db:
            entry = self._insert(db, vehicle, document_id, kind, name, raw)
        return {"version": 1, "entry": entry}

    def prepare_restore(self, vehicle, entry_id, payload):
        vehicle, entry_id = _vehicle(vehicle), _id(entry_id)
        if not isinstance(payload, dict) or set(payload) != {"document_id", "current_project"}:
            raise RecoveryError(422, "Invalid recovery restore request.")
        document_id = _id(payload["document_id"])
        current = _project(payload["current_project"], vehicle)
        with self._database() as db:
            row, project = self._read_row(db, vehicle, entry_id)
            # Target is verified before retaining current. Both retention and
            # pruning commit together; the caller loads only after this returns.
            retained = self._insert(db, vehicle, document_id, "before-restore", "Before restore", current)
            return {"version": 1, "entry": self._metadata(row), "retained": retained, "project": project}
