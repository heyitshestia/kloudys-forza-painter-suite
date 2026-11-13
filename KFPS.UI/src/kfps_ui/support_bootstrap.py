"""Bounded, content-free diagnostics before importing the report window's Qt DLLs."""
from __future__ import annotations

import ctypes
import importlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import stat
import sys

from .support_window_protocol import reports_folder


def setup_logging(root: Path):
    root = Path(root).resolve()
    logger = logging.getLogger("kfps-report-window")
    if any(getattr(handler, "report_root", None) == root for handler in logger.handlers):
        return None
    folder = reports_folder(root, create=True)
    path = folder / "report-window.log"
    for candidate in (path, Path(str(path) + ".1"), Path(str(path) + ".2")):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked report logs are not supported.")
    handler = RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    handler.report_root = root
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return handler


def close_logging(handler):
    if handler is not None:
        logging.getLogger("kfps-report-window").removeHandler(handler)
        handler.close()


def show_failure():
    # Qt may be the failed import. Keep this last-resort message independent of it.
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None,
            "The KFPS report window could not start. Your saved report has not been sent. "
            "Use Saved reports and Open support form in KFPS. "
            "Diagnostics: runtime/support-reports/report-window.log",
            "KFPS Report", 0x30)


def run(root: Path) -> int:
    handler = None
    logger = logging.getLogger("kfps-report-window")
    try:
        handler = setup_logging(root)
        logger.info("reviewer-start python=%s pid=%s", sys.version.split()[0], os.getpid())
        window = importlib.import_module("kfps_ui.support_window")
        try:
            code = window.main(root)
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else 1
        logger.info("reviewer-exit code=%s", code)
        return int(code or 0)
    except Exception as error:
        logger.error("bootstrap-failed type=%s winerror=%s", type(error).__name__, getattr(error, "winerror", None))
        show_failure()
        return 1
    finally:
        close_logging(handler)
