"""Read the optional installed Studio contract without starting any Studio host."""
from functools import lru_cache
import importlib
from pathlib import Path
import sys
import types

from .support_logs import _safe

CODE_ROOT = Path(__file__).resolve().parents[3]
RELATIVE_ROOT = "tools/livery-studio/runs/diagnostics"
NAMES = ("studio.jsonl", "studio.1.jsonl", "studio.2.jsonl")


@lru_cache(maxsize=1)
def _contract():
    # Import only shipped code beside this collector, never code beneath the
    # data root passed to a report or inside a recovery/project directory.
    source = CODE_ROOT / "tools/livery-studio/src/kfps_livery_lab"
    try:
        for name in ("diagnostics.py", "storage_paths.py"):
            _safe(CODE_ROOT, source / name)
    except FileNotFoundError:
        return None
    name = "_kfps_support_studio"
    package = types.ModuleType(name)
    package.__path__ = [str(source)]
    sys.modules[name] = package
    try:
        return importlib.import_module(name + ".diagnostics")
    except Exception:
        for key in tuple(sys.modules):
            if key == name or key.startswith(name + "."):
                sys.modules.pop(key, None)
        raise


def read_studio_snapshot(root):
    try:
        contract = _contract()
        if contract is None:
            return {"persistence": "component_not_installed"}
        return contract.read_snapshot(Path(root) / RELATIVE_ROOT)
    except FileNotFoundError:
        return {"persistence": "component_not_installed"}
    except Exception:
        return {"persistence": "unavailable"}


def clean_studio_record(value):
    try:
        result = _contract().clean_record(value)
    except Exception:
        result = None
    if result is None:
        raise ValueError("unsupported_record")
    return result
