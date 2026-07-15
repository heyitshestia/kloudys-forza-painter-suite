import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from detail_heatmap import detail_heatmap_preview_bytes
from geometry_json import drawable_shape_count
from version_info import get_version


ROOT = Path(__file__).resolve().parent
SETTINGS_DIR = ROOT / "settings"
ACTIVE_PRESET_DIR = SETTINGS_DIR
GENERATOR_EXE = ROOT / "forza_generator_v2.py"
RAW_GENERATOR_EXE_GENESIS = ROOT / "KloudysGalateaGenesis.exe"
RAW_GENERATOR_EXE_V7 = ROOT / "KloudysGeneratorV7.exe"
RAW_GENERATOR_EXE_V6 = ROOT / "KloudysGeneratorV6.exe"
ARCHIVED_PYTHON_GENERATOR_V6 = ROOT / "runtime" / "archives" / "python-v6-structure-prototype-20260529" / "KloudysGeneratorV6.py"
RAW_GENERATOR_EXE = (
    RAW_GENERATOR_EXE_GENESIS
    if RAW_GENERATOR_EXE_GENESIS.exists()
    else (
        RAW_GENERATOR_EXE_V7
        if RAW_GENERATOR_EXE_V7.exists()
        else (RAW_GENERATOR_EXE_V6 if RAW_GENERATOR_EXE_V6.exists() else ARCHIVED_PYTHON_GENERATOR_V6)
    )
)
PREVIEW_DIR = ROOT / "runtime" / "previews"
CUSTOM_SETTINGS_DIR = ROOT / "runtime" / "custom-settings"
USER_PRESET_DIR = ROOT / "runtime" / "user-presets"
GENERATED_ROOT = ROOT / "imgs" / "generated"
FINALS_DIR_NAME = "finals"
CHECKPOINTS_DIR_NAME = "checkpoints"
REPORTS_DIR_NAME = "reports"
PREVIEWS_DIR_NAME = "previews"
LIVE_PREVIEW_EVERY = 100
VERSION_FILE = ROOT / "VERSION"
ACTIVE_PRESET_FILES = (
    "b.shaded-art.ini",
    "a.flat-colors.ini",
    "c.gradients.ini",
)


SETTING_KEYS = (
    "description",
    "detailMode",
    "maxPreviewSize",
    "maxResolution",
    "maxThreads",
    "mutatedSamples",
    "maxNoImproveRetries",
    "forceOpaqueShapes",
    "posterizeLevels",
    "previewEvery",
    "randomSamples",
    "saveAt",
    "saveEvery",
    "shapeMode",
    "stopAt",
    "useWorkGroupEval",
    "enableProgressiveSampling",
    "errorGridSize",
    "enableDetailWeightedSampling",
    "detailSamplingStrength",
    "detailSamplingFloor",
    "detailSamplingStart",
    "enableBoundaryAwareRadius",
    "boundaryRadiusPadding",
    "boundaryRadiusStart",
    "enableAdaptiveWorkload",
    "adaptiveWorkloadStart",
    "adaptiveRandomMinScale",
    "adaptiveMutatedMinScale",
    "enableLateSmallCandidates",
    "lateSmallCandidateShare",
    "lateSmallCandidateStart",
    "lateSmallCandidateRadiusFrac",
    "minUsefulDelta",
    "rectangleCandidateShare",
    "rectangleCandidateStart",
    "enableTwoStageRandom",
    "twoStageRandomStart",
    "randomCoarseSampleStep",
    "randomRefineTopK",
    "enableTwoStageMutation",
    "mutationCoarseSampleStep",
    "mutationRefineTopK",
    "mutationNoImproveRounds",
    "enableAlphaSafeCandidates",
    "alphaSafeCandidateStart",
    "alphaSafeCandidatePadding",
    "v2PreprocessMode",
    "v2EnableRepair",
    "detailHeatmapMode",
    "detailHeatmapStrength",
)


def setting_description(path):
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("description"):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def parse_settings(path):
    values = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def sorted_settings(values):
    return {key: values[key] for key in sorted(values)}


