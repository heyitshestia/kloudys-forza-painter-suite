from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .json_metadata import age_label, count_detail_text, json_count, json_mask_summary, json_summary

if TYPE_CHECKING:
    from .app_paths import AppPaths
    from .preview_service import PreviewService


JSON_INDEX_CACHE_VERSION = 2
OUTPUT_FOLDER_MARKER = ".kfps-output-folder"
_IGNORED_JSON_TOKENS = (
    ".report.",
    "settings",
    "metadata",
    "backup",
    "session",
    "probe",
    "manifest",
)


class StartupJsonIndexBuilder:
    def __init__(
        self,
        paths: AppPaths,
        preview: PreviewService | None = None,
        progress: Callable[[str, int, int], None] | None = None,
        include_existing_previews: bool = True,
    ):
        self.paths = paths
        self.preview = preview
        self.progress = progress
        self.include_existing_previews = bool(include_existing_previews)

    def source_roots(self) -> list[Path]:
        return [
            self.paths.generated_root,
            self.paths.editor_json_root,
            self.paths.exported_root,
            self.paths.library_root,
        ]

    @staticmethod
    def source_names() -> list[str]:
        return ["generated", "editor", "exported", "library"]

    @staticmethod
    def source_label(source: int) -> str:
        labels = ["Generated finals", "Editor exports", "Game exports", "Library"]
        return labels[source] if 0 <= source < len(labels) else "Outputs"

    def cache_key(self, source: int) -> str:
        root = self.source_roots()[source]
        try:
            return str(root.resolve()).casefold()
        except (OSError, RuntimeError):
            return str(root).casefold()

    def report(self, message: str, done: int, total: int) -> None:
        if callable(self.progress):
            self.progress(message, done, total)

    def build_payload(self) -> tuple[dict, int]:
        sources = {}
        total_rows = 0
        roots = self.source_roots()
        for source, root in enumerate(roots):
            self.report(f"Politely interrogating {self.source_label(source)}...", source, len(roots))
            index = self.build_source(source, root)
            rows = index.get("rows", [])
            total_rows += len(rows)
            sources[str(source)] = self.source_payload(source, index)
            self.report(
                f"{self.source_label(source)} filed {len(rows)} JSONs without eating the clipboard.",
                source + 1,
                len(roots),
            )
        return {"version": JSON_INDEX_CACHE_VERSION, "createdAt": time.time(), "sources": sources}, total_rows

    def build_source(self, source: int, root: Path) -> dict:
        root.mkdir(parents=True, exist_ok=True)
        groups = []
        if source == 0:
            root_files = [
                path for path in root.glob("*.json")
                if not any(token in path.name.casefold() for token in _IGNORED_JSON_TOKENS)
            ]
            if root_files:
                groups.append(self.group(root.name, root, root_files))
            for folder in root.iterdir():
                if folder.is_dir():
                    files = self.files(folder, generated=True)
                    if files:
                        groups.append(self.group(folder.name, folder, files))
                    if len(groups) % 25 == 0:
                        time.sleep(0)
        else:
            grouped: dict[Path, list[Path]] = {}
            for path in self.files(root, generated=False):
                grouped.setdefault(path.parent, []).append(path)
            for index, (folder, files) in enumerate(grouped.items()):
                name = str(folder.relative_to(root)) if folder != root else root.name
                groups.append(self.group(name, folder, files))
                if index % 25 == 0:
                    time.sleep(0)
        groups.sort(key=lambda item: item["modified"], reverse=True)
        rows = [self.row_for_json(source, path) for path in self.sorted_visible_files(source, groups)]
        return {
            "root": self.cache_key(source),
            "groups": groups,
            "rows": rows,
            "source": source,
            "scannedAt": time.time(),
        }

    @staticmethod
    def files(root: Path, generated: bool) -> list[Path]:
        output = []
        for path in root.rglob("*.json"):
            if any(token in path.name.lower() for token in _IGNORED_JSON_TOKENS):
                continue
            managed = any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
            if generated and not (path.parent.name.lower() == "finals" or managed):
                continue
            output.append(path)
        return output

    def group(self, name: str, folder: Path, files: list[Path]) -> dict:
        modified = max(path.stat().st_mtime for path in files)
        display_name = name
        detail_text = f"{len(files)} JSON" if len(files) == 1 else f"{len(files)} JSONs"
        if files:
            metadata, layers, _ = json_summary(files[0])
            title = metadata.get("display_name") or metadata.get("title")
            if title:
                display_name = str(title)
            if isinstance(layers, int):
                detail_text = count_detail_text(layers, metadata)
        return {
            "name": name,
            "displayName": display_name,
            "detailText": detail_text,
            "path": str(folder),
            "files": sorted(files, key=lambda path: path.stat().st_mtime, reverse=True),
            "count": len(files),
            "modified": modified,
            "modifiedLabel": age_label(modified),
        }

    def sorted_visible_files(self, source: int, groups: list[dict]) -> list[Path]:
        if source == 0:
            files = []
            root = self.source_roots()[source]
            for group in sorted(groups, key=lambda item: item["modified"], reverse=True):
                managed = [
                    path for path in group["files"]
                    if path.parent == root or any((parent / OUTPUT_FOLDER_MARKER).is_file() for parent in path.parents)
                ]
                generated = [path for path in group["files"] if path not in managed]
                files.extend(sorted(self.dedupe_generated_files(generated), key=lambda path: (json_count(path), path.name.casefold())))
                files.extend(sorted(managed, key=lambda path: (json_count(path), path.name.casefold())))
            return files
        files = [path for group in groups for path in group["files"]]
        return sorted(files, key=lambda path: (path.stat().st_mtime * -1, path.name.casefold()))

    @staticmethod
    def dedupe_generated_files(files: list[Path]) -> list[Path]:
        selected: dict[int, Path] = {}
        for path in files:
            key = json_count(path)
            previous = selected.get(key)
            if previous is None or path.stat().st_mtime >= previous.stat().st_mtime:
                selected[key] = path
        return list(selected.values())

    def row_for_json(self, source: int, path: Path) -> dict:
        stat = path.stat()
        modified_label = age_label(stat.st_mtime)
        metadata, layers, display_name = json_summary(path)
        mask_count, uses_masks = json_mask_summary(path, metadata)
        detail = count_detail_text(layers, metadata)
        return {
            "name": path.name,
            "displayName": display_name,
            "path": str(path),
            "layers": layers,
            "usesMasks": uses_masks,
            "maskCount": mask_count,
            "modifiedLabel": modified_label,
            "previewUrl": self.existing_preview(path, self.source_names()[source]),
            "countDetail": detail,
            "detailText": f"{detail}  •  {modified_label}",
            "folder": str(path.parent),
            "mtime": stat.st_mtime,
            "mtimeNs": stat.st_mtime_ns,
            "size": stat.st_size,
            "source": source,
        }

    def existing_preview(self, path: Path, source_name: str) -> str:
        if not self.include_existing_previews:
            return ""
        existing = getattr(self.preview, "existing_preview_for_json", None)
        if callable(existing):
            try:
                return str(existing(path, source_name) or "")
            except Exception:
                return ""
        return ""

    def source_payload(self, source: int, index: dict) -> dict:
        return {
            "root": index.get("root") or self.cache_key(source),
            "scannedAt": index.get("scannedAt") or time.time(),
            "rows": [
                {
                    "name": row.get("name", ""),
                    "displayName": row.get("displayName", ""),
                    "path": row.get("path", ""),
                    "layers": int(row.get("layers") or 0),
                    "usesMasks": bool(row.get("usesMasks")),
                    "maskCount": int(row.get("maskCount") or 0),
                    "previewUrl": row.get("previewUrl", ""),
                    "countDetail": row.get("countDetail", ""),
                    "folder": row.get("folder", ""),
                    "mtimeNs": int(row.get("mtimeNs") or 0),
                    "size": int(row.get("size") or 0),
                }
                for row in index.get("rows", [])
            ],
            "groups": [
                {
                    "name": group.get("name", ""),
                    "displayName": group.get("displayName", ""),
                    "detailText": group.get("detailText", ""),
                    "path": group.get("path", ""),
                    "files": [str(path) for path in group.get("files", [])],
                }
                for group in index.get("groups", [])
            ],
        }


def write_index_cache_payload(target: str | Path, payload: dict) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def build_startup_json_index_cache(
    paths: AppPaths,
    preview: PreviewService | None = None,
    progress=None,
    include_existing_previews: bool = True,
) -> int:
    builder = StartupJsonIndexBuilder(
        paths,
        preview=preview,
        progress=progress,
        include_existing_previews=include_existing_previews,
    )
    payload, total_rows = builder.build_payload()
    write_index_cache_payload(paths.runtime_root / "json-browser-index.v1.json", payload)
    return total_rows
