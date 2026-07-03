from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Property, Slot
from PySide6.QtWidgets import QFileDialog

from .app_paths import AppPaths
from .log_service import LogService
from .qt_utils import open_path


class DesktopService(QObject):
    def __init__(self, paths: AppPaths, log: LogService, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log

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
