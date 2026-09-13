"""Compatibility import for the editor's installation update guard."""
import importlib
from pathlib import Path
import sys

_root = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(_root), str(_root / "KFPS.Editor/src")]
_implementation = importlib.import_module("kfps_editor.update_guard")
sys.modules[__name__] = _implementation


def __getattr__(name):
    return getattr(_implementation, name)
