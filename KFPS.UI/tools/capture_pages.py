from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
OUT = UI / "Previews"
PAGES = [
    "create", "outputs", "community", "editor", "help",
    "settings", "tools", "images", "reports", "update", "credits",
]
SIZES = [(1360, 820), (1760, 1040), (1920, 1080), (2560, 1440)]

sys.path.insert(0, str(UI / "src"))
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES  # noqa: E402


def parse_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def theme_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture KFPS pages for visual review.")
    parser.add_argument("--theme", action="append", choices=sorted(KNOWN_THEME_NAMES), dest="themes")
    parser.add_argument("--page", action="append", choices=PAGES, dest="pages")
    parser.add_argument("--size", action="append", type=parse_size, dest="sizes")
    parser.add_argument("--ui-scale", type=float)
    parser.add_argument("--output", type=Path, default=OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pages = args.pages or PAGES
    sizes = args.sizes or SIZES
    themes: list[str | None] = args.themes or [None]
    args.output.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("QSG_RHI_BACKEND", "software")
    if os.name == "nt":
        env.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"))
    env["KFPS_APP_ROOT"] = str(ROOT)

    failures: list[tuple[str, str, int, int, int, str]] = []
    capture_count = 0
    for theme in themes:
        theme_output = (
            args.output
            if theme is None
            else args.output / "themes" / theme_slug(theme)
        )
        theme_output.mkdir(parents=True, exist_ok=True)
        for width, height in sizes:
            for page in pages:
                target = theme_output / f"{page}_{width}x{height}.png"
                command = [
                    sys.executable,
                    str(UI / "app.py"),
                    "--allow-unsupported-python",
                    "--demo",
                    "--page", page,
                    "--width", str(width),
                    "--height", str(height),
                    "--screenshot", str(target),
                ]
                if args.ui_scale is not None:
                    command.extend(["--ui-scale", str(args.ui_scale)])
                if theme:
                    command.extend(["--theme-preview", theme])
                run = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=45,
                )
                if run.returncode or not target.exists():
                    failures.append(
                        (theme or "persisted", page, width, height, run.returncode, run.stdout)
                    )
                else:
                    capture_count += 1

    error_report = args.output / "capture-errors.txt"
    if failures:
        report = "\n\n".join(
            f"{theme} / {page} {width}x{height} exit={code}\n{output}"
            for theme, page, width, height, code, output in failures
        )
        error_report.write_text(report, encoding="utf-8")
        print(f"FAILED: {len(failures)} capture(s). See {error_report}")
        return 1

    error_report.unlink(missing_ok=True)
    print(f"Captured {capture_count} page/theme/size case(s) in {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
