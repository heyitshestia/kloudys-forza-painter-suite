from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from .models import DictListModel


class ChangelogService(QObject):
    changed = Signal()

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self._model = DictListModel(["version", "date", "summary", "details"])
        self.refresh()


    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Slot()
    def refresh(self):
        rows = []
        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
            matches = list(re.finditer(r"^##\s+([^\r\n]+)", text, flags=re.MULTILINE))
            for i, match in enumerate(matches[:30]):
                version = match.group(1).strip()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                bullets = [re.sub(r"^[-*]\s*", "", line).strip() for line in text[match.end():end].splitlines() if line.strip().startswith(("-", "*"))]
                if not bullets:
                    continue
                rows.append({
                    "version": version,
                    "date": "Current" if i == 0 else "",
                    "summary": bullets[0],
                    "details": "\n".join(f"- {bullet}" for bullet in bullets[1:]),
                })
        except Exception:
            rows = [{"version": "—", "date": "", "summary": "Changelog is unavailable in this package.", "details": ""}]
        self._model.replace(rows)
        self.changed.emit()
