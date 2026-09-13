from __future__ import annotations

import ctypes
import logging
import sys


def is_korean_display_language() -> bool:
    """Match the Windows user's UI language, never regional or keyboard settings."""
    if sys.platform != "win32":
        return False
    try:
        get_language = ctypes.WinDLL("kernel32", use_last_error=True).GetUserDefaultUILanguage
        get_language.argtypes = []
        get_language.restype = ctypes.c_ushort
        language_id = get_language()
    except (AttributeError, OSError):
        logging.getLogger(__name__).warning("Could not determine the Windows display language", exc_info=True)
        return False
    return language_id & 0x03FF == 0x12  # PRIMARYLANGID / LANG_KOREAN
