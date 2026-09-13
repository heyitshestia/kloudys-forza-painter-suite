"""Legacy import alias; project storage is editor-owned."""
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "KFPS.Editor/src"))
_implementation = importlib.import_module("kfps_editor.projects")
sys.modules[__name__] = _implementation


def __getattr__(name):
    return getattr(_implementation, name)
