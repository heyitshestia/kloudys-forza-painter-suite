#!/usr/bin/env python3
"""Find Forza C_group/C_livery artifacts for the export-only prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .forza_source_decoder import DecodeError, decode_forza_source
except ImportError:  # pragma: no cover - direct script execution fallback
    from forza_source_decoder import DecodeError, decode_forza_source


SOURCE_NAMES = {"c_group", "c_livery"}
SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "checkpoints",
    "generated",
    "imgs",
    "node_modules",
    "previews",
    "python",
    "reports",
    "runtime",
    "site-packages",
    "venv",
}


def is_fh5_layer_group_candidate(path: Path) -> bool:
    name = path.name.lower()
    if name == "c_group":
        return True
    if name.endswith(".c_group"):
        return True
    return False


def is_source_candidate(path: Path, game: str) -> bool:
    name = path.name.lower()
    game_key = str(game or "fh6").lower()
    if name in SOURCE_NAMES:
        return True
    if game_key == "fh5":
        return is_fh5_layer_group_candidate(path)
    if game_key in {"fm", "fm8"}:
        return name == "data" and path.parent.parent.name.lower() in {"layergroups", "liveries"}
    return False


def default_roots() -> list[Path]:
    roots: list[Path] = []
    for candidate in (
        Path("C:/XboxGames/GameSave"),
        Path("C:/XboxGames/GameSave/pgs"),
        Path(os.path.expandvars(r"%USERPROFILE%/Documents")),
        Path(os.path.expandvars(r"%USERPROFILE%/Downloads")),
        Path(os.path.expandvars(r"%USERPROFILE%/Desktop")),
    ):
        if candidate.exists():
            roots.append(candidate)
    return roots


def utc_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    except OSError:
        return ""


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()[:12]


def path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def sibling_hints(folder: Path) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    try:
        siblings = sorted(
            (item for item in folder.iterdir() if item.is_file() and item.name.lower() not in SOURCE_NAMES),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return hints
    for item in siblings[:8]:
        try:
            stat = item.stat()
        except OSError:
            continue
        hints.append(
            {
                "name": item.name,
                "size": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            }
        )
    return hints


def decode_summary(path: Path, expected_layers: int | None, inspect_locked: bool, game: str) -> dict[str, Any]:
    try:
        decoded = decode_forza_source(path, allow_locked=inspect_locked, game=game)
    except DecodeError as exc:
        message = str(exc)
        return {
            "ok": False,
            "locked_or_guarded": "privacy guard" in message.lower(),
            "error": message,
        }
    report = decoded.report
    layers = len(decoded.layers)
    summary: dict[str, Any] = {
        "ok": True,
        "kind": decoded.source_kind,
        "target_game": report.get("target_game"),
        "decoded_layers": layers,
        "expected_layer_match": expected_layers is not None and layers == expected_layers,
        "warnings": report.get("warnings", []),
        "identity_warnings": report.get("identity_warnings", []),
    }
    if "root_expected_children" in report:
        summary["root_expected_children"] = report.get("root_expected_children")
    if "section_counts" in report:
        section_counts = report.get("section_counts") or {}
        summary["non_empty_sections"] = {
            key: value for key, value in section_counts.items() if int(value or 0) > 0
        }
    return summary


def describe_source(path: Path, expected_layers: int | None, inspect: bool, inspect_locked: bool, game: str = "fh6") -> dict[str, Any]:
    try:
        stat = path.stat()
        size = stat.st_size
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        sort_mtime = stat.st_mtime
    except OSError:
        size = 0
        modified = ""
        sort_mtime = 0.0
    name = path.name.lower()
    if name == "c_group" or name.endswith(".c_group") or (name == "data" and path.parent.parent.name.lower() == "layergroups"):
        kind = "cgroup"
    else:
        kind = "clivery"
    entry: dict[str, Any] = {
        "kind": kind,
        "file": str(path),
        "folder": str(path.parent),
        "folder_name": path.parent.name,
        "parent_folder": path.parent.parent.name if path.parent.parent != path.parent else "",
        "file_size": size,
        "modified_utc": modified,
        "fingerprint": file_fingerprint(path),
        "sibling_hints": sibling_hints(path.parent),
        "_sort_mtime": sort_mtime,
    }
    if inspect:
        entry["decode"] = decode_summary(path, expected_layers, inspect_locked=inspect_locked, game=game)
    return entry


def discover_source_paths(root: Path, max_results: int, max_files: int, progress: bool, game: str = "fh6") -> list[Path]:
    candidates: list[Path] = []
    if root.is_file():
        return [root] if is_source_candidate(root, game) else []
    if not root.exists():
        return []
    scanned_files = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        if current != root:
            dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIR_NAMES]
        else:
            dirnames[:] = [name for name in dirnames if name.lower() not in {".git", ".venv", "venv", "__pycache__"}]
        scanned_files += len(filenames)
        for filename in filenames:
            candidate = current / filename
            if not is_source_candidate(candidate, game):
                continue
            candidates.append(candidate)
            if progress:
                print(f"found candidate {len(candidates)}: {candidate}", file=sys.stderr, flush=True)
            if len(candidates) >= max_results:
                return candidates
        if scanned_files >= max_files:
            if progress:
                print(f"stopped discovery after scanning {scanned_files} files", file=sys.stderr, flush=True)
            break
    return candidates


def find_sources(
    root: Path,
    max_results: int,
    max_files: int,
    expected_layers: int | None,
    inspect: bool,
    inspect_locked: bool,
    stop_on_match: bool,
    progress: bool,
    game: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    candidates = discover_source_paths(root, max_results=max_results, max_files=max_files, progress=progress, game=game)
    candidates.sort(key=lambda item: (path_mtime(item), str(item)), reverse=True)
    for index, path in enumerate(candidates[:max_results], 1):
        if progress:
            print(f"inspecting {index}/{len(candidates[:max_results])}: {path}", file=sys.stderr, flush=True)
        entry = describe_source(path, expected_layers, inspect, inspect_locked, game=game)
        results.append(entry)
        decode = entry.get("decode") or {}
        if stop_on_match and decode.get("expected_layer_match"):
            if progress:
                print(f"matched expected layer count at {path}", file=sys.stderr, flush=True)
            break
    return results


def compact_size(size: int) -> str:
    value = float(size)
    for suffix in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or suffix == "GB":
            return f"{value:.1f} {suffix}" if suffix != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{size} B"


def text_report(payload: dict[str, Any]) -> str:
    has_match = any((source.get("decode") or {}).get("expected_layer_match") for source in payload["sources"])
    lines = [
        f"Found {payload['count']} Forza source candidate(s), newest first.",
        "Pick the entry whose decoded layer count matches the visible in-game count and whose modified time matches your last save.",
        "",
    ]
    expected = payload.get("expected_layers")
    if expected is not None:
        lines.append(f"Expected visible layer count: {expected}")
        if payload["count"] and not has_match:
            lines.append("No exact MATCH was found in the inspected candidates.")
            lines.append("If you just saved in game, narrow the scan to the save/export folder or rerun with a higher --max-results.")
        lines.append("")
    for source in payload["sources"]:
        decode = source.get("decode") or {}
        layer_text = "layers=?"
        marker = "     "
        if decode.get("ok"):
            layers = decode.get("decoded_layers")
            layer_text = f"layers={layers}"
            if decode.get("expected_layer_match"):
                marker = "MATCH"
        elif decode.get("locked_or_guarded"):
            layer_text = "locked/guarded"
        elif decode.get("error"):
            layer_text = "decode failed"
        parent = source.get("parent_folder") or "-"
        folder = source.get("folder_name") or "-"
        lines.append(
            f"#{source['index']:03d} {marker} {source['kind']:<7} {layer_text:<16} "
            f"modified={source.get('modified_utc') or '?'} size={compact_size(int(source.get('file_size') or 0))} "
            f"id={source.get('fingerprint') or '-'} parent={parent} folder={folder}"
        )
        if decode.get("root_expected_children") is not None:
            lines.append(f"      root children: {decode['root_expected_children']}")
        if decode.get("non_empty_sections"):
            sections = ", ".join(f"{key}:{value}" for key, value in decode["non_empty_sections"].items())
            lines.append(f"      sections: {sections}")
        if decode.get("error"):
            lines.append(f"      note: {decode['error']}")
        hints = source.get("sibling_hints") or []
        if hints:
            hint_text = ", ".join(f"{item['name']} ({item['modified_utc']})" for item in hints[:3])
            lines.append(f"      nearby files: {hint_text}")
        lines.append(f"      file: {source['file']}")
        lines.append(
            "      export: python -m tools.cgroup.export_forza_source_to_kfps_json "
            f"--game {payload.get('game') or 'fh6'} "
            f"\"{source['file']}\" \"runtime/cgroup-prototype/export-{source['index']:03d}.json\""
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, help="Folders/files to scan. Defaults to common Windows roots.")
    parser.add_argument("--max-results", type=int, default=80)
    parser.add_argument("--max-files", type=int, default=250_000, help="Safety cap for files scanned per root")
    parser.add_argument("--expected-layers", type=int, help="Visible in-game layer count to mark matching candidates")
    parser.add_argument("--no-inspect", action="store_true", help="Skip decode summaries and only list file metadata")
    parser.add_argument(
        "--keep-scanning-after-match",
        action="store_true",
        help="Do not stop after the first decoded candidate matching --expected-layers",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print progress while scanning")
    parser.add_argument(
        "--game",
        default="fh6",
        choices=("fh6", "fh5", "fm", "fm8"),
        help="Source game shape-word mapping to use while inspecting candidates.",
    )
    parser.add_argument(
        "--inspect-locked",
        action="store_true",
        help="Development-only: inspect locked/guarded artifacts while scanning. Do not use for public export workflows.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout instead of the readable candidate list")
    args = parser.parse_args()

    roots = args.roots or default_roots()
    results: list[dict[str, Any]] = []
    stop_on_match = args.expected_layers is not None and not args.keep_scanning_after_match
    progress = not args.quiet and not args.json
    for root in roots:
        if progress:
            print(f"scanning root: {root}", file=sys.stderr, flush=True)
        results.extend(
            find_sources(
                root,
                max_results=args.max_results - len(results),
                max_files=args.max_files,
                expected_layers=args.expected_layers,
                inspect=not args.no_inspect,
                inspect_locked=args.inspect_locked,
                stop_on_match=stop_on_match,
                progress=progress,
                game=args.game,
            )
        )
        if len(results) >= args.max_results:
            break
        if stop_on_match and any((item.get("decode") or {}).get("expected_layer_match") for item in results):
            break
    results.sort(key=lambda item: (item.get("_sort_mtime") or 0.0, item.get("file") or ""), reverse=True)
    results = results[: args.max_results]
    for index, item in enumerate(results, 1):
        item["index"] = index
        item.pop("_sort_mtime", None)

    payload = {
        "roots": [str(root) for root in roots],
        "game": args.game,
        "expected_layers": args.expected_layers,
        "inspected": not args.no_inspect,
        "count": len(results),
        "sources": results,
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text if args.json else text_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
