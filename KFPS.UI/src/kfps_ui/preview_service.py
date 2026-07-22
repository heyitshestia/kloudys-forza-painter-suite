from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path

from .app_paths import AppPaths
from .qt_utils import file_url


PREVIEW_RENDERER_CACHE_VERSION = 3


def _stable_renderer_stamp(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
    except OSError:
        digest = "embedded"
    return f"v{PREVIEW_RENDERER_CACHE_VERSION}:{digest}"


class PreviewService:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.cache = paths.runtime_root / "qml-json-previews"
        self._renderer_stamp = None

    def clear_cached_thumbnails(self) -> int:
        runtime_root = self.paths.runtime_root.resolve()
        cache_root = self.cache.resolve()
        if cache_root.parent != runtime_root or cache_root.name != "qml-json-previews":
            raise RuntimeError("Refusing to clear an unexpected thumbnail cache path.")
        if not cache_root.exists():
            return 0
        removed = sum(1 for path in cache_root.rglob("*") if path.is_file() or path.is_symlink())
        shutil.rmtree(cache_root)
        return removed

    def preview_for_json(self, json_path: str | Path, source: str = "") -> str:
        path = Path(json_path)
        if not path.is_file(): return ""
        source = (source or self._source_for_path(path)).lower()
        if source == "generated":
            for candidate in self._nearby(path, exact=True):
                if candidate.is_file(): return file_url(candidate)
            return self._render_cached(path, "generated") or self._nearby_url(path)
        if source == "editor":
            return self._newest_existing_url(path, "editor") or self._render_cached(path, "editor")
        return self._newest_existing_url(path, "general") or self._render_cached(path, "general")

    def regenerate_preview_for_json(self, json_path: str | Path, source: str = "") -> str:
        path = Path(json_path)
        if not path.is_file():
            return ""
        source = (source or self._source_for_path(path)).lower()
        namespace = "generated" if source == "generated" else ("editor" if source == "editor" else "general")
        target = self._generated_preview_target(path) if namespace == "generated" else self._cache_target(path, namespace)
        temporary = None
        marker_temporary = None
        try:
            from json_preview_renderer import render_json_preview

            data = render_json_preview(path, max_size=900)
            if not data:
                return ""
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
            if namespace != "generated":
                marker = self._forced_marker(target)
                marker_temporary = marker.with_name(f".{marker.name}.{uuid.uuid4().hex}.tmp")
                marker_temporary.write_text("forced-local-thumbnail-v1", encoding="ascii")
                marker_temporary.replace(marker)
            return file_url(target)
        except Exception:
            return ""
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            if marker_temporary is not None:
                try:
                    marker_temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def existing_preview_for_json(self, json_path: str | Path, source: str = "") -> str:
        path = Path(json_path)
        if not path.is_file(): return ""
        source = (source or self._source_for_path(path)).lower()
        if source == "generated":
            for candidate in self._nearby(path, exact=True):
                if candidate.is_file(): return file_url(candidate)
            return self._cached_url(path, "generated") or self._nearby_url(path)
        if source == "editor":
            return self._newest_existing_url(path, "editor")
        return self._newest_existing_url(path, "general")

    def _newest_existing_url(self, path: Path, namespace: str) -> str:
        candidates = {}
        try:
            managed = self._cache_target(path, namespace)
            if managed.is_file():
                if self._forced_marker(managed).is_file():
                    return file_url(managed)
                candidates[managed.resolve()] = (managed.stat().st_mtime_ns, 1, managed)
        except OSError:
            pass
        for nearby in self._nearby(path):
            try:
                if nearby.is_file():
                    resolved = nearby.resolve()
                    current = candidates.get(resolved)
                    candidate = (nearby.stat().st_mtime_ns, 0, nearby)
                    if current is None or candidate[:2] > current[:2]:
                        candidates[resolved] = candidate
            except OSError:
                continue
        if not candidates:
            return ""
        return file_url(max(candidates.values(), key=lambda item: item[:2])[2])

    @staticmethod
    def _forced_marker(target: Path) -> Path:
        return target.with_suffix(target.suffix + ".forced")

    def _render_cached(self, path: Path, namespace: str) -> str:
        try:
            from json_preview_renderer import render_json_preview
            target = self._generated_preview_target(path) if namespace == "generated" else self._cache_target(path, namespace)
            if not target.exists():
                data = None
                if namespace == "generated":
                    legacy_cache = self._cache_target(path, namespace)
                    if legacy_cache.is_file():
                        data = legacy_cache.read_bytes()
                if not data:
                    data = render_json_preview(path, max_size=900)
                if data:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            return file_url(target) if target.exists() else ""
        except Exception:
            return ""

    def _cached_url(self, path: Path, namespace: str) -> str:
        try:
            if namespace == "generated":
                target = self._generated_preview_target(path)
                if target.exists():
                    return file_url(target)
            target = self._cache_target(path, namespace)
            return file_url(target) if target.exists() else ""
        except Exception:
            return ""

    def generated_preview_needs_persistence(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.is_file() or self._source_for_path(path) != "generated":
            return False
        return not any(candidate.is_file() for candidate in self._nearby(path, exact=True))

    def _generated_preview_target(self, path: Path) -> Path:
        parent = path.parent
        run = parent.parent if parent.name.lower() in {"finals", "checkpoints"} else parent
        stem = path.stem
        tagged = re.match(r"^(?P<base>.+)\.(?P<tag>(?:\d+|final)v2|\d+)$", stem, re.IGNORECASE)
        name = f"{tagged.group('base')}.preview.{tagged.group('tag')}.png" if tagged else f"{stem}.preview.png"
        return run / "previews" / name

    def _cache_target(self, path: Path, namespace: str) -> Path:
        renderer_stamp = self._json_preview_renderer_stamp()
        fingerprint = f"{namespace}|{path.resolve()}|{path.stat().st_mtime_ns}|{path.stat().st_size}|{renderer_stamp}"
        return self.cache / (hashlib.sha256(fingerprint.encode()).hexdigest()[:20] + ".png")

    def _json_preview_renderer_stamp(self) -> str:
        if self._renderer_stamp is not None:
            return self._renderer_stamp
        try:
            from json_preview_renderer import render_json_preview
            renderer_path = Path(render_json_preview.__code__.co_filename)
            self._renderer_stamp = _stable_renderer_stamp(renderer_path)
        except Exception:
            self._renderer_stamp = f"v{PREVIEW_RENDERER_CACHE_VERSION}:embedded"
        return self._renderer_stamp

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
        if self._source_for_path(path) == "generated":
            candidates.append(self._generated_preview_target(path))
        parent = path.parent
        run = parent.parent if parent.name.lower() in {"finals", "checkpoints"} else parent
        layer_match = re.match(r"^(?P<base>.+)\.(?P<layer>(?:\d+|final)v2)$", stem, re.IGNORECASE)
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
