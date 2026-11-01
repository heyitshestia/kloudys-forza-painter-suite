"""Choose the UI entry before importing NumPy or Qt."""
from __future__ import annotations

import importlib.util
from pathlib import Path


# These routes use app.main's existing worker dispatch or QML capture harness.
LEGACY_ROUTES = frozenset({
    "--legacy-ui", "--thumbnail-worker", "--full-livery-worker",
    "--full-livery-inspector", "--demo", "--screenshot", "--screenshot-dir",
    "--layout-report", "--layout-report-dir", "--interaction-capture-dir",
    "--output-menu-capture", "--output-actions-report", "--navigation-timing-report",
    "--motion-capture-dir", "--motion-preview", "--community-preview",
    "--community-preview-test", "--startup-preview", "--help", "-h",
})


def uses_workspace(arguments):
    return not any(argument.split("=", 1)[0] in LEGACY_ROUTES for argument in arguments)


def launch_workspace(ui_root: Path):
    # Resolve the adjacent entry directly, including under Python's -I mode.
    entry = Path(ui_root) / "workspace.py"
    spec = importlib.util.spec_from_file_location("_kfps_workspace_entry", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()
