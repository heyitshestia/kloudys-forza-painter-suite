"""Per-car recovery stores with one shared budget and read-only legacy fallback."""
from . import recovery as r
from .project_storage import MAX_CARS, car_identity


class CarRecoveryStore:
    def __init__(self, projects, legacy_root):
        self.projects = projects
        self.legacy_root = legacy_root

    def _legacy(self):
        return r.RecoveryStore(self.legacy_root, readonly=True)

    def _store(self, car, *, readonly=True, limits=None):
        return r.RecoveryStore(self.projects.root / car["folder"] / "recovery",
                               allowed_root=self.projects.root, readonly=readonly, limits=limits)

    def _managed_list(self, vehicle):
        with self.projects.safe.lock(create=False) as exists:
            if not exists or self.projects.safe.check(self.projects.path, directory=False, missing=True) is None:
                return []
            with self.projects.database() as db:
                car = self.projects.car(db, vehicle)
                return [] if car is None else self._store(car).list(vehicle)["entries"]

    def list(self, vehicle):
        vehicle = r._vehicle(vehicle)
        entries = self._managed_list(vehicle)
        known = {entry["id"] for entry in entries}
        warning = None
        try:
            for entry in self._legacy().list(vehicle)["entries"]:
                if entry["id"] not in known:
                    entries.append({**entry, "source": "legacy"})
                    known.add(entry["id"])
        except (r.RecoveryError, ValueError):
            warning = "The preserved legacy recovery store is unavailable or incompatible. It was not changed."
        entries.sort(key=lambda entry: (entry["created_at"], entry["id"]), reverse=True)
        result = {"version": 1, "entries": entries,
                  "limits": {**r.RecoveryStore._limit_info(), "entries": r.MAX_ENTRIES, "automatic_entries": r.MAX_AUTO,
                             "scope": "managed-root", "legacy_separate": True}}
        if warning:
            result["legacy_warning"] = warning
        return result

    def _write_store(self, vehicle):
        # Caller holds the root OS lock. Register the folder first so a process
        # interruption after the per-car SQLite commit cannot hide its usage.
        with self.projects.database() as db:
            car = self.projects.car(db, vehicle, create=True)
            cars = db.execute("SELECT * FROM cars LIMIT ?", (MAX_CARS + 1,)).fetchall()
        if len(cars) > MAX_CARS:
            raise r.RecoveryError(507, "The recovery car catalogue exceeds its limit.")
        remaining = {"entries": r.MAX_ENTRIES, "bytes": r.MAX_TOTAL_BYTES,
                     "auto": r.MAX_AUTO, "protected": r.MAX_PROTECTED}
        for other in cars:
            # Revalidate every registry path; a corrupt row must not turn a
            # global budget scan into an arbitrary filesystem read.
            _value, key, folder = car_identity({"car_id": other["car_id"], "model_code": other["model_code"]})
            if key != other["key"] or folder != other["folder"]:
                raise r.RecoveryError(409, "The recovery car catalogue is inconsistent.")
            if other["key"] != car["key"]:
                for key, amount in self._store(other).usage().items():
                    remaining[key] -= amount
        return self._store(car, readonly=False, limits={key: max(0, value) for key, value in remaining.items()})

    def save(self, vehicle, payload):
        vehicle = r._vehicle(vehicle)
        # Validate before creating a managed directory or touching any budget.
        if not isinstance(payload, dict) or set(payload) - {"document_id", "kind", "name", "project"}:
            raise r.RecoveryError(422, "Invalid recovery request.")
        r._id(payload.get("document_id"))
        if payload.get("kind") not in ("auto", "checkpoint"):
            raise r.RecoveryError(422, "Choose an automatic snapshot or named checkpoint.")
        if payload["kind"] == "checkpoint":
            r._text(payload.get("name"), 80, "checkpoint name")
        r._project(payload.get("project"), vehicle)
        with self.projects.safe.lock():
            return self._write_store(vehicle).save(vehicle, payload)

    def prepare_restore(self, vehicle, entry_id, payload):
        vehicle, entry_id = r._vehicle(vehicle), r._id(entry_id)
        if not isinstance(payload, dict) or set(payload) != {"document_id", "current_project"}:
            raise r.RecoveryError(422, "Invalid recovery restore request.")
        document_id = r._id(payload["document_id"])
        current = r._project(payload["current_project"], vehicle)
        with self.projects.safe.lock():
            with self.projects.database() as db:
                car = self.projects.car(db, vehicle)
            if car is not None:
                try:
                    target = self._store(car).read(vehicle, entry_id)
                except r.RecoveryError as exc:
                    if exc.status != 404:
                        raise
                else:
                    return self._write_store(vehicle).prepare_restore(vehicle, entry_id, payload)
            target = self._legacy().read(vehicle, entry_id)
            store = self._write_store(vehicle)
            with store._database() as db:
                retained = store._insert(db, vehicle, document_id, "before-restore", "Before restore", current)
            return {**target, "entry": {**target["entry"], "source": "legacy"}, "retained": retained}
