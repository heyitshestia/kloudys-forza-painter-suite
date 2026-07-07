from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    app_root: Path
    ui_root: Path
    qml_root: Path
    asset_root: Path
    runtime_root: Path
    bundled_python: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        source_ui = Path(__file__).resolve().parents[2]
        frozen_root = Path(getattr(sys, "_MEIPASS", source_ui))
        qml_root = frozen_root / "KFPS.UI" / "qml"
        asset_root = frozen_root / "KFPS.UI" / "assets"
        ui_root = frozen_root / "KFPS.UI"
        if not qml_root.exists():
            qml_root = source_ui / "qml"
            asset_root = source_ui / "assets"
            ui_root = source_ui

        starts = [
            Path(os.environ.get("KFPS_APP_ROOT", "")) if os.environ.get("KFPS_APP_ROOT") else None,
            Path(sys.executable).resolve().parent,
            Path.cwd(),
            source_ui,
        ]
        app_root = None
        for start in [p for p in starts if p]:
            for candidate in [start, *start.parents]:
                nested = candidate / "KloudysFH6Painter"
                if cls._looks_like_root(nested):
                    app_root = nested
                    break
                if cls._looks_like_root(candidate):
                    app_root = candidate
                    break
            if app_root:
                break
        app_root = (app_root or source_ui.parent).resolve()
        return cls(
            app_root=app_root,
            ui_root=ui_root,
            qml_root=qml_root,
            asset_root=asset_root,
            runtime_root=app_root / "runtime",
            bundled_python=app_root / "python" / "python.exe",
        )

    @staticmethod
    def _looks_like_root(path: Path) -> bool:
        return path.is_dir() and (path / "VERSION").is_file() and (
            (path / "generator_backend.py").is_file()
            or (path / "KloudysGalateaGenesis.exe").is_file()
        )

    @property
    def python_executable(self) -> str:
        if self.bundled_python.is_file():
            return str(self.bundled_python)
        return sys.executable

    @property
    def settings_file(self) -> Path:
        return self.runtime_root / "qml-shell-settings.json"

    @property
    def generated_root(self) -> Path:
        return self.app_root / "imgs" / "generated"

    @property
    def editor_json_root(self) -> Path:
        return self.app_root / "imgs" / "editor"

    @property
    def exported_root(self) -> Path:
        return self.app_root / "imgs" / "exported"

    @property
    def library_root(self) -> Path:
        return self.app_root / "imgs" / "library"

    @property
    def project_root(self) -> Path:
        return self.runtime_root / "fabric-editor" / "projects"
