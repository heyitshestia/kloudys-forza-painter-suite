#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image
import cv2

from detail_heatmap import apply_detail_guidance, build_detail_heatmap, heatmap_to_rgba
from version_info import get_version


ROOT = Path(__file__).resolve().parent
BUNDLED_WINDOWS_GENERATOR_GENESIS = ROOT / "KloudysGalateaGenesis.exe"
BUNDLED_WINDOWS_GENERATOR_V7 = ROOT / "KloudysGeneratorV7.exe"
BUNDLED_WINDOWS_GENERATOR_V6 = ROOT / "KloudysGeneratorV6.exe"
BUNDLED_WINDOWS_GENERATOR_V5 = ROOT / "KloudysGeneratorV5.exe"
BUNDLED_WINDOWS_GENERATOR = (
    BUNDLED_WINDOWS_GENERATOR_GENESIS
    if BUNDLED_WINDOWS_GENERATOR_GENESIS.exists()
    else (
        BUNDLED_WINDOWS_GENERATOR_V7
        if BUNDLED_WINDOWS_GENERATOR_V7.exists()
        else (BUNDLED_WINDOWS_GENERATOR_V6 if BUNDLED_WINDOWS_GENERATOR_V6.exists() else BUNDLED_WINDOWS_GENERATOR_V5)
    )
)
LOCAL_LINUX_GENERATOR_ENV = os.environ.get("KLOUDYS_LINUX_GENERATOR")
LOCAL_LINUX_GENERATOR = Path(LOCAL_LINUX_GENERATOR_ENV) if LOCAL_LINUX_GENERATOR_ENV else None
GENERATOR_BIN = (
    BUNDLED_WINDOWS_GENERATOR
    if os.name == "nt"
    else (LOCAL_LINUX_GENERATOR if LOCAL_LINUX_GENERATOR and LOCAL_LINUX_GENERATOR.is_file() else BUNDLED_WINDOWS_GENERATOR)
)
LINUX_LIBRARY_PATH = os.environ.get("KLOUDYS_LINUX_LIBRARY_PATH")
LD_LIBRARY_PATH = (
    f"{LINUX_LIBRARY_PATH}:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":")
    if LINUX_LIBRARY_PATH
    else os.environ.get("LD_LIBRARY_PATH", "")
)
DEFAULT_RESERVED_IMPORT_LAYERS = 0
FINALS_DIR_NAME = "finals"
CHECKPOINTS_DIR_NAME = "checkpoints"
REPORTS_DIR_NAME = "reports"
PREVIEWS_DIR_NAME = "previews"
VERSION_FILE = ROOT / "VERSION"
RECTANGLE = 1
ROTATED_RECTANGLE = 2
ELLIPSE = 8
ROTATED_ELLIPSE = 16


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Kloudy Finalize Checkpoints: build internal checkpoints, "
            "optionally prune low-contribution ellipse layers, and write manual-pick "
            "final JSON outputs for each usable checkpoint."
        )
    )
    parser.add_argument("image", help="Source image path")
    parser.add_argument("--settings", required=True, help="Base generator settings .ini")
    parser.add_argument("--out-dir", required=True, help="Output directory for this run")
    parser.add_argument(
        "--stop-file",
        default="",
        help="Optional stop-request marker path. If created during generation, V2 stops the raw generator and finalizes from existing checkpoints.",
    )
    parser.add_argument(
        "--target-shapes",
        type=int,
        default=0,
        help="Final drawable target. Defaults to stopAt from settings.",
    )
    parser.add_argument(
        "--reserved-import-layers",
        type=int,
        default=DEFAULT_RESERVED_IMPORT_LAYERS,
        help="Template layers reserved for importer helper layers. Default: 0.",
    )
    parser.add_argument(
        "--overshoot-ratio",
        type=float,
        default=1.0,
        help="Optional overshoot ratio before pruning. Default: 1.0 (disabled)",
    )
    parser.add_argument(
        "--overshoot-max-extra",
        type=int,
        default=0,
        help="Maximum extra shapes above target when overshoot is enabled. Default: 0",
    )
    parser.add_argument(
        "--checkpoint-step",
        type=int,
        default=250,
        help="Checkpoint interval used in the V2 temp settings. Default: 250",
    )
    parser.add_argument(
        "--live-preview-every",
        type=int,
        default=100,
        help=(
            "Overwrite the raw live preview this often during the internal build. "
            "This does not create extra final JSONs. Default: 100"
        ),
    )
    parser.add_argument(
        "--score-size",
        type=int,
        default=640,
        help="Maximum scoring resolution for candidate evaluation/pruning. Default: 640",
    )
    parser.add_argument(
        "--efficiency-tolerance",
        type=float,
        default=0.0,
        help=(
            "Pick the smallest shape count whose error is within this fraction of the "
            "best candidate. Default: 0.0 (disabled)"
        ),
    )
    parser.add_argument(
        "--enable-prune",
        action="store_true",
        help="Enable contribution-based cleanup/pruning. Disabled by default.",
    )
    parser.add_argument(
        "--keep-temp-settings",
        action="store_true",
        help="Keep the generated V2 temp settings file in the output directory.",
    )
    parser.add_argument(
        "--preprocess-mode",
        choices=("none", "luma_bands"),
        default="none",
        help="Optional preprocess mode to simplify the source before generation/scoring.",
    )
    parser.add_argument(
        "--detail-heatmap-mode",
        choices=("off", "auto"),
        default="off",
        help="Guide generation/final scoring with an automatic detail heatmap. Default: off",
    )
    parser.add_argument(
        "--detail-heatmap-strength",
        type=float,
        default=0.10,
        help="Strength of detail-guided source enhancement and scoring emphasis. Default: 0.10",
    )
    parser.add_argument(
        "--enable-repair",
        action="store_true",
        help="Enable the targeted local repair pass on the selected final candidate.",
    )
    parser.add_argument(
        "--repair-candidate-limit",
        type=int,
        default=4,
        help=(
            "Only run targeted repair on the best N scored checkpoints plus the latest checkpoint. "
            "Use 0 to repair every checkpoint. Default: 4"
        ),
    )
    parser.add_argument(
        "--preview-candidate-limit",
        type=int,
        default=0,
        help=(
            "Only render full final preview PNGs for the best N scored checkpoints plus the latest checkpoint. "
            "Use 0 to render every preview. JSON browser can still preview unrendered files on demand. Default: 0"
        ),
    )
    parser.add_argument(
        "--disable-refine",
        action="store_true",
        help="Deprecated alias. Keeps repair disabled.",
    )
    parser.add_argument(
        "--run-metadata",
        default="",
        help="Optional JSON metadata from the UI describing selected presets, overrides, and toggles.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Optional raw generator RNG seed. Default: 0, which keeps the generator's normal time-based seed.",
    )
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Skip raw generation and finalize existing checkpoints in --out-dir.",
    )
    return parser.parse_args()


def parse_ini(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_run_metadata(path: str) -> dict:
    if not path:
        return {}
    metadata_path = Path(path).expanduser()
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "metadata_path": str(metadata_path),
            "metadata_load_error": True,
        }
    if isinstance(payload, dict):
        payload.setdefault("metadata_path", str(metadata_path))
        return payload
    return {
        "metadata_path": str(metadata_path),
        "metadata_load_error": True,
    }


def sorted_mapping(value):
    if isinstance(value, dict):
        return {key: sorted_mapping(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [sorted_mapping(item) for item in value]
    return value


def text_file_value(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        ).strip()
    except Exception:
        return ""


def file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def app_build_info() -> dict:
    commit = git_output("rev-parse", "--short=8", "HEAD") or text_file_value(ROOT / "BUILD_COMMIT")
    return {
        "app_name": "Kloudy's FH6 Painter",
        "app_version": text_file_value(VERSION_FILE) or "unknown",
        "build_label": get_version(),
        "build_commit": commit,
        "metadata_schema": "kloudys_report_metadata_v2",
        "generator_wrapper": Path(__file__).name,
        "raw_generator": GENERATOR_BIN.name if GENERATOR_BIN else "",
        "raw_generator_sha256": file_sha256(GENERATOR_BIN) if GENERATOR_BIN else "",
    }


def build_save_points(target: int, stop_at: int, checkpoint_step: int) -> str:
    points = set()
    step = max(1, checkpoint_step)
    n = step
    while n < stop_at:
        points.add(n)
        n += step
    points.add(target)
    points.add(stop_at)
    return ",".join(str(n) for n in sorted(points))


def parse_save_points(value: str, stop_at: int) -> list[int]:
    points = []
    for part in re.split(r"[,;\s]+", str(value or "")):
        if not part.strip():
            continue
        try:
            point = int(part)
        except ValueError:
            continue
        if 0 < point <= stop_at:
            points.append(point)
    return sorted(set(points))


def parse_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def infer_save_every(points: list[int], fallback: int) -> int:
    if not points:
        return max(1, fallback)
    if len(points) == 1:
        return max(1, points[0])
    deltas = [b - a for a, b in zip(points, points[1:]) if b > a]
    if not deltas:
        return max(1, fallback)
    step = deltas[0]
    for delta in deltas[1:]:
        step = math.gcd(step, delta)
    return max(1, step)


def write_v2_settings(
    base_settings: dict[str, str],
    out_path: Path,
    target: int,
    stop_at: int,
    checkpoint_step: int,
    live_preview_every: int,
) -> None:
    values = dict(base_settings)
    values["description"] = f"V2 settings targeting {target} template layers"
    values.setdefault("shapeMode", "mixed_ellipses")
    values["stopAt"] = str(stop_at)
    preview_every = max(1, min(int(live_preview_every or checkpoint_step or 100), max(1, stop_at)))
    explicit_points = parse_save_points(values.get("saveAt", ""), stop_at)
    if explicit_points:
        explicit_points = sorted(set(explicit_points + [target, stop_at]))
        values["saveAt"] = ",".join(str(point) for point in explicit_points)
        values["saveEvery"] = str(preview_every)
        values["previewEvery"] = str(preview_every)
    else:
        values["saveAt"] = build_save_points(target, stop_at, checkpoint_step)
        values["saveEvery"] = str(preview_every)
        values["previewEvery"] = str(preview_every)

    ordered_keys = [
        "description",
        "detailMode",
        "maxPreviewSize",
        "maxResolution",
        "maxThreads",
        "mutatedSamples",
        "forceOpaqueShapes",
        "logoHardEdges",
        "posterizeLevels",
        "previewEvery",
        "randomSamples",
        "saveAt",
        "saveEvery",
        "shapeMode",
        "stopAt",
    ]
    lines = []
    seen = set()
    for key in ordered_keys:
        if key in values:
            lines.append(f"{key} = {values[key]}")
            seen.add(key)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key} = {value}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resize_source_for_generation(image_path: Path, max_resolution: int) -> np.ndarray:
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    max_dim = max(w, h)
    if max_resolution > 0 and max_dim > max_resolution:
        scale = max_resolution / float(max_dim)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        img = img.resize((nw, nh), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32)


def remove_alpha_fringe_noise(rgba: np.ndarray) -> tuple[np.ndarray, dict[str, int | float | bool]]:
    """Remove low-alpha junk from imperfect background removers.

    Background remover halos often leave thousands of almost-transparent pixels
    far away from the real art. The generator still treats those pixels as work:
    they create alpha edges, consume samples, and encourage faint spill shapes.
    This keeps normal anti-aliased edges near opaque art while dropping isolated
    low-alpha haze.
    """
    if rgba.ndim != 3 or rgba.shape[2] < 4:
        return rgba, {"enabled": False, "changed": False, "removed_pixels": 0}

    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.uint8)
    total = int(alpha.size)
    if total == 0 or int(np.min(alpha)) >= 250:
        return rgba, {"enabled": True, "changed": False, "removed_pixels": 0, "removed_fraction": 0.0}

    hard_drop = alpha <= 16
    core = alpha >= 96
    if np.any(core):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        near_core = cv2.dilate(core.astype(np.uint8), kernel, iterations=1).astype(bool)
        soft_haze = (alpha < 48) & ~near_core
        drop = hard_drop | soft_haze
    else:
        drop = hard_drop

    removed = int(np.count_nonzero(drop & (alpha > 0)))
    if removed <= 0:
        return rgba, {"enabled": True, "changed": False, "removed_pixels": 0, "removed_fraction": 0.0}

    cleaned = rgba.copy()
    cleaned[drop, 3] = 0.0
    cleaned[drop, :3] = 0.0
    return cleaned, {
        "enabled": True,
        "changed": True,
        "removed_pixels": removed,
        "removed_fraction": round(removed / float(max(1, total)), 6),
        "hard_threshold": 16,
        "soft_threshold": 48,
        "core_threshold": 96,
    }


def apply_preprocess(rgba: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return rgba

    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.uint8)
    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.uint8)

    if mode == "luma_bands":
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        l = lab[..., 0].astype(np.float32)
        levels = 64.0
        step = 256.0 / levels
        lq = np.floor(l / step) * step + step * 0.5
        blur = cv2.GaussianBlur(l, (0, 0), 1.1)
        gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        edge = np.sqrt(gx * gx + gy * gy)
        edge = np.clip((edge - 3.0) / 18.0, 0.0, 1.0)
        band_weight = 0.16 + edge * 0.34
        # Keep enough band structure for the shape generator, but retain more
        # source luminance in smooth gradients so luma prep does not posterize.
        l_out = lq * band_weight + l * (1.0 - band_weight)
        l_out = (l_out - 128.0) * 1.005 + 128.0
        lab[..., 0] = np.clip(l_out, 0, 255).astype(np.uint8)
        rgb_out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    else:
        raise ValueError(f"unsupported preprocess mode: {mode}")

    out = np.dstack([rgb_out, alpha]).astype(np.float32)
    return out


def apply_logo_hard_edges(rgba: np.ndarray, alpha_threshold: int = 96) -> np.ndarray:
    """Prepare transparent logo art for opaque vinyl shapes.

    Anti-aliased transparent PNG edges often store blended edge RGB. If those
    colors are imported as opaque FH shapes, they look like accidental
    translucency on a different car color. For logo art, snap visible alpha to
    opaque and borrow edge RGB from nearby solid pixels where possible.
    """
    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.uint8)
    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.uint8)
    visible = alpha >= int(alpha_threshold)
    soft_visible = visible & (alpha < 245)
    solid = alpha >= 245
    rgb_out = rgb.copy()
    if np.any(soft_visible) and np.any(solid):
        repair_mask = soft_visible.astype(np.uint8) * 255
        # Inpaint only the semi-transparent visible edge pixels from nearby
        # solid logo colors; transparent background remains transparent.
        rgb_out = cv2.inpaint(rgb_out, repair_mask, 3, cv2.INPAINT_TELEA)
    alpha_out = np.where(visible, 255, 0).astype(np.uint8)
    return np.dstack([rgb_out, alpha_out]).astype(np.float32)


