"""Compatibility entry point for the editor's canonical source manifest."""
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "KFPS.Editor/src"))
_implementation = importlib.import_module("kfps_editor.manifest")
if __name__ == "__main__":
    if sys.argv[1:] == ["sync"]:
        _implementation.sync()
    _implementation.check()
else:
    sys.modules[__name__] = _implementation


def __getattr__(name):
    return getattr(_implementation, name)
