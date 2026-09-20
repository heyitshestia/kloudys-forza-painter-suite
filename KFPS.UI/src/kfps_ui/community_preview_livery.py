"""Disposable 3D session using the normal supervised livery pipeline."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from .app_paths import AppPaths
from .experimental.full_livery.paths import FullLiveryPaths
from .full_livery_service import FullLiveryService
from .log_service import LogService


class PreviewLiverySession:
    def __init__(self, repo, root, payload):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = TemporaryDirectory(prefix="viewer-", dir=root)
        self.service = self.log = None
        try:
            folder = Path(self.temporary.name)
            ui = Path(repo) / "KFPS.UI"
            paths = AppPaths(Path(repo), ui, ui / "qml", ui / "assets", folder, Path(repo) / "python/python.exe")
            scoped = replace(FullLiveryPaths.for_app(paths), package_root=folder / "packages")
            scoped.ensure()
            # Read only presentation/asset preferences; never copy save locations.
            ordinary = FullLiveryPaths.for_app(replace(paths, runtime_root=Path(repo) / "runtime"))
            import json
            try:
                settings = json.loads(ordinary.settings_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                settings = {}
            scoped.save_settings({k: settings[k] for k in ("fh6_game_folder", "viewer_quality", "viewer_wheels_visible") if k in settings})
            package = folder / "artwork.kfpslivery"
            package.write_bytes(payload)
            self.log = LogService(runtime_root=root / "logs")
            self.service = FullLiveryService(paths, self.log, experiment_paths=scoped)
            self.package = str(package)
        except Exception:
            self.close()
            raise

    def start(self):
        self.service.openPreviewPackage(self.package)

    def close(self):
        if self.service is not None:
            self.service.close()
            self.service.deleteLater()
            self.service = None
        if self.log is not None:
            self.log.close()
            self.log.deleteLater()
            self.log = None
        self.temporary.cleanup()