def text_file_value(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def git_output(*args):
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


def file_sha256(path):
    path = Path(path)
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def app_build_info():
    commit = git_output("rev-parse", "--short=8", "HEAD")
    if not commit:
        commit = text_file_value(ROOT / "BUILD_COMMIT")
    return {
        "app_name": "Kloudy's FH6 Painter",
        "app_version": text_file_value(VERSION_FILE) or "unknown",
        "build_label": get_version(),
        "build_commit": commit,
        "metadata_schema": "kloudys_run_metadata_v2",
        "generator_wrapper": GENERATOR_EXE.name,
        "raw_generator": RAW_GENERATOR_EXE.name if RAW_GENERATOR_EXE else "",
        "raw_generator_sha256": file_sha256(RAW_GENERATOR_EXE) if RAW_GENERATOR_EXE else "",
    }


def load_settings():
    profiles = []
    preset_dir = ACTIVE_PRESET_DIR if ACTIVE_PRESET_DIR.exists() else SETTINGS_DIR
    active_paths = [preset_dir / name for name in ACTIVE_PRESET_FILES if (preset_dir / name).exists()]
    paths = active_paths or [path for path in sorted(preset_dir.glob("*.ini")) if not path.name.startswith("_")]
    for path in paths:
        values = sorted_settings(parse_settings(path))
        if not values.get("stopAt") or not values.get("randomSamples"):
            continue
        name = preset_display_name(path, values)
        profiles.append({
            "path": path,
            "name": name,
            "description": setting_description(path),
            "values": values,
        })
    for path in sorted(USER_PRESET_DIR.glob("*.ini")) if USER_PRESET_DIR.exists() else []:
        values = sorted_settings(parse_settings(path))
        if not values.get("stopAt") or not values.get("randomSamples"):
            continue
        name = preset_display_name(path, values)
        profiles.append({
            "path": path,
            "name": name,
            "description": setting_description(path) or f"Saved custom preset: {name}",
            "values": values,
            "is_user_preset": True,
        })
    profiles.sort(key=preset_sort_key)
    for index, item in enumerate(profiles, start=1):
        item["index"] = index
        item["label"] = f"{index}. {item['name']}"
    return profiles


def preset_display_name(path, values):
    stem = Path(path).stem.lower()
    if Path(path).parent == USER_PRESET_DIR:
        family = values.get("presetName") or Path(path).stem
        family = re.sub(r"[-_]+", " ", family).strip().title()
        return f"Custom: {family}"
    if "flat-colors" in stem:
        family = "Flat Colors"
    elif "shaded-art" in stem:
        family = "Shaded Character Art"
    elif "gradients" in stem:
        family = "Smooth Gradients"
    else:
        family = re.sub(r"^[a-z0-9]+[.)]\s*", "", Path(path).stem, flags=re.IGNORECASE)
        family = re.sub(r"[-_]+", " ", family).strip().title()
    return family


def preset_sort_key(item):
    stem = item["path"].stem.lower()
    ladder_order = {
        "shaded-art": 0,
        "flat-colors": 1,
        "gradients": 2,
    }
    preset_rank = 99
    for key, rank in ladder_order.items():
        if key in stem:
            preset_rank = rank
            break
    if item.get("is_user_preset"):
        preset_rank = 50
    return (preset_rank, item["path"].name.lower())


def safe_preset_slug(name):
    slug = re.sub(r"[^A-Za-z0-9._ -]+", "", str(name)).strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = slug.strip(".-_")
    return slug[:80] or "custom-preset"


def merged_setting_values(base_setting, custom_values):
    values = sorted_settings(parse_settings(base_setting["path"]))
    applied_overrides = {}
    for key, value in custom_values.items():
        value = str(value).strip()
        if value:
            values[key] = value
            applied_overrides[key] = value
    return values, sorted_settings(applied_overrides)


def write_settings_file(path, values, description, preset_name=None):
    lines = [f"description = {description}"]
    written = {"description"}
    if preset_name:
        lines.append(f"presetName = {preset_name}")
        written.add("presetName")
    for key in SETTING_KEYS:
        if key in values and key not in written:
            lines.append(f"{key} = {values[key]}")
            written.add(key)
    for key, value in values.items():
        if key not in written:
            lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_custom_settings(base_setting, custom_values):
    values, applied_overrides = merged_setting_values(base_setting, custom_values)
    CUSTOM_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOM_SETTINGS_DIR / "custom.ini"
    write_settings_file(path, values, "Custom UI settings")
    setting = dict(base_setting)
    setting["path"] = path
    setting["label"] = f"{base_setting.get('label', 'Custom')} + overrides"
    setting["description"] = "Custom UI settings"
    setting["values"] = values
    setting["base_setting"] = {
        "label": base_setting.get("label"),
        "name": base_setting.get("name"),
        "description": base_setting.get("description"),
        "path": str(base_setting.get("path")),
        "values": sorted_settings(parse_settings(base_setting["path"])),
    }
    setting["ui_overrides"] = sorted_settings(applied_overrides)
    return setting


def save_user_preset(name, base_setting, custom_values):
    preset_name = str(name).strip()
    if not preset_name:
        raise ValueError("Preset name is required.")
    USER_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_PRESET_DIR / f"{safe_preset_slug(preset_name)}.ini"
    values, applied_overrides = merged_setting_values(base_setting, custom_values)
    values["presetName"] = preset_name
    write_settings_file(path, values, f"Saved custom preset: {preset_name}", preset_name=preset_name)
    setting = dict(base_setting)
    setting["path"] = path
    setting["label"] = f"Custom: {preset_name}"
    setting["name"] = f"Custom: {preset_name}"
    setting["description"] = f"Saved custom preset: {preset_name}"
    setting["values"] = sorted_settings(parse_settings(path))
    setting["ui_overrides"] = sorted_settings(applied_overrides)
    setting["is_user_preset"] = True
    return setting


def delete_user_preset(setting):
    if not setting or not setting.get("is_user_preset"):
        return False
    path = Path(setting.get("path", ""))
    try:
        if path.exists() and path.resolve().is_relative_to(USER_PRESET_DIR.resolve()):
            path.unlink()
            return True
    except OSError:
        return False
    return False


def generated_jsons(image_path):
    image_path = Path(image_path)
    candidates = []
    for folder in generator_output_dirs(image_path):
        candidates.extend(folder.rglob("*.json"))
    legacy_folder = image_path.parent / image_path.stem
    if legacy_folder.exists():
        candidates.extend(legacy_folder.rglob("*.json"))
    candidates.extend(image_path.parent.glob(f"{image_path.stem}*.json"))
    filtered = []
    for path in candidates:
        if is_internal_generator_json(path):
            continue
        filtered.append(path)
    return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)


