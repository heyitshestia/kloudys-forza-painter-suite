"""Output boundaries for tests; never infer a Desktop sibling runs directory."""
import os
from pathlib import Path
import tempfile


def _absolute_ordinary(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Test evidence paths must be absolute.")
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Test evidence paths must not be redirected.")
    return path.resolve()


def evidence_root():
    root = _absolute_ordinary(os.environ.get("KFPS_TEST_EVIDENCE_ROOT",
                                           Path(tempfile.gettempdir()) / "kfps-test-evidence"))
    if root == Path(root.anchor):
        raise ValueError("Use a named test evidence directory, not a drive root.")
    return root


def evidence_directory(label, override=None):
    root = evidence_root()
    value = os.environ.get(override) if override else None
    path = _absolute_ordinary(value if value is not None else root / label)
    if path == root or not path.is_relative_to(root):
        raise ValueError("Test evidence must stay below KFPS_TEST_EVIDENCE_ROOT.")
    return path
