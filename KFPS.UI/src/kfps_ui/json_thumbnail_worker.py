from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QUrl

from .app_paths import AppPaths
from .json_index import StartupJsonIndexBuilder, write_index_cache_payload
from .preview_service import PreviewService


SOURCE_NAMES = ["generated", "editor", "exported", "library"]
THUMBNAIL_RESULTS_VERSION = 1


def worker_environment(paths: AppPaths) -> dict:
    env = dict(os.environ)
    python_path = [str(paths.ui_root / "src"), str(paths.ui_root.parent)]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    return env


def worker_command(
    paths: AppPaths,
    cache_file: Path | None = None,
    max_seconds: float = 0.0,
    max_items: int = 0,
    app_executable: str | None = None,
    preferred_source: int | str | None = None,
    regenerate: bool = False,
) -> list[str]:
    python_exe = Path(paths.python_executable)
    cache_file = cache_file or _cache_file(paths)
    module_args = [
        "--app-root",
        str(paths.app_root),
        "--ui-root",
        str(paths.ui_root),
        "--runtime-root",
        str(paths.runtime_root),
        "--cache-file",
        str(cache_file),
        "--max-seconds",
        str(max(0.0, float(max_seconds or 0.0))),
    ]
    if max_items:
        module_args.extend(["--max-items", str(max(0, int(max_items)))])
    if preferred_source is not None:
        module_args.extend(["--preferred-source", str(preferred_source)])
    if regenerate:
        module_args.append("--regenerate")
    app_args = [
        "--thumbnail-worker",
        "--thumbnail-worker-app-root",
        str(paths.app_root),
        "--thumbnail-worker-ui-root",
        str(paths.ui_root),
        "--thumbnail-worker-runtime-root",
        str(paths.runtime_root),
        "--thumbnail-worker-cache-file",
        str(cache_file),
        "--thumbnail-worker-max-seconds",
        str(max(0.0, float(max_seconds or 0.0))),
    ]
    if max_items:
        app_args.extend(["--thumbnail-worker-max-items", str(max(0, int(max_items)))])
    if preferred_source is not None:
        app_args.extend(["--thumbnail-worker-preferred-source", str(preferred_source)])
    if regenerate:
        app_args.append("--thumbnail-worker-regenerate")
    app_script = paths.ui_root / "app.py"
    if python_exe.is_file() and python_exe.name.lower().startswith(("python", "pythonw")):
        if app_script.is_file():
            return [str(python_exe), str(app_script), *app_args]
        return [str(python_exe), "-m", "kfps_ui.json_thumbnail_worker", *module_args]
    return [str(app_executable or sys.executable), *app_args]


def _cache_file(paths: AppPaths) -> Path:
    return paths.runtime_root / "json-browser-index.v1.json"


def _load_payload(cache_file: Path) -> dict:
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def thumbnail_results_file(cache_file: Path) -> Path:
    return cache_file.with_name(cache_file.name + ".thumbnails.v1.json")


def thumbnail_file_revision(path: Path) -> dict:
    try:
        stat = path.stat()
        if not path.is_file():
            return {}
    except OSError:
        return {}
    return {"mtimeNs": stat.st_mtime_ns, "size": stat.st_size,
            "ctimeNs": stat.st_ctime_ns, "fileId": stat.st_ino}


def thumbnail_preview_missing(url: str) -> bool:
    value = QUrl(str(url or ""))
    return value.isLocalFile() and not Path(value.toLocalFile()).is_file()


def _thumbnail_cleanup_snapshot(preview, path, source):
    target_for = getattr(preview, "_cache_target", None)
    if not callable(target_for):
        return []
    cache_root = preview.cache.resolve()
    if cache_root.parent != preview.paths.runtime_root.resolve() or cache_root.name != "qml-json-previews":
        raise RuntimeError("Refusing to clear an unexpected thumbnail cache path.")
    namespace = source if source in {"generated", "editor"} else "general"
    target = target_for(path, namespace)
    targets = (target, preview._forced_marker(target))
    if any(item.is_symlink() or item.resolve().parent != cache_root for item in targets):
        raise RuntimeError("Refusing to clear an unexpected thumbnail target.")
    return [(item, thumbnail_file_revision(item)) for item in targets]


def _ordered_source_items(sources: dict, preferred_source: int | str | None = None):
    items = list(sources.items())
    if preferred_source is None:
        return items
    preferred = str(preferred_source).strip().lower()
    source_index = None
    if preferred in SOURCE_NAMES:
        source_index = str(SOURCE_NAMES.index(preferred))
    elif preferred.isdigit():
        source_index = str(int(preferred))
    if source_index is None:
        return items
    return sorted(items, key=lambda item: 0 if str(item[0]) == source_index else 1)


def warm_thumbnail_cache(
    paths: AppPaths,
    cache_file: Path | None = None,
    max_seconds: float = 0.0,
    max_items: int = 0,
    preview=None,
    preferred_source: int | str | None = None,
    force: bool = False,
) -> int:
    """Render a snapshot and publish preview results, never inventory changes."""
    cache_file = cache_file or _cache_file(paths)
    payload = _load_payload(cache_file)
    return _render_thumbnail_payload(
        payload, thumbnail_results_file(cache_file), preview or PreviewService(paths),
        max_seconds=max_seconds, max_items=max_items, preferred_source=preferred_source, force=force,
    )


