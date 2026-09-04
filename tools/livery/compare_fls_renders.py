from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.cgroup.forza_source_decoder import (  # noqa: E402
    LIVERY_SECTION_NAMES,
    unwrap_forza_container,
)
from tools.livery.package import (  # noqa: E402
    _decode_livery_contract,
    _render_livery_sections,
)


FLS_SECTION_FILES = {
    "Front": "front.png",
    "Back": "back.png",
    "Top": "top.png",
    "Left": "left.png",
    "Right": "right.png",
    "Spoiler": "spoiler.png",
    "FrontWindshield": "frontWindow.png",
    "BackWindshield": "backWindow.png",
    "TopWindow": "topWindow.png",
    "LeftWindow": "leftWindow.png",
    "RightWindow": "rightWindow.png",
}
COMPARISON_REVISION = 2


def _canonical_shape_word(value: Any) -> int:
    word = int(value or 0) & 0xFFFF
    return {
        0x07D0: 0x07D1,
        0x0BB8: 0x0BB9,
    }.get(word, word)


def _kfps_world_matrix(layer: dict[str, Any]) -> list[float]:
    data = list(layer.get("data") or [])
    if len(data) < 6:
        return []
    x, y, sx, sy, rotation, skew = (float(value) for value in data[:6])
    radians = math.radians(rotation)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return [
        cosine * sx,
        (cosine * skew - sine) * sy,
        x,
        sine * sx,
        (sine * skew + cosine) * sy,
        y,
        0.0,
        0.0,
        1.0,
    ]


def _semantic_leaf_mismatches(oracle: dict[str, Any], layer: dict[str, Any]) -> list[str]:
    mismatched: list[str] = []
    oracle_raster = bool(oracle.get("raster"))
    layer_raster = bool(layer.get("is_raster_logo"))
    if oracle_raster != layer_raster:
        mismatched.append("raster")
    elif oracle_raster:
        if int(oracle.get("raster_id") or 0) != int(layer.get("raster_id") or 0):
            mismatched.append("raster_id")
    elif _canonical_shape_word(oracle.get("shape_id")) != _canonical_shape_word(
        layer.get("type_word")
    ):
        mismatched.append("shape_id")
    if bool(oracle.get("mask")) != bool(layer.get("mask")):
        mismatched.append("mask")
    layer_rgba = [int(channel) for channel in (layer.get("color") or [0, 0, 0, 0])]
    layer_bgra = [layer_rgba[2], layer_rgba[1], layer_rgba[0], layer_rgba[3]]
    if list(oracle.get("color_bgra") or []) != layer_bgra:
        mismatched.append("color")
    oracle_matrix = [float(value) for value in (oracle.get("world_matrix") or [])]
    layer_matrix = _kfps_world_matrix(layer)
    if len(oracle_matrix) != 9 or len(layer_matrix) != 9 or max(
        abs(first - second) for first, second in zip(oracle_matrix, layer_matrix, strict=True)
    ) > 1e-5:
        mismatched.append("world_matrix")
    return mismatched