def source_art_profile(rgba: np.ndarray) -> dict:
    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.float32)
    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.float32)
    visible = alpha > 16.0
    visible_count = int(np.count_nonzero(visible))
    total_pixels = int(alpha.size)
    alpha_coverage = visible_count / float(max(1, total_pixels))
    if visible_count == 0:
        return {
            "alpha_coverage": 0.0,
            "edge_density": 0.0,
            "luma_std": 0.0,
            "white_fraction": 0.0,
            "category": "empty_alpha",
            "recommended_shape_mode": "mixed_character_art",
            "recommended_luma_prep": "none",
            "recommendation": "No visible pixels were detected.",
        }

    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    luma_visible = luma[visible]
    alpha_visible = alpha[visible]
    alpha_norm = (alpha / 255.0).astype(np.float32)
    luma_masked = (luma * alpha_norm).astype(np.float32)
    gx = cv2.Sobel(luma_masked, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(luma_masked, cv2.CV_32F, 0, 1, ksize=3)
    agx = cv2.Sobel(alpha_norm, cv2.CV_32F, 1, 0, ksize=3)
    agy = cv2.Sobel(alpha_norm, cv2.CV_32F, 0, 1, ksize=3)
    edge = np.sqrt(gx * gx + gy * gy) + np.sqrt(agx * agx + agy * agy) * 255.0
    edge_density = float(np.count_nonzero(edge[visible] > 35.0) / float(max(1, visible_count)))
    luma_std = float(np.std(luma_visible))
    white_fraction = float(np.count_nonzero((luma_visible > 232.0) & (alpha_visible > 128.0)) / float(max(1, visible_count)))

    if alpha_coverage < 0.18 and white_fraction > 0.45:
        category = "sparse_white_line_art"
        recommended_shape_mode = "mixed_edge_bias"
        recommended_luma = "none"
        recommendation = "Sparse white transparent line art: use edge-biased shapes, enough layers, and usually leave Luma Prep off."
    elif edge_density >= 0.34 and luma_std >= 55.0:
        category = "flat_crisp_livery"
        recommended_shape_mode = "mixed_edge_bias"
        recommended_luma = "luma_bands"
        recommendation = "Flat crisp livery art: edge-biased shapes and Luma Prep usually preserve borders and broad color regions best."
    elif alpha_coverage < 0.70 and edge_density < 0.30 and luma_std < 65.0:
        category = "soft_gradient_character"
        recommended_shape_mode = "mixed_soft_detail"
        recommended_luma = "none"
        recommendation = "Soft transparent character art: soft-detail or smart-detail weighting without Luma Prep usually avoids posterized gradients, hard rectangle blocks, and over-smoothed hair."
    else:
        category = "general_art"
        recommended_shape_mode = "mixed_smart_detail"
        recommended_luma = "none"
        recommendation = "General art: smart-detail weighting without Luma Prep is the safer default; enable Luma Prep manually for flat logo/livery sources."

    return {
        "alpha_coverage": round(alpha_coverage, 4),
        "edge_density": round(edge_density, 4),
        "luma_std": round(luma_std, 4),
        "white_fraction": round(white_fraction, 4),
        "category": category,
        "recommended_shape_mode": recommended_shape_mode,
        "recommended_luma_prep": recommended_luma,
        "recommendation": recommendation,
    }


def downscale_rgba(arr: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = arr.shape[:2]
    if max_dim <= 0 or max(h, w) <= max_dim:
        return arr
    scale = max_dim / float(max(h, w))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")
    img = img.resize((nw, nh), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32)


def normalize_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "shapes" not in payload:
        raise ValueError(f"{path} is not a generator geometry JSON")
    return payload


def drawable_shapes(payload: dict) -> list[dict]:
    out = []
    for shape in payload.get("shapes", [])[1:]:
        color = shape.get("color", [0, 0, 0, 0])
        if len(color) < 4 or int(color[3]) <= 0:
            continue
        out.append(shape)
    return out


def shape_type_name(shape_type: int) -> str:
    if shape_type == RECTANGLE:
        return "rectangle"
    if shape_type == ROTATED_RECTANGLE:
        return "rotated_rectangle"
    if shape_type == ELLIPSE:
        return "ellipse"
    if shape_type == ROTATED_ELLIPSE:
        return "rotated_ellipse"
    return f"type_{shape_type}"


def shape_type_counts(shapes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for shape in shapes:
        name = shape_type_name(int(shape.get("type", ROTATED_ELLIPSE)))
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def background_shape(payload: dict) -> dict:
    shapes = payload.get("shapes", [])
    if not shapes:
        raise ValueError("geometry payload has no shapes")
    return shapes[0]


def canvas_size_from_payload(payload: dict) -> tuple[int, int]:
    bg = background_shape(payload)
    data = bg.get("data", [])
    if len(data) >= 4:
        return max(1, int(data[2])), max(1, int(data[3]))
    raise ValueError("background shape is missing canvas size")


def raw_checkpoint_number(path: Path, stem: str) -> int | None:
    core = path.stem
    if not core.startswith(f"{stem}."):
        return None
    tag = core[len(stem) + 1 :]
    if not tag.isdigit():
        return None
    return int(tag)


def collect_candidate_jsons(out_dir: Path, stem: str, max_checkpoint: int | None = None) -> list[Path]:
    paths = []
    for path in out_dir.glob(f"{stem}*.json"):
        name = path.name
        if ".v2." in name or ".fh6." in name or ".report." in name or re.search(r"\.\d+v2\.json$", name) or name.endswith(".v2.json"):
            continue
        checkpoint = raw_checkpoint_number(path, stem)
        if max_checkpoint is not None and checkpoint is not None and checkpoint > max_checkpoint:
            print(
                f"Found overflow-named checkpoint {name}: checkpoint {checkpoint} > requested raw stop {max_checkpoint}; "
                "Finalize Checkpoints will validate and cap it before writing import outputs.",
                flush=True,
            )
        paths.append(path)
    paths = sorted(set(paths), key=lambda path: candidate_json_sort_key(path, stem))
    final_path = out_dir / f"{stem}.json"
    if final_path in paths and max_checkpoint is not None and (out_dir / f"{stem}.{max_checkpoint}.json") in paths:
        print(
            f"Skipping duplicate final raw checkpoint {final_path.name}; "
            f"using {stem}.{max_checkpoint}.json for the same target instead.",
            flush=True,
        )
        paths = [path for path in paths if path != final_path]
    return paths


def drawable_count_from_payload(payload: dict) -> int:
    return len(drawable_shapes(payload))


def first_drawable_shapes(payload: dict, count: int) -> list[dict]:
    selected = []
    for shape in payload.get("shapes", [])[1:]:
        color = shape.get("color", [0, 0, 0, 0])
        if len(color) >= 4 and int(color[3]) > 0:
            selected.append(shape)
            if len(selected) >= count:
                break
    return selected


def synthesize_missing_checkpoints(out_dir: Path, stem: str, requested_points: list[int], max_checkpoint: int) -> None:
    requested = sorted({int(point) for point in requested_points if 0 < int(point) <= max_checkpoint})
    if not requested:
        return

    available: list[tuple[int, Path, dict]] = []
    for path in collect_candidate_jsons(out_dir, stem, max_checkpoint=max_checkpoint):
        try:
            payload = normalize_payload(path)
            count = drawable_count_from_payload(payload)
        except Exception as exc:
            print(f"Checkpoint repair skipped unreadable raw JSON {path.name}: {exc}", flush=True)
            continue
        if count > 0:
            available.append((count, path, payload))
    if not available:
        return
    available.sort(key=lambda item: (item[0], item[1].name.lower()))

    existing_by_number = {
        checkpoint: path
        for count, path, _payload in available
        if (checkpoint := raw_checkpoint_number(path, stem)) is not None
    }
    for point in requested:
        existing = existing_by_number.get(point)
        if existing is not None and existing.exists():
            continue
        source = next(((count, path, payload) for count, path, payload in available if count >= point), None)
        if source is None:
            continue
        source_count, source_path, source_payload = source
        selected_shapes = first_drawable_shapes(source_payload, point)
        if len(selected_shapes) < point:
            continue
        synthesized = dict(source_payload)
        synthesized["shapes"] = [background_shape(source_payload)] + selected_shapes
        dest = out_dir / f"{stem}.{point}.json"
        save_json(dest, synthesized)
        available.append((point, dest, synthesized))
        available.sort(key=lambda item: (item[0], item[1].name.lower()))
        existing_by_number[point] = dest
        print(
            f"Recovered missing internal checkpoint {point}: "
            f"trimmed {source_path.name} ({source_count} shapes) -> {dest.name}",
            flush=True,
        )


def candidate_json_sort_key(path: Path, stem: str) -> tuple[int, int, str]:
    checkpoint = raw_checkpoint_number(path, stem)
    if checkpoint is None:
        return (1, 0, path.name.lower())
    return (0, checkpoint, path.name.lower())


def scale_shape(shape: dict, sx: float, sy: float) -> dict:
    scaled = {
        "type": int(shape.get("type", ROTATED_ELLIPSE)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
    }
    data = list(shape.get("data", []))
    if len(data) < 4:
        raise ValueError("shape missing data")
    cx, cy, rx, ry = data[:4]
    rot = data[4] if len(data) >= 5 else 0
    scaled["data"] = [
        float(cx) * sx,
        float(cy) * sy,
        max(0.5, float(rx) * sx),
        max(0.5, float(ry) * sy),
        float(rot),
    ]
    return scaled


def target_has_alpha_boundary(target_rgba: np.ndarray) -> bool:
    if target_rgba.ndim < 3 or target_rgba.shape[2] < 4:
        return False
    alpha = target_rgba[..., 3]
    return bool(alpha.size and int(np.min(alpha)) < 250)


def build_importance_map(target_rgba: np.ndarray) -> np.ndarray:
    """Weight scoring toward edges, alpha cuts, saturated detail, and linework."""
    height, width = target_rgba.shape[:2]
    if height <= 0 or width <= 0:
        return np.ones((max(1, height), max(1, width)), dtype=np.float32)

    rgba = target_rgba.astype(np.float32)
    rgb = rgba[..., :3]
    alpha = np.clip(rgba[..., 3] / 255.0, 0.0, 1.0)
    luma = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0
    maxc = rgb.max(axis=2) / 255.0
    minc = rgb.min(axis=2) / 255.0
    saturation = maxc - minc

    gx = np.zeros_like(luma, dtype=np.float32)
    gy = np.zeros_like(luma, dtype=np.float32)
    gx[:, 1:] = np.abs(luma[:, 1:] - luma[:, :-1])
    gy[1:, :] = np.abs(luma[1:, :] - luma[:-1, :])
    edge = np.maximum(gx, gy)

    agx = np.zeros_like(alpha, dtype=np.float32)
    agy = np.zeros_like(alpha, dtype=np.float32)
    agx[:, 1:] = np.abs(alpha[:, 1:] - alpha[:, :-1])
    agy[1:, :] = np.abs(alpha[1:, :] - alpha[:-1, :])
    alpha_edge = np.maximum(agx, agy)

    linework = np.clip((0.48 - luma) / 0.48, 0.0, 1.0) * np.clip(saturation * 1.35, 0.0, 1.0) * alpha
    highlights = np.clip((luma - 0.78) / 0.22, 0.0, 1.0) * np.clip(saturation * 1.15, 0.0, 1.0) * alpha
    visible = np.where(alpha > 0.02, 1.0, 0.55).astype(np.float32)

    importance = (
        1.0
        + np.clip(edge * 9.0, 0.0, 2.6)
        + np.clip(alpha_edge * 7.5, 0.0, 2.8)
        + np.clip(saturation * 0.55, 0.0, 0.75) * alpha
        + linework * 1.35
        + highlights * 0.70
    ) * visible

    # Cheap dilation prevents one-pixel hair/eye edges from being pruned by
    # nearby average-color improvements.
    padded = np.pad(importance, 1, mode="edge")
    dilated = importance.copy()
    for dy in range(3):
        for dx in range(3):
            dilated = np.maximum(dilated, padded[dy : dy + height, dx : dx + width] * 0.92)
    return np.clip(dilated, 0.55, 5.25).astype(np.float32)


def canvas_edge_context(target_rgba: np.ndarray) -> dict | None:
    if not target_has_alpha_boundary(target_rgba):
        return None
    height, width = target_rgba.shape[:2]
    if height <= 0 or width <= 0:
        return None
    alpha = target_rgba[..., 3] if target_rgba.ndim >= 3 and target_rgba.shape[2] >= 4 else None
    if alpha is None:
        return None
    strip = max(2, min(12, int(round(min(height, width) * 0.01))))
    visible = alpha > 8
    return {
        "left": np.max(visible[:, :strip], axis=1),
        "right": np.max(visible[:, width - strip :], axis=1),
        "top": np.max(visible[:strip, :], axis=0),
        "bottom": np.max(visible[height - strip :, :], axis=0),
        "strip": strip,
    }


def edge_side_allows_overhang(
    edge_context: dict | None,
    side: str,
    span_start: float,
    span_end: float,
    length: int,
    min_visible_fraction: float = 0.08,
) -> bool:
    if not edge_context:
        return False
    edge = edge_context.get(side)
    if edge is None or length <= 0:
        return False
    start = max(0, min(length - 1, int(math.floor(span_start))))
    end = max(0, min(length - 1, int(math.ceil(span_end))))
    if end < start:
        return False
    span = edge[start : end + 1]
    if span.size == 0:
        return False
    return (float(np.count_nonzero(span)) / float(span.size)) >= min_visible_fraction


def raw_rotated_bbox(cx: float, cy: float, rx: float, ry: float, rot_deg: float) -> tuple[float, float, float, float]:
    theta = math.radians(rot_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    ex = math.sqrt((rx * rx * cos_t * cos_t) + (ry * ry * sin_t * sin_t))
    ey = math.sqrt((rx * rx * sin_t * sin_t) + (ry * ry * cos_t * cos_t))
    return cx - ex, cx + ex, cy - ey, cy + ey


def rotated_bbox(cx: float, cy: float, rx: float, ry: float, rot_deg: float, width: int, height: int) -> tuple[int, int, int, int]:
    raw_x0, raw_x1, raw_y0, raw_y1 = raw_rotated_bbox(cx, cy, rx, ry, rot_deg)
    x0 = max(0, int(math.floor(raw_x0 - 1)))
    x1 = min(width - 1, int(math.ceil(raw_x1 + 1)))
    y0 = max(0, int(math.floor(raw_y0 - 1)))
    y1 = min(height - 1, int(math.ceil(raw_y1 + 1)))
    return x0, x1, y0, y1


def rectangle_mask(shape: dict, width: int, height: int) -> tuple[tuple[int, int, int, int], np.ndarray]:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return (0, -1, 0, -1), np.zeros((0, 0), dtype=bool)
    cx, cy, w, h = [float(v) for v in data[:4]]
    rot_deg = float(data[4]) if len(data) >= 5 else 0.0
    rx = max(0.5, w * 0.5)
    ry = max(0.5, h * 0.5)
    x0, x1, y0, y1 = rotated_bbox(cx, cy, rx, ry, rot_deg, width, height)
    if x1 < x0 or y1 < y0:
        return (x0, x1, y0, y1), np.zeros((0, 0), dtype=bool)
    xs = np.arange(x0, x1 + 1, dtype=np.float32) + 0.5
    ys = np.arange(y0, y1 + 1, dtype=np.float32) + 0.5
    xx, yy = np.meshgrid(xs, ys)
    theta = math.radians(rot_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    dx = xx - cx
    dy = yy - cy
    xr = dx * cos_t + dy * sin_t
    yr = -dx * sin_t + dy * cos_t
    return (x0, x1, y0, y1), (np.abs(xr) <= rx) & (np.abs(yr) <= ry)


def ellipse_mask(shape: dict, width: int, height: int) -> tuple[tuple[int, int, int, int], np.ndarray]:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return (0, -1, 0, -1), np.zeros((0, 0), dtype=bool)
    cx, cy, rx, ry = [float(v) for v in data[:4]]
    rot_deg = float(data[4]) if len(data) >= 5 else 0.0
    rx, ry = compensated_ellipse_size(rx, ry)
    x0, x1, y0, y1 = rotated_bbox(cx, cy, rx, ry, rot_deg, width, height)
    xs = np.arange(x0, x1 + 1, dtype=np.float32) + 0.5
    ys = np.arange(y0, y1 + 1, dtype=np.float32) + 0.5
    xx, yy = np.meshgrid(xs, ys)
    theta = math.radians(rot_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    dx = xx - cx
    dy = yy - cy
    xr = dx * cos_t + dy * sin_t
    yr = -dx * sin_t + dy * cos_t
    mask = (xr * xr) / max(1e-6, rx * rx) + (yr * yr) / max(1e-6, ry * ry) <= 1.0
    return (x0, x1, y0, y1), mask


def shape_mask(shape: dict, width: int, height: int) -> tuple[tuple[int, int, int, int], np.ndarray]:
    if int(shape.get("type", ROTATED_ELLIPSE)) in (RECTANGLE, ROTATED_RECTANGLE):
        return rectangle_mask(shape, width, height)
    return ellipse_mask(shape, width, height)


def shape_bbox(shape: dict, width: int, height: int) -> tuple[int, int, int, int]:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return (0, -1, 0, -1)
    cx, cy, w, h = [float(v) for v in data[:4]]
    rot = float(data[4]) if len(data) >= 5 else 0.0
    if int(shape.get("type", ROTATED_ELLIPSE)) in (RECTANGLE, ROTATED_RECTANGLE):
        return rotated_bbox(cx, cy, max(0.5, w * 0.5), max(0.5, h * 0.5), rot, width, height)
    return rotated_bbox(cx, cy, *compensated_ellipse_size(w, h), rot, width, height)


def shape_raw_bbox(shape: dict) -> tuple[float, float, float, float] | None:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return None
    cx, cy, w, h = [float(v) for v in data[:4]]
    rot = float(data[4]) if len(data) >= 5 else 0.0
    if int(shape.get("type", ROTATED_ELLIPSE)) in (RECTANGLE, ROTATED_RECTANGLE):
        return raw_rotated_bbox(cx, cy, max(0.5, w * 0.5), max(0.5, h * 0.5), rot)
    return raw_rotated_bbox(cx, cy, *compensated_ellipse_size(w, h), rot)


def shape_boundary_penalty(shape: dict, width: int, height: int, enabled: bool, edge_context: dict | None = None) -> float:
    if not enabled:
        return 0.0
    bbox = shape_raw_bbox(shape)
    if bbox is None:
        return 0.0
    x0, x1, y0, y1 = bbox
    bbox_w = max(0.0, x1 - x0)
    bbox_h = max(0.0, y1 - y0)
    if bbox_w <= 0.0 or bbox_h <= 0.0:
        return 0.0
    outside_area = 0.0
    if x0 < 0.0 and not edge_side_allows_overhang(edge_context, "left", y0, y1, height):
        outside_area += min(-x0, bbox_w) * bbox_h
    if x1 > float(width) and not edge_side_allows_overhang(edge_context, "right", y0, y1, height):
        outside_area += min(x1 - float(width), bbox_w) * bbox_h
    if y0 < 0.0 and not edge_side_allows_overhang(edge_context, "top", x0, x1, width):
        outside_area += min(-y0, bbox_h) * bbox_w
    if y1 > float(height) and not edge_side_allows_overhang(edge_context, "bottom", x0, x1, width):
        outside_area += min(y1 - float(height), bbox_h) * bbox_w
    outside_area = min(outside_area, bbox_w * bbox_h)
    if outside_area <= 0.25:
        return 0.0
    color = list(shape.get("color", [0, 0, 0, 255]))
    alpha = float(color[3]) / 255.0 if len(color) >= 4 else 1.0
    alpha = max(0.0, min(1.0, alpha))
    if alpha <= 0.0:
        return 0.0
    return outside_area * alpha * alpha * float(255.0 * 255.0 * 3.0 * 8.0)


def shape_boundary_penalties(shapes: list[dict], width: int, height: int, enabled: bool, edge_context: dict | None = None) -> np.ndarray:
    if not enabled:
        return np.zeros(len(shapes), dtype=np.float64)
    return np.array([shape_boundary_penalty(shape, width, height, True, edge_context) for shape in shapes], dtype=np.float64)


def fit_shape_inside_canvas(shape: dict, width: int, height: int, edge_context: dict | None = None) -> dict:
    fitted = copy_shape(shape)
    data = list(fitted.get("data", []))
    if len(data) < 4:
        return fitted
    for _ in range(8):
        bbox = shape_raw_bbox(fitted)
        if bbox is None:
            break
        x0, x1, y0, y1 = bbox
        allow_left = edge_side_allows_overhang(edge_context, "left", y0, y1, height)
        allow_right = edge_side_allows_overhang(edge_context, "right", y0, y1, height)
        allow_top = edge_side_allows_overhang(edge_context, "top", x0, x1, width)
        allow_bottom = edge_side_allows_overhang(edge_context, "bottom", x0, x1, width)
        violate_left = x0 < 0.0 and not allow_left
        violate_right = x1 > float(width) and not allow_right
        violate_top = y0 < 0.0 and not allow_top
        violate_bottom = y1 > float(height) and not allow_bottom
        if not (violate_left or violate_right or violate_top or violate_bottom):
            break
        bbox_w = max(1.0, x1 - x0)
        bbox_h = max(1.0, y1 - y0)
        scale_limits = [1.0]
        if violate_left and violate_right:
            scale_limits.append(max(1.0, float(width) - 1.0) / bbox_w)
        if violate_top and violate_bottom:
            scale_limits.append(max(1.0, float(height) - 1.0) / bbox_h)
        scale = min(scale_limits)
        if scale < 0.999:
            data = list(fitted["data"])
            data[2] = max(1.0, float(data[2]) * scale)
            data[3] = max(1.0, float(data[3]) * scale)
            fitted["data"] = data
            bbox = shape_raw_bbox(fitted)
            if bbox is None:
                break
            x0, x1, y0, y1 = bbox
            allow_left = edge_side_allows_overhang(edge_context, "left", y0, y1, height)
            allow_right = edge_side_allows_overhang(edge_context, "right", y0, y1, height)
            allow_top = edge_side_allows_overhang(edge_context, "top", x0, x1, width)
            allow_bottom = edge_side_allows_overhang(edge_context, "bottom", x0, x1, width)
        dx = 0.0
        dy = 0.0
        if x0 < 0.0 and not allow_left:
            dx = -x0
        if x1 > float(width) and not allow_right:
            dx = min(dx, float(width) - x1) if dx else float(width) - x1
        if y0 < 0.0 and not allow_top:
            dy = -y0
        if y1 > float(height) and not allow_bottom:
            dy = min(dy, float(height) - y1) if dy else float(height) - y1
        data = list(fitted["data"])
        data[0] = float(data[0]) + dx
        data[1] = float(data[1]) + dy
        fitted["data"] = data
    return fitted


def compensated_ellipse_size(w: float, h: float) -> tuple[float, float]:
    major = max(w, h)
    minor = max(1.0, min(w, h))
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

    if w >= h:
        sx = uniform_scale * major_axis_scale
        sy = uniform_scale
    else:
        sx = uniform_scale
        sy = uniform_scale * major_axis_scale

    return max(1.0, w * sx), max(1.0, h * sy)


def render_and_score(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    height, width = target_rgba.shape[:2]
    edge_context = canvas_edge_context(target_rgba) if enforce_canvas_boundary else None
    bg_rgba = np.array(list(background.get("color", [0, 0, 0, 0]))[:4], dtype=np.float32)
    top_rgb = np.empty((height, width, 3), dtype=np.float32)
    top_rgb[:] = bg_rgba[:3]
    under_rgb = np.empty((height, width, 3), dtype=np.float32)
    under_rgb[:] = bg_rgba[:3]
    top_alpha = np.full((height, width), max(0.0, min(1.0, float(bg_rgba[3]) / 255.0)), dtype=np.float32)
    under_alpha = np.full((height, width), max(0.0, min(1.0, float(bg_rgba[3]) / 255.0)), dtype=np.float32)
    top_idx = np.full((height, width), -1, dtype=np.int32)

    for idx, shape in enumerate(shapes):
        rgba = list(shape.get("color", [0, 0, 0, 255]))[:4]
        color = np.array(rgba[:3], dtype=np.float32)
        alpha = float(rgba[3]) / 255.0 if len(rgba) >= 4 else 1.0
        alpha = max(0.0, min(1.0, alpha))
        bbox, mask = shape_mask(shape, width, height)
        x0, x1, y0, y1 = bbox
        if x1 < x0 or y1 < y0 or not np.any(mask):
            continue
        top_sub = top_rgb[y0 : y1 + 1, x0 : x1 + 1]
        under_sub = under_rgb[y0 : y1 + 1, x0 : x1 + 1]
        top_alpha_sub = top_alpha[y0 : y1 + 1, x0 : x1 + 1]
        under_alpha_sub = under_alpha[y0 : y1 + 1, x0 : x1 + 1]
        idx_sub = top_idx[y0 : y1 + 1, x0 : x1 + 1]
        old_top = top_sub.copy()
        old_alpha = top_alpha_sub.copy()
        under_sub[mask] = old_top[mask]
        under_alpha_sub[mask] = old_alpha[mask]
        if alpha >= 1.0:
            top_sub[mask] = color
        elif alpha > 0.0:
            top_sub[mask] = old_top[mask] * (1.0 - alpha) + color * alpha
        if alpha > 0.0:
            top_alpha_sub[mask] = old_alpha[mask] + alpha * (1.0 - old_alpha[mask])
        idx_sub[mask] = idx

    target_rgb = target_rgba[..., :3].astype(np.float32)
    target_alpha = np.clip(target_rgba[..., 3].astype(np.float32) / 255.0, 0.0, 1.0)
    rgb_weight = np.maximum(target_alpha, 0.08)
    transparent_boost = np.where(target_alpha < 0.02, 3.25, np.where(target_alpha < 0.15, 2.35, 1.0)).astype(np.float32)
    rgb_top = np.square(top_rgb - target_rgb).sum(axis=2) * rgb_weight
    rgb_under = np.square(under_rgb - target_rgb).sum(axis=2) * rgb_weight
    alpha_scale = float(255.0 * 255.0 * 3.0 * 1.10)
    spill_scale = float(255.0 * 255.0 * 3.0 * 0.95)
    alpha_top = np.square(top_alpha - target_alpha) * alpha_scale
    alpha_under = np.square(under_alpha - target_alpha) * alpha_scale
    spill_top = np.square(np.maximum(0.0, top_alpha - target_alpha)) * transparent_boost * spill_scale
    spill_under = np.square(np.maximum(0.0, under_alpha - target_alpha)) * transparent_boost * spill_scale
    if importance_map is not None and importance_map.shape == target_alpha.shape:
        importance = np.clip(importance_map.astype(np.float32), 0.25, 8.0)
    else:
        importance = np.ones_like(target_alpha, dtype=np.float32)
    diff_top = (rgb_top + alpha_top + spill_top) * importance
    diff_under = (rgb_under + alpha_under + spill_under) * importance
    contrib_map = diff_under - diff_top
    valid = top_idx >= 0
    if np.any(valid):
        contributions = np.bincount(
            top_idx[valid].ravel(),
            weights=contrib_map[valid].ravel(),
            minlength=len(shapes),
        ).astype(np.float64)
    else:
        contributions = np.zeros(len(shapes), dtype=np.float64)
    boundary_penalties = shape_boundary_penalties(shapes, width, height, enforce_canvas_boundary, edge_context)
    if len(boundary_penalties):
        contributions -= boundary_penalties
    pixel_weights = np.where(target_alpha > 0.02, 1.0, 0.35).astype(np.float32)
    total_error = float((diff_top * pixel_weights).sum() + boundary_penalties.sum())
    scored_pixels = float((pixel_weights * importance).sum())
    return top_rgb, top_alpha, top_idx, diff_top, contributions, total_error, scored_pixels


def bbox_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ax1, ay0, ay1 = a
    bx0, bx1, by0, by1 = b
    return ax0 <= bx1 and ax1 >= bx0 and ay0 <= by1 and ay1 >= by0


def render_and_score_region(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    bbox: tuple[int, int, int, int],
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0:
        return render_and_score(background, [], target_rgba[:1, :1], enforce_canvas_boundary=False)

    height, width = target_rgba.shape[:2]
    x0 = max(0, min(width - 1, int(x0)))
    x1 = max(0, min(width - 1, int(x1)))
    y0 = max(0, min(height - 1, int(y0)))
    y1 = max(0, min(height - 1, int(y1)))
    if x1 < x0 or y1 < y0:
        return render_and_score(background, [], target_rgba[:1, :1], enforce_canvas_boundary=False)

    crop_bbox = (x0, x1, y0, y1)
    crop_w = x1 - x0 + 1
    crop_h = y1 - y0 + 1
    crop_shapes = []
    for shape in shapes:
        current_bbox = shape_bbox(shape, width, height)
        if not bbox_intersects(current_bbox, crop_bbox):
            continue
        shifted = copy_shape(shape)
        shifted["data"] = list(shifted["data"])
        shifted["data"][0] = float(shifted["data"][0]) - x0
        shifted["data"][1] = float(shifted["data"][1]) - y0
        crop_shapes.append(shifted)

    crop_bg = dict(background)
    crop_bg["data"] = [0, 0, crop_w, crop_h]
    crop_importance = importance_map[y0 : y1 + 1, x0 : x1 + 1] if importance_map is not None else None
    return render_and_score(
        crop_bg,
        crop_shapes,
        target_rgba[y0 : y1 + 1, x0 : x1 + 1],
        enforce_canvas_boundary=False,
        importance_map=crop_importance,
    )


def prune_to_target(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    target_count: int,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> tuple[list[dict], float]:
    working = list(shapes)
    working, _, _ = remove_fully_covered_layers(
        background,
        working,
        target_rgba,
        enforce_canvas_boundary=enforce_canvas_boundary,
        importance_map=importance_map,
        max_batch=96,
        removal_limit=max(0, len(working) - target_count),
    )
    if len(working) <= target_count:
        _, _, _, _, _, total_error, scored_pixels = render_and_score(
            background,
            working,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        return working, normalized_error(total_error, scored_pixels)

    while len(working) > target_count:
        _, _, _, _, contributions, total_error, scored_pixels = render_and_score(
            background,
            working,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        current_error = normalized_error(total_error, scored_pixels)
        excess = len(working) - target_count
        order = np.argsort(contributions)
        zeroish = int(np.count_nonzero(contributions[order] <= 1e-6))
        if zeroish > 0:
            remove_count = min(excess, zeroish)
        else:
            # Overshoot checkpoints can be hundreds of shapes over the FH-safe
            # budget, but large blind batches can thin hair/edges. Start with
            # a moderate batch, then validate and shrink it if the score jumps.
            remove_count = min(excess, max(1, min(72, excess // 8 if excess > 24 else 1)))
        working, current_error = remove_lowest_ranked_batch(
            background,
            working,
            target_rgba,
            order,
            remove_count,
            current_error,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )

    _, _, _, _, _, total_error, scored_pixels = render_and_score(
        background,
        working,
        target_rgba,
        enforce_canvas_boundary=enforce_canvas_boundary,
        importance_map=importance_map,
    )
    return working, normalized_error(total_error, scored_pixels)


def normalized_error(total_error: float, scored_pixels: float) -> float:
    denom = max(1.0, scored_pixels * 4.0)
    return total_error / float(denom)


def score_shape_list(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> float:
    _, _, _, _, _, total_error, scored_pixels = render_and_score(
        background,
        shapes,
        target_rgba,
        enforce_canvas_boundary=enforce_canvas_boundary,
        importance_map=importance_map,
    )
    return normalized_error(total_error, scored_pixels)


def remove_lowest_ranked_batch(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    ranked_indices: np.ndarray,
    requested_remove_count: int,
    current_error: float,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> tuple[list[dict], float]:
    if requested_remove_count <= 0 or len(shapes) <= 1:
        return shapes, current_error

    requested_remove_count = max(1, min(int(requested_remove_count), len(shapes) - 1))
    tolerance = max(0.0025, current_error * 0.0018)
    trial_sizes = []
    size = requested_remove_count
    while size >= 1:
        if size not in trial_sizes:
            trial_sizes.append(size)
        if size == 1:
            break
        size = max(1, size // 2)

    for remove_count in trial_sizes:
        remove_idx = set(int(i) for i in ranked_indices[:remove_count])
        candidate = [shape for idx, shape in enumerate(shapes) if idx not in remove_idx]
        candidate_error = score_shape_list(
            background,
            candidate,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        if candidate_error <= current_error + tolerance or remove_count == 1:
            return candidate, candidate_error
    return shapes, current_error


def visible_shape_pixels(top_idx: np.ndarray, shape_count: int) -> np.ndarray:
    valid = top_idx >= 0
    if not np.any(valid):
        return np.zeros(shape_count, dtype=np.int64)
    return np.bincount(top_idx[valid].ravel(), minlength=shape_count).astype(np.int64)


def remove_fully_covered_layers(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
    max_batch: int = 64,
    removal_limit: int | None = None,
) -> tuple[list[dict], float, dict]:
    if not shapes:
        return [], 0.0, {"removed": 0, "before": 0, "after": 0, "score_before": 0.0, "score_after": 0.0}
    if removal_limit is not None and removal_limit <= 0:
        current_error = score_shape_list(
            background,
            shapes,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        return list(shapes), current_error, {
            "removed": 0,
            "rejected": 0,
            "before": len(shapes),
            "after": len(shapes),
            "score_before": current_error,
            "score_after": current_error,
            "skipped": "candidate is already at or under the target layer budget",
        }

    working = list(shapes)
    initial_count = len(working)
    current_error = score_shape_list(
        background,
        working,
        target_rgba,
        enforce_canvas_boundary=enforce_canvas_boundary,
        importance_map=importance_map,
    )
    removed_total = 0
    rejected_total = 0

    while working:
        _, _, top_idx, _, _, _, _ = render_and_score(
            background,
            working,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        visible_pixels = visible_shape_pixels(top_idx, len(working))
        hidden_indices = [idx for idx, pixels in enumerate(visible_pixels) if int(pixels) <= 0]
        if not hidden_indices:
            break

        progress = False
        while hidden_indices:
            remaining_allowed = None if removal_limit is None else max(0, int(removal_limit) - removed_total)
            if remaining_allowed is not None and remaining_allowed <= 0:
                hidden_indices = []
                break
            batch_size = max(1, min(max_batch, len(hidden_indices)))
            if remaining_allowed is not None:
                batch_size = min(batch_size, remaining_allowed)
            batch = hidden_indices[:batch_size]
            remove_idx = set(batch)
            candidate = [shape for idx, shape in enumerate(working) if idx not in remove_idx]
            candidate_error = score_shape_list(
                background,
                candidate,
                target_rgba,
                enforce_canvas_boundary=enforce_canvas_boundary,
                importance_map=importance_map,
            )
            tolerance = max(0.0015, current_error * 0.00075)
            if candidate_error <= current_error + tolerance:
                working = candidate
                current_error = candidate_error
                removed_total += len(remove_idx)
                progress = True
                break
            if len(batch) == 1:
                rejected_total += 1
                hidden_indices = hidden_indices[1:]
                continue
            max_batch = max(1, len(batch) // 2)

        if not progress and not hidden_indices:
            break

    return working, current_error, {
        "removed": removed_total,
        "rejected": rejected_total,
        "before": initial_count,
        "after": len(working),
        "score_before": score_shape_list(
            background,
            shapes,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        ),
        "score_after": current_error,
    }


def render_import_preview(background: dict, shapes: list[dict], width: int, height: int) -> Image.Image:
    checker = np.zeros((height, width, 3), dtype=np.float32)
    bg_rgba = [int(v) for v in list(background.get("color", [0, 0, 0, 0]))[:4]]
    if len(bg_rgba) < 4:
        bg_rgba += [0] * (4 - len(bg_rgba))
    bg_r, bg_g, bg_b, bg_a = bg_rgba
    premul = np.zeros((height, width, 3), dtype=np.float32)
    alpha_canvas = np.zeros((height, width), dtype=np.float32)
    if bg_a > 0:
        base_alpha = max(0.0, min(1.0, bg_a / 255.0))
        premul[:, :] = np.array((bg_r, bg_g, bg_b), dtype=np.float32) * base_alpha
        alpha_canvas[:, :] = base_alpha
        checker[:, :] = (38, 38, 38)
    else:
        checker[:, :] = (38, 38, 38)
        tile = 32
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                if ((x // tile) + (y // tile)) % 2 == 0:
                    checker[y : y + tile, x : x + tile] = (58, 58, 58)

    for shape in shapes:
        color = [int(v) for v in list(shape.get("color", [0, 0, 0, 255]))[:4]]
        if len(color) < 4 or color[3] <= 0:
            continue
        r, g, b, a = color
        mask = np.zeros((height, width), dtype=np.uint8)
        data = list(shape.get("data", []))
        if len(data) < 4:
            continue
        x, y, w, h = [float(v) for v in data[:4]]
        rot_deg = float(data[4]) if len(data) >= 5 else 0.0
        if int(shape.get("type", ROTATED_ELLIPSE)) in (RECTANGLE, ROTATED_RECTANGLE):
            rect = ((x, y), (max(1.0, w), max(1.0, h)), rot_deg)
            box = cv2.boxPoints(rect).astype(np.int32)
            cv2.fillConvexPoly(mask, box, 255)
        else:
            adj_w, adj_h = compensated_ellipse_size(w, h)
            center = (int(round(x)), int(round(y)))
            axes = (max(1, int(round(adj_h))), max(1, int(round(adj_w))))
            cv2.ellipse(mask, center, axes, -90 + rot_deg, 0.0, 360.0, 255, thickness=-1)
        alpha = max(0.0, min(1.0, a / 255.0))
        if alpha <= 0.0:
            continue
        src_rgb = np.array((r, g, b), dtype=np.float32)
        shape_mask = mask > 0
        old_alpha = alpha_canvas[shape_mask]
        premul[shape_mask] = src_rgb * alpha + premul[shape_mask] * (1.0 - alpha)
        alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)

    out = premul + checker * (1.0 - alpha_canvas[..., None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def copy_shape(shape: dict) -> dict:
    return {
        "type": int(shape.get("type", ROTATED_ELLIPSE)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
        "data": list(shape.get("data", [])),
        "score": shape.get("score", 0),
    }


def force_opaque_drawables(shapes: list[dict]) -> list[dict]:
    out = []
    for shape in shapes:
        fixed = copy_shape(shape)
        color = list(fixed.get("color", [0, 0, 0, 255]))
        if len(color) < 4:
            color += [255] * (4 - len(color))
        if int(color[3]) > 0:
            color[3] = 255
        fixed["color"] = color
        out.append(fixed)
    return out


def stabilize_flat_region_colors(
    shapes: list[dict],
    target_rgba: np.ndarray,
    force_opaque: bool = True,
    min_pixels: int = 48,
) -> tuple[list[dict], dict]:
    """Snap large low-variance flat-art shapes to dominant source colors.

    The raw generator can choose slightly different optimal colors for many
    overlapping shapes in one flat field. That lowers numeric error locally but
    reads as milky/noisy patches in FH. This pass is deliberately conservative:
    only shapes whose local source pixels have a clear dominant color bin are
    changed.
    """
    if not shapes:
        return shapes, {"enabled": True, "changed": 0, "checked": 0, "skipped": 0}

    height, width = target_rgba.shape[:2]
    target = np.clip(target_rgba, 0, 255).astype(np.uint8)
    stabilized: list[dict] = []
    changed = 0
    checked = 0
    skipped = 0
    protected_large_underpaint = 0
    protected_extreme_snap = 0
    canvas_pixels = max(1, width * height)
    total_shapes = max(1, len(shapes))
    for shape_index, shape in enumerate(shapes):
        fixed = copy_shape(shape)
        color = list(fixed.get("color", [0, 0, 0, 255]))
        if len(color) < 4 or int(color[3]) <= 0:
            stabilized.append(fixed)
            skipped += 1
            continue
        bbox, mask = shape_mask(fixed, width, height)
        x0, x1, y0, y1 = bbox
        if x1 < x0 or y1 < y0 or not np.any(mask):
            stabilized.append(fixed)
            skipped += 1
            continue
        local = target[y0 : y1 + 1, x0 : x1 + 1]
        visible = mask & (local[..., 3] > 32)
        pixel_count = int(np.count_nonzero(visible))
        if pixel_count < min_pixels:
            stabilized.append(fixed)
            skipped += 1
            continue
        checked += 1
        layer_fraction = float(shape_index) / float(max(1, total_shapes - 1))
        pixel_fraction = float(pixel_count) / float(canvas_pixels)
        rgb = local[..., :3][visible].astype(np.uint8)
        channel_std = float(np.mean(np.std(rgb.astype(np.float32), axis=0))) if rgb.size else 999.0
        bins = (rgb // 10).astype(np.uint16)
        packed = (bins[:, 0] << 10) | (bins[:, 1] << 5) | bins[:, 2]
        values, counts = np.unique(packed, return_counts=True)
        if values.size == 0:
            stabilized.append(fixed)
            skipped += 1
            continue
        best = int(np.argmax(counts))
        dominant_fraction = float(counts[best]) / float(max(1, pixel_count))
        if dominant_fraction < 0.46 or (dominant_fraction < 0.62 and channel_std > 22.0):
            stabilized.append(fixed)
            skipped += 1
            continue
        dominant_rgb = rgb[packed == values[best]]
        if dominant_rgb.size == 0:
            stabilized.append(fixed)
            skipped += 1
            continue
        new_rgb = [int(round(v)) for v in np.median(dominant_rgb, axis=0)]
        old_rgb = [int(v) for v in color[:3]]
        old_luma = sum(old_rgb) / 3.0
        new_luma = sum(new_rgb) / 3.0
        snap_delta = sum(abs(a - b) for a, b in zip(old_rgb, new_rgb))
        snaps_to_extreme = new_luma <= 18.0 or new_luma >= 237.0
        old_was_mid = 48.0 < old_luma < 207.0

        # Large early layers are often broad underpaint. Snapping them to hard
        # black/white can look like V2 added new blobs in corners/edges even
        # though it only changed an existing layer color. Require much stronger
        # evidence before touching these foundation shapes.
        if pixel_fraction >= 0.010 and layer_fraction <= 0.12:
            if dominant_fraction < 0.88 or channel_std > 8.0:
                stabilized.append(fixed)
                skipped += 1
                protected_large_underpaint += 1
                continue
        elif pixel_fraction >= 0.004 and layer_fraction <= 0.22:
            if dominant_fraction < 0.78 or channel_std > 14.0:
                stabilized.append(fixed)
                skipped += 1
                protected_large_underpaint += 1
                continue

        # A mid-gray ellipse that suddenly becomes pure white/black is exactly
        # the visible bleeding failure mode on flat logos. Allow it only when
        # the local source is overwhelmingly one flat color.
        if snaps_to_extreme and old_was_mid and snap_delta >= 90:
            if dominant_fraction < 0.82 or channel_std > 10.0:
                stabilized.append(fixed)
                skipped += 1
                protected_extreme_snap += 1
                continue

        if snap_delta >= 3:
            color[:3] = new_rgb
            if force_opaque:
                color[3] = 255
            fixed["color"] = color
            changed += 1
        stabilized.append(fixed)

    return stabilized, {
        "enabled": True,
        "changed": changed,
        "checked": checked,
        "skipped": skipped,
        "min_pixels": min_pixels,
        "protected_large_underpaint": protected_large_underpaint,
        "protected_extreme_snap": protected_extreme_snap,
    }


def shape_visual_extents(shape: dict) -> tuple[float, float, float, float, float] | None:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return None
    cx, cy, a, b = [float(v) for v in data[:4]]
    rot = float(data[4]) if len(data) >= 5 else 0.0
    if int(shape.get("type", ROTATED_ELLIPSE)) in (RECTANGLE, ROTATED_RECTANGLE):
        half_w = max(0.5, a * 0.5)
        half_h = max(0.5, b * 0.5)
    else:
        half_w = max(0.5, a)
        half_h = max(0.5, b)
    return cx, cy, half_w, half_h, rot


def shape_family_variant(shape: dict, shape_type: int) -> dict | None:
    extents = shape_visual_extents(shape)
    if extents is None:
        return None
    cx, cy, half_w, half_h, rot = extents
    variant = copy_shape(shape)
    variant["type"] = shape_type
    if shape_type == RECTANGLE:
        variant["data"] = [
            cx,
            cy,
            max(1.0, half_w * 2.0),
            max(1.0, half_h * 2.0),
        ]
    elif shape_type == ROTATED_RECTANGLE:
        variant["data"] = [
            cx,
            cy,
            max(1.0, half_w * 2.0),
            max(1.0, half_h * 2.0),
            rot % 360.0,
        ]
    elif shape_type == ELLIPSE:
        variant["data"] = [
            cx,
            cy,
            max(1.0, half_w),
            max(1.0, half_h),
            0.0,
        ]
    elif shape_type == ROTATED_ELLIPSE:
        variant["data"] = [
            cx,
            cy,
            max(1.0, half_w),
            max(1.0, half_h),
            rot % 360.0,
        ]
    else:
        return None
    return variant


def shape_family_variants(shape: dict, prefer_smooth_shapes: bool = False) -> list[dict]:
    current_type = int(shape.get("type", ROTATED_ELLIPSE))
    extents = shape_visual_extents(shape)
    if extents is None:
        return []
    _, _, half_w, half_h, rot = extents
    aspect = max(half_w, half_h) / max(1.0, min(half_w, half_h))
    near_axis = abs((rot % 90.0)) <= 2.0 or abs((rot % 90.0) - 90.0) <= 2.0

    if prefer_smooth_shapes:
        candidates = [ROTATED_ELLIPSE, ELLIPSE, ROTATED_RECTANGLE]
        if near_axis:
            candidates.append(RECTANGLE)
        if aspect >= 4.0:
            # Very long strokes may still need rectangles, but soft/shaded
            # presets should only reach them after ellipse variants fail.
            candidates = [ROTATED_ELLIPSE, ROTATED_RECTANGLE, ELLIPSE, RECTANGLE]
    else:
        candidates = [ROTATED_ELLIPSE, ROTATED_RECTANGLE]
        if near_axis:
            candidates.extend([ELLIPSE, RECTANGLE])
        if aspect <= 1.20:
            # Round-ish details rarely benefit from rotated rectangles unless
            # the score proves otherwise, so test ellipses first.
            candidates = [ROTATED_ELLIPSE, ELLIPSE, ROTATED_RECTANGLE, RECTANGLE]
        elif aspect >= 2.20:
            # Long strokes often fit better as rectangles, but keep ellipses
            # available for tapered hair/finger detail.
            candidates = [ROTATED_RECTANGLE, ROTATED_ELLIPSE, RECTANGLE, ELLIPSE]

    out = []
    seen: set[int] = set()
    for shape_type in candidates:
        if shape_type == current_type or shape_type in seen:
            continue
        seen.add(shape_type)
        variant = shape_family_variant(shape, shape_type)
        if variant is not None:
            out.append(variant)
    return out


def unscale_shape(shape: dict, sx: float, sy: float) -> dict:
    data = list(shape.get("data", []))
    if len(data) < 4:
        raise ValueError("shape missing data")
    x, y, rx, ry = [float(v) for v in data[:4]]
    rot = float(data[4]) if len(data) >= 5 else 0.0
    return {
        "type": int(shape.get("type", ROTATED_ELLIPSE)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
        "data": [
            int(round(x / max(sx, 1e-6))),
            int(round(y / max(sy, 1e-6))),
            max(1, int(round(rx / max(sx, 1e-6)))),
            max(1, int(round(ry / max(sy, 1e-6)))),
            int(round(rot)) % 360,
        ],
        "score": shape.get("score", 0),
    }


def local_error_value(diff_map: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0:
        return 0.0
    sub = diff_map[y0 : y1 + 1, x0 : x1 + 1]
    if sub.size == 0:
        return 0.0
    return float(sub.mean())


def shape_homogeneity_penalty(shape: dict, target_rgba: np.ndarray) -> float:
    height, width = target_rgba.shape[:2]
    bbox, mask = shape_mask(shape, width, height)
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0 or not np.any(mask):
        return 0.0
    target_mask = target_rgba[..., 3] > 0.5
    sub_target_mask = target_mask[y0 : y1 + 1, x0 : x1 + 1]
    valid = mask & sub_target_mask
    if not np.any(valid):
        return 0.0
    sub_rgb = target_rgba[y0 : y1 + 1, x0 : x1 + 1, :3].astype(np.float32)
    pixels = sub_rgb[valid]
    if len(pixels) < 4:
        return 0.0
    mean = pixels.mean(axis=0)
    sq = np.square(pixels - mean).sum(axis=1)
    return float(sq.mean())


def expanded_shape_bbox(shape: dict, width: int, height: int, move_step: float, radius_step: float) -> tuple[int, int, int, int]:
    data = list(shape.get("data", []))
    if len(data) < 4:
        return (0, width - 1, 0, height - 1)
    cx, cy, rx, ry = [float(v) for v in data[:4]]
    rot_deg = float(data[4]) if len(data) >= 5 else 0.0
    shape_type = int(shape.get("type", ROTATED_ELLIPSE))
    if shape_type in (RECTANGLE, ROTATED_RECTANGLE):
        # Rectangle data stores full width/height, while ellipse data stores
        # radii. Inflate full dimensions, then convert to half extents.
        half_w = max(0.5, (rx + radius_step * 2.0) * 0.5) + move_step
        half_h = max(0.5, (ry + radius_step * 2.0) * 0.5) + move_step
        x0, x1, y0, y1 = rotated_bbox(cx, cy, half_w, half_h, rot_deg, width, height)
    else:
        erx, ery = compensated_ellipse_size(rx + radius_step, ry + radius_step)
        x0, x1, y0, y1 = rotated_bbox(cx, cy, erx + move_step, ery + move_step, rot_deg, width, height)
    margin = max(4, int(math.ceil(max(move_step, radius_step))))
    return (
        max(0, x0 - margin),
        min(width - 1, x1 + margin),
        max(0, y0 - margin),
        min(height - 1, y1 + margin),
    )


def rank_repair_targets(
    shapes: list[dict],
    top_idx: np.ndarray,
    diff_top: np.ndarray,
    top_alpha: np.ndarray,
    target_rgba: np.ndarray,
    max_shapes: int,
    enforce_canvas_boundary: bool = False,
    importance_map: np.ndarray | None = None,
) -> list[int]:
    target_alpha = np.clip(target_rgba[..., 3].astype(np.float32) / 255.0, 0.0, 1.0)
    valid = top_idx >= 0
    if not np.any(valid):
        return []
    shape_error = np.bincount(top_idx[valid].ravel(), weights=diff_top[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    if importance_map is not None and importance_map.shape == target_alpha.shape:
        visible_weights = np.clip(importance_map.astype(np.float32), 0.25, 8.0)
        visible_pixels = np.bincount(top_idx[valid].ravel(), weights=visible_weights[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    else:
        visible_pixels = np.bincount(top_idx[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    spill = np.maximum(0.0, top_alpha - target_alpha)
    spill_pixels = np.bincount(top_idx[valid].ravel(), weights=spill[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    edge_context = canvas_edge_context(target_rgba) if enforce_canvas_boundary else None
    boundary_penalty = shape_boundary_penalties(shapes, target_rgba.shape[1], target_rgba.shape[0], enforce_canvas_boundary, edge_context)
    area = np.array([max(1.0, float(shape["data"][2]) * float(shape["data"][3])) for shape in shapes], dtype=np.float64)
    homogeneity = np.array([shape_homogeneity_penalty(shape, target_rgba) for shape in shapes], dtype=np.float64)
    index = np.arange(len(shapes), dtype=np.float64)
    early_weight = np.where(index < 250, 1.8 - (index / 250.0) * 0.8, 1.0)
    size_weight = np.sqrt(np.maximum(1.0, area))
    score = (
        (shape_error * 1.05)
        + (spill_pixels * size_weight * 9500.0 * early_weight)
        + (homogeneity * size_weight * early_weight)
        + (boundary_penalty * 1.75)
    ) * (1.0 + np.sqrt(np.maximum(1.0, visible_pixels)) / 6.0) / np.sqrt(area)
    ranked = np.argsort(score)[::-1]
    ranked = [
        int(idx)
        for idx in ranked
        if (shape_error[idx] > 0 or homogeneity[idx] > 0 or spill_pixels[idx] > 0 or boundary_penalty[idx] > 0)
        and (visible_pixels[idx] > 0 or boundary_penalty[idx] > 0)
    ]
    return ranked[:max_shapes]


def repair_shapes(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    max_shapes: int = 8,
    rounds: int = 1,
    enforce_canvas_boundary: bool = False,
    prefer_smooth_shapes: bool = False,
    importance_map: np.ndarray | None = None,
    allow_alpha_repair: bool = True,
) -> tuple[list[dict], float, dict]:
    if not shapes:
        _, _, _, _, _, total_error, scored_pixels = render_and_score(
            background,
            shapes,
            target_rgba,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        error = normalized_error(total_error, scored_pixels)
        return shapes, error, {"enabled": True, "touched": 0, "improvements": 0, "before": error, "after": error}

    working = [copy_shape(shape) for shape in shapes]
    render_rgb, top_alpha, top_idx, diff_top, _, total_error, scored_pixels = render_and_score(
        background,
        working,
        target_rgba,
        enforce_canvas_boundary=enforce_canvas_boundary,
        importance_map=importance_map,
    )
    best_error = normalized_error(total_error, scored_pixels)
    before_error = best_error
    edge_context = canvas_edge_context(target_rgba) if enforce_canvas_boundary else None

    improvements = 0
    family_changes = 0
    boundary_fits = 0
    touched_indices: set[int] = set()
    for _round in range(rounds):
        ranked = rank_repair_targets(
            working,
            top_idx,
            diff_top,
            top_alpha,
            target_rgba,
            max_shapes,
            enforce_canvas_boundary=enforce_canvas_boundary,
            importance_map=importance_map,
        )
        changed = False
        for idx in ranked:
            if idx >= len(working):
                continue
            touched_indices.add(idx)
            shape = working[idx]
            data = list(shape.get("data", []))
            if len(data) < 4:
                continue
            x, y, rx, ry = [float(v) for v in data[:4]]
            rot = float(data[4]) if len(data) >= 5 else 0.0
            move_step = max(1.0, round(max(rx, ry) * 0.014))
            radius_step = max(1.0, round(max(rx, ry) * 0.03))
            rot_step = 2.0
            local_bbox = expanded_shape_bbox(shape, target_rgba.shape[1], target_rgba.shape[0], move_step, radius_step)
            local_best_score = local_error_value(diff_top, local_bbox)
            if enforce_canvas_boundary:
                local_area = max(1.0, float((local_bbox[1] - local_bbox[0] + 1) * (local_bbox[3] - local_bbox[2] + 1)))
                local_best_score += shape_boundary_penalty(shape, target_rgba.shape[1], target_rgba.shape[0], True, edge_context) / local_area
            alpha0 = float(shape.get("color", [0, 0, 0, 255])[3])
            alpha_step = max(10.0, round(alpha0 * 0.12))
            proposals = [
                (False,  move_step, 0.0, 0.0, 0.0, 0.0),
                (False, -move_step, 0.0, 0.0, 0.0, 0.0),
                (False, 0.0,  move_step, 0.0, 0.0, 0.0),
                (False, 0.0, -move_step, 0.0, 0.0, 0.0),
                (False,  move_step * 0.5, 0.0, 0.0, 0.0, 0.0),
                (False, -move_step * 0.5, 0.0, 0.0, 0.0, 0.0),
                (False, 0.0,  move_step * 0.5, 0.0, 0.0, 0.0),
                (False, 0.0, -move_step * 0.5, 0.0, 0.0, 0.0),
                (False, 0.0, 0.0, -radius_step, 0.0, 0.0),
                (False, 0.0, 0.0, 0.0, -radius_step, 0.0),
                (False, 0.0, 0.0, -radius_step, -radius_step, 0.0),
                (False, 0.0, 0.0, 0.0, 0.0,  rot_step),
                (False, 0.0, 0.0, 0.0, 0.0, -rot_step),
                (False, 0.0, 0.0, -radius_step, 0.0, rot_step),
                (False, 0.0, 0.0, 0.0, -radius_step, -rot_step),
            ]
            if allow_alpha_repair:
                proposals.extend([
                    (False, 0.0, 0.0, -radius_step, -radius_step, 0.0, -alpha_step),
                    (False, 0.0, 0.0, 0.0, 0.0, 0.0, -alpha_step),
                    (False, 0.0, 0.0, 0.0, 0.0, 0.0, -alpha_step * 2.0),
                    (False,  move_step * 0.5, 0.0, -radius_step, 0.0, 0.0, -alpha_step),
                    (False, -move_step * 0.5, 0.0, -radius_step, 0.0, 0.0, -alpha_step),
                    (False, 0.0,  move_step * 0.5, 0.0, -radius_step, 0.0, -alpha_step),
                    (False, 0.0, -move_step * 0.5, 0.0, -radius_step, 0.0, -alpha_step),
                ])

            local_best = copy_shape(shape)
            original_local_score = local_best_score
            local_best_deleted = False
            trial_shapes: list[dict | None] = shape_family_variants(shape, prefer_smooth_shapes=prefer_smooth_shapes)
            if enforce_canvas_boundary and shape_boundary_penalty(shape, target_rgba.shape[1], target_rgba.shape[0], True, edge_context) > 0:
                trial_shapes.append(fit_shape_inside_canvas(shape, target_rgba.shape[1], target_rgba.shape[0], edge_context))
            for proposal in proposals:
                if len(proposal) == 6:
                    delete_shape, dx, dy, drx, dry, drot = proposal
                    dalpha = 0.0
                else:
                    delete_shape, dx, dy, drx, dry, drot, dalpha = proposal
                if delete_shape:
                    trial_shapes.append(None)
                    continue
                trial = copy_shape(shape)
                trial["data"] = [
                    x + dx,
                    y + dy,
                    max(1.0, rx + drx),
                    max(1.0, ry + dry),
                    (rot + drot) % 360.0,
                ]
                trial["color"] = list(trial.get("color", [0, 0, 0, 255]))
                if len(trial["color"]) < 4:
                    trial["color"] += [255] * (4 - len(trial["color"]))
                trial["color"][3] = int(max(0, min(255, round(alpha0 + dalpha)))) if allow_alpha_repair else int(max(1, min(255, round(alpha0))))
                trial_shapes.append(trial)

            for trial in trial_shapes:
                prev = working[idx]
                if trial is None:
                    del working[idx]
                else:
                    working[idx] = trial
                _, _, _, trial_diff, _, _, _ = render_and_score_region(
                    background,
                    working,
                    target_rgba,
                    local_bbox,
                    importance_map=importance_map,
                )
                trial_local_score = float(trial_diff.mean()) if trial_diff.size else local_best_score
                if enforce_canvas_boundary and trial is not None:
                    local_area = max(1.0, float((local_bbox[1] - local_bbox[0] + 1) * (local_bbox[3] - local_bbox[2] + 1)))
                    trial_local_score += shape_boundary_penalty(trial, target_rgba.shape[1], target_rgba.shape[0], True, edge_context) / local_area
                if trial_local_score + 1e-9 < local_best_score:
                    local_best_score = trial_local_score
                    local_best = None if trial is None else copy_shape(trial)
                    local_best_deleted = trial is None
                if trial is None:
                    working.insert(idx, prev)
                else:
                    working[idx] = prev

            if local_best_score + 1e-9 < original_local_score:
                prev = working[idx]
                changed_family = bool(
                    not local_best_deleted
                    and local_best is not None
                    and int(local_best.get("type", ROTATED_ELLIPSE)) != int(prev.get("type", ROTATED_ELLIPSE))
                )
                if local_best_deleted:
                    del working[idx]
                else:
                    working[idx] = local_best
                trial_render_rgb, trial_alpha, trial_top_idx, trial_diff, _, trial_total_error, trial_scored_pixels = render_and_score(
                    background,
                    working,
                    target_rgba,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    importance_map=importance_map,
                )
                trial_error = normalized_error(trial_total_error, trial_scored_pixels)
                if trial_error <= best_error + 1e-6 or trial_error + 1e-9 < best_error:
                    best_error = trial_error
                    render_rgb = trial_render_rgb
                    top_alpha = trial_alpha
                    top_idx = trial_top_idx
                    diff_top = trial_diff
                    improvements += 1
                    if changed_family:
                        family_changes += 1
                    if enforce_canvas_boundary and shape_boundary_penalty(prev, target_rgba.shape[1], target_rgba.shape[0], True, edge_context) > 0:
                        boundary_fits += 1
                    changed = True
                else:
                    if local_best_deleted:
                        working.insert(idx, prev)
                    else:
                        working[idx] = prev

        if not changed:
            break

    summary = {
        "enabled": True,
        "touched": len(touched_indices),
        "improvements": improvements,
        "family_changes": family_changes,
        "boundary_fits": boundary_fits,
        "alpha_repair": allow_alpha_repair,
        "canvas_boundary_enforced": enforce_canvas_boundary,
        "before": before_error,
        "after": best_error,
    }
    return working, best_error, summary


def enforce_shapes_inside_canvas(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    importance_map: np.ndarray | None = None,
) -> tuple[list[dict], float, dict]:
    width = target_rgba.shape[1]
    height = target_rgba.shape[0]
    edge_context = canvas_edge_context(target_rgba)
    working: list[dict] = []
    fitted_count = 0
    remaining_penalty = 0.0
    for shape in shapes:
        before_penalty = shape_boundary_penalty(shape, width, height, True, edge_context)
        if before_penalty > 0.0:
            fitted = fit_shape_inside_canvas(shape, width, height, edge_context)
            after_penalty = shape_boundary_penalty(fitted, width, height, True, edge_context)
            if after_penalty < before_penalty:
                working.append(fitted)
                fitted_count += 1
                remaining_penalty += after_penalty
                continue
            remaining_penalty += before_penalty
        working.append(copy_shape(shape))
    _, _, _, _, _, total_error, scored_pixels = render_and_score(
        background,
        working,
        target_rgba,
        enforce_canvas_boundary=True,
        importance_map=importance_map,
    )
    error = normalized_error(total_error, scored_pixels)
    return working, error, {
        "enabled": True,
        "fitted": fitted_count,
        "remaining_penalty": remaining_penalty,
    }


def preview_path_for_candidate(candidate_path: Path, stem: str) -> Path:
    name = candidate_path.name
    if name == f"{stem}.json":
        return candidate_path.with_name(f"{stem}.preview.png")
    suffix = f".json"
    if not name.endswith(suffix):
        return candidate_path.with_suffix(candidate_path.suffix + ".preview.png")
    core = name[: -len(suffix)]
    if core.startswith(f"{stem}."):
        checkpoint = core[len(stem) + 1 :]
        return candidate_path.with_name(f"{stem}.preview.{checkpoint}.png")
    return candidate_path.with_name(f"{core}.preview.png")


def checkpoint_tag_for_candidate(candidate_path: Path, stem: str) -> str:
    core = candidate_path.stem
    if core == stem:
        return "final"
    if core.startswith(f"{stem}."):
        return core[len(stem) + 1 :]
    return core


def v2_json_path_for_candidate(out_dir: Path, stem: str, candidate_path: Path) -> Path:
    return v2_json_path_for_tag(out_dir, stem, checkpoint_tag_for_candidate(candidate_path, stem))


def v2_json_path_for_tag(out_dir: Path, stem: str, tag: str) -> Path:
    tag = re.sub(r"[^A-Za-z0-9_-]+", "", tag).strip() or "final"
    return out_dir / FINALS_DIR_NAME / f"{stem}.{tag}v2.json"


def v2_preview_path_for_candidate(out_dir: Path, stem: str, candidate_path: Path) -> Path:
    return v2_preview_path_for_tag(out_dir, stem, checkpoint_tag_for_candidate(candidate_path, stem))


def v2_preview_path_for_tag(out_dir: Path, stem: str, tag: str) -> Path:
    tag = re.sub(r"[^A-Za-z0-9_-]+", "", tag).strip() or "final"
    return out_dir / PREVIEWS_DIR_NAME / f"{stem}.preview.{tag}v2.png"


def stem_from_image(path: Path) -> str:
    # The Go generator treats dots in the output base as extension separators.
    # A source like "Untitled_16.01.36.png" otherwise produces
    # "Untitled_16.01.5.json" instead of "...16.01.36.5.json", and V2 cannot
    # find its checkpoints. Keep the run stem extension-safe.
    return re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem).strip("_") or "image"


def run_generator(image: Path, settings_path: Path, checkpoint_dir: Path, preview_dir: Path, out_stem: str, stop_file: Path | None = None, seed: int = 0) -> bool:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_base = checkpoint_dir / out_stem
    preview_path = preview_dir / f"{out_stem}.raw.preview.png"
    env = dict(os.environ)
    if os.name != "nt":
        env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH
    cmd = [
        str(GENERATOR_BIN),
        str(image),
        "-settings",
        str(settings_path),
        "-output",
        str(out_base),
        "-preview",
        str(preview_path),
    ]
    if seed:
        cmd.extend(["-seed", str(seed)])
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        creationflags=flags,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    interrupted = False

    def _cleanup_live_preview_snapshots() -> None:
        # The raw generator writes numbered snapshots beside the overwritten
        # live preview. Promote the newest numbered snapshot to the stable
        # preview path first so the UI has one file to poll, then remove the
        # numbered files to avoid preview clutter.
        snapshots = sorted(
            preview_dir.glob(f"{out_stem}.raw.preview.*.png"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        )
        if snapshots:
            latest = snapshots[-1]
            temp_preview = preview_path.with_suffix(preview_path.suffix + ".tmp")
            try:
                shutil.copy2(latest, temp_preview)
                os.replace(temp_preview, preview_path)
            except OSError:
                try:
                    if temp_preview.exists():
                        temp_preview.unlink()
                except OSError:
                    pass
        for snapshot in snapshots:
            try:
                snapshot.unlink()
            except OSError:
                pass

    def _forward_output():
        try:
            if proc.stdout is None:
                return
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    print(line, flush=True)
                    if "Saved preview snapshot" in line:
                        _cleanup_live_preview_snapshots()
        finally:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

    reader = threading.Thread(target=_forward_output, daemon=True)
    reader.start()
    while proc.poll() is None:
        if stop_file is not None and stop_file.exists():
            interrupted = True
            print("Stop requested. Ending internal build after the latest saved checkpoint...", flush=True)
            try:
                proc.terminate()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            break
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue
    reader.join(timeout=2)
    _cleanup_live_preview_snapshots()
    if not interrupted and proc.returncode not in (0, None):
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return interrupted


def select_candidate(results: list[dict], tolerance: float) -> tuple[dict, dict]:
    best_accuracy = min(results, key=lambda item: item["error"])
    if tolerance <= 0:
        return best_accuracy, best_accuracy
    threshold = best_accuracy["error"] * (1.0 + max(0.0, tolerance))
    within = [item for item in results if item["error"] <= threshold]
    selected = min(within, key=lambda item: (item["final_drawables"], item["error"]))
    return best_accuracy, selected


def select_top_checkpoint_indices(records: list[dict], limit: int) -> set[int]:
    if limit <= 0 or len(records) <= limit:
        return set(range(len(records)))
    selected = {
        int(item["index"])
        for item in sorted(records, key=lambda item: (item["base_error"], item["raw_drawables"]))[:limit]
    }
    latest = max(records, key=lambda item: (item["raw_drawables"], item["candidate"]))
    selected.add(int(latest["index"]))
    return selected


def replace_atomic(temp_path: Path, destination: Path) -> None:
    last_error = None
    for attempt in range(6):
        try:
            os.replace(temp_path, destination)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(payload, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        replace_atomic(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def save_png(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        image.save(temp_path, format="PNG")
        with temp_path.open("r+b") as output:
            os.fsync(output.fileno())
        replace_atomic(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def require_saved_file(path: Path, label: str) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RuntimeError(f"{label} was not saved: {path}") from exc
    if size <= 0:
        raise RuntimeError(f"{label} was saved as an empty file: {path}")


def ensure_source_copy(source_path: Path, out_dir: Path) -> Path | None:
    dest = out_dir / source_path.name
    if dest.exists():
        return dest
    try:
        shutil.copy2(source_path, dest)
        return dest
    except OSError:
        return None


def main() -> int:
    args = parse_args()
    image_path = Path(args.image).expanduser().resolve()
    settings_path = Path(args.settings).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not image_path.is_file():
        print(f"Missing image: {image_path}", file=sys.stderr)
        return 1
    if not settings_path.is_file():
        print(f"Missing settings file: {settings_path}", file=sys.stderr)
        return 1
    if not args.finalize_only and not GENERATOR_BIN.is_file():
        print(f"Missing generator binary: {GENERATOR_BIN}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = out_dir / CHECKPOINTS_DIR_NAME
    finals_dir = out_dir / FINALS_DIR_NAME
    reports_dir = out_dir / REPORTS_DIR_NAME
    previews_dir = out_dir / PREVIEWS_DIR_NAME
    for folder in (checkpoint_dir, finals_dir, reports_dir, previews_dir):
        folder.mkdir(parents=True, exist_ok=True)
    stem = stem_from_image(image_path)
    source_copy_path = ensure_source_copy(image_path, out_dir)
    stop_file = Path(args.stop_file).expanduser().resolve() if args.stop_file else None
    if stop_file is not None:
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        if stop_file.exists():
            try:
                stop_file.unlink()
            except OSError:
                pass

    base_settings = parse_ini(settings_path)
    run_metadata = load_run_metadata(args.run_metadata)
    target_shapes = args.target_shapes or int(base_settings.get("stopAt", "3000"))
    if target_shapes < 1:
        print("target shape count must be positive", file=sys.stderr)
        return 1

    reserved_import_layers = max(0, min(int(args.reserved_import_layers), max(0, target_shapes - 1)))
    drawable_target_shapes = max(1, target_shapes - reserved_import_layers)
    overshoot_extra = min(args.overshoot_max_extra, max(0, int(math.ceil(target_shapes * max(0.0, args.overshoot_ratio - 1.0)))))
    if overshoot_extra == 0 and args.overshoot_ratio > 1.0:
        overshoot_extra = min(args.overshoot_max_extra, max(1, int(round(target_shapes * 0.08))))
    raw_stop = target_shapes + overshoot_extra
    shape_mode = str(base_settings.get("shapeMode", "")).strip().lower()
    force_opaque_shapes = parse_bool(base_settings.get("forceOpaqueShapes"), False)
    logo_hard_edges = parse_bool(base_settings.get("logoHardEdges"), False)
    prefer_smooth_repair = (
        shape_mode in {"mixed_soft_detail", "mixed_character_art", "mixed_smart_detail"}
        and args.preprocess_mode == "none"
    )

    v2_settings_path = reports_dir / f"{stem}.v2.settings.ini"
    live_preview_every = max(1, int(args.live_preview_every or 100))
    write_v2_settings(base_settings, v2_settings_path, target_shapes, raw_stop, args.checkpoint_step, live_preview_every)

    max_resolution = int(base_settings.get("maxResolution", "0") or 0)
    source_rgba = resize_source_for_generation(image_path, max_resolution)
    source_rgba, alpha_cleanup = remove_alpha_fringe_noise(source_rgba)
    art_profile = source_art_profile(source_rgba)
    prepared_rgba = apply_logo_hard_edges(source_rgba) if logo_hard_edges else source_rgba
    processed_rgba = apply_preprocess(prepared_rgba, args.preprocess_mode)
    detail_heatmap = None
    detail_heatmap_output_path = None
    detail_guided_output_path = None
    detail_strength = float(np.clip(args.detail_heatmap_strength, 0.0, 1.0))
    if args.detail_heatmap_mode == "auto":
        detail_heatmap = build_detail_heatmap(processed_rgba)
        detail_heatmap_output_path = previews_dir / f"{stem}.detail-heatmap.png"
        Image.fromarray(heatmap_to_rgba(detail_heatmap, processed_rgba), mode="RGBA").save(detail_heatmap_output_path)
        if detail_strength > 0:
            processed_rgba = apply_detail_guidance(processed_rgba, detail_heatmap, detail_strength)
            detail_guided_output_path = previews_dir / f"{stem}.detail-guided.png"
            Image.fromarray(np.clip(processed_rgba, 0, 255).astype(np.uint8), mode="RGBA").save(detail_guided_output_path)
    generation_image_path = image_path
    preprocess_output_path = None
    if alpha_cleanup.get("changed") or logo_hard_edges or args.preprocess_mode != "none" or detail_guided_output_path is not None:
        prep_parts = []
        if alpha_cleanup.get("changed"):
            prep_parts.append("alpha-clean")
        if logo_hard_edges:
            prep_parts.append("logo-edges")
        if args.preprocess_mode != "none":
            prep_parts.append(args.preprocess_mode.replace("_", "-"))
        if detail_guided_output_path is not None:
            prep_parts.append("detail-guided")
        preprocess_output_path = previews_dir / f"{stem}.{'-'.join(prep_parts)}.png"
        Image.fromarray(np.clip(processed_rgba, 0, 255).astype(np.uint8), mode="RGBA").save(preprocess_output_path)
        generation_image_path = preprocess_output_path

    print(f"Building internal base geometry for {image_path.name}")
    print(f"Target template layers: {target_shapes}")
    if reserved_import_layers:
        print(f"Target drawable shapes: {drawable_target_shapes} ({target_shapes} - {reserved_import_layers} reserved import layer(s))")
    else:
        print(f"Target drawable shapes: {drawable_target_shapes} (no reserved import layers)")
    if raw_stop > target_shapes:
        print(f"Internal build stop:    {raw_stop} ({target_shapes} target + {overshoot_extra} overshoot)")
    else:
        print(f"Internal build stop:    {raw_stop}")
    print(f"Using settings:         {settings_path}")
    print(f"Luma Prep mode:         {args.preprocess_mode}")
    print(f"Detail Heatmap:         {args.detail_heatmap_mode} strength={detail_strength:.2f}")
    if alpha_cleanup.get("changed"):
        print(
            "Alpha cleanup:         removed "
            f"{alpha_cleanup.get('removed_pixels')} low-alpha fringe pixel(s) "
            f"({float(alpha_cleanup.get('removed_fraction') or 0.0) * 100.0:.3f}%)",
            flush=True,
        )
    else:
        print("Alpha cleanup:         no low-alpha fringe cleanup needed")
    print(f"Logo edge prep:         {logo_hard_edges}")
    print(f"Force opaque shapes:   {force_opaque_shapes}")
    print(f"Live preview every:     {live_preview_every} layer(s)")
    print(f"Source profile:         {art_profile['category']}")
    print(f"Source recommendation:  {art_profile['recommendation']}")
    if preprocess_output_path is not None:
        print(f"Preprocessed image:     {preprocess_output_path}")
    if detail_heatmap_output_path is not None:
        print(f"Detail Heatmap preview: {detail_heatmap_output_path}")
    if detail_guided_output_path is not None:
        print(f"Detail-guided image:    {detail_guided_output_path}")
    raw_generator_error = None
    if args.finalize_only:
        interrupted = True
        print("RESUME FINALIZE CHECKPOINTS. Reusing existing internal checkpoints; no raw generation will run.", flush=True)
    else:
        try:
            interrupted = run_generator(
                generation_image_path,
                v2_settings_path,
                checkpoint_dir,
                previews_dir,
                stem,
                stop_file=stop_file,
                seed=int(args.seed or 0),
            )
        except Exception as exc:
            recoverable = collect_candidate_jsons(checkpoint_dir, stem, max_checkpoint=raw_stop)
            if not recoverable:
                raise
            interrupted = True
            raw_generator_error = f"{type(exc).__name__}: {exc}"
            print(
                "RAW GENERATOR STOPPED ABNORMALLY. Recovering every complete checkpoint instead of losing the run: "
                f"{raw_generator_error}",
                flush=True,
            )
        print("INTERNAL BUILD COMPLETE. Finalize Checkpoints is starting now; the saved checkpoints are protected.", flush=True)
    print("Finalized JSONs are the only import-ready vinyl files. Internal checkpoints are not final.", flush=True)

    requested_checkpoints = parse_save_points(base_settings.get("saveAt", ""), raw_stop)
    synthesize_missing_checkpoints(checkpoint_dir, stem, requested_checkpoints, raw_stop)
    raw_candidates = collect_candidate_jsons(checkpoint_dir, stem, max_checkpoint=raw_stop)
    if not raw_candidates:
        print("No internal checkpoint JSON outputs found after base build.", file=sys.stderr)
        return 1
    if interrupted:
        print("Continuing Finalize Checkpoints from interrupted internal checkpoints.")
    print(
        f"Finalize Checkpoints: found {len(raw_candidates)} internal checkpoint JSON(s). "
        "Scoring and preparing final import files...",
        flush=True,
    )

    # Final scoring, pruning, preview rendering, and Edge Repair compare
    # checkpoints against the original source. Luma Prep is only a raw-build
    # helper; using it here makes fine details look artificially soft.
    score_rgba = downscale_rgba(source_rgba, args.score_size)
    score_importance = build_importance_map(score_rgba)
    if detail_heatmap is not None:
        score_heatmap = cv2.resize(detail_heatmap, (score_rgba.shape[1], score_rgba.shape[0]), interpolation=cv2.INTER_AREA)
        score_importance = np.clip(score_importance * (1.0 + score_heatmap * (detail_strength * 0.85)), 0.55, 7.0).astype(np.float32)
    print(
        "V5 detail weighting: Finalize Checkpoints protects edges, alpha cuts, saturated detail, and linework during scoring/cleanup.",
        flush=True,
    )
    enforce_canvas_boundary = target_has_alpha_boundary(source_rgba)
    if enforce_canvas_boundary:
        print(
            "Canvas boundary: transparent source detected; transparent outer edge spans are constrained, cropped visible edge spans are preserved.",
            flush=True,
        )
    else:
        print(
            "Canvas boundary: no source alpha transparency detected; outer PNG edges are left unconstrained.",
            flush=True,
        )

    candidate_records = []
    repair_enabled = bool(args.enable_repair and not args.disable_refine)
    for index, candidate_path in enumerate(raw_candidates):
        print(f"Finalize scoring {index + 1}/{len(raw_candidates)}: {candidate_path.name}", flush=True)
        try:
            payload = normalize_payload(candidate_path)
            background = background_shape(payload)
            drawables = drawable_shapes(payload)
            raw_generator_name = str(payload.get("generator", "") or "")
            is_modern_raw = raw_generator_name.lower().startswith(("kloudysgeneratorv6", "kloudysgeneratorv7"))
            raw_count = len(drawables)
            checkpoint_number = raw_checkpoint_number(candidate_path, stem)
            checkpoint_tag = checkpoint_tag_for_candidate(candidate_path, stem)
            if checkpoint_number is not None and checkpoint_number > raw_stop:
                if checkpoint_number == raw_stop + 1 and raw_count <= raw_stop:
                    checkpoint_tag = str(raw_stop)
                    print(
                        f"Normalizing checkpoint name {candidate_path.name} to {checkpoint_tag} "
                        f"because it contains {raw_count} drawable layers.",
                        flush=True,
                    )
                else:
                    print(
                        f"Checkpoint {candidate_path.name} is above requested raw stop {raw_stop}; "
                        "Finalize Checkpoints will cap the import output.",
                        flush=True,
                    )

            full_w, full_h = canvas_size_from_payload(payload)
            score_h, score_w = score_rgba.shape[:2]
            sx = score_w / float(max(1, full_w))
            sy = score_h / float(max(1, full_h))

            scaled_bg = dict(background)
            bg_color = list(background.get("color", [0, 0, 0, 0]))
            scaled_bg["color"] = bg_color

            if raw_count > raw_stop:
                print(
                    f"Checkpoint {candidate_path.name} has {raw_count} drawable layers, above raw stop {raw_stop}; "
                    "Finalize Checkpoints will cap it before import output.",
                    flush=True,
                )

            scaled_drawables = [scale_shape(shape, sx, sy) for shape in drawables]
            should_prune = args.enable_prune or raw_count > drawable_target_shapes
            if should_prune:
                kept_scaled, error = prune_to_target(
                    scaled_bg,
                    scaled_drawables,
                    score_rgba,
                    drawable_target_shapes,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    importance_map=score_importance,
                )
                kept_indices = []
                scaled_map = {id(shape): idx for idx, shape in enumerate(scaled_drawables)}
                for kept_shape in kept_scaled:
                    kept_indices.append(scaled_map[id(kept_shape)])
                kept_original = [drawables[idx] for idx in kept_indices]
                final_count = len(kept_original)
            else:
                _, _, _, _, _, total_error, scored_pixels = render_and_score(
                    scaled_bg,
                    scaled_drawables,
                    score_rgba,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    importance_map=score_importance,
                )
                error = normalized_error(total_error, scored_pixels)
                kept_original = list(drawables)
                final_count = len(kept_original)
        except Exception as exc:
            print(
                f"Skipping candidate {candidate_path.name}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            continue
        candidate_records.append(
            {
                "index": index,
                "candidate_path": candidate_path,
                "candidate": candidate_path.name,
                "background": background,
                "drawables": drawables,
                "raw_drawables": raw_count,
                "base_drawables": final_count,
                "base_shapes": kept_original,
                "base_error": error,
                "canvas_size": [full_w, full_h],
                "scale": [sx, sy],
                "checkpoint_tag": checkpoint_tag,
                "raw_generator": raw_generator_name,
                "v6_raw": is_modern_raw,
            }
        )
    if not candidate_records:
        print("No usable internal checkpoints remained after finalization validation.", file=sys.stderr)
        return 1

    repair_indices = select_top_checkpoint_indices(candidate_records, args.repair_candidate_limit) if repair_enabled else set()
    preview_indices = select_top_checkpoint_indices(candidate_records, args.preview_candidate_limit)
    if repair_enabled:
        skipped = len(candidate_records) - len(repair_indices)
        if skipped > 0:
            print(
                f"Edge Repair: repairing {len(repair_indices)}/{len(candidate_records)} finalized checkpoints "
                f"(best scored + latest), skipping {skipped} lower-ranked checkpoints.",
                flush=True,
            )
        else:
            print(f"Edge Repair: repairing all {len(candidate_records)} finalized checkpoints.", flush=True)
    skipped_previews = len(candidate_records) - len(preview_indices)
    if skipped_previews > 0:
        print(
            f"Final previews: rendering {len(preview_indices)}/{len(candidate_records)} preview PNGs; "
            "other JSONs preview on demand in the browser.",
            flush=True,
        )

    results = []
    print(
        f"Finalize Checkpoints: writing import-ready JSONs for {len(candidate_records)} candidate(s)...",
        flush=True,
    )
    for result_index, record in enumerate(candidate_records, start=1):
        candidate_path = record["candidate_path"]
        print(f"Finalizing import JSON {result_index}/{len(candidate_records)}: {candidate_path.name}", flush=True)
        background = record["background"]
        raw_count = record["raw_drawables"]
        full_w, full_h = record["canvas_size"]
        sx, sy = record["scale"]
        refinement = {
            "enabled": False,
            "touched": 0,
            "improvements": 0,
            "before": record["base_error"],
            "after": record["base_error"],
        }
        final_shapes = list(record["base_shapes"])
        final_error = record["base_error"]
        repair_applied = repair_enabled and (not bool(record.get("v6_raw"))) and int(record["index"]) in repair_indices
        if repair_enabled and bool(record.get("v6_raw")) and int(record["index"]) in repair_indices:
            refinement = dict(refinement)
            refinement["skipped"] = "Modern raw geometry has its own prediction/detail phases; legacy Edge Repair is disabled for V7/V6 candidates."
        if repair_applied:
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                refined_scaled, refined_error, refinement = repair_shapes(
                    scaled_bg,
                    scaled_selected,
                    score_rgba,
                    max_shapes=18 if enforce_canvas_boundary else 8,
                    rounds=2 if enforce_canvas_boundary else 1,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    prefer_smooth_shapes=prefer_smooth_repair,
                    importance_map=score_importance,
                    allow_alpha_repair=(not force_opaque_shapes and not prefer_smooth_repair),
                )
                final_shapes = [unscale_shape(shape, sx, sy) for shape in refined_scaled]
                if force_opaque_shapes:
                    final_shapes = force_opaque_drawables(final_shapes)
                final_error = refined_error
                refinement = dict(refinement)
                refinement["prefer_smooth_shapes"] = prefer_smooth_repair
                refinement["force_opaque_shapes"] = force_opaque_shapes
            except Exception as exc:
                refinement = dict(refinement)
                refinement.update({
                    "enabled": True,
                    "failed": True,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                print(
                    f"Edge Repair failed for {candidate_path.name}: {type(exc).__name__}: {exc}. "
                    "Using the pruned base candidate.",
                    file=sys.stderr,
                    flush=True,
                )
        if enforce_canvas_boundary:
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                bounded_scaled, bounded_error, boundary_summary = enforce_shapes_inside_canvas(
                    scaled_bg,
                    scaled_selected,
                    score_rgba,
                    importance_map=score_importance,
                )
                if boundary_summary.get("fitted", 0):
                    final_shapes = [unscale_shape(shape, sx, sy) for shape in bounded_scaled]
                    final_error = bounded_error
                refinement = dict(refinement)
                refinement["canvas_boundary"] = boundary_summary
            except Exception as exc:
                refinement = dict(refinement)
                refinement["canvas_boundary_failed"] = f"{type(exc).__name__}: {exc}"
        try:
            scaled_bg = dict(background)
            scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
            if force_opaque_shapes:
                final_shapes = force_opaque_drawables(final_shapes)
            scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
            flat_color_summary = {"enabled": False, "skipped": "not a flat opaque preset"}
            should_stabilize_flat_colors = bool(
                force_opaque_shapes
                and (
                    args.preprocess_mode == "luma_bands"
                    or any(token in shape_mode for token in ("flat", "edge", "logo", "livery"))
                )
            )
            if should_stabilize_flat_colors:
                stabilized_scaled, flat_color_summary = stabilize_flat_region_colors(
                    scaled_selected,
                    score_rgba,
                    force_opaque=True,
                )
                if flat_color_summary.get("changed", 0):
                    final_shapes = [unscale_shape(shape, sx, sy) for shape in stabilized_scaled]
                    scaled_selected = stabilized_scaled
                    print(
                        f"Flat Color Stabilizer: snapped {flat_color_summary['changed']} layer color(s) "
                        f"toward dominant source regions in {candidate_path.name}.",
                        flush=True,
                    )
            refinement = dict(refinement)
            refinement["flat_color_stabilization"] = flat_color_summary
            cleanup_budget = max(0, len(final_shapes) - drawable_target_shapes)
            cleaned_scaled, cleaned_error, covered_cleanup = remove_fully_covered_layers(
                scaled_bg,
                scaled_selected,
                score_rgba,
                enforce_canvas_boundary=enforce_canvas_boundary,
                importance_map=score_importance,
                removal_limit=cleanup_budget,
            )
            final_error = cleaned_error
            if covered_cleanup.get("removed", 0):
                final_shapes = [unscale_shape(shape, sx, sy) for shape in cleaned_scaled]
                print(
                    f"Covered Layer Cleanup: removed {covered_cleanup['removed']} fully hidden layer(s) "
                    f"from {candidate_path.name}.",
                    flush=True,
                )
            refinement = dict(refinement)
            refinement["covered_layer_cleanup"] = covered_cleanup
        except Exception as exc:
            refinement = dict(refinement)
            refinement["covered_layer_cleanup_failed"] = f"{type(exc).__name__}: {exc}"
        if len(final_shapes) > drawable_target_shapes:
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                capped_scaled, capped_error = prune_to_target(
                    scaled_bg,
                    scaled_selected,
                    score_rgba,
                    drawable_target_shapes,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    importance_map=score_importance,
                )
                final_shapes = [unscale_shape(shape, sx, sy) for shape in capped_scaled]
                final_error = capped_error
            except Exception as exc:
                final_shapes = final_shapes[:drawable_target_shapes]
                final_error = record["base_error"]
                refinement = dict(refinement)
                refinement["hard_cap_failed"] = f"{type(exc).__name__}: {exc}"
            refinement = dict(refinement)
            refinement["after_hard_cap"] = final_error
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                cleaned_scaled, cleaned_error, post_cap_cleanup = remove_fully_covered_layers(
                    scaled_bg,
                    scaled_selected,
                    score_rgba,
                    enforce_canvas_boundary=enforce_canvas_boundary,
                    importance_map=score_importance,
                    removal_limit=0,
                )
                if post_cap_cleanup.get("removed", 0):
                    final_shapes = [unscale_shape(shape, sx, sy) for shape in cleaned_scaled]
                    final_error = cleaned_error
                    print(
                        f"Covered Layer Cleanup after cap: removed {post_cap_cleanup['removed']} fully hidden layer(s) "
                        f"from {candidate_path.name}.",
                        flush=True,
                    )
                refinement["covered_layer_cleanup_after_cap"] = post_cap_cleanup
            except Exception as exc:
                refinement["covered_layer_cleanup_after_cap_failed"] = f"{type(exc).__name__}: {exc}"
        checkpoint_tag = record["checkpoint_tag"]
        final_json_path = v2_json_path_for_tag(out_dir, stem, checkpoint_tag)
        final_preview_path = v2_preview_path_for_tag(out_dir, stem, checkpoint_tag)
        if force_opaque_shapes:
            final_shapes = force_opaque_drawables(final_shapes)
        final_payload = {"shapes": final_shapes}
        save_json(final_json_path, final_payload)
        require_saved_file(final_json_path, "Final checkpoint JSON")
        preview_written = int(record["index"]) in preview_indices
        if preview_written:
            preview = render_import_preview(background, final_shapes, full_w, full_h)
            save_png(final_preview_path, preview)
            require_saved_file(final_preview_path, "Final checkpoint preview")
        results.append(
            {
                "candidate": candidate_path.name,
                "candidate_path": str(candidate_path),
                "raw_drawables": raw_count,
                "final_drawables": len(final_shapes),
                "background_dropped": True,
                "final_import_layers": len(final_shapes),
                "error": final_error,
                "base_error": record["base_error"],
                "background": background,
                "kept_shapes": final_shapes,
                "canvas_size": [full_w, full_h],
                "scale": [sx, sy],
                "refinement": refinement,
                "repair_applied": repair_applied,
                "v2_json": str(final_json_path),
                "v2_preview": str(final_preview_path),
                "preview_written": preview_written,
                "checkpoint_tag": checkpoint_tag,
            }
        )
        repair_label = "repaired" if repair_applied else ("repair skipped" if repair_enabled else "repair off")
        preview_label = "preview" if preview_written else "on-demand preview"
        print(
            f"Candidate {candidate_path.name}: raw={raw_count} final={len(final_shapes)} "
            f"error={final_error:.6f} ({repair_label}, {preview_label})"
        )

    best_accuracy = min(results, key=lambda item: item["error"])
    latest_checkpoint = max(results, key=lambda item: (item["raw_drawables"], item["candidate"]))

    report_path = reports_dir / f"{stem}.v2.report.json"
    preset = run_metadata.get("selected_profile") or {
        "path": str(settings_path),
        "values": dict(base_settings),
    }
    base_preset = run_metadata.get("base_profile")
    ui_overrides = run_metadata.get("ui_overrides", {})
    effective_settings = run_metadata.get("effective_settings", dict(base_settings))
    run_toggles = run_metadata.get("toggles", {
        "luma_bands": args.preprocess_mode == "luma_bands",
        "quality_overshoot": overshoot_extra > 0,
        "targeted_repair": repair_enabled,
    })
    generator_command_options = run_metadata.get("generator_command_options", {
        "target_shapes": str(target_shapes),
        "reserved_import_layers": str(reserved_import_layers),
        "checkpoint_step": str(args.checkpoint_step),
        "preprocess_mode": args.preprocess_mode,
        "overshoot_ratio": str(args.overshoot_ratio),
        "overshoot_max_extra": str(args.overshoot_max_extra),
        "repair_enabled": repair_enabled,
    })
    generator_command_options = dict(generator_command_options)
    generator_command_options["reserved_import_layers"] = str(reserved_import_layers)
    app_build = run_metadata.get("app_build") or app_build_info()
    app_version = run_metadata.get("app_version") or app_build.get("app_version") or "unknown"

    def report_candidate(item: dict) -> dict:
        return {
            "checkpoint_tag": item["checkpoint_tag"],
            "candidate": item["candidate"],
            "raw_drawables": item["raw_drawables"],
            "final_drawables": item["final_drawables"],
            "background_dropped": item.get("background_dropped", False),
            "final_import_layers": item.get("final_import_layers", item["final_drawables"]),
            "shape_types": shape_type_counts(item.get("kept_shapes", [])),
            "error": item["error"],
            "base_error": item["base_error"],
            "repair_applied": item["repair_applied"],
            "preview_written": item["preview_written"],
            "v2_json": item["v2_json"],
            "v2_preview": item["v2_preview"],
            "refinement": sorted_mapping(item["refinement"]),
        }

    candidates_by_checkpoint = [
        report_candidate(item)
        for item in sorted(results, key=lambda item: (item["raw_drawables"], item["candidate"]))
    ]
    candidates_by_accuracy = [
        report_candidate(item)
        for item in sorted(results, key=lambda item: (item["error"], item["final_drawables"], item["raw_drawables"]))
    ]

    report = {
        "app_version": app_version,
        "app_build": sorted_mapping(app_build),
        "source_image": str(image_path),
        "source_copy": str(source_copy_path) if source_copy_path is not None else None,
        "settings": {
            "app_build": sorted_mapping(app_build),
            "preset": sorted_mapping(preset),
            "base_preset": sorted_mapping(base_preset),
            "ui_overrides": sorted_mapping(ui_overrides),
            "effective_settings": sorted_mapping(effective_settings),
            "toggles": sorted_mapping(run_toggles),
            "command_options": sorted_mapping(generator_command_options),
            "settings_path": str(settings_path),
            "v2_settings_path": str(v2_settings_path),
            "run_metadata": sorted_mapping(run_metadata),
        },
        "preprocess": {
            "mode": args.preprocess_mode,
            "output": str(preprocess_output_path) if preprocess_output_path is not None else None,
            "alpha_cleanup": sorted_mapping(alpha_cleanup),
            "detail_heatmap": {
                "mode": args.detail_heatmap_mode,
                "strength": detail_strength,
                "heatmap_output": str(detail_heatmap_output_path) if detail_heatmap_output_path is not None else None,
                "guided_output": str(detail_guided_output_path) if detail_guided_output_path is not None else None,
            },
        },
        "source_art_profile": sorted_mapping(art_profile),
        "preprocess_mode": args.preprocess_mode,
        "preprocess_output": str(preprocess_output_path) if preprocess_output_path is not None else None,
        "base_settings": str(settings_path),
        "v2_settings": str(v2_settings_path),
        "target_shapes": target_shapes,
        "drawable_target_shapes": drawable_target_shapes,
        "raw_stop": raw_stop,
        "overshoot_extra": overshoot_extra,
        "interrupted": interrupted,
        "finalize_only_recovery": bool(args.finalize_only),
        "raw_generator_error": raw_generator_error,
        "score_size": args.score_size,
        "v5_detail_weighting": True,
        "detail_heatmap_weighting": detail_heatmap is not None,
        "live_preview_every": live_preview_every,
        "prefer_smooth_repair": prefer_smooth_repair,
        "efficiency_tolerance": args.efficiency_tolerance,
        "prune_enabled": args.enable_prune,
        "refine_enabled": repair_enabled,
        "repair_candidate_limit": args.repair_candidate_limit,
        "preview_candidate_limit": args.preview_candidate_limit,
        "best_accuracy": {
            "candidate": best_accuracy["candidate"],
            "checkpoint_tag": best_accuracy["checkpoint_tag"],
            "raw_drawables": best_accuracy["raw_drawables"],
            "final_drawables": best_accuracy["final_drawables"],
            "background_dropped": best_accuracy.get("background_dropped", False),
            "final_import_layers": best_accuracy.get("final_import_layers", best_accuracy["final_drawables"]),
            "error": best_accuracy["error"],
            "base_error": best_accuracy["base_error"],
            "repair_applied": best_accuracy["repair_applied"],
            "v2_json": best_accuracy["v2_json"],
            "v2_preview": best_accuracy["v2_preview"],
            "preview_written": best_accuracy["preview_written"],
        },
        "latest_checkpoint_v2": {
            "candidate": latest_checkpoint["candidate"],
            "checkpoint_tag": latest_checkpoint["checkpoint_tag"],
            "raw_drawables": latest_checkpoint["raw_drawables"],
            "final_drawables": latest_checkpoint["final_drawables"],
            "background_dropped": latest_checkpoint.get("background_dropped", False),
            "final_import_layers": latest_checkpoint.get("final_import_layers", latest_checkpoint["final_drawables"]),
            "error": latest_checkpoint["error"],
            "base_error": latest_checkpoint["base_error"],
            "repair_applied": latest_checkpoint["repair_applied"],
            "v2_json": latest_checkpoint["v2_json"],
            "v2_preview": latest_checkpoint["v2_preview"],
            "preview_written": latest_checkpoint["preview_written"],
        },
        "candidates": candidates_by_checkpoint,
        "candidates_by_accuracy": candidates_by_accuracy,
    }
    save_json(report_path, report)

    print()
    print(
        f"Best accuracy: {best_accuracy['candidate']} -> "
        f"{best_accuracy.get('final_import_layers', best_accuracy['final_drawables'])} import layers "
        f"({best_accuracy['final_drawables']} drawable), error {best_accuracy['error']:.6f}"
    )
    print(
        f"Latest finalized checkpoint: {latest_checkpoint['candidate']} -> "
        f"{latest_checkpoint.get('final_import_layers', latest_checkpoint['final_drawables'])} import layers "
        f"({latest_checkpoint['final_drawables']} drawable), error {latest_checkpoint['error']:.6f}"
    )
    for item in sorted(results, key=lambda entry: (entry["raw_drawables"], entry["candidate"])):
        print(f"Final JSON:     {item['v2_json']}")
        print(f"Final preview:  {item['v2_preview']}")
    print(f"Report:         {report_path}")
    if args.finalize_only:
        print("Recovered import-ready outputs from the existing checkpoints without rerunning Genesis.")
    elif raw_generator_error:
        print("Genesis stopped abnormally, but every usable completed checkpoint was finalized and saved.")
    elif interrupted:
        print("Stopped early by request. Every usable checkpoint was finalized, including the latest saved checkpoint.")
    else:
        print("Finalized outputs written for every usable checkpoint. Pick the one you want in Import Final JSON.")
    print("FINALIZE CHECKPOINTS COMPLETE. Import-ready JSONs are now available in the Final JSON browser.", flush=True)

    if not args.keep_temp_settings:
        try:
            v2_settings_path.unlink()
        except OSError:
            pass
    if stop_file is not None and stop_file.exists():
        try:
            stop_file.unlink()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
