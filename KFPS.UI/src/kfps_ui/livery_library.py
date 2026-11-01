"""In-memory livery browsing helpers, independent of scanning and export services."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from PySide6.QtCore import Property, QSortFilterProxyModel, Qt, Signal, Slot


_MAX_INT = 2 ** 31 - 1


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: Any) -> int:
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            return 0
    return value if type(value) is int and 0 <= value <= _MAX_INT else 0


def _flag(value: Any) -> bool:
    return value is True or (type(value) is int and value == 1)


def source_details(row: Any, manifest: Any = None) -> dict[str, Any]:
    """Return only JSON/QML-safe display values, with no file or URL access.

    An optional already-loaded mapping may supply the same named fields when
    absent from the row. Explicit row values (including False, empty and invalid
    values) always win. Strings default to empty, nonnegative 32-bit integers to
    zero, and flags to False; only True or integer 1 enables a flag. These are
    display values, not an export authorization decision.
    """
    row = row if isinstance(row, Mapping) else {}
    manifest = manifest if isinstance(manifest, Mapping) else {}

    def value(name: str) -> Any:
        return row[name] if name in row else manifest.get(name)

    return {
        "title": _text(value("title")),
        "modelCode": _text(value("modelCode")),
        "carId": _integer(value("carId")),
        "placementCount": _integer(value("placementCount")),
        "modified": _text(value("modified")),
        "hasHeader": _flag(value("hasHeader")),
        "exportable": _flag(value("exportable")),
        "privacyDetail": _text(value("privacyDetail")),
        "thumbnailUrl": _text(value("thumbnailUrl")),
    }


class LiveryLibraryFilter(QSortFilterProxyModel):
    """Filter a DictListModel without copying, reordering or editing its rows.

    Search is a literal Unicode-casefolded substring in searchText, title, path,
    modelCode or carId. Whitespace is significant. Car 0 disables the exact-ID
    filter; preview means not exportable, including missing/invalid flags.

    Modified uses the scanner's sortable YYYY-MM-DD HH:MM strings, newest first.
    Placements sort numerically descending, titles casefolded ascending and cars
    numerically ascending by ID. Every mode breaks ties by casefolded path then
    exact path, ascending. Missing/invalid fields use the source_details defaults.
    Invalid setter arguments raise ValueError and leave the state unchanged.
    """

    searchChanged = Signal()
    carIdChanged = Signal()
    availabilityChanged = Signal()
    sortOrderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search = ""
        self._needle = ""
        self._car_id = 0
        self._availability = "all"
        self._sort_order = "modified"
        self._roles: dict[str, int] = {}
        self.setDynamicSortFilter(True)
        self.sort(0, Qt.AscendingOrder)

    @Property(str, notify=searchChanged)
    def search(self) -> str:
        return self._search

    @Property(int, notify=carIdChanged)
    def car_id(self) -> int:
        return self._car_id

    @Property(str, notify=availabilityChanged)
    def availability(self) -> str:
        return self._availability

    @Property(str, notify=sortOrderChanged)
    def sort_order(self) -> str:
        return self._sort_order

    @contextmanager
    def _filter_change(self):
        # Qt 6.10+ supports scoped filter updates; older launchers use the
        # equivalent row-only invalidation. Neither repeats the full sort.
        scoped = hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange")
        if scoped:
            self.beginFilterChange()
        try:
            yield
        finally:
            if scoped:
                self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
            else:
                self.invalidateRowsFilter()

    @Slot(str)
    def setSearch(self, text: str) -> None:
        if not isinstance(text, str):
            raise ValueError("search must be a string")
        if text != self._search:
            with self._filter_change():
                self._search = text
                self._needle = text.casefold()
            self.searchChanged.emit()

    @Slot(int)
    def setCarId(self, car_id: int) -> None:
        if type(car_id) is not int or not 0 <= car_id <= _MAX_INT:
            raise ValueError("car ID must be a nonnegative 32-bit integer (0 means all)")
        if car_id != self._car_id:
            with self._filter_change():
                self._car_id = car_id
            self.carIdChanged.emit()

    @Slot(str)
    def setAvailability(self, availability: str) -> None:
        if availability not in ("all", "exportable", "preview"):
            raise ValueError("availability must be all, exportable or preview")
        if availability != self._availability:
            with self._filter_change():
                self._availability = availability
            self.availabilityChanged.emit()

    @Slot(str)
    def setSortOrder(self, sort_order: str) -> None:
        if sort_order not in ("modified", "title", "car", "placements"):
            raise ValueError("sort order must be modified, title, car or placements")
        if sort_order != self._sort_order:
            self._sort_order = sort_order
            # Direction belongs to the primary key; path ties always ascend.
            self.sort(0, Qt.AscendingOrder)
            self.invalidate()
            self.sortOrderChanged.emit()

    def setSourceModel(self, source_model) -> None:
        previous = self.sourceModel()
        if previous is source_model:
            return
        if previous is not None:
            previous.modelReset.disconnect(self._refresh_roles)
            previous.dataChanged.disconnect(self.invalidate)
        self._roles = self._role_names(source_model)
        if source_model is not None:
            # Resolve roles before Qt rebuilds its mappings on a source reset.
            source_model.modelReset.connect(self._refresh_roles)
        super().setSourceModel(source_model)
        if source_model is not None:
            # Our predicates and tie-breaks depend on more than Qt's single
            # filterRole/sortRole. Observe changes to any source role.
            source_model.dataChanged.connect(self.invalidate)

    @staticmethod
    def _role_names(source_model) -> dict[str, int]:
        if source_model is None:
            return {}
        return {bytes(name).decode("utf-8", errors="replace"): role
                for role, name in source_model.roleNames().items()}

    @Slot()
    def _refresh_roles(self) -> None:
        self._roles = self._role_names(self.sourceModel())

    def _value(self, index, name: str) -> Any:
        role = self._roles.get(name)
        return index.model().data(index, role) if role is not None else None

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        source = self.sourceModel()
        if source is None:
            return False
        index = source.index(source_row, 0, source_parent)
        car_id = _integer(self._value(index, "carId"))
        if self._car_id and car_id != self._car_id:
            return False
        if self._availability != "all":
            exportable = _flag(self._value(index, "exportable"))
            if exportable != (self._availability == "exportable"):
                return False
        if not self._needle:
            return True
        return (any(self._needle in _text(self._value(index, name)).casefold()
                    for name in ("searchText", "title", "modelCode", "path"))
                or (car_id > 0 and self._needle in str(car_id)))

    def _sort_value(self, index):
        if self._sort_order == "car":
            return _integer(self._value(index, "carId"))
        if self._sort_order == "placements":
            return _integer(self._value(index, "placementCount"))
        return _text(self._value(index, self._sort_order)).casefold()

    def lessThan(self, source_left, source_right) -> bool:
        left = self._sort_value(source_left)
        right = self._sort_value(source_right)
        if left != right:
            return left > right if self._sort_order in ("modified", "placements") else left < right
        left_path = _text(self._value(source_left, "path"))
        right_path = _text(self._value(source_right, "path"))
        return (left_path.casefold(), left_path) < (right_path.casefold(), right_path)
