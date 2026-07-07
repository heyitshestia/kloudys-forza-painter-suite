from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .app_paths import AppPaths
from .qt_utils import file_url


class PreviewService:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.cache = paths.runtime_root / "qml-json-previews"

    def preview_for_json(self, json_path: str | Path, source: str = "") -> str:
        path = Path(json_path)
        if not path.is_file(): return ""
        source = (source or self._source_for_path(path)).lower()
        if source == "generated":
            for candidate in self._nearby(path, exact=True):
                if candidate.is_file(): return file_url(candidate)
            return self._render_cached(path, "generated") or self._nearby_url(path)
        if source == "editor":
            return self._render_cached(path, "editor") or self._nearby_url(path)
        return self._nearby_url(path) or self._render_cached(path, "general")

    def _render_cached(self, path: Path, namespace: str) -> str:
        try:
            from json_preview_renderer import render_json_preview
            renderer_path = Path(render_json_preview.__code__.co_filename)
            renderer_stamp = renderer_path.stat().st_mtime_ns if renderer_path.is_file() else 0
            fingerprint = f"{namespace}|{path.resolve()}|{path.stat().st_mtime_ns}|{path.stat().st_size}|{renderer_stamp}"
            target = self.cache / (hashlib.sha256(fingerprint.encode()).hexdigest()[:20] + ".png")
            if not target.exists():
                data = render_json_preview(path, max_size=900)
                if data:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            return file_url(target) if target.exists() else ""
        except Exception:
            return ""

    def _nearby_url(self, path: Path) -> str:
        for candidate in self._nearby(path):
            if candidate.is_file(): return file_url(candidate)
        return ""

    def _source_for_path(self, path: Path) -> str:
        try:
            resolved = path.resolve()
            if self.paths.generated_root.resolve() in resolved.parents:
                return "generated"
            if self.paths.editor_json_root.resolve() in resolved.parents:
                return "editor"
            if self.paths.exported_root.resolve() in resolved.parents:
                return "exported"
            if self.paths.library_root.resolve() in resolved.parents:
                return "library"
        except Exception:
            pass
        return ""

    def _nearby(self, path: Path, exact: bool = False):
        stem = path.stem
        candidates = [path.with_suffix(".png")]
        parent = path.parent
        run = parent.parent if parent.name.lower() in {"finals", "checkpoints"} else parent
        layer_match = re.match(r"^(?P<base>.+)\.(?P<layer>\d+v2)$", stem, re.IGNORECASE)
        if layer_match:
            base = layer_match.group("base")
            layer = layer_match.group("layer")
            for folder in [parent, run / "previews", run / "finals"]:
                candidates.extend([
                    folder / f"{base}.preview.{layer}.png",
                    folder / f"{base}.{layer}.preview.png",
                    folder / f"{stem}.preview.png",
                    folder / f"{stem}.png",
                ])
                if folder.exists():
                    candidates.extend(
                        item for item in folder.glob(f"{base}*{layer}*.png")
                        if "preview" in item.name.lower()
                    )
            return sorted(
                {item for item in candidates if item.exists()},
                key=lambda item: (
                    0 if item.name.lower() == f"{base}.preview.{layer}.png".lower() else 1,
                    -item.stat().st_mtime,
                ),
            )
        if exact:
            return sorted({item for item in candidates if item.exists()}, key=lambda p: p.stat().st_mtime, reverse=True)
        for folder in [parent, run / "previews", run / "finals"]:
            if folder.exists():
                candidates.extend(folder.glob(f"{stem}*.png"))
                # checkpoint naming variants
                prefix = stem.rsplit(".", 1)[0]
                candidates.extend(folder.glob(f"{prefix}*preview*.png"))
        return sorted(set(candidates), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
