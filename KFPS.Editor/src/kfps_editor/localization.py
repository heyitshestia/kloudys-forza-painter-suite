"""Shared-catalog localization for editor-owned desktop UI (no Qt dependency)."""
from __future__ import annotations

import json
import ctypes
import logging
import re
import sys
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parents[3]
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))
from kfps_editor.manifest import editor_web_root


def editor_system_language() -> str:
    """Windows UI language, not the independent regional date/number format."""
    if sys.platform == "win32":
        try:
            get_language = ctypes.WinDLL("kernel32", use_last_error=True).GetUserDefaultUILanguage
            get_language.argtypes = []
            get_language.restype = ctypes.c_ushort
            primary_language = get_language() & 0x03FF
            return {0x11: "ja", 0x12: "ko"}.get(primary_language, "en")
        except (AttributeError, OSError):
            logging.getLogger(__name__).warning("Could not determine the Windows display language", exc_info=True)
            return "en"
    from PySide6.QtCore import QLocale
    languages = QLocale.system().uiLanguages()
    return languages[0] if languages else "en"


class EditorTranslator:
    """Translate app-owned messages; keep user filenames and diagnostics opaque."""

    def __init__(self, app_root: Path, runtime: Path, system_locale: str = "en") -> None:
        system = re.match(r"^(ko|ja)(?:[-_]|$)", system_locale, re.I)
        self.language = system[1].lower() if system else "en"
        self.messages: dict[str, str] = {}
        self._patterns: list[tuple[str, re.Pattern[str], list[int]]] = []
        try:
            preferences = json.loads((runtime / "preferences.json").read_text(encoding="utf-8"))
            selected = preferences.get("settings", {}).get("kloudyFabricLanguage")
            if selected in ("en", "ko", "ja"):
                self.language = selected
        except (OSError, ValueError, AttributeError, TypeError):
            # The editor's existing preference-error UI handles corrupt settings.
            pass
        for language in dict.fromkeys(("en", self.language)):
            try:
                path = editor_web_root(app_root) / "locales" / f"{language}.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.messages.update({key: value for key, value in payload["messages"].items()
                                      if isinstance(key, str) and isinstance(value, str) and value})
            except (OSError, ValueError, KeyError, AttributeError, TypeError):
                pass  # A missing language pack must not prevent recovery.
        for key in sorted(self.messages, key=len, reverse=True):
            if not re.search(r"\{\d+\}", key) or re.search(r"<[a-z]", key, re.I):
                continue
            indexes: list[int] = []
            pieces: list[str] = []
            last = 0
            for match in re.finditer(r"\{(\d+)\}", key):
                pieces.extend([re.escape(key[last:match.start()]), r"([\s\S]*?)"])
                indexes.append(int(match.group(1)))
                last = match.end()
            pieces.append(re.escape(key[last:]))
            self._patterns.append((key, re.compile("".join(pieces)), indexes))

    def tr(self, source: str, *values: Any) -> str:
        text = self.messages.get(source, source)
        return re.sub(r"\{(\d+)\}", lambda match: str(values[int(match.group(1))])
                      if int(match.group(1)) < len(values) else match.group(0), text)

    def message(self, source: Any) -> str:
        text = str(source)
        if text in self.messages:
            return self.tr(text)
        for key, pattern, indexes in self._patterns:
            match = pattern.fullmatch(text)
            if match:
                values = [""] * (max(indexes) + 1)
                for group, index in enumerate(indexes, 1):
                    values[index] = match.group(group)
                return self.tr(key, *values)
        return text
