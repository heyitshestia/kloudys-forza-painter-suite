from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent

sys.path.insert(0, str(UI / "src"))
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES  # noqa: E402


def theme_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture deterministic frames from a live KFPS theme.")
    parser.add_argument("--theme", required=True, choices=sorted(KNOWN_THEME_NAMES))
    parser.add_argument("--page", default="create")
    parser.add_argument("--size", type=parse_size, default=(1360, 820))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    width, height = args.size
    target = args.output.resolve() / "themes" / theme_slug(args.theme) / args.page / f"{width}x{height}"
    target.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    environment.setdefault("QT_QUICK_BACKEND", "software")
    environment.setdefault("QSG_RHI_BACKEND", "software")
    environment["KFPS_APP_ROOT"] = str(ROOT)
    if os.name == "nt":
        environment.setdefault(
            "QT_QPA_FONTDIR",
            str(Path(environment.get("WINDIR", r"C:\Windows")) / "Fonts"),
        )

    command = [
        sys.executable,
        str(UI / "app.py"),
        "--allow-unsupported-python",
        "--demo",
        "--theme-preview", args.theme,
        "--page", args.page,
        "--width", str(width),
        "--height", str(height),
        "--motion-capture-dir", str(target),
    ]
    run = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
    )
    frames = sorted(target.glob("frame-*.png"))
    if run.returncode or len(frames) != 8:
        report = target / "capture-error.txt"
        report.write_text(run.stdout, encoding="utf-8")
        print(f"FAILED: captured {len(frames)} of 8 frames. See {report}")
        return 1

    print(f"Captured {len(frames)} live-motion frames in {target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
