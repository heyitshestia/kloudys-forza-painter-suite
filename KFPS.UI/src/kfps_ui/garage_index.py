"""Minimal local garage records and bounded, read-only comparisons."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from datetime import datetime, timezone

MAX_CARS = 10000
MAX_BYTES = 16 * 1024 * 1024
PARTS = ("CarBody", "RearWing", "FrontBumper", "RearBumper", "Hood", "SideSkirts",
         "Rims", "RimStyle", "WheelStyle", "WheelStyleRear", "RimSizeFront", "RimSizeRear",
         "TireWidthFront", "TireWidthRear", "TrackSpacingFront", "TrackSpacingRear",
         "FrontAspectRatio", "RearAspectRatio", "TireCompound", "TireBrand", "ChassisStiffness")
REQUIRED = PARTS[:6]
BODY_PARTS = ("CarBody", "ChassisStiffness", "FrontBumper", "Hood", "RearBumper", "RearWing", "SideSkirts")
TOKEN = re.compile(r"[a-f0-9]{64}\Z")
FORMAT = 2


def clean_diagnostics(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for name in ("loaded", "busy", "historyAvailable", "lastScanReused", "accountsDiscovered", "accountSelected", "catalogueBusy"):
        if type(value.get(name)) is bool:
            result[name] = value[name]
    for name, maximum in (("carCount", MAX_CARS), ("comparisonCount", 100), ("lastScanMs", 600000), ("accountCount", 65),
                          ("catalogueCount", 4096), ("stockThumbnailCount", 4096)):
        if type(value.get(name)) is int and 0 <= value[name] <= maximum:
            result[name] = value[name]
    return result


class GarageError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_vehicle_identity(value):
    if (not isinstance(value, dict) or set(value) != {"car_id", "model_code"}
            or type(value["car_id"]) is not int or not 0 < value["car_id"] < 2**31
            or not isinstance(value["model_code"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", value["model_code"])):
        raise GarageError("The selected Garage car identity is unavailable. Refresh Garage and link FH6.")
    return dict(value)


def validate_body_snapshot(value):
    if (not isinstance(value, dict) or set(value) != {"version", "parts", "fingerprint"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["parts"], dict) or set(value["parts"]) != set(BODY_PARTS)
            or not isinstance(value["fingerprint"], str) or not TOKEN.fullmatch(value["fingerprint"])):
        raise GarageError("The Garage body snapshot is invalid. Refresh Garage and try again.")
    parts = {name: value["parts"][name] for name in BODY_PARTS}
    if any(part is not None and (type(part) is not int or not -1 <= part < 2**31) for part in parts.values()):
        raise GarageError("The Garage body snapshot contains an invalid part.")
    normalized = {"version": 1, "parts": parts}
    if value["fingerprint"] != digest(normalized):
        raise GarageError("The Garage body snapshot has changed. Refresh Garage and try again.")
    return {**normalized, "fingerprint": value["fingerprint"]}


def body_snapshot(row):
    # Historical snapshots remain useful for comparisons, not complete builds.
    parts = row.get("parts") if isinstance(row, dict) else None
    if not isinstance(parts, dict) or any(name not in parts for name in BODY_PARTS):
        raise GarageError("Refresh Garage before opening this build; its saved body selection is incomplete.")
    value = {"version": 1, "parts": {name: parts[name] for name in BODY_PARTS}}
    return validate_body_snapshot({**value, "fingerprint": digest(value)})


def log_body_launch(log, target, outcome, snapshot=None):
    target = target if target in {"selection", "preview", "studio", "artwork", "project"} else "unknown"
    outcome = outcome if outcome in {"requested", "queued", "cancelled", "unavailable", "stale",
                                    "prepared", "ready", "handoff", "rejected"} else "unknown"
    parts = snapshot.get("parts", {}) if isinstance(snapshot, dict) else {}
    parts = parts if isinstance(parts, dict) else {}
    present = sum(name in parts for name in BODY_PARTS)
    known = sum(type(parts.get(name)) is int and -1 <= parts[name] < 2**31 for name in BODY_PARTS)
    log.append(f"Garage build: target={target}; outcome={outcome}; body_slots={present}; "
               f"known_parts={known}; unknown_parts={present - known}", update_status=False)


def resolve_body_vehicle(game_folder, vehicle_index, car_id, *, model_code=None, cancel_event=None):
    from tools.livery.vehicle_assets import load_or_build_vehicle_asset_index
    def cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Garage build launch cancelled")
    cancelled()
    if not game_folder:
        raise GarageError("Choose the local FH6 game folder before opening a Garage build.")
    if type(car_id) is not int or not 0 < car_id < 2**31:
        raise GarageError("The selected Garage car identity is invalid.")
    asset = load_or_build_vehicle_asset_index(game_folder, vehicle_index).get(car_id)
    cancelled()
    if asset is None or asset.car_id != car_id:
        raise GarageError("The local FH6 installation has no exact archive for this Garage car.")
    validate_vehicle_identity({"car_id": asset.car_id, "model_code": asset.model_code})
    if model_code is not None and asset.model_code != model_code:
        raise GarageError("The Garage car does not exactly match the local FH6 model. Refresh Garage and try again.")
    return asset


def profile_identity(source):
    return hashlib.sha256(os.path.normcase(str(Path(source).resolve())).encode()).hexdigest()


def artwork_identity(path, kind):
    path = Path(path)
    if kind not in ("package", "save") or not path.is_absolute():
        raise GarageError("Choose local Garage artwork.")
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise GarageError("Redirected artwork locations are not supported.")
    info = path.stat()
    limit = (256 if kind == "package" else 16) * 1024**2
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
        raise GarageError("The artwork is not a supported regular file.")
    return info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev


def artwork_fingerprint(path, kind, expected, cancel):
    """Bind a click to stable source bytes without reading large files on the UI."""
    def check():
        if cancel.is_set():
            raise InterruptedError("Artwork launch cancelled")
    check()
    if artwork_identity(path, kind) != expected:
        raise GarageError("Artwork changed during launch. Select it again.")
    hasher, count = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns, opened.st_ino, opened.st_dev) != expected:
            raise GarageError("Artwork changed during launch. Select it again.")
        while block := stream.read(min(1024**2, expected[0] + 1 - count)):
            check()
            count += len(block)
            if count > expected[0]:
                raise GarageError("Artwork changed during launch. Select it again.")
            hasher.update(block)
        finished = os.fstat(stream.fileno())
    if (count != expected[0] or artwork_identity(path, kind) != expected
            or (finished.st_size, finished.st_mtime_ns, finished.st_ino, finished.st_dev) != expected):
        raise GarageError("Artwork changed during launch. Select it again.")
    check()
    return hasher.hexdigest()


def reference(value):
    if value is None:
        return ""
    if (not isinstance(value, str) or len(value) > 256
            or any(ord(c) < 32 for c in value) or any(c in value for c in '/\\:')
            or value in (".", "..")):
        raise GarageError("The garage contains an invalid file reference.")
    return value


def normalize_garage(value):
    if not isinstance(value, list) or len(value) > MAX_CARS:
        raise GarageError("The garage has an unsupported record count.")
    seen, rows = set(), []
    for item in value:
        if not isinstance(item, dict):
            raise GarageError("The garage contains an invalid car record.")
        ident, model = item.get("Id"), item.get("CarId")
        if (type(ident) is not int or not 0 <= ident < 2**63
                or type(model) is not int or not 0 < model < 2**31 or ident in seen):
            raise GarageError("The garage contains invalid or repeated car identities.")
        seen.add(ident)
        parts = {}
        for name in PARTS:
            part = item.get(name)
            if part is None and name not in REQUIRED:
                parts[name] = None
            elif type(part) is int and -1 <= part < 2**31:
                parts[name] = part
            else:
                raise GarageError("The garage contains an unsupported saved part.")
        rows.append({"instanceId": str(ident), "carId": model, "parts": parts,
                     "liveryRef": reference(item.get("LiveryFileName")),
                     "tuneRef": reference(item.get("TuneFileName")),
                     "buildSignature": digest([model, parts])})
    return rows


def snapshot_records(value):
    if isinstance(value, list):
        return normalize_garage(value), ""
    if (not isinstance(value, dict) or set(value) != {"format", "profileToken", "cars"}
            or value["format"] != "kfps-garage-snapshot-v1"
            or not isinstance(value["profileToken"], str)
            or value["profileToken"] and not TOKEN.fullmatch(value["profileToken"])):
        raise GarageError("The garage snapshot identity is invalid.")
    return normalize_garage(value["cars"]), value["profileToken"]


def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > MAX_CARS:
        raise GarageError("The garage index is invalid.")
    raw = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("instanceId"), str)
                or not row["instanceId"].isascii() or not row["instanceId"].isdigit()
                or len(row["instanceId"]) > 19 or not isinstance(row.get("parts"), dict)):
            raise GarageError("The garage index is invalid.")
        raw.append({**row["parts"], "Id": int(row["instanceId"]), "CarId": row.get("carId"),
                    "LiveryFileName": row.get("liveryRef"), "TuneFileName": row.get("tuneRef")})
    normalized = normalize_garage(raw)
    for old, current in zip(rows, normalized):
        if old == current:
            continue
        # Preserve valid pre-body-build named comparisons without treating an
        # absent chassis selection as stock. The cache loader requires a scan.
        legacy = {**current, "parts": {k: v for k, v in current["parts"].items() if k != "ChassisStiffness"}}
        legacy["buildSignature"] = digest([current["carId"], legacy["parts"]])
        if old != legacy:
            raise GarageError("The garage index requires a fresh scan.")
    return normalized


def compare_builds(before, after):
    result = []
    def add(label, left, right):
        if left != right:
            result.append({"field": label, "before": "Unknown" if left is None else str(left),
                           "after": "Unknown" if right is None else str(right)})
    add("Car model", before["carId"], after["carId"])
    for name in PARTS:
        add(name, before["parts"].get(name), after["parts"].get(name))
    add("Livery", before["liveryRef"], after["liveryRef"])
    add("Tune", before["tuneRef"], after["tuneRef"])
    return result


def match_livery(car, sources, profile):
    if not car["liveryRef"]:
        return {"status": "none", "path": "", "title": "No saved livery reference"}
    root = Path(profile).resolve().parent.parent
    matches = []
    for source in sources:
        if source.get("carId") != car["carId"]:
            continue
        path = Path(str(source.get("path") or ""))
        # Require the same save root and the actual stored container name.
        if (path.parent.name.casefold() == car["liveryRef"].casefold()
                and path.resolve().parent.parent == root):
            matches.append(source)
    if len(matches) != 1:
        return {"status": "ambiguous" if matches else "unavailable", "path": "",
                "title": "Multiple matching liveries" if matches else "Not in scanned saves"}
    return {"status": "matched", "path": matches[0]["path"],
            "title": str(matches[0].get("title") or car["liveryRef"])}


def available_livery_models(sources, packages, profile):
    """Library availability by car, not applied artwork or export authorship.

    Availability is probed by the existing library refresh. No file contents,
    renders, or additional scanner are needed to filter the Garage afterwards.
    """
    try:
        root = Path(profile).resolve().parent.parent if profile else None
    except (OSError, ValueError):
        return set()
    cars = set()
    for rows, account_scoped in ((sources, True), (packages, False)):
        for row in rows:
            car_id, path = row.get("carId"), row.get("path")
            if (type(car_id) is not int or not 0 < car_id < 2**31 or row.get("available") is not True
                    or not isinstance(path, str) or not path or "\0" in path):
                continue
            if car_id in cars:
                continue
            try:
                file = Path(path)
                if not file.is_absolute():
                    continue
                if account_scoped and root is not None and file.resolve().parent.parent != root:
                    continue
            except (OSError, ValueError):
                continue
            cars.add(car_id)
    return cars


def atomic_json(path, value, *, before_commit=None):
    path = Path(path)
    data = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_BYTES:
        raise GarageError("The garage index exceeds its storage limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".garage-", delete=False) as stream:
            name = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if name.read_bytes() != data:
            raise OSError("Garage index readback failed.")
        if before_commit:
            before_commit()
        os.replace(name, path)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def read_json(path):
    with Path(path).open("rb") as stream:
        data = stream.read(min(os.fstat(stream.fileno()).st_size, MAX_BYTES) + 1)
    return parse_json(data)


def parse_json(data):
    if len(data) > MAX_BYTES:
        raise GarageError("The garage file exceeds its size limit.")
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise GarageError("The garage file contains repeated fields.")
            result[name] = value
        return result
    def invalid(_):
        raise GarageError("The garage file contains an invalid number.")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


class GarageStore:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, ident):
        if not isinstance(ident, str) or not TOKEN.fullmatch(ident):
            raise GarageError("Invalid local garage identity.")
        return self.root / (ident + ".json")

    def load(self, ident):
        path = self.path(ident)
        try:
            state = read_json(path)
            if (not isinstance(state, dict) or state.get("format") != FORMAT
                    or state.get("profile") != ident or not TOKEN.fullmatch(state.get("sourceHash", ""))
                    or not isinstance(state.get("scope"), str)
                    or state["scope"] and not TOKEN.fullmatch(state["scope"])
                    or not isinstance(state.get("history"), list) or len(state["history"]) > 20
                    or state.get("checksum") != digest({k: v for k, v in state.items() if k != "checksum"})):
                return None
            validate_rows(state["cars"])
            if any("ChassisStiffness" not in row["parts"] for row in state["cars"]):
                return None
            allowed = {"Added", "Removed", "Car model", "Livery", "Tune", *PARTS}
            for event in state["history"]:
                if (not isinstance(event, dict) or set(event) != {"at", "count", "changes"}
                        or not isinstance(event["at"], str) or len(event["at"]) > 40
                        or type(event["count"]) is not int or not 1 <= event["count"] <= 2 * MAX_CARS
                        or not isinstance(event["changes"], list) or not 1 <= len(event["changes"]) <= 200):
                    return None
                for change in event["changes"]:
                    if (not isinstance(change, dict) or set(change) != {"instanceId", "carId", "fields"}
                            or not isinstance(change["instanceId"], str) or not change["instanceId"].isascii()
                            or not change["instanceId"].isdigit() or len(change["instanceId"]) > 19
                            or type(change["carId"]) is not int or not 0 < change["carId"] < 2**31
                            or not isinstance(change["fields"], list) or not 1 <= len(change["fields"]) <= len(allowed)
                            or any(not isinstance(field, str) or field not in allowed for field in change["fields"])):
                        return None
            return state
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            return None

    def publish(self, ident, source_hash, rows, *, history, scope="", before_commit=None):
        validate_rows(rows)
        if not TOKEN.fullmatch(source_hash):
            raise GarageError("Invalid garage source signature.")
        if not isinstance(scope, str) or scope and not TOKEN.fullmatch(scope):
            raise GarageError("Invalid garage profile scope.")
        old = self.load(ident)
        # A locator is not proof of profile continuity. Unscoped readers can
        # browse/compare snapshots, but cannot accumulate automatic associations.
        continuous = bool(scope and old and old["scope"] == scope)
        events = list(old["history"]) if continuous and history else []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if continuous and history and old["cars"] != rows:
            previous = {row["instanceId"]: row for row in old["cars"]}
            current = {row["instanceId"]: row for row in rows}
            changes = []
            for instance in sorted(set(previous) | set(current), key=int):
                a, b = previous.get(instance), current.get(instance)
                fields = (["Added"] if a is None else ["Removed"] if b is None else
                          [item["field"] for item in compare_builds(a, b)])
                if fields:
                    changes.append({"instanceId": instance, "carId": (b or a)["carId"], "fields": fields})
            if changes:
                events.append({"at": now, "count": len(changes), "changes": changes[:200]})
        state = {"format": FORMAT, "profile": ident, "scope": scope, "sourceHash": source_hash,
                 "scannedAt": now, "cars": rows, "history": events[-20:]}
        state["checksum"] = digest(state)
        atomic_json(self.path(ident), state, before_commit=before_commit)
        return state

    def clear_history(self):
        if not self.root.is_dir():
            return
        for path in self.root.glob("*.json"):
            if TOKEN.fullmatch(path.stem):
                state = self.load(path.stem)
                if state:
                    self.publish(path.stem, state["sourceHash"], state["cars"], history=False, scope=state["scope"])