def _safe_stem(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return normalized[:80] or "unnamed"


def _load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def _orient(image: np.ndarray, mode: str) -> np.ndarray:
    if mode == "flip_x":
        return image[:, ::-1]
    if mode == "flip_y":
        return image[::-1]
    if mode == "rotate_180":
        return image[::-1, ::-1]
    return image


def _alpha_iou(first: np.ndarray, second: np.ndarray) -> float:
    first_visible = first[..., 3] > 0
    second_visible = second[..., 3] > 0
    union = np.count_nonzero(first_visible | second_visible)
    if union == 0:
        return 1.0
    return float(np.count_nonzero(first_visible & second_visible) / union)


def _checker_composite(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    yy, xx = np.indices((height, width))
    tile = ((xx // 24 + yy // 24) & 1)[..., None]
    background = np.where(
        tile,
        np.array([72, 72, 72], dtype=np.float32),
        np.array([42, 42, 42], dtype=np.float32),
    )
    alpha = image[..., 3:4].astype(np.float32) / 255.0
    return np.clip(image[..., :3] * alpha + background * (1.0 - alpha), 0, 255).astype(np.uint8)


def _compare_section(
    section: str,
    fls_path: Path,
    kfps_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    fls = _load_rgba(fls_path)
    kfps = _load_rgba(kfps_path)
    if fls.shape != kfps.shape:
        raise RuntimeError(f"{section}: image sizes do not match ({fls.shape} vs {kfps.shape})")

    orientation_scores = {
        mode: _alpha_iou(_orient(fls, mode), kfps)
        for mode in ("identity", "flip_x", "flip_y", "rotate_180")
    }
    fls_composite = _checker_composite(fls)
    kfps_composite = _checker_composite(kfps)
    visible_union = (fls[..., 3] > 0) | (kfps[..., 3] > 0)
    rgb_delta = np.abs(fls_composite.astype(np.int16) - kfps_composite.astype(np.int16))
    alpha_delta = np.abs(fls[..., 3].astype(np.int16) - kfps[..., 3].astype(np.int16))
    max_delta = rgb_delta.max(axis=2).astype(np.uint8)
    heatmap = np.zeros((*max_delta.shape, 3), dtype=np.uint8)
    heatmap[..., 0] = max_delta
    heatmap[..., 1] = max_delta // 5

    display_size = (1024, 512)
    panels = (
        Image.fromarray(fls_composite).resize(display_size, Image.Resampling.LANCZOS),
        Image.fromarray(kfps_composite).resize(display_size, Image.Resampling.LANCZOS),
        Image.fromarray(heatmap).resize(display_size, Image.Resampling.LANCZOS),
    )
    sheet = Image.new("RGB", (display_size[0] * 3, display_size[1] + 36), (15, 15, 18))
    draw = ImageDraw.Draw(sheet)
    for index, (panel, label) in enumerate(
        zip(panels, ("FLS oracle", "KFPS current", "absolute difference"), strict=True)
    ):
        x = index * display_size[0]
        sheet.paste(panel, (x, 36))
        draw.text((x + 12, 10), f"{section}: {label}", fill="white")
    sheet.save(output_path)

    return {
        "section": section,
        "alpha_iou": orientation_scores["identity"],
        "best_orientation": max(orientation_scores, key=orientation_scores.get),
        "orientation_scores": orientation_scores,
        "checker_rgb_mae": float(rgb_delta.mean()),
        "visible_union_rgb_mae": float(rgb_delta[visible_union].mean()) if visible_union.any() else 0.0,
        "alpha_mae": float(alpha_delta.mean()),
        "fls_visible_pixels": int(np.count_nonzero(fls[..., 3])),
        "kfps_visible_pixels": int(np.count_nonzero(kfps[..., 3])),
        "comparison": output_path.name,
    }


def _run_fls(
    *,
    executable: Path,
    fls_root: Path,
    qt_bin: Path | None,
    source: Path,
    output: Path,
    semantic: bool,
    timeout_seconds: float,
) -> str:
    environment = os.environ.copy()
    if qt_bin is not None:
        environment["PATH"] = str(qt_bin) + os.pathsep + environment.get("PATH", "")
        plugin_root = qt_bin / "plugins"
        platform_root = plugin_root / "platforms"
        if plugin_root.is_dir():
            environment["QT_PLUGIN_PATH"] = str(plugin_root)
        if platform_root.is_dir():
            environment["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_root)
    command = [str(executable), str(source), str(output), "2048", "1024"]
    if semantic:
        command.append("--semantic")
    try:
        completed = subprocess.run(
            command,
            cwd=fls_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        raise RuntimeError(
            f"Reference renderer timed out after {timeout_seconds:g} seconds.\n"
            f"stdout:\n{stdout or ''}\nstderr:\n{stderr or ''}"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"FLS oracle failed with exit code {completed.returncode}:\n"
            f"{completed.stdout}\n{completed.stderr}".strip()
        )
    return completed.stdout


def _render_kfps(source: Path, game_folder: Path, output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = unwrap_forza_container(source)
    contract, decode_report, counts, _ = _decode_livery_contract(payload)
    rendered, raster_verified, unresolved_raster_ids = _render_livery_sections(
        contract["layers"],
        game_folder=game_folder,
        strict_assets=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    for section, data in rendered.items():
        (output / f"{section}.png").write_bytes(data)
    return contract, {
        "declared_counts": dict(zip(LIVERY_SECTION_NAMES, counts, strict=True)),
        "decoded_layer_count": len(contract["layers"]),
        "decode_warnings": decode_report.get("warnings") or [],
        "raster_verified": raster_verified,
        "unresolved_raster_ids": unresolved_raster_ids,
    }


def _selected_records(manifest: dict[str, Any], titles: list[str], run_all: bool) -> list[dict[str, Any]]:
    records = list(manifest.get("liveries") or [])
    if run_all:
        return records
    wanted = {title.casefold() for title in titles}
    selected = [record for record in records if str(record.get("title") or "").casefold() in wanted]
    found = {str(record.get("title") or "").casefold() for record in selected}
    missing = sorted(wanted - found)
    if missing:
        raise RuntimeError("titles not found in catalog manifest: " + ", ".join(missing))
    return selected


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Differentially compare FLS and KFPS FH6 livery-section rendering."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fls-root", type=Path, required=True)
    parser.add_argument("--fls-renderer", type=Path, required=True)
    parser.add_argument("--qt-bin", type=Path)
    parser.add_argument("--game-folder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reference-timeout", type=float, default=180.0)
    args = parser.parse_args()
    if not args.all and not args.title:
        parser.error("choose at least one --title or use --all")
    if not math.isfinite(args.reference_timeout) or args.reference_timeout <= 0:
        parser.error("--reference-timeout must be a positive finite number")
    return args


def main() -> int:
    args = _parse_args()
    args.manifest = args.manifest.resolve()
    args.fls_root = args.fls_root.resolve()
    args.fls_renderer = args.fls_renderer.resolve()
    args.qt_bin = args.qt_bin.resolve() if args.qt_bin is not None else None
    args.game_folder = args.game_folder.resolve()
    args.output = args.output.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = _selected_records(manifest, args.title, args.all)
    args.output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        source = Path(record["source_path"])
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        title = str(record.get("title") or source.parent.name)
        result_root = args.output / f"{source_hash[:12]}-{_safe_stem(title)}"
        fls_output = result_root / "fls"
        kfps_output = result_root / "kfps"
        comparisons = result_root / "comparisons"
        comparisons.mkdir(parents=True, exist_ok=True)
        print(f"[{index}/{len(records)}] {title}", flush=True)

        report_path = result_root / "report.json"
        if args.resume and report_path.is_file():
            cached = json.loads(report_path.read_text(encoding="utf-8"))
            if int(cached.get("comparison_revision") or 0) == COMPARISON_REVISION:
                results.append(cached)
                continue

        stage = "reference_render"
        try:
            fls_log = _run_fls(
                executable=args.fls_renderer,
                fls_root=args.fls_root,
                qt_bin=args.qt_bin,
                source=source,
                output=fls_output,
                semantic=args.semantic,
                timeout_seconds=args.reference_timeout,
            )
            stage = "kfps_render"
            contract, kfps_report = _render_kfps(source, args.game_folder, kfps_output)
            stage = "reference_manifest"
            fls_manifest = json.loads(
                (fls_output / "manifest.json").read_text(encoding="utf-8")
            )
        except Exception as exc:
            result = {
                "comparison_revision": COMPARISON_REVISION,
                "status": "error",
                "stage": stage,
                "title": title,
                "source_path": str(source),
                "source_sha256": source_hash,
                "car_id": record.get("car_id"),
                "source_owned": bool(record.get("source_owned")),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            report_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
            )
            results.append(result)
            print(f"  failed stage={stage}: {exc}", flush=True)
            continue
        fls_counts = {
            str(section["name"]): int(section["logical_leaf_count"])
            for section in fls_manifest["sections"]
        }
        kfps_counts = {
            section: sum(1 for layer in contract["layers"] if layer.get("source_section") == section)
            for section in LIVERY_SECTION_NAMES
        }

        section_results = []
        for section in LIVERY_SECTION_NAMES:
            if fls_counts.get(section, 0) == 0 and kfps_counts.get(section, 0) == 0:
                continue
            fls_path = fls_output / FLS_SECTION_FILES[section]
            kfps_path = kfps_output / f"{section}.png"
            if not fls_path.is_file() or not kfps_path.is_file():
                section_results.append(
                    {
                        "section": section,
                        "error": "renderer output missing",
                        "fls_file": fls_path.is_file(),
                        "kfps_file": kfps_path.is_file(),
                    }
                )
                continue
            section_results.append(
                _compare_section(section, fls_path, kfps_path, comparisons / f"{section}.png")
            )

        count_mismatches = {
            section: {"fls": fls_counts.get(section, 0), "kfps": kfps_counts.get(section, 0)}
            for section in LIVERY_SECTION_NAMES
            if fls_counts.get(section, 0) != kfps_counts.get(section, 0)
        }
        declared_count_mismatches = {
            section: {
                "declared": int(kfps_report["declared_counts"].get(section, 0)),
                "decoded": kfps_counts.get(section, 0),
            }
            for section in LIVERY_SECTION_NAMES
            if int(kfps_report["declared_counts"].get(section, 0)) != kfps_counts.get(section, 0)
        }
        semantic_differences: dict[str, Any] = {}
        if args.semantic:
            fls_sections = {
                str(section["name"]): section
                for section in fls_manifest["sections"]
            }
            for section in LIVERY_SECTION_NAMES:
                fls_leaves = list(fls_sections.get(section, {}).get("leaves") or [])
                kfps_leaves = [
                    layer for layer in contract["layers"] if layer.get("source_section") == section
                ]
                fls_offsets = [int(leaf.get("source_offset") or 0) for leaf in fls_leaves]
                kfps_offsets = [int(leaf.get("source_offset") or 0) for leaf in kfps_leaves]
                fls_offset_set = set(fls_offsets)
                kfps_offset_set = set(kfps_offsets)
                common_fls = [offset for offset in fls_offsets if offset in kfps_offset_set]
                common_kfps = [offset for offset in kfps_offsets if offset in fls_offset_set]
                attribute_mismatches = []
                fls_by_offset = {int(leaf.get("source_offset") or 0): leaf for leaf in fls_leaves}
                for leaf in kfps_leaves:
                    offset = int(leaf.get("source_offset") or 0)
                    oracle = fls_by_offset.get(offset)
                    if oracle is None:
                        continue
                    mismatched = _semantic_leaf_mismatches(oracle, leaf)
                    if mismatched:
                        attribute_mismatches.append({"source_offset": offset, "fields": mismatched})
                draw_index_mismatches = []
                for draw_index, (oracle, leaf) in enumerate(
                    zip(fls_leaves, kfps_leaves, strict=False)
                ):
                    mismatched = _semantic_leaf_mismatches(oracle, leaf)
                    if int(oracle.get("source_offset") or 0) != int(leaf.get("source_offset") or 0):
                        mismatched.insert(0, "source_offset")
                    if mismatched and len(draw_index_mismatches) < 64:
                        draw_index_mismatches.append(
                            {
                                "draw_index": draw_index,
                                "fls_source_offset": int(oracle.get("source_offset") or 0),
                                "kfps_source_offset": int(leaf.get("source_offset") or 0),
                                "fields": mismatched,
                            }
                        )
                draw_index_mismatch_count = sum(
                    1
                    for oracle, leaf in zip(fls_leaves, kfps_leaves, strict=False)
                    if int(oracle.get("source_offset") or 0) != int(leaf.get("source_offset") or 0)
                    or _semantic_leaf_mismatches(oracle, leaf)
                ) + abs(len(fls_leaves) - len(kfps_leaves))
                if (
                    fls_offsets != kfps_offsets
                    or attribute_mismatches
                    or draw_index_mismatch_count
                ):
                    semantic_differences[section] = {
                        "same_common_order": common_fls == common_kfps,
                        "missing_in_kfps": sorted(fls_offset_set - kfps_offset_set),
                        "extra_in_kfps": sorted(kfps_offset_set - fls_offset_set),
                        "attribute_mismatches": attribute_mismatches,
                        "draw_index_mismatch_count": draw_index_mismatch_count,
                        "draw_index_mismatches": draw_index_mismatches,
                    }
        result = {
            "comparison_revision": COMPARISON_REVISION,
            "status": "incomplete_source" if declared_count_mismatches else "ok",
            "title": title,
            "source_path": str(source),
            "source_sha256": source_hash,
            "car_id": record.get("car_id"),
            "source_owned": bool(record.get("source_owned")),
            "fls_log": fls_log,
            "fls_logical_leaf_count": int(fls_manifest["logical_leaf_count"]),
            "kfps_decoded_layer_count": len(contract["layers"]),
            "count_mismatches": count_mismatches,
            "declared_count_mismatches": declared_count_mismatches,
            "semantic_differences": semantic_differences,
            "kfps_report": kfps_report,
            "sections": section_results,
        }
        report_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        results.append(result)

    aggregate = {
        "format": "kfps_fls_livery_render_differential_v2",
        "comparison_revision": COMPARISON_REVISION,
        "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "reference_renderer_sha256": hashlib.sha256(args.fls_renderer.read_bytes()).hexdigest(),
        "semantic": bool(args.semantic),
        "reference_timeout_seconds": args.reference_timeout,
        "record_count": len(results),
        "success_count": sum(result.get("status") == "ok" for result in results),
        "failure_count": sum(result.get("status") != "ok" for result in results),
        "complete": len(results) == len(records),
        "records": results,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(aggregate, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(
        "complete "
        f"records={len(results)} successes={aggregate['success_count']} "
        f"failures={aggregate['failure_count']} output={args.output}"
    )
    return 1 if aggregate["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
