from __future__ import annotations

import webbrowser
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .app_paths import AppPaths
from .editor_launch import find_chrome
from .log_service import LogService
from .qt_utils import open_path


def validated_output_file(paths: AppPaths, value: str) -> Path:
    """Resolve an existing vinyl only within the four configured output roots."""
    if not value or len(value) > 32768:
        raise ValueError("Choose an existing JSON from the Outputs folders.")
    candidate = Path(value).resolve()
    roots = (paths.generated_root, paths.editor_json_root, paths.exported_root, paths.library_root)
    root = next((root.resolve() for root in roots if candidate.is_relative_to(root.resolve())), None)
    if (root is None or not root.is_relative_to(paths.app_root.resolve())
            or candidate.suffix.lower() != ".json" or not candidate.is_file()
            or candidate.name.lower().endswith((".meta.json", ".fabric-project.json"))):
        raise ValueError("Choose an existing JSON from the Outputs folders.")
    return candidate


class DesktopService(QObject):
    chromeStatusChanged = Signal()

    def __init__(self, paths: AppPaths, log: LogService, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log
        self._chrome_installed = find_chrome() is not None
        self._chrome_install_error = ""

    @Property(bool, notify=chromeStatusChanged)
    def chromeInstalled(self):
        return self._chrome_installed

    @Property(str, notify=chromeStatusChanged)
    def chromeInstallError(self):
        return self._chrome_install_error

    @Slot()
    def refreshChromeStatus(self):
        installed = find_chrome() is not None
        if installed != self._chrome_installed:
            self._chrome_installed = installed
            if installed:
                self._chrome_install_error = ""
            self.chromeStatusChanged.emit()

    @Slot()
    def openChromeInstallPage(self):
        self.refreshChromeStatus()
        if self._chrome_installed:
            return
        self._chrome_install_error = ""
        try:
            if not QDesktopServices.openUrl(QUrl("https://www.google.com/chrome/")):
                raise RuntimeError("Windows could not open the official Chrome download page.")
            self.log.append("Opened Google's Chrome installation page at the user's request.")
        except Exception as exc:
            self._chrome_install_error = "Could not open the browser. Visit google.com/chrome to install."
            self.log.append(f"Could not open Chrome installation page: {exc}", "error")
        self.chromeStatusChanged.emit()

    @Property(str, constant=True)
    def appRoot(self):
        return str(self.paths.app_root)

    @Property(str, constant=True)
    def sourceImagesFolder(self):
        return str(self.paths.app_root.parent / "Images")

    @Property(str, constant=True)
    def jsonRootFolder(self):
        return str(self.paths.app_root / "imgs")

    @Property(str, constant=True)
    def generatedFolder(self):
        return str(self.paths.generated_root)

    @Property(str, constant=True)
    def exportedFolder(self):
        return str(self.paths.exported_root)

    @Property(str, constant=True)
    def editorProjectsFolder(self):
        return str(self.paths.project_root)

    @Property(str, constant=True)
    def runtimeFolder(self):
        return str(self.paths.runtime_root)

    @Property(str, constant=True)
    def reportsFolder(self):
        return str(self.paths.runtime_root / "bug-reports")

    @Slot(result=str)
    def chooseImage(self):
        initial = Path(self.sourceImagesFolder)
        path, _ = QFileDialog.getOpenFileName(None, "Choose source image", str(initial if initial.exists() else self.paths.app_root), "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)")
        return path

    @Slot(result="QStringList")
    def chooseImages(self):
        initial = Path(self.sourceImagesFolder)
        paths, _ = QFileDialog.getOpenFileNames(None, "Choose source image(s)", str(initial if initial.exists() else self.paths.app_root), "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)")
        return paths

    @Slot(result=str)
    def chooseJson(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose vinyl JSON", str(self.paths.generated_root if self.paths.generated_root.exists() else self.paths.app_root), "Vinyl JSON (*.json);;All files (*)")
        return path

    @Slot(str)
    def openFolder(self, value):
        try:
            open_path(Path(value))
            self.log.append(f"Opened folder: {value}")
        except Exception as exc:
            self.log.append(f"Could not open folder: {exc}", "error")

    @Slot(str, result=bool)
    def revealOutputFile(self, value):
        try:
            candidate = validated_output_file(self.paths, value)
            if sys.platform != "win32":
                raise ValueError("File selection in Explorer is available on Windows only.")
            subprocess.Popen(["explorer.exe", f"/select,{candidate}"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except (OSError, ValueError) as exc:
            self.log.append(f"Could not show output file: {exc}", "error")
            return False

    def _open_or_create(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.openFolder(str(path))

    @Slot()
    def openRoot(self):
        self.openFolder(str(self.paths.app_root))

    @Slot()
    def openSourceImages(self):
        self._open_or_create(Path(self.sourceImagesFolder))

    @Slot()
    def openRuntime(self):
        self._open_or_create(self.paths.runtime_root)

    @Slot()
    def openJsonFolders(self):
        self._open_or_create(self.paths.app_root / "imgs")

    @Slot()
    def openGenerated(self):
        self._open_or_create(self.paths.generated_root)

    @Slot()
    def openExported(self):
        self._open_or_create(self.paths.exported_root)

    @Slot()
    def openProjects(self):
        self._open_or_create(self.paths.project_root)

    @Slot()
    def openReports(self):
        self._open_or_create(self.paths.runtime_root / "bug-reports")

    @Slot(str)
    def openUrl(self, url):
        try:
            webbrowser.open(url)
            self.log.append(f"Opened: {url}")
        except Exception as exc:
            self.log.append(f"Could not open URL: {exc}", "error")
