from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .garage_index import (GarageError, GarageStore, PARTS, atomic_json, compare_builds,
                           match_livery, available_livery_models, profile_identity, read_json, body_snapshot, resolve_body_vehicle, log_body_launch,
                           artwork_identity, artwork_fingerprint)
from .experimental.full_livery.paths import FullLiveryPaths
from .garage_reader import scan
from .garage_notes import GarageNotes, inspect_project, resolve_project
from .garage_accounts import discover_accounts, resolve_account, account_for_source
from .models import DictListModel


def load_catalogue(*args):
    from .garage_catalogue import load_catalogue as load
    return load(*args)


def catalogue_signature(*args):
    from .garage_catalogue import catalogue_signature as signature
    return signature(*args)


class GarageService(QObject):
    changed = Signal()
    liveryRequested = Signal(str)
    previewRequested = Signal("QVariantMap", "QVariantMap")
    studioRequested = Signal("QVariantMap", "QVariantMap", str)
    stockPreviewRequested = Signal("QVariantMap")
    stockStudioRequested = Signal("QVariantMap")
    artworkRequested = Signal("QVariantMap", "QVariantMap", str, str, str)
    projectRequested = Signal("QVariantMap")
    _finished = Signal(object)
    _projectFinished = Signal(object)
    _buildFinished = Signal(object)
    _accountsFinished = Signal(object)
    _catalogueFinished = Signal(object)
    FILTERS = ("all", "livery", "duplicates", "owned")
    SORTS = ("name", "owned", "livery")
    ROLES = ("instanceId", "carId", "title", "detail", "livery", "buildSignature", "owned", "thumbnailUrl", "hasLivery")

    def __init__(self, paths, log, liveries, parent=None):
        super().__init__(parent)
        self.paths, self.log, self.liveries = paths, log, liveries
        self.root = paths.runtime_root / "garage"
        self.store = GarageStore(self.root / "index")
        self.notes = GarageNotes(self.root / "comparisons.json")
        self._notes = []
        self._note_id = ""
        self._project_status = ""
        self._model = DictListModel(self.ROLES, self)
        self._source = ""
        self._accounts = []
        self._selected_account = {}
        self._accounts_attempted = False
        self._accounts_discovered = False
        self._account_status = "Choose an FH6 account"
        self._summary = {"cars": 0, "models": 0, "liveries": 0, "duplicates": 0, "scanned": ""}
        self._state = None
        self._settings = {}
        self._persisted_settings = None
        self._settings_read_failed = False
        self._loaded = False
        self._closed = False
        self._busy = False
        self._status = "No garage selected"
        self._search = ""
        self._filter = "all"
        self._sort = "name"
        self._selected = ""
        self._compare = None
        self._names = {}
        self._catalogue_stamp = None
        self._catalogue = {}
        self._catalogue_game = None
        self._catalogue_source_stamp = None
        self._catalogue_status = ""
        self._catalogue_busy = False
        self._catalogue_cancel = threading.Event()
        self._catalogue_thread = None
        self._indexed_rows = None
        self._rows_by_id = {}
        self._ordered_rows_source = None
        self._ordered_rows = []
        self._display_names = {}
        self._counts = {}
        self._sources_dirty = True
        self._visible_ids = ()
        self._view_filter = None
        self._match_cache = None
        self._artwork_by_car = {}
        self._thread = None
        self._build_row = None
        self._build_serial = 0
        self._last_scan_ms = 0
        self._last_scan_reused = False
        self._cancel = threading.Event()
        self._finished.connect(self._apply)
        self._projectFinished.connect(self._apply_project)
        self._buildFinished.connect(self._apply_build)
        self._accountsFinished.connect(self._apply_accounts)
        self._catalogueFinished.connect(self._apply_catalogue)
        self.liveries.sourceModel.dataChanged.connect(self._source_data_changed)
        for signal in (self.liveries.sourceModel.modelReset,
                       self.liveries.sourceModel.rowsInserted, self.liveries.sourceModel.rowsRemoved,
                       self.liveries.sourceModel.layoutChanged):
            signal.connect(self._sources_changed)
        packages = getattr(self.liveries, "packageModel", None)
        if packages is not None:
            packages.dataChanged.connect(self._packages_changed)
            for signal in (packages.modelReset, packages.rowsInserted, packages.rowsRemoved, packages.layoutChanged):
                signal.connect(self._sources_changed)

    @Property(QObject, constant=True)
    def cars(self): return self._model

    @Property(bool, notify=changed)
    def busy(self): return self._busy

    @Property(str, notify=changed)
    def status(self): return self._status

    @Property(str, notify=changed)
    def sourceName(self): return Path(self._source).name if self._source else "No garage selected"

    @Property(bool, notify=changed)
    def hasSource(self): return bool(self._source)

    @Property(str, notify=changed)
    def selectedAccountId(self):
        return self._selected_account.get("id", "") or ("manual:" + profile_identity(self._source) if self._source else "")

    @Property("QVariantList", notify=changed)
    def accountOptions(self):
        rows = [{key: row[key] for key in ("id", "label", "available")} for row in self._accounts]
        if self._source and not any(row["id"] == self.selectedAccountId for row in rows):
            rows.insert(0, {"id": self.selectedAccountId,
                           "label": self._selected_account.get("label", "Manually selected garage"),
                           "available": not bool(self._selected_account)})
        return rows

    @Property(str, notify=changed)
    def accountStatus(self): return self._account_status

    @Property(bool, notify=changed)
    def accountsDiscovered(self): return self._accounts_discovered

    @Property("QVariantMap", notify=changed)
    def summary(self): return dict(self._summary)

    @Property(int, notify=changed)
    def total(self): return len(self._state["cars"]) if self._state else 0

    @Property(int, notify=changed)
    def browseTotal(self): return len(self._ordered_rows)

    @Property(bool, notify=changed)
    def ownershipKnown(self): return self._state is not None

    @Property(bool, notify=changed)
    def catalogueBusy(self): return self._catalogue_busy

    @Property(str, notify=changed)
    def catalogueStatus(self): return self._catalogue_status

    @Property(int, notify=changed)
    def visibleCount(self): return self._model.rowCount()

    @Property(str, notify=changed)
    def selectedId(self): return self._selected

    @Property("QVariantList", notify=changed)
    def artworkOptions(self):
        row = self._row()
        return [dict(item) for item in self._artwork_by_car.get(row["carId"], ())] if row else []

    @Property(str, notify=changed)
    def searchText(self): return self._search

    @Property(int, notify=changed)
    def filterIndex(self): return self.FILTERS.index(self._filter)

    @Property(int, notify=changed)
    def sortIndex(self): return self.SORTS.index(self._sort)

    @Property(bool, notify=changed)
    def historyEnabled(self): return self._settings.get("history") is True

    @Property(bool, notify=changed)
    def historyAvailable(self): return bool(self._state and self._state["scope"])

    @Property("QVariantList", notify=changed)
    def history(self):
        if not self._state:
            return []
        return [{**event, "changes": [change for change in event["changes"]
                                      if change["instanceId"] == self._selected]}
                for event in reversed(self._state["history"])]

    @Property(str, notify=changed)
    def compareLabel(self):
        note = self._note()
        if note:
            return note["name"]
        return f"Copy {self._compare['instanceId']} / Car {self._compare['carId']}" if self._compare else ""

    @Property("QVariantList", notify=changed)
    def savedComparisons(self):
        return [{"id": e["id"], "name": e["name"], "carId": e["car"]["carId"]} for e in self._notes]

    @Property(str, notify=changed)
    def savedComparisonId(self): return self._note_id

    @Property(bool, notify=changed)
    def projectLinked(self): return bool(self._note() and self._note()["project"])

    @Property(str, notify=changed)
    def projectStatus(self): return self._project_status

    @Property("QVariantMap", notify=changed)
    def diagnosticSummary(self):
        return {"loaded": self._state is not None, "busy": self._busy, "carCount": self.total,
                "comparisonCount": len(self._notes), "historyAvailable": self.historyAvailable,
                "lastScanReused": self._last_scan_reused, "lastScanMs": self._last_scan_ms,
                "accountCount": len(self._accounts), "accountsDiscovered": self._accounts_discovered,
                "accountSelected": bool(self._selected_account), "catalogueBusy": self._catalogue_busy,
                "catalogueCount": len(self._catalogue),
                "stockThumbnailCount": sum(bool(row.get("thumbnailUrl")) for row in self._catalogue.values())}

    def _note(self):
        return next((e for e in self._notes if e["id"] == self._note_id), None)

    @Property("QVariantList", notify=changed)
    def differences(self):
        row = self._row()
        return compare_builds(self._compare, row) if self._compare and row else []

    def _row(self):
        if self._closed:
            return None
        rows = self._state["cars"] if self._state else None
        if rows is not self._indexed_rows:
            self._indexed_rows = rows
            self._rows_by_id = {row["instanceId"]: row for row in rows or ()}
        return self._rows_by_id.get(self._selected)

    def _set_state(self, state):
        rows = state["cars"] if state else None
        if rows is not self._ordered_rows_source:
            self._indexed_rows, self._ordered_rows_source = None, None
            self._rows_by_id, self._ordered_rows = {}, []
            self._sources_dirty = True
        self._state = state
        self._match_cache = None

    def _sources(self):
        return self.liveries.sourceModel.rows

    def _source_data_changed(self, first, last, roles):
        if self._closed:
            return
        names = self.liveries.sourceModel.roleNames()
        changed = {bytes(names[role]).decode() for role in roles if role in names}
        if roles and len(changed) == len(roles):
            if not changed.intersection({"path", "carId", "modelCode", "title", "available", "exportable"}):
                return
        self._sources_changed()

    def _packages_changed(self, first, last, roles):
        model = getattr(self.liveries, "packageModel", None)
        names = model.roleNames() if model is not None else {}
        changed = {bytes(names[role]).decode() for role in roles if role in names}
        if roles and len(changed) == len(roles) and not changed.intersection({"carId", "path", "available", "title"}):
            return
        self._sources_changed()

    def _sources_changed(self, *unused):
        if self._closed:
            return
        self._sources_dirty = True
        self._match_cache = None
        # Source scans before the first Garage visit must not initialize its view.
        if self._loaded:
            self._rebuild()
        else:
            self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def details(self):
        row = self._row()
        if not row:
            selected = next((r for r in self._ordered_rows if r["instanceId"] == self._selected), {})
            return {"title": selected.get("title", "Select a car"), "parts": [], "matched": False,
                    "livery": "", "reference": "", "tune": "", "scanned": "", "owned": False,
                    "thumbnailUrl": selected.get("thumbnailUrl", ""),
                    "ownership": ("Not owned" if self.ownershipKnown else "Ownership unknown") if selected else ""}
        if self._match_cache is None or self._match_cache[0] is not row:
            self._match_cache = (row, match_livery(row, self._sources(), self._source))
        match = self._match_cache[1]
        return {"title": f"{self._display_names.get(row['carId'], 'Car ' + str(row['carId']))} / Copy {row['instanceId']}",
                "owned": True, "ownership": "Owned", "thumbnailUrl": self._catalogue.get(row["carId"], {}).get("thumbnailUrl", ""),
                "parts": [{"name": name, "value": str(row["parts"].get(name)) if row["parts"].get(name) is not None else "Unknown"}
                          for name in PARTS],
                "matched": match["status"] == "matched", "livery": match["title"],
                "reference": row["liveryRef"], "tune": row["tuneRef"] or "No saved tune reference",
                "scanned": self._state["scannedAt"]}

    @Slot()
    def activate(self):
        if self._closed or self._busy:
            return
        if not self._loaded:
            self._loaded = True
            try:
                settings = read_json(self.root / "settings.json")
                if not isinstance(settings, dict):
                    raise ValueError()
                source = settings.get("source", "")
                if (not isinstance(source, str) or len(source) > 32768 or any(ord(c) < 32 for c in source)
                        or source and not Path(source).is_absolute()):
                    raise ValueError()
                self._source = source
                self._settings = {"source": self._source, "history": settings.get("history") is True}
                for key, choices in (("filter", self.FILTERS), ("sort", self.SORTS)):
                    value = settings.get(key)
                    if isinstance(value, str) and value in choices:
                        setattr(self, "_" + key, value)
                        self._settings[key] = value
                account = settings.get("account")
                if (source and isinstance(account, dict)
                        and all(isinstance(account.get(key), str) and 0 < len(account[key]) <= limit
                                and not any(ord(c) < 32 for c in account[key])
                                for key, limit in (("id", 128), ("label", 200), ("directory", 32768)))
                        and Path(account["directory"]).is_absolute()):
                    self._selected_account = {key: account[key] for key in ("id", "label", "directory")}
                    self._settings["account"] = dict(self._selected_account)
                self._persisted_settings = dict(self._settings)
                if self._source:
                    self._set_state(self.store.load(profile_identity(self._source)))
                    self._status = "Saved garage snapshot; refresh to check for changes" if self._state else "Refresh garage"
                    self._account_status = "Saved account" if self._selected_account else "Manually selected garage"
            except (OSError, ValueError, TypeError) as error:
                self._settings = {}
                self._settings_read_failed = not isinstance(error, FileNotFoundError)
            try:
                self._notes = self.notes.load()
            except GarageError as error:
                self._status = str(error)
        index = getattr(getattr(self.liveries, "_experiment_paths", None), "vehicle_index", None)
        if index:
            try:
                stat = Path(index).stat()
                stamp = (str(index), stat.st_mtime_ns, stat.st_size, stat.st_ino, stat.st_dev)
                if stamp != self._catalogue_stamp:
                    catalogue = read_json(index)
                    vehicles = catalogue.get("vehicles", {})
                    if catalogue.get("format") == "kfps_fh6_vehicle_asset_index_v1" and isinstance(vehicles, dict):
                        names = {int(ident): str(row["model_code"])[:200] for ident, row in vehicles.items()
                                 if isinstance(row, dict) and isinstance(row.get("model_code"), str)}
                        self._sources_dirty |= names != self._names
                        self._names = names
                        self._catalogue_stamp = stamp
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        self._match_cache = None
        self._rebuild()

    @Slot()
    def enter(self):
        if self._closed or self._busy:
            return
        self.activate()
        self._load_catalogue()
        if not self._accounts_attempted:
            self._discover_accounts(restore=True)

    @Slot()
    def rescanAccounts(self):
        if not self._closed and not self._busy:
            self.activate()
            self._load_catalogue(force=True)
            self._discover_accounts(restore=False)

    def _load_catalogue(self, *, force=False):
        game = str(getattr(self.liveries, "gameFolder", "") or "")
        if self._closed or self._catalogue_busy or not game:
            return
        previous = (self._catalogue_game, self._catalogue_source_stamp)
        self._catalogue_game = game
        self._catalogue_busy = True
        if not self._catalogue:
            self._catalogue_status = "Loading car catalogue..."
        cancel = self._catalogue_cancel = threading.Event()
        index = getattr(getattr(self.liveries, "_experiment_paths", None), "vehicle_index", None)
        self.changed.emit()
        def work():
            try:
                stamp = catalogue_signature(game, cancel)
                if not force and previous == (game, stamp):
                    result = {'unchanged': True}
                else:
                    result = load_catalogue(game, index, self.root / "car-catalogue", cancel)
                    if catalogue_signature(game, cancel) != stamp:
                        result = {'error': True, 'status': 'Car files changed while loading; refresh to retry.'}
                    else:
                        result = {**result, 'sourceStamp': stamp}
            except InterruptedError:
                result = {"error": True, "status": "Car catalogue cancelled"}
            except (OSError, ValueError, TypeError, RuntimeError):
                result = {"error": True, "status": "Car catalogue unavailable; rescan to retry"}
            self._catalogueFinished.emit({**result, "game": game})
        try:
            self._catalogue_thread = threading.Thread(target=work, name="kfps-garage-catalogue", daemon=True)
            self._catalogue_thread.start()
        except (OSError, RuntimeError):
            self._catalogue_thread = None
            self._catalogue_busy = False
            self._catalogue_game = None
            self._catalogue_status = "Car catalogue could not start; rescan to retry"
            self.changed.emit()

    @Slot(object)
    def _apply_catalogue(self, result):
        if self._closed:
            return
        self._catalogue_busy = False
        if self._catalogue_cancel.is_set():
            self._catalogue_game = None
            self._catalogue_status = "Car catalogue cancelled"
            self.changed.emit()
            return
        if result.get("game") != str(getattr(self.liveries, "gameFolder", "") or ""):
            self._catalogue_game = None
            self._load_catalogue()
            return
        if result.get('unchanged'):
            self.changed.emit()
            return
        if result.get("error") or not result.get('cars'):
            self._catalogue_source_stamp = None
            self._catalogue_status = result.get("status", "Car catalogue unavailable; refresh to retry")
            self.log.append('Garage catalogue: refresh incomplete; retaining previous cars', update_status=False)
            self.changed.emit()
            return
        self._catalogue = {row["carId"]: dict(row) for row in result["cars"]}
        self._catalogue_source_stamp = result.get('sourceStamp')
        self._catalogue_status = result.get("status", "")
        self._sources_dirty = True
        self.log.append(f"Garage catalogue: completed; cars={len(self._catalogue)}; thumbnails={sum(bool(r.get('thumbnailUrl')) for r in self._catalogue.values())}", update_status=False)
        self._rebuild()

    def _discover_accounts(self, *, restore):
        self._accounts_attempted = True
        self._busy = True
        self._account_status = "Finding FH6 accounts..."
        cancel = self._cancel = threading.Event()
        remembered = self._selected_account.get("directory", "")
        self.changed.emit()
        def work():
            result = {"restore": restore}
            try:
                result["accounts"] = discover_accounts(cancel)
                if remembered and not any(row["directory"] == remembered for row in result["accounts"]):
                    result["accounts"].extend(discover_accounts(cancel, roots=[remembered], local_app_data=""))
            except InterruptedError:
                result["error"] = "Account search cancelled"
                result["category"] = "cancelled"
            except (OSError, ValueError, TypeError):
                result["error"] = "Accounts could not be checked. Rescan or choose a garage file."
                result["category"] = "unavailable"
            self._accountsFinished.emit(result)
        self._start_worker(work, "accounts")

    @Slot(object)
    def _apply_accounts(self, result):
        if self._closed:
            return
        self._busy = False
        self._accounts_discovered = True
        if result.get("error") or self._cancel.is_set():
            self._account_status = result.get("error", "Account search cancelled")
            self.log.append("Garage accounts: " + result.get("category", "cancelled"), update_status=False)
            self.changed.emit()
            return
        self._accounts = [dict(row) for row in result["accounts"]]
        selected = next((row for row in self._accounts if row["id"] == self.selectedAccountId), None)
        count = len(self._accounts)
        self._account_status = ("Saved account unavailable; last snapshot kept" if self._selected_account and (not selected or not selected["available"])
                                else f"{count} FH6 account{'s' if count != 1 else ''} found" if count
                                else "No FH6 accounts found. Rescan or choose a garage file.")
        self.log.append(f"Garage accounts: completed; count={len(self._accounts)}; selected={int(bool(selected))}",
                        update_status=False)
        self.changed.emit()
        # Never choose for a first-time user, even when discovery finds one account.
        if result.get("restore") and selected and selected["available"]:
            self.selectAccount(selected["id"])

    @Slot(str)
    def selectAccount(self, ident):
        if self._closed or self._busy:
            return
        row = next((row for row in self._accounts if row["id"] == ident), None)
        if row and row["available"]:
            self._scan_source("", account=row)
        elif ident == self.selectedAccountId and self._source:
            self.refresh()
        else:
            self._account_status = "This account is unavailable. Rescan accounts and try again."
            self.changed.emit()

    def _save_settings(self):
        if self._settings_read_failed:
            try:
                previous = read_json(self.root / "settings.json")
                if not isinstance(previous, dict):
                    raise ValueError()
            except FileNotFoundError:
                previous = {}
            except (OSError, ValueError, TypeError) as error:
                raise OSError("Garage preferences could not be read safely") from error
            self._settings = {**previous, **self._settings}
            self._settings_read_failed = False
        if self._settings != self._persisted_settings:
            atomic_json(self.root / "settings.json", self._settings)
            self._persisted_settings = dict(self._settings)

    @Slot()
    def chooseSource(self):
        if self._busy or self._closed:
            return
        path, _ = QFileDialog.getOpenFileName(None, "Choose Garage Save", str(Path(self._source).parent) if self._source else "",
            "Garage saves (C_ProfileData C_ProfileBackup garage.json);;All files (*)")
        if path:
            self.scanSource(path)

    @Slot(str)
    def scanSource(self, path):
        self._scan_source(path)

    def _scan_source(self, path, *, account=None):
        if self._busy or self._closed:
            return
        self.activate()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._status = "Garage storage is unavailable. Check folder access and try again."
            self.log.append("Garage scan: storage_unavailable", update_status=False)
            self.changed.emit()
            return
        self._busy, self._status = True, "Reading garage..."
        cancel = self._cancel = threading.Event()
        history = self.historyEnabled
        account = dict(account) if account else None
        self.changed.emit()
        def work():
            try:
                source = resolve_account(account["directory"]) if account else Path(path)
                selected = account if account else account_for_source(source, cancel=cancel)
                if selected:
                    source = source.resolve(strict=True)
                def validate_current():
                    if selected and resolve_account(selected["directory"]) != source:
                        raise GarageError("The active save changed during the scan. Refresh Garage after saving finishes.")
                result = scan(source, self.store, self.root / "reader.json", cancel, history=history,
                              validate_source=validate_current)
                result["account"] = {key: selected[key] for key in ("id", "label", "directory")} if selected else {}
            except InterruptedError:
                result = {"error": "Garage scan cancelled", "category": "cancelled"}
            except GarageError as error:
                result = {"error": str(error), "category": "unsupported"}
            except (OSError, ValueError, TypeError, RecursionError):
                result = {"error": "The garage could not be read. Check the selected file and try again.", "category": "unavailable"}
            self._finished.emit(result)
        self._start_worker(work, "scan")

    def _start_worker(self, work, operation):
        try:
            self._thread = threading.Thread(target=work, name=f"kfps-garage-{operation}", daemon=True)
            self._thread.start()
        except (OSError, RuntimeError):
            self._thread = None
            self._busy = False
            self._build_row = None
            self._cancel.set()
            self._status = "Garage task could not start. Try again."
            if operation == "project":
                self._project_status = self._status
            elif operation == "accounts":
                self._account_status = "Account search could not start. Rescan accounts to retry."
                self._accounts_attempted = False
            self.log.append(f"Garage {operation}: worker_start_failed", update_status=False)
            self.changed.emit()

    @Slot()
    def refresh(self):
        if self._closed or self._busy:
            return
        self._load_catalogue(force=True)
        if self._source:
            self._scan_source(self._source, account=self._selected_account or None)
        refresh_library = getattr(self.liveries, "scanSaves", None)
        if callable(refresh_library):
            refresh_library()

    @Slot()
    def cancel(self):
        self._cancel.set()
        self._catalogue_cancel.set()

    @Slot(object)
    def _apply(self, result):
        if self._closed:
            return
        self._busy = False
        if "error" in result:
            self._status = result["error"]
            self.log.append("Garage scan: " + result["category"], update_status=False)
        else:
            before, after = self._state, result["state"]
            same_profile = bool(before and before["scope"] and before["scope"] == after["scope"])
            same_snapshot = bool(before and before["sourceHash"] == after["sourceHash"])
            if result["source"] != self._source or not (same_profile or same_snapshot):
                self._selected, self._compare = "", None
                self._note_id, self._project_status = "", ""
            if (same_snapshot and before["profile"] == after["profile"]
                    and before["cars"] == after["cars"]):
                after = {**after, "cars": before["cars"]}
            self._source = result["source"]
            self._selected_account = dict(result.get("account", {}))
            self._set_state(after)
            self._last_scan_ms, self._last_scan_reused = result["elapsedMs"], result["reused"]
            self._settings["source"] = self._source
            if self._selected_account:
                self._settings["account"] = dict(self._selected_account)
                self._account_status = "Selected account loaded"
            else:
                self._settings.pop("account", None)
                self._account_status = "Manually selected garage"
            try:
                self._save_settings()
                self._status = ("Garage unchanged" if result["reused"] else "Garage refreshed") + f" / {self.total} cars"
            except OSError:
                self._status = "Garage loaded; location could not be remembered"
            self.log.append(f"Garage scan: completed; cars={self.total}; reused={int(result['reused'])}; elapsed_ms={result['elapsedMs']}",
                            update_status=False)
        self._rebuild()

    @Slot(str)
    def setSearch(self, text):
        if self._closed:
            return
        text = str(text)[:256]
        if self._search != text:
            self._search = text
            self._rebuild()

    @Slot(str)
    def setFilter(self, value):
        if self._closed:
            return
        self.activate()
        if value in self.FILTERS and value != self._filter:
            self._filter = value
            self._remember_view("filter", value)
            self._rebuild()

    @Slot(str)
    def setSort(self, value):
        if self._closed:
            return
        self.activate()
        if value in self.SORTS and value != self._sort:
            self._sort = value
            self._remember_view("sort", value)
            self._rebuild()

    def _remember_view(self, key, value):
        self._settings[key] = value
        try:
            self._save_settings()
        except OSError:
            self._status = "Garage view changed; preference could not be remembered"

    @Slot(bool)
    def setHistoryEnabled(self, enabled):
        if self._busy or self._closed:
            return
        self.activate()
        if enabled and not self.historyAvailable:
            self._status = "Change history is unavailable for this snapshot"
            self.changed.emit()
            return
        try:
            if not enabled:
                self.store.clear_history()
                if self._state:
                    self._set_state(self.store.load(profile_identity(self._source)))
            updated = {**self._settings, "history": bool(enabled)}
            atomic_json(self.root / "settings.json", updated)
            self._settings = updated
            self._persisted_settings = dict(updated)
        except (OSError, GarageError):
            self._status = "History preference could not be saved"
        self._rebuild()

    def _rebuild(self):
        if self._closed:
            return
        rows = self._state["cars"] if self._state else None
        view_changed = self._sources_dirty or rows is not self._ordered_rows_source
        query = self._search.strip().casefold()
        view_filter = (query, self._filter, self._sort)
        if not view_changed and view_filter == self._view_filter:
            self.changed.emit()
            return
        if view_changed:
            counts, names = {}, dict(self._names)
            for row in rows or ():
                counts[row["carId"]] = counts.get(row["carId"], 0) + 1
            sources = self._sources()
            packages = getattr(self.liveries, "packageModel", None)
            livery_models = available_livery_models(sources, packages.rows if packages is not None else (), self._source)
            artwork = {}
            try:
                account_root = Path(self._source).resolve().parent.parent if self._source else None
            except (OSError, ValueError):
                account_root = None
            for kind, candidates in (("save", sources), ("package", packages.rows if packages is not None else ())):
                for item in candidates:
                    if item.get("available") is not True or type(item.get("carId")) is not int:
                        continue
                    path = item.get("path")
                    if not isinstance(path, str) or not path or "\0" in path:
                        continue
                    try:
                        file = Path(path)
                        if not file.is_absolute():
                            continue
                        if kind == "save" and (not account_root or item.get("exportable") is not True
                                or file.resolve().parent.parent != account_root):
                            continue
                    except (OSError, ValueError):
                        continue
                    artwork.setdefault(item["carId"], []).append({"path": path, "kind": kind,
                        "label": str(item.get("title") or file.stem) + (" / Package" if kind == "package" else " / Saved livery")})
            self._artwork_by_car = artwork
            for source in sources:
                if source.get("modelCode"):
                    names[source["carId"]] = str(source["modelCode"])
            names.update({ident: row["title"] for ident, row in self._catalogue.items()})
            self._counts, self._display_names = counts, names
            self._summary = {"cars": len(rows or ()), "models": len(counts),
                             "liveries": 0,
                             "duplicates": sum(count for count in counts.values() if count > 1),
                             "scanned": self._state["scannedAt"] if self._state else ""}
            combined = [{"instanceId": r["instanceId"], "carId": r["carId"],
                         "title": names.get(r["carId"], f"Car {r['carId']}"),
                         "detail": f"Copy {r['instanceId']} / Car {r['carId']}",
                         "livery": r["liveryRef"], "buildSignature": r["buildSignature"], "owned": True,
                         "thumbnailUrl": self._catalogue.get(r["carId"], {}).get("thumbnailUrl", "")}
                        for r in rows or ()]
            combined.extend({"instanceId": f"catalogue:{ident}", "carId": ident, "title": r["title"],
                             "detail": f"{r['modelCode']} / Car {ident}", "livery": "", "buildSignature": "",
                             "owned": False, "thumbnailUrl": r.get("thumbnailUrl", "")}
                            for ident, r in self._catalogue.items() if ident not in counts)
            for row in combined:
                row["hasLivery"] = row["carId"] in livery_models
            self._summary["liveries"] = sum(row["hasLivery"] for row in combined)
            def manufacturer_order(row):
                meta = self._catalogue.get(row['carId'], {})
                return (meta.get('manufacturer', row['title']).casefold(),
                        meta.get('modelName', row['title']).casefold(), meta.get('year', 0),
                        row['carId'], int(row['instanceId']) if row['owned'] else 0)
            self._ordered_rows = sorted(combined, key=manufacturer_order)
            self._ordered_rows_source = rows
            self._sources_dirty = False
        selected = []
        for row in self._ordered_rows:
            if self._filter == "livery" and not row["hasLivery"]:
                continue
            if self._filter == "owned" and not row["owned"]:
                continue
            if self._filter == "duplicates" and self._counts.get(row["carId"], 0) < 2:
                continue
            if query and query not in (row["title"] + " " + row["detail"] + " " + row["livery"]).casefold():
                continue
            selected.append(row)
        if self._sort == "owned":
            selected.sort(key=lambda r: not r["owned"])
        elif self._sort == "livery":
            selected.sort(key=lambda r: (not r["hasLivery"], not r["owned"]))
        visible_ids = tuple(row["instanceId"] for row in selected)
        self._view_filter = view_filter
        if view_changed or visible_ids != self._visible_ids:
            self._visible_ids = visible_ids
            self._model.replace(selected)
        if self._selected and not self._row() and not any(r["instanceId"] == self._selected for r in self._ordered_rows):
            self._selected = ""
        self.changed.emit()

    @Slot(str)
    def select(self, ident):
        if self._closed:
            return
        if self._selected != ident:
            self._build_serial += 1
            self._selected = ident
            self._match_cache = None
            self.changed.emit()

    @Slot()
    def pinComparison(self):
        if self._busy or self._closed:
            return
        self._note_id, self._project_status = "", ""
        self._compare = self._row()
        self.changed.emit()

    @Slot()
    def clearComparison(self):
        if self._busy or self._closed:
            return
        self._note_id, self._project_status = "", ""
        self._compare = None
        self.changed.emit()

    @Slot(str)
    def saveComparison(self, name):
        if self._busy or self._closed or not self._row():
            return
        try:
            note = self.notes.add(name, self._row())
            self._notes = self.notes.load()
            self.chooseComparison(note["id"])
            self._status = "Comparison saved"
        except (OSError, GarageError) as error:
            self._status = str(error) if isinstance(error, GarageError) else "Comparison could not be saved"
        self.changed.emit()

    @Slot(str)
    def chooseComparison(self, ident):
        if self._busy or self._closed:
            return
        note = next((e for e in self._notes if e["id"] == ident), None)
        self._note_id = ident if note else ""
        self._compare = note["car"] if note else None
        self._project_status = "Project not checked" if note and note["project"] else ""
        self.changed.emit()

    @Slot()
    def removeComparison(self):
        if self._busy or self._closed or not self._note():
            return
        try:
            self.notes.remove(self._note_id)
            self._notes = self.notes.load()
            self.clearComparison()
            self._status = "Comparison removed; project files were not changed"
        except (OSError, GarageError):
            self._status = "Comparison could not be removed"
        self.changed.emit()

    @Slot()
    def chooseProject(self):
        if self._busy or self._closed or not self._note():
            return
        folder = self.paths.app_root / "imgs/livery-projects"
        path, _ = QFileDialog.getOpenFileName(None, "Link Studio Project", str(folder), "Studio projects (*.json)")
        if path:
            self.linkProject(path)

    @Slot(str)
    def linkProject(self, path):
        self._project_task("link", path)

    @Slot()
    def checkProject(self):
        self._project_task("check")

    @Slot()
    def revealProject(self):
        self._project_task("reveal")

    @Slot()
    def openProject(self):
        self._project_task("open")

    def _project_task(self, action, path=None):
        note = self._note()
        if self._busy or self._closed or not note or (action != "link" and not note["project"]):
            return
        self._cancel = threading.Event()
        self._busy = True
        self._project_status = "Checking project..."
        self.changed.emit()
        def work():
            result = {"action": action, "id": note["id"]}
            try:
                if action == "link":
                    result["project"] = inspect_project(path, note["car"]["carId"], self.paths.app_root, cancel=self._cancel)
                else:
                    result.update(resolve_project(note["project"], self.paths.app_root, cancel=self._cancel))
            except (OSError, ValueError, TypeError, RecursionError):
                result["error"] = "Project is missing, busy, unsupported or belongs to another car"
            self._projectFinished.emit(result)
        self._start_worker(work, "project")

    @Slot(object)
    def _apply_project(self, result):
        if self._closed:
            return
        self._busy = False
        if self._cancel.is_set():
            self._project_status = "Project check cancelled"
        elif result.get("error"):
            self._project_status = result["error"]
        elif result["id"] == self._note_id:
            if result["action"] == "link":
                try:
                    self.notes.link(result["id"], result["project"])
                    self._notes = self.notes.load()
                    self._project_status = "Project linked; project contents were not changed"
                except (OSError, GarageError):
                    self._project_status = "Project link could not be saved"
            else:
                self._project_status = {
                    "current": "Project matches its linked revision",
                    "changed": "Project has changed since linking; comparison was kept",
                    "missing": "Linked project is missing; comparison was kept",
                    "unavailable": "Linked project is busy or unsupported; comparison was kept",
                }[result["status"]]
                if result["action"] == "reveal" and result["status"] in ("current", "changed"):
                    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result["path"]).parent))):
                        self._project_status = "The project folder could not be opened"
                elif result["action"] == "open" and result["status"] in ("current", "changed"):
                    note = self._note()
                    if note and note["id"] == result["id"]:
                        self._project_status = "Opening current Studio project revision"
                        self.projectRequested.emit(dict(note["project"]))
        self.log.append("Garage project: " + ("cancelled" if self._cancel.is_set() else "failed" if result.get("error") else "checked"),
                        update_status=False)
        self.changed.emit()

    @Slot()
    def openLivery(self):
        row = self._row()
        if row and not self._busy:
            match = match_livery(row, self._sources(), self._source)
            if match["status"] == "matched":
                self.liveryRequested.emit(match["path"])

    @Slot()
    def openPreview(self):
        self._open_build("preview")

    @Slot()
    def openStudio(self):
        self._open_build("studio")

    @Slot(str, str)
    def openArtwork(self, path, kind):
        if self._busy or self._closed:
            return
        choice = next((item for item in self.artworkOptions if item["path"] == path and item["kind"] == kind), None)
        if choice is None:
            self._status = "Artwork is no longer available for this car. Refresh Garage."
            self.changed.emit()
            return
        try:
            stamp = artwork_identity(path, kind)
        except (OSError, ValueError):
            self._status = "Artwork is unavailable or changed. Refresh Garage."
            self.changed.emit()
            return
        self._open_build("artwork", choice, stamp)

    def _open_build(self, target, artwork=None, artwork_stamp=None):
        row = self._row()
        stock = row is None
        if stock:
            row = next((r for r in self._ordered_rows if r["instanceId"] == self._selected and not r["owned"]), None)
        if self._busy or self._closed or not row or (stock and artwork):
            return
        try:
            snapshot = None if stock else body_snapshot(row)
            game = str(getattr(self.liveries, "gameFolder", "") or "")
            if not game:
                raise GarageError("Choose the local FH6 game folder before opening a Garage build.")
        except GarageError as error:
            self._status = str(error)
            log_body_launch(self.log, target, "rejected")
            self.changed.emit()
            return
        paths = getattr(self.liveries, "_experiment_paths", None) or FullLiveryPaths.for_app(self.paths)
        cancel = self._cancel = threading.Event()
        serial = self._build_serial
        selected_id = self._selected
        self._build_row = row
        self._busy, self._status = True, "Resolving stock car..." if stock else "Resolving selected Garage build..."
        log_body_launch(self.log, target, "requested", snapshot)
        self.changed.emit()
        def work():
            result = {"target": target, "snapshot": snapshot, "serial": serial, "game": game,
                      "selected_id": selected_id, "stock": stock, "artwork": artwork}
            try:
                if artwork:
                    result["artwork_hash"] = artwork_fingerprint(artwork["path"], artwork["kind"], artwork_stamp, cancel)
                model = self._catalogue.get(row["carId"], {}).get("modelCode") if stock else None
                asset = resolve_body_vehicle(game, paths.vehicle_index, row["carId"], model_code=model, cancel_event=cancel)
                result["identity"] = {"car_id": asset.car_id, "model_code": asset.model_code}
            except InterruptedError:
                result["error"] = "Garage build launch cancelled"
            except GarageError as exc:
                result["error"] = str(exc)
            except (OSError, ValueError, TypeError):
                result["error"] = "The exact Garage model could not be resolved. Check the linked FH6 folder and refresh Garage."
            self._buildFinished.emit(result)
        self._start_worker(work, "build")

    @Slot(object)
    def _apply_build(self, result):
        if self._closed:
            return
        self._busy = False
        row = (next((r for r in self._ordered_rows if r["instanceId"] == self._selected), None)
               if result.get("stock") else self._row())
        selected = (self._build_row is row and result.get("serial") == self._build_serial
                    and result.get("selected_id", self._selected) == self._selected)
        game_changed = result.get("game") != str(getattr(self.liveries, "gameFolder", "") or "")
        self._build_row = None
        if self._cancel.is_set() or not selected:
            self._status = "Garage build launch cancelled"
        elif game_changed:
            self._status = "The linked game folder changed. Open the Garage build again."
        elif result.get("error"):
            self._status = result["error"]
        else:
            self._status = "Opening selected body build; no artwork included"
            if result.get("stock"):
                self._status = "Opening stock body; no artwork included"
                signal = self.stockStudioRequested if result["target"] == "studio" else self.stockPreviewRequested
                signal.emit(result["identity"])
            elif result["target"] == "artwork":
                choice = result["artwork"]
                if choice not in self.artworkOptions:
                    self._status = "Artwork changed during launch. Select it again."
                else:
                    self._status = "Opening artwork on the selected car's current body build"
                    self.artworkRequested.emit(result["identity"], result["snapshot"], choice["path"], choice["kind"], result["artwork_hash"])
            elif result["target"] == "studio":
                self.studioRequested.emit(result["identity"], result["snapshot"], "Garage body build")
            else:
                self.previewRequested.emit(result["identity"], result["snapshot"])
        log_body_launch(self.log, result["target"], "cancelled" if self._cancel.is_set() or not selected
                        else "unavailable" if result.get("error") or game_changed else "handoff", result["snapshot"])
        self.changed.emit()

    def close(self):
        self._closed = True
        self._cancel.set()
        self._catalogue_cancel.set()
        self._build_row = None
        self._indexed_rows, self._ordered_rows_source = None, None
        self._rows_by_id, self._ordered_rows = {}, []
        self._artwork_by_car = {}
        self._match_cache = None
        if self._thread:
            self._thread.join(timeout=5)
        if self._catalogue_thread:
            self._catalogue_thread.join(timeout=5)
        return not any(t and t.is_alive() for t in (self._thread, self._catalogue_thread))
