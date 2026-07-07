from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

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
        batch = self._fresh_updater_batch() or self.paths.app_root / "03_update_from_github.bat"
        if not batch.is_file():
            self.log.append(f"Updater is missing: {batch}", "error")
            return
        try:
            comspec = os.environ.get("COMSPEC") or "cmd.exe"
            env = os.environ.copy()
            if batch.parent != self.paths.app_root:
                env["KFPS_UPDATER_REMOTE_BOOTSTRAP"] = "1"
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

    def _fresh_updater_batch(self):
        url = "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/main/03_update_from_github.bat"
        try:
            target = os.path.join(tempfile.gettempdir(), f"kfps-live-updater-{int(time.time())}.bat")
            request = urllib.request.Request(url, headers={"User-Agent": "KFPS-Updater"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
            if b":sync_program_files_from_repo" not in data or b":verify_program_file_sync" not in data:
                raise RuntimeError("downloaded updater did not pass sanity checks")
            with open(target, "wb") as handle:
                handle.write(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.log.append("Fetched fresh updater script from GitHub.")
            return Path(target)
        except Exception as exc:
            self.log.append(f"Fresh updater fetch failed, using local updater: {exc}", "warn")
            return None
