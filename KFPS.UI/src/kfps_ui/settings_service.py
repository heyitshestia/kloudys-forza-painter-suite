from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot


class SettingsService(QObject):
    changed = Signal()

    DEFAULTS = {
        "theme": "Night Blossom",
        "uiScale": 1.0,
        "manualOverrides": False,
        "reducedMotion": False,
        "ambientMotion": True,
        "glassEffects": True,
        "consoleCollapsed": False,
    }
    KNOWN_THEMES = {"Night Blossom", "Ko-fi Cherry"}

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self._data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for key in self.DEFAULTS:
                    if key in payload:
                        self._data[key] = payload[key]
        except Exception:
            pass
        if self._data.get("theme") not in self.KNOWN_THEMES:
            self._data["theme"] = "Night Blossom"
        self._data["uiScale"] = max(0.80, min(1.35, float(self._data["uiScale"])))

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def _get(self, key): return self._data[key]
    def _set(self, key, value):
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.save(); self.changed.emit()

    @Property(str, notify=changed)
    def theme(self): return str(self._get("theme"))
    @theme.setter
    def theme(self, value):
        text = str(value)
        if text not in self.KNOWN_THEMES:
            text = "Night Blossom"
        self._set("theme", text)
    @Property(float, notify=changed)
    def uiScale(self): return float(self._get("uiScale"))
    @uiScale.setter
    def uiScale(self, value): self._set("uiScale", max(0.80, min(1.35, float(value))))
    @Property(bool, notify=changed)
    def manualOverrides(self): return bool(self._get("manualOverrides"))
    @manualOverrides.setter
    def manualOverrides(self, value): self._set("manualOverrides", bool(value))
    @Property(bool, notify=changed)
    def reducedMotion(self): return bool(self._get("reducedMotion"))
    @reducedMotion.setter
    def reducedMotion(self, value): self._set("reducedMotion", bool(value))
    @Property(bool, notify=changed)
    def ambientMotion(self): return bool(self._get("ambientMotion"))
    @ambientMotion.setter
    def ambientMotion(self, value): self._set("ambientMotion", bool(value))
    @Property(bool, notify=changed)
    def glassEffects(self): return bool(self._get("glassEffects"))
    @glassEffects.setter
    def glassEffects(self, value): self._set("glassEffects", bool(value))
    @Property(bool, notify=changed)
    def consoleCollapsed(self): return bool(self._get("consoleCollapsed"))
    @consoleCollapsed.setter
    def consoleCollapsed(self, value): self._set("consoleCollapsed", bool(value))

    @Slot()
    def reset(self):
        self._data = dict(self.DEFAULTS)
        self.save(); self.changed.emit()
