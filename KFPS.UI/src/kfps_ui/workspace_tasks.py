"""Bounded observation of existing workers, never an alternate job scheduler."""
import uuid
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class TaskJournal(QObject):
    changed = Signal()
    actionFailed = Signal(str)

    def __init__(self, parent=None, *, limit=40):
        super().__init__(parent)
        self._sources = {}
        self._rows = []
        self._limit = max(1, int(limit))
        self._closed = False
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._flush_settled)

    def watch(self, key, source, *, label, page, busy="running", status="status",
              detail=None, cancel=None, retry=None, result=None, can_cancel=None,
              can_retry=None, can_result=None):
        if key in self._sources:
            raise ValueError("Task source already registered")
        config = dict(source=source, label=label, page=page, busy=busy, status=status,
                      detail=detail, cancel=cancel, retry=retry, result=result,
                      can_cancel=can_cancel, can_retry=can_retry, can_result=can_result, current=None, settling=None)
        self._sources[key] = config
        config["changed_slot"] = lambda: self._update(key)
        source.changed.connect(config["changed_slot"])
        self._update(key)

    @staticmethod
    def _read(config, name, default=None):
        value = config.get(name)
        if value is None:
            return default
        return value() if callable(value) else getattr(config["source"], value, default)

    def _update(self, key):
        if self._closed:
            return
        c = self._sources[key]
        busy = bool(self._read(c, "busy", False))
        row = c["current"]
        if busy and (row is None or not row["running"]):
            row = dict(id=uuid.uuid4().hex, source=key, label=c["label"], page=c["page"],
                       running=True, status="", detail="")
            self._rows.insert(0, row)
            c["current"] = row
        if row is None or (not row["running"] and c["settling"] is not row):
            return
        was_running = row["running"]
        row.update(running=busy, status=str(self._read(c, "status", ""))[:2000],
                   detail=str(self._read(c, "detail", "") or "")[:4000])
        if was_running and not busy:
            c["settling"] = row
            # Supervisors may clear busy immediately before publishing the result.
            if not self._settle_timer.isActive():
                self._settle_timer.start(0)
        # A completed row keeps its exact worker status, not an inferred success.
        inactive = [r for r in self._rows if not r["running"]]
        for old in inactive[max(0, self._limit - sum(r["running"] for r in self._rows)):]:
            self._rows.remove(old)
        self.changed.emit()

    @Slot()
    def _flush_settled(self):
        pending = [(key, c["settling"]) for key, c in self._sources.items() if c["settling"] is not None]
        for key, row in pending:
            self._settle(key, row)

    def _settle(self, key, row):
        if self._closed:
            return
        c = self._sources[key]
        if c["settling"] is not row:
            return
        c["settling"] = None
        if c["current"] is row and not self._read(c, "busy", False):
            row.update(status=str(self._read(c, "status", ""))[:2000],
                       detail=str(self._read(c, "detail", "") or "")[:4000])
            self.changed.emit()

    def _capabilities(self, row):
        if self._closed:
            return dict(cancel=False, retry=False, result=False)
        c = self._sources[row["source"]]
        current = c["current"] is row
        busy = bool(self._read(c, "busy", False))
        return dict(cancel=bool(current and busy and c["cancel"] and
                                self._read(c, "can_cancel", True)),
                    retry=bool(current and not busy and c["retry"] and
                               self._read(c, "can_retry", False)),
                    result=bool(current and not busy and c["result"] and
                                self._read(c, "can_result", True)))

    @Property("QVariantList", notify=changed)
    def rows(self):
        return [dict(row, **self._capabilities(row)) for row in self._rows]

    @Property(int, notify=changed)
    def activeCount(self):
        return sum(bool(row["running"]) for row in self._rows)

    @Slot(str, str, result=bool)
    def act(self, task_id, action):
        row = next((r for r in self._rows if r["id"] == task_id), None)
        if row is None or action not in ("cancel", "retry", "result"):
            return False
        if not self._capabilities(row)[action]:
            return False
        try:
            self._sources[row["source"]][action]()
            return True
        except (OSError, ValueError, RuntimeError) as exc:
            self.actionFailed.emit(str(exc))
            return False

    @Slot()
    def clearFinished(self):
        self._rows = [row for row in self._rows if row["running"]]
        self.changed.emit()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._settle_timer.stop()
        self._settle_timer.timeout.disconnect(self._flush_settled)
        for c in self._sources.values():
            try:
                c["source"].changed.disconnect(c["changed_slot"])
            except (RuntimeError, TypeError):
                pass
        self._sources.clear()
