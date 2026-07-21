from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
PAGES = [
    "create", "outputs", "community", "editor", "help", "settings",
    "tools", "images", "reports", "update", "credits",
]
DEFAULT_SIZES = [
    (960, 600),
    (1280, 720),
    (1360, 820),
    (1760, 1040),
    (1920, 1080),
    (2560, 1440),
]

sys.path.insert(0, str(UI / "src"))
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES  # noqa: E402


def parse_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit visible QML controls across window sizes.")
    parser.add_argument("--size", action="append", type=parse_size, dest="sizes")
    parser.add_argument("--page", action="append", choices=PAGES, dest="pages")
    parser.add_argument("--theme", choices=sorted(KNOWN_THEME_NAMES))
    parser.add_argument("--output", type=Path, default=UI / "Previews" / "layout-audit")
    args = parser.parse_args()

    sizes = args.sizes or DEFAULT_SIZES
    pages = args.pages or PAGES
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("QSG_RHI_BACKEND", "software")
    if os.name == "nt":
        env.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"))
    env["KFPS_APP_ROOT"] = str(ROOT)

    failures: list[dict] = []
    summaries: list[dict] = []
    for width, height in sizes:
        case_dir = args.output / f"{width}x{height}"
        case_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(UI / "app.py"),
            "--allow-unsupported-python",
            "--demo",
            "--width", str(width),
            "--height", str(height),
            "--layout-report-dir", str(case_dir),
        ]
        if args.theme:
            command.extend(["--theme-preview", args.theme])
        run = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=45,
        )
        if run.returncode != 0:
            failures.append({
                "width": width,
                "height": height,
                "reason": f"process exit {run.returncode}",
                "output": run.stdout,
            })
            continue

        for page in pages:
            report = case_dir / f"{page}.json"
            if not report.exists():
                failures.append({
                    "page": page,
                    "width": width,
                    "height": height,
                    "reason": "layout report missing",
                    "output": run.stdout,
                })
                continue
            payload = json.loads(report.read_text(encoding="utf-8"))
            clipped = [
                control["name"]
                for control in payload.get("controls", [])
                if (control.get("intersectsWindow")
                    and not control.get("fullyInsideWindow")
                    and not control.get("clippedByAncestor"))
            ]
            summary = {
                "page": page,
                "width": width,
                "height": height,
                "devicePixelRatio": payload.get("devicePixelRatio", 1.0),
                "controlCount": len(payload.get("controls", [])),
                "zeroSize": payload.get("zeroSize", []),
                "tooSmall": payload.get("tooSmall", []),
                "clipped": clipped,
            }
            summaries.append(summary)
            if summary["zeroSize"] or summary["tooSmall"] or summary["clipped"]:
                failures.append({**summary, "reason": "invalid interactive geometry"})

    aggregate = {
        "sizes": sizes,
        "pages": pages,
        "scaling": "native",
        "theme": args.theme or "persisted",
        "cases": summaries,
        "failures": failures,
    }
    (args.output / "summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")

    print(
        f"Audited {len(summaries)} page/size cases for {args.theme or 'the persisted theme'} "
        "with native Qt/Windows scaling."
    )
    if failures:
        print(f"FAILED: {len(failures)} case(s). See {args.output / 'summary.json'}")
        return 1
    print("PASS: no visible interactive control was clipped, zero-sized, or undersized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
