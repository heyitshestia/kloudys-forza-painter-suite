import argparse
import subprocess
import sys
import time
import os
import re
from pathlib import Path

def discover_app_root():
    starts = []
    env_root = os.environ.get("KFPS_APP_ROOT")
    if env_root:
        starts.append(Path(env_root))
    starts.extend([Path.cwd(), Path(__file__).resolve().parents[2]])
    for start in starts:
        for candidate in [start, *start.parents]:
            nested = candidate / "KloudysFH6Painter"
            if looks_like_app_root(nested):
                return nested.resolve()
            if looks_like_app_root(candidate):
                return candidate.resolve()
    return Path.cwd().resolve()


def looks_like_app_root(path):
    return path.is_dir() and (path / "VERSION").is_file() and (path / "generator_backend.py").is_file()


ROOT = discover_app_root()
sys.path.insert(0, str(ROOT))

from generator_backend import (
    auto_generation_values,
    build_generator_command,
    generated_preview_files,
    load_settings,
    next_generator_output_dir,
    write_custom_settings,
)


def parse_args():
    parser = argparse.ArgumentParser(description="KFPS headless generation bridge")
    parser.add_argument("--image", required=True)
    parser.add_argument("--preset-index", type=int, default=0)
    parser.add_argument("--layers", default="2000")
    parser.add_argument("--save-at", default="500,1000,1250,1500,2000,2500,3000")
    parser.add_argument("--luma-prep", action="store_true")
    parser.add_argument("--detail-heatmap", action="store_true")
    parser.add_argument("--edge-repair", action="store_true")
    parser.add_argument("--sample-boost", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-resolution", default="")
    parser.add_argument("--random-samples", default="")
    parser.add_argument("--mutated-samples", default="")
    return parser.parse_args()


def safe_print(line):
    try:
        print(str(line).rstrip("\r\n"), flush=True)
        return True
    except (BrokenPipeError, OSError):
        # The QML shell can disappear while a generation is running. The
        # worker must keep its file-backed output channel and finish saving.
        return False


def worker_log_path(run_dir, image_path):
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", image_path.stem).strip("_") or "image"
    return run_dir / "reports" / f"{stem}.v2.worker.log"


def start_durable_worker(cmd, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    if sys.platform.startswith("win") and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    with log_path.open("w", encoding="utf-8", errors="replace") as output:
        return subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )


def stream_worker_log(proc, log_path):
    output_available = True
    with log_path.open("r", encoding="utf-8", errors="replace") as output:
        while True:
            line = output.readline()
            if line:
                if output_available:
                    output_available = safe_print(line)
                continue
            if proc.poll() is not None:
                # The worker has closed its inherited file handle. Drain any
                # bytes written between the last read and process exit.
                for remaining in output:
                    if output_available:
                        output_available = safe_print(remaining)
                break
            time.sleep(0.10)
    return proc.wait()


def main():
    args = parse_args()
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        print(f"Generator failed: missing source image: {image_path}", flush=True)
        return 2

    settings = load_settings()
    if not settings:
        print("Generator failed: no presets found.", flush=True)
        return 2

    preset_index = max(0, min(args.preset_index, len(settings) - 1))
    setting = settings[preset_index]
    base_values = dict(setting.get("values", {}))
    base_values.update(
        {
            "stopAt": str(args.layers).strip() or base_values.get("stopAt", "2000"),
            "saveAt": str(args.save_at).strip() or base_values.get("saveAt", ""),
            "v2PreprocessMode": "luma_bands" if args.luma_prep else "none",
            "v2EnableRepair": "true" if args.edge_repair else "false",
            "detailHeatmapMode": "auto" if args.detail_heatmap else "off",
            "detailHeatmapStrength": "0.10",
        }
    )

    pro_overrides = {}
    for cli_value, setting_key in (
        (args.max_resolution, "maxResolution"),
        (args.random_samples, "randomSamples"),
        (args.mutated_samples, "mutatedSamples"),
    ):
        value = str(cli_value).strip()
        if value:
            pro_overrides[setting_key] = value

    tuned_values, auto_summary = auto_generation_values(
        image_path,
        base_values,
        pro_overrides=pro_overrides,
        sample_boost=bool(args.sample_boost),
    )
    effective = write_custom_settings(setting, tuned_values)
    effective["label"] = setting.get("label", effective.get("label"))
    effective["auto_tune"] = auto_summary
    if args.sample_boost:
        effective["vroom_boost"] = True

    values = effective.get("values", {})
    run_dir = next_generator_output_dir(image_path)
    cmd = build_generator_command(
        image_path,
        effective,
        enable_repair=bool(args.edge_repair),
        enable_overshoot=False,
        output_dir=run_dir,
        seed=max(0, int(args.seed or 0)),
    )

    log_path = worker_log_path(run_dir, image_path)
    safe_print(f"KFPS_RUN_DIR: {run_dir}")
    safe_print(f"Selected Kloudy preset: {effective.get('label') or setting.get('label') or setting.get('name')}")
    safe_print(f"Generating final vinyl from: {image_path}")
    safe_print(f"Vinyl run folder: {run_dir}")
    safe_print(f"Durable worker log: {log_path}")
    safe_print(f"Target template layers: {values.get('stopAt', 'n/a')}")
    safe_print(f"Finalize at layers: {values.get('saveAt', values.get('stopAt', 'n/a'))}")
    safe_print(
        "Preset effort: "
        f"maxRes={values.get('maxResolution', 'n/a')} "
        f"random={values.get('randomSamples', 'n/a')} "
        f"mutated={values.get('mutatedSamples', 'n/a')}"
    )
    safe_print(f"Seed: {args.seed if int(args.seed or 0) > 0 else 'random'}")
    safe_print(f"Detail Heatmap: {values.get('detailHeatmapMode', 'off')}")
    safe_print(f"Luma Prep: {values.get('v2PreprocessMode', 'none')}")

    proc = start_durable_worker(cmd, log_path)
    return_code = stream_worker_log(proc, log_path)
    if return_code != 0:
        safe_print(f"Generator exited with code {return_code} for {image_path.name}.")
        return return_code

    previews = generated_preview_files(image_path)
    if previews:
        safe_print(f"KFPS_PREVIEW: {previews[0]}")
    safe_print("Universal generation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
