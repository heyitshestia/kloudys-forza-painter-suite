"""Compatibility import for the shared source-download policy."""
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
_implementation = importlib.import_module("tools.source_download_guard")
sys.modules[__name__] = _implementation


def __getattr__(name):
    return getattr(_implementation, name)
