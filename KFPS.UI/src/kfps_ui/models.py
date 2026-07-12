from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot


class DictListModel(QAbstractListModel):
    countChanged = Signal()

    def __init__(self, roles: Iterable[str], parent=None):
        super().__init__(parent)
        self._roles = list(roles)
        self._role_ids = {Qt.UserRole + i + 1: name for i, name in enumerate(self._roles)}
        self._rows: list[dict[str, Any]] = []

    def roleNames(self):
        return {role: QByteArray(name.encode("utf-8")) for role, name in self._role_ids.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        if role == Qt.DisplayRole:
            return self._rows[index.row()].get(self._roles[0]) if self._roles else None
        name = self._role_ids.get(role)
        return self._rows[index.row()].get(name) if name else None

    def replace(self, rows: Iterable[dict[str, Any]]):
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()
        self.countChanged.emit()

    def append_many(self, rows: Iterable[dict[str, Any]], max_rows: int | None = None):
        rows = [dict(row) for row in rows]
        if not rows:
            return
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self._rows.extend(rows)
        self.endInsertRows()
        if max_rows is not None and len(self._rows) > max_rows:
            remove = len(self._rows) - max_rows
            self.beginRemoveRows(QModelIndex(), 0, remove - 1)
            del self._rows[:remove]
            self.endRemoveRows()
        self.countChanged.emit()

    def set_row_value(self, index: int, role_name: str, value: Any) -> bool:
        if not 0 <= index < len(self._rows) or role_name not in self._roles:
            return False
        if self._rows[index].get(role_name) == value:
            return True
        self._rows[index][role_name] = value
        role_id = next((role for role, name in self._role_ids.items() if name == role_name), None)
        if role_id is not None:
            model_index = self.index(index, 0)
            self.dataChanged.emit(model_index, model_index, [role_id])
        return True

    def row(self, index: int) -> dict[str, Any] | None:
        return dict(self._rows[index]) if 0 <= index < len(self._rows) else None

    @Slot(int, result="QVariant")
    def get(self, index: int):
        return self.row(index) or {}

    @property
    def rows(self):
        return [dict(row) for row in self._rows]