def _render_thumbnail_payload(payload, result_file, preview, *, max_seconds=0.0,
                              max_items=0, preferred_source=None, force=False, clear_cache=False):
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        return 0
    started = time.monotonic()
    updated = 0
    results = {"version": THUMBNAIL_RESULTS_VERSION, "sources": {}}
    jobs = []
    for source_key, source_payload in _ordered_source_items(sources, preferred_source=preferred_source):
        try:
            source_name = SOURCE_NAMES[int(source_key)]
        except (TypeError, ValueError, IndexError):
            continue
        rows = source_payload.get("rows") if isinstance(source_payload, dict) else None
        if not isinstance(rows, list):
            continue
        result_rows = []
        results["sources"][str(source_key)] = {"root": source_payload.get("root"), "rows": result_rows}
        for row in rows:
            if not isinstance(row, dict):
                continue
            path = Path(str(row.get("path") or ""))
            needs_preview = bool(force) or not bool(row.get("previewUrl")) or thumbnail_preview_missing(row.get("previewUrl"))
            if not needs_preview and source_name == "generated":
                checker = getattr(preview, "generated_preview_needs_persistence", None)
                needs_preview = bool(callable(checker) and checker(path))
            if not needs_preview:
                continue
            revision = thumbnail_file_revision(path)
            if not revision or any(row.get(key, revision[key]) != revision[key] for key in ("mtimeNs", "size")):
                continue
            try:
                cleanup = _thumbnail_cleanup_snapshot(preview, path, source_name) if clear_cache else []
            except OSError:
                continue
            if thumbnail_file_revision(path) != revision:
                continue
            result = {"path": str(path), **revision, "previewUrl": ""}
            if force:
                result_rows.append(result)
            jobs.append((path, source_name, revision, result_rows, result, cleanup))
    # Publish bounded invalidations before deleting managed previews, so a killed
    # regeneration cannot leave the owner pointing at missing cache files.
    write_index_cache_payload(result_file, results)
    if clear_cache:
        results["removed"] = 0
    for path, source_name, revision, result_rows, result, cleanup in jobs:
        if max_items and updated >= max_items:
            break
        if max_seconds and time.monotonic() - started >= max_seconds:
            break
        if thumbnail_file_revision(path) != revision:
            continue
        # Do not delete or replace previews repaired after this job's snapshot.
        if any(item.is_symlink() or thumbnail_file_revision(item) != captured for item, captured in cleanup):
            continue
        for item, captured in cleanup:
            if captured:
                try:
                    item.unlink()
                    results["removed"] += 1
                except OSError:
                    pass
        try:
            renderer = getattr(preview, "regenerate_preview_for_json", None) if force else None
            if not callable(renderer):
                renderer = preview.preview_for_json
            preview_url = str(renderer(path, source_name) or "")
        except Exception:
            preview_url = ""
        if preview_url and thumbnail_file_revision(path) == revision:
            result["previewUrl"] = preview_url
            if not force:
                result_rows.append(result)
            updated += 1
            if updated % 25 == 0:
                write_index_cache_payload(result_file, results)
    write_index_cache_payload(result_file, results)
    return updated


def regenerate_thumbnail_cache(paths: AppPaths, cache_file: Path | None = None, preview=None) -> tuple[int, int, int]:
    cache_file = cache_file or _cache_file(paths)
    preview = preview or PreviewService(paths)
    # Standalone regeneration still discovers every source, but this snapshot is
    # read-only: only JsonService may publish inventory while the app is running.
    payload, indexed = StartupJsonIndexBuilder(paths, preview=preview, include_existing_previews=False).build_payload()
    result_file = thumbnail_results_file(cache_file)
    rendered = _render_thumbnail_payload(payload, result_file, preview, force=True, clear_cache=True)
    removed = int(_load_payload(result_file).get("removed") or 0)
    return rendered, removed, indexed


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--ui-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--cache-file")
    parser.add_argument("--max-seconds", type=float, default=0.0)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--preferred-source")
    parser.add_argument("--regenerate", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_root = Path(args.app_root)
    ui_root = Path(args.ui_root)
    paths = AppPaths(
        app_root=app_root,
        ui_root=ui_root,
        qml_root=ui_root / "qml",
        asset_root=ui_root / "assets",
        runtime_root=Path(args.runtime_root),
        bundled_python=app_root / "python" / "python.exe",
    )
    cache_file = Path(args.cache_file) if args.cache_file else None
    if args.regenerate:
        count, removed, indexed = regenerate_thumbnail_cache(paths, cache_file=cache_file)
        print(json.dumps({
            "rendered": count,
            "removed": removed,
            "indexed": indexed,
            "failed": max(0, indexed - count),
        }, separators=(",", ":")))
    else:
        count = warm_thumbnail_cache(
            paths,
            cache_file=cache_file,
            max_seconds=max(0.0, float(args.max_seconds or 0.0)),
            max_items=max(0, int(args.max_items or 0)),
            preferred_source=args.preferred_source,
        )
        print(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
