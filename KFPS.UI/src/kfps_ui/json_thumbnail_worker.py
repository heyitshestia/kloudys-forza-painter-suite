from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .app_paths import AppPaths
from .preview_service import PreviewService


SOURCE_NAMES = ["generated", "editor", "exported", "library"]


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


def _write_payload(cache_file: Path, payload: dict) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    tmp.replace(cache_file)


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
) -> int:
    cache_file = cache_file or _cache_file(paths)
    payload = _load_payload(cache_file)
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        return 0
    preview = preview or PreviewService(paths)
    started = time.monotonic()
    updated = 0
    for source_key, source_payload in _ordered_source_items(sources, preferred_source=preferred_source):
        try:
            source_name = SOURCE_NAMES[int(source_key)]
        except (TypeError, ValueError, IndexError):
            source_name = ""
        rows = source_payload.get("rows") if isinstance(source_payload, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            path = Path(str(row.get("path") or ""))
            needs_preview = not bool(row.get("previewUrl"))
            if not needs_preview and source_name == "generated":
                checker = getattr(preview, "generated_preview_needs_persistence", None)
                needs_preview = bool(callable(checker) and checker(path))
            if not needs_preview:
                continue
            if max_items and updated >= max_items:
                _write_payload(cache_file, payload)
                return updated
            if max_seconds and time.monotonic() - started >= max_seconds:
                _write_payload(cache_file, payload)
                return updated
            if not path.is_file():
                continue
            try:
                preview_url = str(preview.preview_for_json(path, source_name) or "")
            except Exception:
                preview_url = ""
            if preview_url:
                row["previewUrl"] = preview_url
                updated += 1
                if updated % 25 == 0:
                    _write_payload(cache_file, payload)
    if updated:
        _write_payload(cache_file, payload)
    return updated


def regenerate_thumbnail_cache(paths: AppPaths, cache_file: Path | None = None, preview=None) -> tuple[int, int, int]:
    cache_file = cache_file or _cache_file(paths)
    preview = preview or PreviewService(paths)
    removed = int(preview.clear_cached_thumbnails())
    from .json_service import build_startup_json_index_cache
    indexed = int(build_startup_json_index_cache(paths, preview=preview))
    rendered = int(warm_thumbnail_cache(paths, cache_file=cache_file, preview=preview))
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
        count, _removed, _indexed = regenerate_thumbnail_cache(paths, cache_file=cache_file)
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
