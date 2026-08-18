#!/usr/bin/env python3
"""Serve the local KFPS Fabric editor."""

from __future__ import annotations

import http.server
import argparse
import hmac
import io
import json
import math
import os
import re
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry
from json_preview_renderer import render_json_preview as shared_render_json_preview
from kfps_shapes import resolve_full_type_resource, resolve_vinyl_resource, shape_word_resource_map

EDITOR = ROOT / "tools" / "fabric-editor" / "index.html"
STARTUP_HELP_MARKER = ROOT / "runtime" / "fabric-editor" / "startup-help-confirmed.json"
EDITOR_PREFS_MARKER = ROOT / "runtime" / "fabric-editor" / "preferences.json"
EDITOR_AUTOSAVE_MARKER = ROOT / "runtime" / "fabric-editor" / "autosave.json"
EDITOR_SERVER_MARKER = ROOT / "runtime" / "fabric-editor" / "server.json"
EDITOR_OUTPUT_CHANGE_MARKER = ROOT / "runtime" / "fabric-editor" / "editor-output-change.json"
EDITOR_PROJECT_CHANGE_MARKER = ROOT / "runtime" / "fabric-editor" / "project-change.json"
EDITOR_THEME_ROOT = ROOT / "runtime" / "fabric-editor" / "themes"
EDITOR_HEALTH_API = "/api/fabric-editor/health"
STARTUP_HELP_API = "/api/fabric-editor/startup-help-confirmed"
EDITOR_PREFS_API = "/api/fabric-editor/preferences"
EDITOR_THEMES_API = "/api/fabric-editor/themes"
EDITOR_AUTOSAVE_API = "/api/fabric-editor/autosave"
JSON_BROWSER_API = "/api/fabric-editor/json-browser"
JSON_FILE_API = "/api/fabric-editor/json-file"
JSON_PREVIEW_API = "/api/fabric-editor/json-preview"
EDITOR_EXPORT_API = "/api/fabric-editor/save-editor-json"
PROJECT_BROWSER_API = "/api/fabric-editor/project-browser"
PROJECT_FILE_API = "/api/fabric-editor/project-file"
PROJECT_SAVE_API = "/api/fabric-editor/save-project"
PROJECT_OPEN_FOLDER_API = "/api/fabric-editor/open-project-folder"
EDITOR_MUTATION_HEADER = "X-KFPS-Editor-Session"
EDITOR_MUTATION_APIS = {
    STARTUP_HELP_API,
    EDITOR_PREFS_API,
    EDITOR_THEMES_API,
    EDITOR_AUTOSAVE_API,
    EDITOR_EXPORT_API,
    PROJECT_SAVE_API,
    PROJECT_OPEN_FOLDER_API,
}
GENERATED_ROOT = ROOT / "imgs" / "generated"
EDITOR_JSON_ROOT = ROOT / "imgs" / "editor"
EXPORTED_JSON_ROOT = ROOT / "imgs" / "exported"
EDITOR_PROJECT_ROOT = ROOT / "runtime" / "fabric-editor" / "projects"
VINYL_RESOURCE_ROOT = ROOT / "tools" / "fabric-editor" / "Resources" / "Vinyls"
SHAPE_WORDS_PATH = ROOT / "tools" / "fabric-editor" / "shape-words.json"
PREVIEW_MAX = 420
VINYL_RESOURCE_CACHE: dict[tuple[str, int], list[list[tuple[float, float]]]] = {}


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _record_desktop_change(marker: Path, target: Path) -> None:
    try:
        _write_json_atomic(
            marker,
            {"path": str(target.resolve()), "changed_at_ns": time.time_ns()},
        )
    except OSError:
        # The editor save remains valid even if the desktop notification fails.
        pass


def _is_allowed_static_path(raw_path: str) -> bool:
    decoded = unquote(str(raw_path or "")).replace("\\", "/")
    candidate = (ROOT / decoded.lstrip("/")).resolve()
    editor_root = (ROOT / "tools" / "fabric-editor").resolve()
    if candidate.is_relative_to(editor_root):
        return True
    return candidate == (ROOT / "assets" / "kfps-logo.ico").resolve()


def _resolve_full_type_resource(type_code: int) -> tuple[str, int] | None:
    return resolve_full_type_resource(type_code)


