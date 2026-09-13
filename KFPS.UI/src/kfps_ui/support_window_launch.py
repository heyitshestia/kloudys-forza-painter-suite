"""Start the isolated report reviewer with the editor's managed runtime policy."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from .support_window_protocol import report_id


def launch_review(paths, identifier: str) -> str:
    identifier = report_id(identifier)
    root = paths.app_root.resolve()
    entry = root / "KFPS.UI" / "report.py"
    if not entry.is_file():
        return "failed"
    editor_source = str(root / "KFPS.Editor" / "src")
    if editor_source not in sys.path:
        sys.path.insert(0, editor_source)
    from kfps_editor.baseline import launch_command
    command, environment = launch_command(root, entry, ["--report-id", identifier],
                                          fallback=paths.python_executable)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Report contents stay on disk and off command lines, process lists and URLs.
    with open(os.devnull, "wb") as output:
        subprocess.Popen(command, cwd=root, env=environment, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output, close_fds=True)
    return "review"
