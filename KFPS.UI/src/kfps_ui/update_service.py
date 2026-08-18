from __future__ import annotations

import os
from pathlib import Path
import subprocess

from PySide6.QtCore import QCoreApplication, QObject, Slot

from .app_paths import AppPaths
from .log_service import LogService


class UpdateService(QObject):
    def __init__(self, paths: AppPaths, log: LogService, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log

    @Slot()
    def startUpdate(self):
        batch = self.paths.app_root / "03_update_from_github.bat"
        if not batch.is_file():
            self.log.append(f"Updater is missing: {batch}", "error")
            return
        try:
            comspec = os.environ.get("COMSPEC") or "cmd.exe"
            env = os.environ.copy()
            env["KFPS_UPDATER_ROOT"] = str(self.paths.app_root)
            env["KFPS_RELAUNCH_AFTER_UPDATE"] = "1"
            env["FORZA_PAINTER_NO_PAUSE"] = "1"
            relaunch_target = self.paths.app_root.parent / "KFPS.exe"
            if not relaunch_target.is_file():
                relaunch_target = self.paths.app_root / "KFPS.exe"
            if relaunch_target.is_file():
                env["KFPS_RELAUNCH_TARGET"] = str(relaunch_target)
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(
                [comspec, "/c", "start", "KFPS Updater", str(batch)],
                cwd=self.paths.app_root,
                creationflags=flags,
                close_fds=True,
                env=env,
            )
            self.log.append("Updater started. Closing KFPS.")
            QCoreApplication.quit()
        except Exception as exc:
            self.log.append(f"Could not start updater: {exc}", "error")