def is_internal_generator_json(path):
    name = Path(path).name.lower()
    return (
        ".v2.report." in name
        or ".v2.settings." in name
        or ".v2.preprocess." in name
        or ".v2.run_metadata." in name
        or ".fh6." in name
    )


def geometry_shape_count(path):
    return drawable_shape_count(path)


def geometry_group_stem(path):
    path = Path(path)
    base_name = re.sub(r"\.v2\.final\.\d+$", "", path.stem)
    base_name = re.sub(r"\.\d+v2$", "", base_name)
    base_name = re.sub(r"\.v2$", "", base_name)
    base_name = re.sub(r"\.\d+$", "", base_name)
    return base_name


def generation_report_path(path):
    path = Path(path)
    candidates = [
        path.with_name(f"{geometry_group_stem(path)}.v2.report.json"),
        path.parent.parent / REPORTS_DIR_NAME / f"{geometry_group_stem(path)}.v2.report.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def import_drawable_budget(path):
    report_path = generation_report_path(path)
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("drawable_target_shapes", "target_drawable_shapes"):
        try:
            value = int(report.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        target_shapes = int(report.get("target_shapes"))
    except (TypeError, ValueError):
        return None
    return target_shapes if target_shapes > 0 else None


def is_v2_output_json(path):
    lower_name = Path(path).name.lower()
    return bool(".v2.final." in lower_name or re.search(r"\.\d+v2\.json$", lower_name) or lower_name.endswith(".v2.json"))


def is_import_safe_geometry_json(path):
    budget = import_drawable_budget(path)
    if budget is None:
        return True
    return geometry_shape_count(path) <= budget


def best_geometry_jsons(paths):
    best_by_stem = {}
    for path in paths:
        path = Path(path)
        if is_internal_generator_json(path):
            continue
        if not is_import_safe_geometry_json(path):
            continue
        base_name = geometry_group_stem(path)
        key = str(path.with_name(base_name).resolve()).lower()
        is_v2_final = 1 if is_v2_output_json(path) else 0
        try:
            shape_count = geometry_shape_count(path)
        except Exception:
            continue
        score = (is_v2_final, shape_count, path.stat().st_mtime)
        current = best_by_stem.get(key)
        if current is None or score > current[0]:
            best_by_stem[key] = (score, path)
    return [item[1] for item in sorted(best_by_stem.values(), key=lambda item: item[1].stat().st_mtime, reverse=True)]


def generator_preview_path(image_path):
    image_path = Path(image_path)
    return generator_output_dir(image_path) / PREVIEWS_DIR_NAME / f"{image_path.stem}.preview.png"


def generated_preview_files(image_path):
    image_path = Path(image_path)
    candidates = []
    for folder in generator_output_dirs(image_path):
        candidates.extend(folder.glob(f"{image_path.stem}.preview*.png"))
        candidates.extend(folder.glob(f"{image_path.stem}.v2.final.*.preview.png"))
        preview_dir = folder / PREVIEWS_DIR_NAME
        if preview_dir.exists():
            candidates.extend(preview_dir.glob(f"{image_path.stem}*.preview*.png"))
            candidates.extend(preview_dir.glob("*.preview*.png"))
    legacy_folder = image_path.parent / image_path.stem
    if legacy_folder.exists():
        candidates.extend(legacy_folder.glob(f"{image_path.stem}.preview*.png"))
        candidates.extend(legacy_folder.glob(f"{image_path.stem}.v2.final.*.preview.png"))
    candidates.extend(image_path.parent.glob(f"{image_path.stem}.preview*.png"))
    filtered = [path for path in candidates if ".v2.preprocess." not in path.name]
    return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)


def generator_output_base(image_path):
    image_path = Path(image_path)
    return image_path.with_suffix("")


def generator_safe_stem(image_path):
    image_path = Path(image_path)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", image_path.stem).strip("._") or "image"


def legacy_generator_output_dir(image_path):
    image_path = Path(image_path)
    digest = hashlib.sha1(str(image_path.resolve()).encode("utf-8", errors="replace")).hexdigest()[:8]
    return GENERATED_ROOT / f"{generator_safe_stem(image_path)}-{digest}"


def generator_output_dir(image_path):
    return GENERATED_ROOT / generator_safe_stem(image_path)


def generator_output_dirs(image_path):
    safe_stem = generator_safe_stem(image_path)
    candidates = []
    if GENERATED_ROOT.exists():
        for path in GENERATED_ROOT.iterdir():
            if not path.is_dir():
                continue
            name = path.name
            if name == safe_stem or re.fullmatch(re.escape(safe_stem) + r"v\d+", name):
                candidates.append(path)
            elif re.fullmatch(re.escape(safe_stem) + r"-[0-9a-f]{8}", name, flags=re.IGNORECASE):
                candidates.append(path)
    legacy = legacy_generator_output_dir(image_path)
    if legacy.exists():
        candidates.append(legacy)
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def next_generator_output_dir(image_path):
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    base = generator_output_dir(image_path)
    if not base.exists():
        return base
    safe_stem = generator_safe_stem(image_path)
    index = 2
    while True:
        candidate = GENERATED_ROOT / f"{safe_stem}v{index}"
        if not candidate.exists():
            return candidate
        index += 1


def generator_run_subdir(output_dir, name):
    folder = Path(output_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def generator_stop_request_path(image_path, output_dir=None):
    folder = Path(output_dir) if output_dir is not None else generator_output_dir(image_path)
    return folder / ".v2-stop"


def cleanup_generated_outputs(image_path):
    image_path = Path(image_path)
    folder = generator_output_dir(image_path)
    if not folder.exists():
        return
    patterns = (
        f"{image_path.stem}*.json",
        f"{image_path.stem}*.png",
        f"{image_path.stem}*.ini",
    )
    for pattern in patterns:
        for path in folder.glob(pattern):
            try:
                path.unlink()
            except OSError:
                pass
    stop_path = generator_stop_request_path(image_path)
    if stop_path.exists():
        try:
            stop_path.unlink()
        except OSError:
            pass


def positive_int_text(value, fallback):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = int(fallback)
    return str(max(1, number))


def clamp_number(value, low, high):
    return max(low, min(high, value))


def source_image_metrics(image_path):
    """Return cheap source statistics used for automatic generation settings."""
    try:
        from PIL import Image, ImageFilter, ImageStat
    except Exception:
        image_path = Path(image_path)
        return {
            "width": 0,
            "height": 0,
            "total_pixels": 0,
            "megapixels": 0.0,
            "alpha_coverage": 1.0,
            "edge_density": 0.18,
            "long_edge": 0,
            "short_edge": 0,
            "analysis_error": "Pillow unavailable",
        }

    image_path = Path(image_path)
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            long_edge = max(width, height)
            short_edge = min(width, height)
            sample = img.convert("RGBA")
            sample.thumbnail((512, 512), Image.Resampling.LANCZOS)
            alpha = sample.getchannel("A")
            alpha_values = alpha.getdata()
            visible = sum(1 for value in alpha_values if value > 16)
            alpha_coverage = visible / float(max(1, sample.width * sample.height))
            gray = sample.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges, mask=alpha.point(lambda value: 255 if value > 16 else 0))
            edge_density = (edge_stat.mean[0] / 255.0) if edge_stat.count and edge_stat.count[0] else 0.18
    except Exception as exc:
        return {
            "width": 0,
            "height": 0,
            "total_pixels": 0,
            "megapixels": 0.0,
            "alpha_coverage": 1.0,
            "edge_density": 0.18,
            "long_edge": 0,
            "short_edge": 0,
            "analysis_error": f"{type(exc).__name__}: {exc}",
        }

    total_pixels = int(width * height)
    return {
        "width": int(width),
        "height": int(height),
        "total_pixels": total_pixels,
        "megapixels": round(total_pixels / 1_000_000.0, 4),
        "alpha_coverage": round(float(alpha_coverage), 4),
        "edge_density": round(float(edge_density), 4),
        "long_edge": int(long_edge),
        "short_edge": int(short_edge),
    }


def source_sanity_check(image_path):
    """Return user-facing source warnings for the generator preview banner."""
    severity_rank = {"ok": 0, "warn": 1, "bad": 2}
    messages = []

    def add(severity, text):
        messages.append({"severity": severity, "text": text})

    metrics = source_image_metrics(image_path)
    if metrics.get("analysis_error"):
        return {
            "severity": "warn",
            "title": "Source Check",
            "messages": [f"Could not inspect image: {metrics['analysis_error']}"],
            "metrics": metrics,
        }

    megapixels = float(metrics.get("megapixels") or 0.0)
    short_edge = int(metrics.get("short_edge") or 0)
    width = int(metrics.get("width") or 0)
    height = int(metrics.get("height") or 0)

    if megapixels < 0.25 or short_edge < 400:
        add("bad", "Very small source. Details will likely become soft or simplified; use the Image Tools upscaler first.")
    elif megapixels < 0.45 or short_edge < 600:
        add("warn", "Small source. It should still run, but tiny details may not survive well.")

    if megapixels > 18.0:
        add("bad", "Very large source. KFPS will downscale it heavily, so tiny details may be wasted or unstable.")
    elif megapixels > 10.0:
        add("warn", "Large source. KFPS will downscale it; resizing/cropping first may give more predictable detail.")

    try:
        from PIL import Image
        import numpy as np

        with Image.open(image_path) as img:
            has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
            rgba = img.convert("RGBA")
            rgba.thumbnail((512, 512), Image.Resampling.LANCZOS)
            alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
            visible = alpha > 16
            alpha_coverage = float(np.mean(visible))
            border_width = max(1, min(alpha.shape[:2]) // 32)
            border = np.concatenate([
                alpha[:border_width, :].reshape(-1),
                alpha[-border_width:, :].reshape(-1),
                alpha[:, :border_width].reshape(-1),
                alpha[:, -border_width:].reshape(-1),
            ])
            border_opaque = float(np.mean(border > 240))
            border_transparent = float(np.mean(border < 16))
            border_soft = float(np.mean((border >= 16) & (border <= 240)))
            metrics.update({
                "has_alpha": bool(has_alpha),
                "border_opaque": round(border_opaque, 4),
                "border_transparent": round(border_transparent, 4),
                "border_soft": round(border_soft, 4),
            })
            if not has_alpha:
                add("warn", "No transparency detected. Fine for full rectangular art; cutout vinyls should use background removal first.")
            elif alpha_coverage < 0.03:
                add("bad", "Almost everything is transparent. This may be the wrong file or an empty cutout.")
            elif alpha_coverage > 0.97 and border_opaque > 0.92:
                add("warn", "Alpha exists, but the background looks effectively opaque. It may not actually be removed.")
            elif alpha_coverage > 0.90 and border_opaque > 0.70:
                add("warn", "Only a little transparency detected. Check that the background is really removed.")
            elif border_soft > 0.12:
                add("warn", "Transparent edge looks soft. KFPS cleans some fringe pixels, but a cleaner cutout may generate better.")
    except Exception as exc:
        add("warn", f"Background check unavailable: {type(exc).__name__}: {exc}")

    if not messages:
        add("ok", f"Looks usable - {width}x{height}, {megapixels:.2f} MP.")

    severity = max((msg["severity"] for msg in messages), key=lambda value: severity_rank.get(value, 0))
    titles = {
        "ok": "Source Check - Good",
        "warn": "Source Check - Warning",
        "bad": "Source Check - Problem",
    }
    return {
        "severity": severity,
        "title": titles[severity],
        "messages": [msg["text"] for msg in messages],
        "metrics": metrics,
    }


def preset_auto_family(values):
    shape_mode = str(values.get("shapeMode", "")).strip().lower()
    description = str(values.get("description", "")).strip().lower()
    if "flat" in description or "edge_bias" in shape_mode or str(values.get("v2PreprocessMode", "")).strip().lower() == "luma_bands":
        return "flat"
    if "gradient" in shape_mode or "gradient" in description or "soft" in shape_mode:
        return "gradient"
    return "shaded"


def auto_generation_values(image_path, values, pro_overrides=None, sample_boost=False):
    """Build effective settings from the selected preset and optional overrides.

    V7 presets are intentionally fixed by default. Source metrics are reported
    for context, but they no longer raise resolution or sample counts silently.
    """
    values = dict(values)
    pro_overrides = {k: str(v).strip() for k, v in (pro_overrides or {}).items() if str(v).strip()}
    metrics = source_image_metrics(image_path)
    family = preset_auto_family(values)
    target_layers = int(positive_int_text(values.get("stopAt", "2000"), 2000))
    save_at = normalized_save_at_text(values.get("saveAt", ""), target_layers)
    values["saveAt"] = save_at
    values["saveEvery"] = checkpoint_step_from_save_at(save_at, target_layers)

    for key in ("maxResolution", "randomSamples", "mutatedSamples", "maxNoImproveRetries", "posterizeLevels", "previewEvery", "saveEvery"):
        if key in pro_overrides:
            values[key] = pro_overrides[key]

    if sample_boost:
        random_samples = int(positive_int_text(values.get("randomSamples", "0"), 0)) * 2
        mutated_samples = int(positive_int_text(values.get("mutatedSamples", "0"), 0)) * 2
        retries = int(positive_int_text(values.get("maxNoImproveRetries", "0"), 0))
        values["randomSamples"] = str(int(clamp_number(random_samples, 1, 2_400_000)))
        values["mutatedSamples"] = str(int(clamp_number(mutated_samples, 1, 140_000)))
        if retries:
            values["maxNoImproveRetries"] = str(int(clamp_number(retries * 2, 1, 96)))

    summary = {
        "mode": "fixed_preset",
        "family": family,
        "source": metrics,
        "target_layers": target_layers,
        "sample_boost": bool(sample_boost),
        "computed": {key: values.get(key) for key in ("maxResolution", "randomSamples", "mutatedSamples", "maxNoImproveRetries", "posterizeLevels", "previewEvery", "saveEvery", "saveAt")},
        "pro_overrides": sorted_settings(pro_overrides),
    }
    return values, summary


def normalized_save_at_text(value, target_count):
    points = set()
    for part in re.split(r"[,;\s]+", str(value or "")):
        if not part.strip():
            continue
        try:
            point = int(part)
        except ValueError:
            continue
        if point > 0:
            points.add(point)
    points.add(max(1, int(target_count)))
    return ",".join(str(point) for point in sorted(points))


def checkpoint_step_from_save_at(save_at_text, target_count):
    save_at_points = []
    for part in re.split(r"[,;\s]+", str(save_at_text or "")):
        if not part.strip():
            continue
        try:
            point = int(part)
        except ValueError:
            continue
        if point > 0:
            save_at_points.append(point)
    if len(save_at_points) >= 2:
        ordered = sorted(set(save_at_points))
        deltas = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
        return str(min(deltas) if deltas else ordered[0])
    if save_at_points:
        return str(save_at_points[0])
    return "250" if target_count <= 1000 else "500"


def build_generator_command(image_path, setting, enable_repair=False, enable_overshoot=False, output_dir=None, seed=0):
    image_path = Path(image_path)
    output_dir = Path(output_dir) if output_dir is not None else generator_output_dir(image_path)
    reports_dir = generator_run_subdir(output_dir, REPORTS_DIR_NAME)
    values = setting.get("values", {})
    target_shapes = positive_int_text(values.get("stopAt", "3000"), 3000)
    target_count = int(target_shapes)
    values = dict(values)
    values["stopAt"] = target_shapes
    values["saveAt"] = normalized_save_at_text(values.get("saveAt", ""), target_count)
    reserved_import_layers = str(values.get("reservedImportLayers", "0"))
    checkpoint_step = checkpoint_step_from_save_at(values.get("saveAt", ""), target_count)
    preprocess_mode = values.get("v2PreprocessMode", "none")
    detail_heatmap_mode = str(values.get("detailHeatmapMode", "off")).strip().lower()
    if detail_heatmap_mode not in ("off", "auto"):
        detail_heatmap_mode = "off"
    detail_heatmap_strength = str(values.get("detailHeatmapStrength", "0.10")).strip() or "0.10"
    setting_repair = str(values.get("v2EnableRepair", "false")).strip().lower() in ("1", "true", "yes", "on")
    run_metadata_path = reports_dir / f"{image_path.stem}.v2.run_metadata.json"
    build_info = app_build_info()
    run_metadata = {
        "app_version": build_info["app_version"],
        "app_build": build_info,
        "selected_profile": {
            "label": setting.get("label"),
            "name": setting.get("name"),
            "description": setting.get("description"),
            "path": str(setting.get("path")),
            "values": sorted_settings(values),
        },
        "base_profile": setting.get("base_setting"),
        "ui_overrides": sorted_settings(setting.get("ui_overrides", {})),
        "effective_settings": sorted_settings(values),
        "auto_tune": setting.get("auto_tune"),
        "toggles": {
            "luma_bands": str(preprocess_mode).strip().lower() == "luma_bands",
            "detail_heatmap": detail_heatmap_mode != "off",
            "quality_overshoot": bool(enable_overshoot),
            "targeted_repair": bool(enable_repair or setting_repair),
            "vroom_boost": bool(setting.get("vroom_boost")),
        },
        "seed": int(seed or 0),
        "generator_command_options": {
            "target_shapes": target_shapes,
            "reserved_import_layers": reserved_import_layers,
            "checkpoint_step": checkpoint_step,
            "live_preview_every": str(LIVE_PREVIEW_EVERY),
            "preview_candidate_limit": "0",
            "preprocess_mode": preprocess_mode,
            "detail_heatmap_mode": detail_heatmap_mode,
            "detail_heatmap_strength": detail_heatmap_strength,
            "overshoot_ratio": "1.12" if enable_overshoot else "1.0",
            "overshoot_max_extra": "400" if enable_overshoot else "0",
            "repair_enabled": bool(enable_repair or setting_repair),
            "seed": int(seed or 0),
        },
    }
    run_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    run_metadata_path.write_text(json.dumps(run_metadata, indent=2) + "\n", encoding="utf-8")
    cmd = [
        sys.executable,
        "-u",
        str(GENERATOR_EXE),
        str(image_path),
        "--settings",
        str(setting["path"]),
        "--out-dir",
        str(output_dir),
        "--target-shapes",
        target_shapes,
        "--reserved-import-layers",
        reserved_import_layers,
        "--checkpoint-step",
        checkpoint_step,
        "--live-preview-every",
        str(LIVE_PREVIEW_EVERY),
        "--preview-candidate-limit",
        "0",
        "--stop-file",
        str(generator_stop_request_path(image_path, output_dir)),
        "--preprocess-mode",
        preprocess_mode,
        "--detail-heatmap-mode",
        detail_heatmap_mode,
        "--detail-heatmap-strength",
        detail_heatmap_strength,
        "--run-metadata",
        str(run_metadata_path),
    ]
    if enable_overshoot:
        cmd.extend(["--overshoot-ratio", "1.12", "--overshoot-max-extra", "400"])
    if enable_repair or setting_repair:
        cmd.append("--enable-repair")
    else:
        cmd.append("--disable-refine")
    if int(seed or 0) > 0:
        cmd.extend(["--seed", str(int(seed))])
    return cmd