def _safe_relpath(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _resolve_browser_id(path_id: str) -> Path:
    if not path_id or "\x00" in path_id:
        raise ValueError("missing JSON id")
    candidate = (ROOT / path_id).resolve()
    allowed_roots = [GENERATED_ROOT.resolve(), EDITOR_JSON_ROOT.resolve(), EXPORTED_JSON_ROOT.resolve()]
    if not any(candidate.is_relative_to(root) for root in allowed_roots):
        raise ValueError("JSON path is outside the editable browser roots")
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise ValueError("JSON file was not found")
    return candidate


def _resolve_project_id(path_id: str) -> Path:
    if not path_id or "\x00" in path_id:
        raise ValueError("missing project id")
    candidate = (EDITOR_PROJECT_ROOT / path_id).resolve()
    if not candidate.is_relative_to(EDITOR_PROJECT_ROOT.resolve()):
        raise ValueError("project path is outside the internal project folder")
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise ValueError("project file was not found")
    return candidate


def _clean_filename_base(name: str, fallback: str = "vinyl") -> str:
    base = str(name or fallback).replace("\\", "/").split("/")[-1].strip()
    base = re.sub(r"\.json$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\.(fabric-project|fabric-export|normal-import|fh6-import)$", "", base, flags=re.IGNORECASE)
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    base = re.sub(r"\s+", " ", base).strip(" .")
    return base or fallback


def _theme_id_from_name(name: str) -> str:
    base = _clean_filename_base(name, "custom-theme").lower()
    base = re.sub(r"[^a-z0-9._-]+", "-", base).strip(".-_")
    if base in {"pastel", "dark"}:
        base = f"{base}-custom"
    return base or "custom-theme"


def _theme_entries() -> list[dict]:
    entries = [
        {"id": "pastel", "name": "Signature Pink", "builtin": True, "values": {}},
        {"id": "dark", "name": "Dark", "builtin": True, "values": {}},
    ]
    if not EDITOR_THEME_ROOT.exists():
        return entries
    for path in sorted(EDITOR_THEME_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            theme_id = str(payload.get("id") or path.stem)
            if not theme_id or theme_id in {"pastel", "dark"}:
                continue
            values = payload.get("values")
            if not isinstance(values, dict):
                continue
            entries.append({
                "id": theme_id,
                "name": str(payload.get("name") or theme_id),
                "builtin": False,
                "values": {str(key): str(value) for key, value in values.items()},
            })
        except Exception:
            continue
    return entries


def _theme_exists(theme_id: str) -> bool:
    if theme_id in {"pastel", "dark"}:
        return True
    if not theme_id or "\x00" in theme_id:
        return False
    candidate = (EDITOR_THEME_ROOT / f"{theme_id}.json").resolve()
    return candidate.is_relative_to(EDITOR_THEME_ROOT.resolve()) and candidate.is_file()


def _unique_theme_id(base_id: str) -> str:
    theme_id = base_id
    for index in range(2, 10000):
        target = (EDITOR_THEME_ROOT / f"{theme_id}.json").resolve()
        if target.is_relative_to(EDITOR_THEME_ROOT.resolve()) and not target.exists():
            return theme_id
        theme_id = f"{base_id}-{index}"
    return f"{base_id}-{int(time.time())}"


def _unique_json_path(folder: Path, base_name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    clean = _clean_filename_base(base_name)
    candidate = folder / f"{clean}.fh6-import.json"
    if not candidate.exists():
        return candidate
    for index in range(2, 10000):
        candidate = folder / f"{clean}-{index}.fh6-import.json"
        if not candidate.exists():
            return candidate
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return folder / f"{clean}-{stamp}.fh6-import.json"


def _unique_editor_export_path(base_name: str) -> Path:
    clean = _clean_filename_base(base_name)
    return _unique_json_path(EDITOR_JSON_ROOT / clean, clean)


def _project_path(base_name: str) -> Path:
    clean = _clean_filename_base(base_name, "project")
    EDITOR_PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    return EDITOR_PROJECT_ROOT / f"{clean}.fabric-project.json"


def _is_internal_json(path: Path) -> bool:
    lower = path.name.lower()
    internal_tokens = (
        ".v2.report.",
        ".v2.settings.",
        ".v2.preprocess.",
        ".v2.run_metadata.",
        ".fh6.",
        ".probe.",
    )
    return any(token in lower for token in internal_tokens)


def _looks_like_final_json(path: Path) -> bool:
    if path.parent.name.lower() == "finals":
        return True
    lower = path.name.lower()
    return lower.endswith("v2.json") or ".final" in lower


def _shape_count(path: Path) -> int:
    checkpoint_match = re.search(r"\.(\d+)v2\.json$", path.name.lower())
    if checkpoint_match:
        return int(checkpoint_match.group(1))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    return len(shapes) if isinstance(shapes, list) else 0


def _preview_url(path: Path) -> str:
    return f"{JSON_PREVIEW_API}?id={quote(_safe_relpath(path))}"


def _json_entry(path: Path, source: str) -> dict:
    stat = path.stat()
    count = _shape_count(path)
    return {
        "id": _safe_relpath(path),
        "name": path.name,
        "source": source,
        "layers": count,
        "mtime": stat.st_mtime,
        "mtime_label": f"{stat.st_mtime:.0f}",
        "preview_url": _preview_url(path),
    }


def _generated_groups() -> list[dict]:
    groups: dict[str, dict] = {}
    if not GENERATED_ROOT.exists():
        return []
    for path in GENERATED_ROOT.rglob("*.json"):
        if _is_internal_json(path) or not _looks_like_final_json(path):
            continue
        try:
            rel = path.relative_to(GENERATED_ROOT)
        except ValueError:
            continue
        if not rel.parts:
            continue
        run_key = rel.parts[0]
        entry = _json_entry(path, "generated")
        group = groups.setdefault(run_key, {
            "key": run_key,
            "title": run_key,
            "source": "generated",
            "mtime": 0.0,
            "entries": [],
        })
        group["entries"].append(entry)
        group["mtime"] = max(group["mtime"], entry["mtime"])
    for group in groups.values():
        group["entries"].sort(key=lambda item: (item["layers"], item["mtime"], item["name"]), reverse=True)
        group["count"] = len(group["entries"])
        group["max_layers"] = max((item["layers"] for item in group["entries"]), default=0)
    return sorted(groups.values(), key=lambda item: (item["mtime"], item["title"]), reverse=True)


def _single_file_groups(root: Path, source: str) -> list[dict]:
    groups = []
    if not root.exists():
        return groups
    for path in root.rglob("*.json"):
        if _is_internal_json(path):
            continue
        entry = _json_entry(path, source)
        rel_parent = path.parent.relative_to(root)
        folder = "" if str(rel_parent) == "." else rel_parent.as_posix()
        title = path.name if not folder else f"{folder}/{path.name}"
        groups.append({
            "key": entry["id"],
            "title": title,
            "source": source,
            "mtime": entry["mtime"],
            "count": 1,
            "max_layers": entry["layers"],
            "entries": [entry],
        })
    return sorted(groups, key=lambda item: (item["mtime"], item["title"]), reverse=True)


def _editor_groups() -> list[dict]:
    groups: dict[str, dict] = {}
    if not EDITOR_JSON_ROOT.exists():
        return []
    for path in EDITOR_JSON_ROOT.rglob("*.json"):
        if _is_internal_json(path):
            continue
        try:
            rel = path.relative_to(EDITOR_JSON_ROOT)
        except ValueError:
            continue
        run_key = rel.parts[0] if len(rel.parts) > 1 else path.stem
        entry = _json_entry(path, "editor")
        group = groups.setdefault(run_key, {
            "key": run_key,
            "title": run_key,
            "source": "editor",
            "mtime": 0.0,
            "entries": [],
        })
        group["entries"].append(entry)
        group["mtime"] = max(group["mtime"], entry["mtime"])
    for group in groups.values():
        group["entries"].sort(key=lambda item: (item["layers"], item["mtime"], item["name"]), reverse=True)
        group["count"] = len(group["entries"])
        group["max_layers"] = max((item["layers"] for item in group["entries"]), default=0)
    return sorted(groups.values(), key=lambda item: (item["mtime"], item["title"]), reverse=True)


def _project_entry(path: Path) -> dict:
    stat = path.stat()
    name = path.name
    title = re.sub(r"\.fabric-project\.json$", "", name, flags=re.IGNORECASE)
    layers = None
    try:
        with path.open("r", encoding="utf-8") as stream:
            prefix = stream.read(64 * 1024)
            count_match = re.search(r'"layer_count"\s*:\s*(\d+)', prefix)
            if count_match:
                layers = int(count_match.group(1))
            name_match = re.search(r'"name"\s*:\s*"([^"]+)"', prefix)
            if name_match:
                title = name_match.group(1)
            if layers is None:
                payload = json.loads(prefix + stream.read())
                shapes = payload.get("shapes") if isinstance(payload, dict) else None
                layers = len(shapes) if isinstance(shapes, list) else 0
                title = str(payload.get("name") or title) if isinstance(payload, dict) else title
    except Exception:
        layers = 0
    return {
        "id": path.relative_to(EDITOR_PROJECT_ROOT).as_posix(),
        "name": name,
        "title": title,
        "layers": int(layers or 0),
        "mtime": stat.st_mtime,
    }


def _project_entries() -> list[dict]:
    if not EDITOR_PROJECT_ROOT.exists():
        return []
    entries = []
    for path in EDITOR_PROJECT_ROOT.rglob("*.fabric-project.json"):
        try:
            entries.append(_project_entry(path))
        except Exception:
            continue
    return sorted(entries, key=lambda item: (item["mtime"], item["title"]), reverse=True)


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _read_stable_file_bytes(path: Path, checks: int = 2, delay: float = 0.035) -> bytes | None:
    previous_size = None
    for attempt in range(max(1, checks)):
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if size <= 0:
            return None
        if previous_size == size or attempt == checks - 1:
            try:
                data = path.read_bytes()
            except OSError:
                return None
            return data if len(data) == size else None
        previous_size = size
        time.sleep(delay)
    return None


def _tag_from_final_json(path: Path) -> str | None:
    name = path.name
    match = re.search(r"\.([A-Za-z0-9_-]+)v2\.json$", name)
    if match:
        return f"{match.group(1)}v2"
    match = re.search(r"\.([A-Za-z0-9_-]+)\.json$", name)
    return match.group(1) if match else None


def _existing_generated_preview(path: Path) -> Path | None:
    try:
        rel = path.relative_to(GENERATED_ROOT)
    except ValueError:
        return None
    if not rel.parts:
        return None
    run_dir = GENERATED_ROOT / rel.parts[0]
    previews = run_dir / "previews"
    candidates: list[Path] = [
        path.with_suffix(".png"),
        path.with_name(f"{path.stem}.png"),
        path.with_name(f"{path.stem}.preview.png"),
    ]
    tag = _tag_from_final_json(path)
    if previews.exists():
        if tag:
            candidates.extend(previews.glob(f"*.preview.{tag}.png"))
            candidates.extend(previews.glob(f"*{tag}*.png"))
        candidates.extend(previews.glob(f"*{path.stem}*.png"))
    valid = [candidate for candidate in candidates if candidate.exists() and candidate.is_file()]
    if not valid:
        return None
    return max(valid, key=lambda item: item.stat().st_mtime)


def _checkerboard(size: tuple[int, int]):
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGBA", size, (38, 38, 38, 255))
    draw = ImageDraw.Draw(image)
    tile = 16
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(58, 58, 58, 255))
    return image


def _color_tuple(value) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    values = list(value[:4])
    if len(values) == 3:
        values.append(255)
    try:
        nums = [float(item) for item in values]
    except (TypeError, ValueError):
        return None
    if all(0.0 <= item <= 1.0 for item in nums):
        nums = [item * 255.0 for item in nums]
    out = [max(0, min(255, int(round(item)))) for item in nums]
    return out[0], out[1], out[2], out[3]


def _compensated_ellipse_size(width: float, height: float) -> tuple[float, float]:
    major = max(width, height)
    minor = max(1.0, min(width, height))
    aspect = major / minor
    uniform_scale = 1.0
    if major >= 220:
        uniform_scale *= 0.985
    if major >= 300:
        uniform_scale *= 0.975
    major_axis_scale = 1.0
    if aspect >= 2.0:
        major_axis_scale *= 0.985
    if aspect >= 3.5:
        major_axis_scale *= 0.970
    if aspect >= 6.0:
        major_axis_scale *= 0.955
    if width >= height:
        return max(1.0, width * uniform_scale * major_axis_scale), max(1.0, height * uniform_scale)
    return max(1.0, width * uniform_scale), max(1.0, height * uniform_scale * major_axis_scale)


def _ellipse_points(cx: float, cy: float, radius_x: float, radius_y: float, rot_deg: float, steps: int = 48) -> list[tuple[float, float]]:
    # Legacy KFPS primitive types 8/16 store ellipse radii. Rectangle types
    # 1/2 use full dimensions and are handled separately by _rect_points.
    rx, ry = _compensated_ellipse_size(radius_x, radius_y)
    rot = math.radians(rot_deg)
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    points = []
    for step in range(steps):
        angle = math.tau * step / steps
        px = math.cos(angle) * rx
        py = math.sin(angle) * ry
        points.append((cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r))
    return points


def _rect_points(cx: float, cy: float, width: float, height: float, rot_deg: float) -> list[tuple[float, float]]:
    hw = width / 2.0
    hh = height / 2.0
    rot = math.radians(rot_deg)
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    points = []
    for px, py in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        points.append((cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r))
    return points


def _shape_word_resource_map() -> dict[int, tuple[str, int] | None]:
    return shape_word_resource_map(SHAPE_WORDS_PATH)


def _resolve_vinyl_resource(type_code: int, shape: dict | None = None) -> tuple[str, int] | None:
    return resolve_vinyl_resource(type_code, shape, SHAPE_WORDS_PATH)


def _resource_triangles(family: str, index: int) -> list[list[tuple[float, float]]] | None:
    key = (family, int(index))
    if key in VINYL_RESOURCE_CACHE:
        return VINYL_RESOURCE_CACHE[key]
    path = VINYL_RESOURCE_ROOT / family / str(index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    vertices = payload.get("Vertices") or []
    indices = payload.get("Indices") or []
    triangles = []
    for pos in range(0, len(indices) - 2, 3):
        tri = []
        for raw_index in indices[pos : pos + 3]:
            try:
                vertex = vertices[int(raw_index)]
                tri.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
            except (TypeError, ValueError, IndexError, AttributeError):
                break
        if len(tri) == 3:
            triangles.append(tri)
    if not triangles:
        points = []
        for vertex in vertices:
            try:
                points.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(points) >= 3:
            triangles = [points]
    if not triangles:
        return None
    VINYL_RESOURCE_CACHE[key] = triangles
    return triangles


def _fallback_triangles(word: int) -> list[list[tuple[float, float]]]:
    if (int(word) & 0xFFFF) == 0x65:
        return [[(-64.0, -64.0), (64.0, -64.0), (64.0, 64.0), (-64.0, 64.0)]]
    return [[(math.cos(math.tau * step / 32) * 64.0, math.sin(math.tau * step / 32) * 64.0) for step in range(32)]]


def _transform_resource_polygon(points: list[tuple[float, float]], data: list) -> list[tuple[float, float]]:
    x = float(data[0]) if len(data) > 0 else 0.0
    y = float(data[1]) if len(data) > 1 else 0.0
    sx = float(data[2]) if len(data) > 2 else 1.0
    sy = float(data[3]) if len(data) > 3 else 1.0
    rot = math.radians(float(data[4]) if len(data) > 4 else 0.0)
    skew = float(data[5]) if len(data) > 5 else 0.0
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    transformed = []
    for px, py in points:
        lx = float(px) * sx
        ly = float(py) * sy
        if skew:
            lx += float(py) * sy * skew
        transformed.append((x + lx * cos_r - ly * sin_r, y + lx * sin_r + ly * cos_r))
    return transformed


def _render_polygons(polygons: list[dict], max_size: int = PREVIEW_MAX) -> bytes | None:
    from PIL import Image, ImageDraw

    all_points = [point for item in polygons for poly in item["polygons"] for point in poly]
    if not all_points:
        return None
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    padding = max(12.0, min(80.0, span * 0.05))
    world_w = max(1.0, (max_x - min_x) + padding * 2.0)
    world_h = max(1.0, (max_y - min_y) + padding * 2.0)
    scale = min(float(max_size) / max(world_w, world_h), 4.0)
    width = max(1, int(round(world_w * scale)))
    height = max(1, int(round(world_h * scale)))

    def to_canvas(point: tuple[float, float]) -> tuple[float, float]:
        return ((point[0] - min_x + padding) * scale, (max_y - point[1] + padding) * scale)

    image = _checkerboard((width, height))
    for item in polygons:
        color = item["color"]
        if color[3] <= 0:
            continue
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer, "RGBA")
        for poly in item["polygons"]:
            points = [to_canvas(point) for point in poly]
            if len(points) >= 3:
                draw.polygon(points, fill=color)
        image = Image.alpha_composite(image, layer)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _render_primitive_preview(path: Path) -> bytes | None:
    try:
        data = load_normalized_geometry(path)
        shapes = data["shapes"]
        background = shapes[0]
    except Exception:
        return None
    polygons = []
    for shape in shapes[1:]:
        color = _color_tuple(shape.get("color"))
        if not color or color[3] <= 0:
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        try:
            x, y, width, height = [float(item) for item in data[:4]]
            rot = float(data[4]) if len(data) >= 5 else 0.0
        except (TypeError, ValueError):
            continue
        shape_type = int(shape.get("type", ROTATED_ELLIPSE))
        if shape_type in (RECTANGLE, ROTATED_RECTANGLE):
            poly = _rect_points(x, -y, abs(width), abs(height), -rot)
        else:
            poly = _ellipse_points(x, -y, abs(width), abs(height), -rot)
        polygons.append({"polygons": [poly], "color": color})
    if polygons:
        return _render_polygons(polygons)
    color = _color_tuple(background.get("color"))
    if color and color[3] > 0:
        return _render_polygons([{"polygons": [[(-1, -1), (1, -1), (1, 1), (-1, 1)]], "color": color}])
    return None


def _render_typecode_preview(path: Path) -> bytes | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list):
        return None
    polygons = []
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        color = _color_tuple(shape.get("color"))
        if not color or color[3] <= 0:
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        try:
            [float(item) for item in data[:4]]
        except (TypeError, ValueError):
            continue
        type_code = int(shape.get("type", ROTATED_ELLIPSE))
        if type_code <= 1000000:
            continue
        word = int(shape.get("type_word", type_code & 0xFFFF)) & 0xFFFF
        resource = _resolve_vinyl_resource(type_code, shape)
        triangles = _resource_triangles(*resource) if resource else None
        if not triangles:
            triangles = _fallback_triangles(word)
        transformed = [_transform_resource_polygon(poly, data) for poly in triangles]
        if transformed:
            polygons.append({"polygons": transformed, "color": color})
    return _render_polygons(polygons) if polygons else None


def _render_json_preview(path: Path) -> bytes | None:
    return shared_render_json_preview(path, max_size=PREVIEW_MAX)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_png(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _mutation_authorized(self) -> bool:
        expected = str(getattr(self.server, "editor_session_token", ""))
        supplied = str(self.headers.get(EDITOR_MUTATION_HEADER) or "")
        if not expected or not hmac.compare_digest(supplied, expected):
            return False
        port = int(self.server.server_address[1])
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if str(self.headers.get("Host") or "").casefold() not in allowed_hosts:
            return False
        origin = str(self.headers.get("Origin") or "").rstrip("/").casefold()
        if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
            return False
        return str(self.headers.get("Sec-Fetch-Site") or "").casefold() not in {"cross-site"}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == EDITOR_HEALTH_API:
            self._send_json({
                "ok": True,
                "service": "kfps-fabric-editor",
                "pid": os.getpid(),
                "root": str(ROOT.resolve()),
            })
            return
        if parsed.path == STARTUP_HELP_API:
            self._send_json({
                "confirmed": STARTUP_HELP_MARKER.exists(),
                "marker": str(STARTUP_HELP_MARKER),
            })
            return
        if parsed.path == EDITOR_PREFS_API:
            payload = {}
            if EDITOR_PREFS_MARKER.exists():
                try:
                    payload = json.loads(EDITOR_PREFS_MARKER.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
            theme = str(payload.get("theme") or "")
            self._send_json({
                "theme": theme if _theme_exists(theme) else None,
                "marker": str(EDITOR_PREFS_MARKER),
            })
            return
        if parsed.path == EDITOR_THEMES_API:
            self._send_json({
                "themes": _theme_entries(),
                "folder": str(EDITOR_THEME_ROOT),
            })
            return
        if parsed.path == EDITOR_AUTOSAVE_API:
            if not EDITOR_AUTOSAVE_MARKER.exists():
                self._send_json({"exists": False, "marker": str(EDITOR_AUTOSAVE_MARKER)})
                return
            try:
                payload = json.loads(EDITOR_AUTOSAVE_MARKER.read_text(encoding="utf-8"))
            except Exception as err:
                self._send_json({"exists": False, "error": str(err), "marker": str(EDITOR_AUTOSAVE_MARKER)})
                return
            shapes = payload.get("shapes") if isinstance(payload, dict) else None
            self._send_json({
                "exists": isinstance(shapes, list),
                "payload": payload if isinstance(shapes, list) else None,
                "marker": str(EDITOR_AUTOSAVE_MARKER),
            })
            return
        if parsed.path == JSON_BROWSER_API:
            query = parse_qs(parsed.query)
            source = (query.get("source") or ["generated"])[0]
            if source == "editor":
                groups = _editor_groups()
            elif source in {"exported", "handmade"}:
                source = "exported"
                groups = _single_file_groups(EXPORTED_JSON_ROOT, "exported")
            else:
                source = "generated"
                groups = _generated_groups()
            self._send_json({
                "source": source,
                "groups": groups,
                "total_entries": sum(len(group["entries"]) for group in groups),
            })
            return
        if parsed.path == JSON_FILE_API:
            query = parse_qs(parsed.query)
            try:
                path = _resolve_browser_id((query.get("id") or [""])[0])
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "id": _safe_relpath(path),
                "name": path.name,
                "payload": payload,
            })
            return
        if parsed.path == PROJECT_BROWSER_API:
            entries = _project_entries()
            self._send_json({
                "entries": entries,
                "total_entries": len(entries),
                "folder": str(EDITOR_PROJECT_ROOT),
            })
            return
        if parsed.path == PROJECT_FILE_API:
            query = parse_qs(parsed.query)
            try:
                path = _resolve_project_id((query.get("id") or [""])[0])
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "id": path.relative_to(EDITOR_PROJECT_ROOT).as_posix(),
                "name": path.name,
                "payload": payload,
            })
            return
        if parsed.path == JSON_PREVIEW_API:
            query = parse_qs(parsed.query)
            try:
                path = _resolve_browser_id((query.get("id") or [""])[0])
                preview_path = _existing_generated_preview(path)
                body = _read_stable_file_bytes(preview_path) if preview_path else None
                if not body:
                    body = _render_json_preview(path)
                if not body:
                    raise ValueError("JSON preview could not be rendered")
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_png(body)
            return
        if not _is_allowed_static_path(parsed.path):
            self._send_json({"error": "not found"}, status=404)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in EDITOR_MUTATION_APIS and not self._mutation_authorized():
            self._send_json(
                {"error": "editor session authorization failed"},
                status=403,
            )
            return
        if parsed.path == STARTUP_HELP_API:
            _write_json_atomic(STARTUP_HELP_MARKER, {"confirmed": True})
            self._send_json({
                "confirmed": True,
                "marker": str(STARTUP_HELP_MARKER),
            })
            return
        if parsed.path == EDITOR_PREFS_API:
            try:
                length = int(self.headers.get("Content-Length") or "0")
                data = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
                theme = str(data.get("theme") or "")
                if not _theme_exists(theme):
                    raise ValueError("invalid editor theme")
                _write_json_atomic(EDITOR_PREFS_MARKER, {"theme": theme})
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({"ok": True, "theme": theme, "marker": str(EDITOR_PREFS_MARKER)})
            return
        if parsed.path == EDITOR_THEMES_API:
            try:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0 or length > 256 * 1024:
                    raise ValueError("invalid theme payload size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                name = str(data.get("name") or "Custom Theme").strip() or "Custom Theme"
                values = data.get("values")
                if not isinstance(values, dict) or not values:
                    raise ValueError("theme values must be a non-empty object")
                EDITOR_THEME_ROOT.mkdir(parents=True, exist_ok=True)
                theme_id = _unique_theme_id(_theme_id_from_name(str(data.get("id") or name)))
                target = EDITOR_THEME_ROOT / f"{theme_id}.json"
                payload = {
                    "format": "kfps_fabric_editor_theme_v1",
                    "id": theme_id,
                    "name": name,
                    "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "values": {str(key): str(value) for key, value in values.items()},
                }
                _write_json_atomic(target, payload)
                _write_json_atomic(EDITOR_PREFS_MARKER, {"theme": theme_id})
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "ok": True,
                "theme": payload,
                "path": str(target),
            })
            return
        if parsed.path == EDITOR_AUTOSAVE_API:
            try:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0 or length > 25 * 1024 * 1024:
                    raise ValueError("invalid autosave size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if data.get("action") == "clear":
                    if EDITOR_AUTOSAVE_MARKER.exists():
                        EDITOR_AUTOSAVE_MARKER.unlink()
                    self._send_json({"ok": True, "cleared": True, "marker": str(EDITOR_AUTOSAVE_MARKER)})
                    return
                shapes = data.get("shapes")
                if not isinstance(shapes, list):
                    raise ValueError("autosave payload must contain a shapes list")
                _write_json_atomic(EDITOR_AUTOSAVE_MARKER, data)
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({"ok": True, "marker": str(EDITOR_AUTOSAVE_MARKER)})
            return
        if parsed.path == EDITOR_EXPORT_API:
            try:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0 or length > 20 * 1024 * 1024:
                    raise ValueError("invalid editor export size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                payload = data.get("payload")
                if not isinstance(payload, dict) or not isinstance(payload.get("shapes"), list):
                    raise ValueError("editor export payload must contain a shapes list")
                target = _unique_editor_export_path(str(data.get("name") or "vinyl"))
                _write_json_atomic(target, payload)
                _record_desktop_change(EDITOR_OUTPUT_CHANGE_MARKER, target)
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "ok": True,
                "id": _safe_relpath(target),
                "path": str(target),
                "name": target.name,
            })
            return
        if parsed.path == PROJECT_SAVE_API:
            try:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0 or length > 25 * 1024 * 1024:
                    raise ValueError("invalid project save size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                payload = data.get("payload")
                if not isinstance(payload, dict) or not isinstance(payload.get("shapes"), list):
                    raise ValueError("project payload must contain a shapes list")
                project_name = _clean_filename_base(str(data.get("name") or payload.get("name") or "project"), "project")
                payload["name"] = project_name
                payload["layer_count"] = len(payload["shapes"])
                target = _project_path(project_name)
                if target.exists() and not bool(data.get("overwrite")):
                    self._send_json(
                        {
                            "error": (
                                f'A project named "{project_name}" already exists. '
                                "Choose a different name or open it before using Save."
                            ),
                            "code": "project_exists",
                        },
                        status=409,
                    )
                    return
                _write_json_atomic(target, payload)
                _record_desktop_change(EDITOR_PROJECT_CHANGE_MARKER, target)
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "ok": True,
                "id": target.relative_to(EDITOR_PROJECT_ROOT).as_posix(),
                "path": str(target),
                "name": target.name,
                "title": project_name,
            })
            return
        if parsed.path == PROJECT_OPEN_FOLDER_API:
            try:
                _open_folder(EDITOR_PROJECT_ROOT)
            except Exception as err:
                self._send_json({"error": str(err)}, status=400)
                return
            self._send_json({
                "ok": True,
                "folder": str(EDITOR_PROJECT_ROOT),
            })
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class EditorServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.editor_session_token = secrets.token_urlsafe(32)
        super().__init__(*args, **kwargs)


