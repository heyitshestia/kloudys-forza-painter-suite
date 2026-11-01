"""Validated installation-local connection storage, separate from UI construction."""
from pathlib import Path


def workspace_connection_dir(root):
    root = Path(root).resolve()
    directory = root / "runtime/workspace"
    if directory.resolve() != directory or any(
            path.is_symlink() or path.is_junction() for path in (root / "runtime", directory)):
        raise RuntimeError("The workspace connection folder is redirected.")
    return directory
