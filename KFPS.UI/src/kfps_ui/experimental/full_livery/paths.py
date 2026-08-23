from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CACHE_REVISION = 11


@dataclass(frozen=True)
class FullLiveryPaths:
    root: Path
    state: Path
    cache: Path
    sessions: Path
    diagnostics: Path
    recovery: Path
    quarantine: Path
    package_root: Path
    settings_file: Path
    catalog_file: Path
    qualification_file: Path
    vehicle_index: Path
    mesh_cache: Path
    render_cache: Path
    preview_cache: Path
    legacy_root: Path

    @classmethod
    def for_app(cls, paths) -> "FullLiveryPaths":
        root = paths.runtime_root / "experiments" / "full-livery"
        state = root / "state"
        cache = root / "cache" / f"v{CACHE_REVISION}"
        return cls(
            root=root,
            state=state,
            cache=cache,
            sessions=root / "sessions",
            diagnostics=root / "diagnostics",
            recovery=root / "recovery",
            quarantine=root / "quarantine",
            package_root=paths.exported_root / "full-liveries",
            settings_file=state / "settings.json",
            catalog_file=state / "catalog.sqlite3",
            qualification_file=state / "qualification.json",
            vehicle_index=cache / "vehicle-index" / "fh6.json",
            mesh_cache=cache / "meshes",
            render_cache=cache / "atlases",
            preview_cache=cache / "previews",
            legacy_root=paths.runtime_root / "full-livery",
        )

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.state,
            self.cache,
            self.sessions,
            self.diagnostics,
            self.recovery,
            self.quarantine,
            self.package_root,
            self.vehicle_index.parent,
            self.mesh_cache,
            self.render_cache,
            self.preview_cache,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> dict[str, Any]:
        self.ensure()
        for candidate in (self.settings_file, self.legacy_root / "settings.json"):
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict):
                if candidate != self.settings_file:
                    self.save_settings(value)
                return value
        return {}

    def save_settings(self, value: dict[str, Any]) -> None:
        self.ensure()
        temporary = self.settings_file.with_name(
            f".{self.settings_file.name}.{os.getpid()}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.settings_file)
        finally:
            temporary.unlink(missing_ok=True)

    def as_worker_payload(self) -> dict[str, str]:
        return {
            "root": str(self.root.resolve()),
            "state": str(self.state.resolve()),
            "cache": str(self.cache.resolve()),
            "sessions": str(self.sessions.resolve()),
            "diagnostics": str(self.diagnostics.resolve()),
            "recovery": str(self.recovery.resolve()),
            "quarantine": str(self.quarantine.resolve()),
            "package_root": str(self.package_root.resolve()),
            "settings_file": str(self.settings_file.resolve()),
            "catalog_file": str(self.catalog_file.resolve()),
            "qualification_file": str(self.qualification_file.resolve()),
            "vehicle_index": str(self.vehicle_index.resolve()),
            "mesh_cache": str(self.mesh_cache.resolve()),
            "render_cache": str(self.render_cache.resolve()),
            "preview_cache": str(self.preview_cache.resolve()),
        }