def _write_server_marker(port: int, session_token: str) -> None:
    payload = {
        "service": "kfps-fabric-editor",
        "pid": os.getpid(),
        "port": int(port),
        "root": str(ROOT.resolve()),
        "session_token": str(session_token),
        "url": f"http://127.0.0.1:{port}/tools/fabric-editor/index.html",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json_atomic(EDITOR_SERVER_MARKER, payload)


def _remove_owned_server_marker() -> None:
    try:
        payload = json.loads(EDITOR_SERVER_MARKER.read_text(encoding="utf-8"))
        if int(payload.get("pid") or -1) == os.getpid():
            EDITOR_SERVER_MARKER.unlink(missing_ok=True)
    except Exception:
        pass


def _browser_app_candidates() -> list[Path]:
    if sys.platform != "win32":
        return []
    candidates: list[Path] = []
    for env_name, suffixes in (
        ("ProgramFiles", ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")),
        ("ProgramFiles(x86)", ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")),
        ("LocalAppData", ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")),
    ):
        root = os.environ.get(env_name)
        if not root:
            continue
        for suffix in suffixes:
            candidates.append(Path(root) / suffix)
    return candidates


def open_editor_window(url: str) -> None:
    """Open the editor with the user's default browser.

    The previous app-window path preferred Edge whenever it was installed. That
    looked cleaner, but it ignored the browser Windows is configured to use.
    """
    try:
        if webbrowser.open(url, new=1, autoraise=True):
            return
    except Exception:
        pass

    # Last-resort fallback for machines where the OS default browser handler is
    # broken. This may use Edge/Chrome, but only after the default browser fails.
    for browser in _browser_app_candidates():
        if not browser.exists():
            continue
        try:
            subprocess.Popen(
                [
                    str(browser),
                    f"--app={url}",
                    "--new-window",
                    "--start-maximized",
                    "--start-fullscreen",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            continue
    webbrowser.open(url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the KFPS Fabric editor.")
    parser.add_argument("--project-id", default="", help="Relative project id under runtime/fabric-editor/projects to load on startup.")
    parser.add_argument("--port", type=int, default=0, help="Local port to use. Zero chooses an available port.")
    parser.add_argument("--no-browser", action="store_true", help="Start the service without opening a browser window.")
    args = parser.parse_args()

    if not EDITOR.exists():
        print(f"Missing editor: {EDITOR}")
        return 1
    port = args.port if 0 < args.port < 65536 else find_port()
    with EditorServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/tools/fabric-editor/index.html"
        if args.project_id:
            url += f"?project={quote(args.project_id, safe='')}"
        url += f"#session={quote(httpd.editor_session_token, safe='')}"
        _write_server_marker(port, httpd.editor_session_token)
        print("KFPS Fabric editor")
        print(f"Serving: {ROOT}")
        print(f"Open:    {url}")
        if not args.no_browser:
            threading.Timer(0.35, lambda: open_editor_window(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            _remove_owned_server_marker()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
