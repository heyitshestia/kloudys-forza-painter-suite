from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
PAGES = [
    "create", "outputs", "community", "editor", "help",
    "settings", "tools", "images", "reports", "update", "credits",
]

sys.path.insert(0, str(UI / "src"))
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES  # noqa: E402


def parse_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def theme_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def image_array(path: Path) -> np.ndarray:
    image = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():
        raise RuntimeError(f"Could not read {path}")
    raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
    rows = raw.reshape(image.height(), image.bytesPerLine())
    return rows[:, : image.width() * 4].reshape(image.height(), image.width(), 4).copy()


def compare_state(control: dict, idle_path: Path, state_path: Path) -> dict:
    idle = image_array(idle_path)
    state = image_array(state_path)
    if idle.shape != state.shape:
        return {"changedPixels": 0, "outsideChangedPixels": 0, "bleedDistance": 0, "shapeMismatch": True}

    difference = np.max(np.abs(idle.astype(np.int16) - state.astype(np.int16)), axis=2) > 12
    changed_pixels = int(np.count_nonzero(difference))
    crop = control["crop"]
    bounds = control["bounds"]
    scale_x = state.shape[1] / max(1, crop["width"])
    scale_y = state.shape[0] / max(1, crop["height"])
    x0 = max(0, round(crop["controlX"] * scale_x) - 1)
    y0 = max(0, round(crop["controlY"] * scale_y) - 1)
    x1 = min(state.shape[1], round((crop["controlX"] + bounds["width"]) * scale_x) + 1)
    y1 = min(state.shape[0], round((crop["controlY"] + bounds["height"]) * scale_y) + 1)
    outside = difference.copy()
    outside[y0:y1, x0:x1] = False
    outside_changed = int(np.count_nonzero(outside))

    bleed_distance = 0
    if outside_changed:
        ys, xs = np.nonzero(outside)
        bleed_distance = max(
            max(0, x0 - int(xs.min())),
            max(0, int(xs.max()) - (x1 - 1)),
            max(0, y0 - int(ys.min())),
            max(0, int(ys.max()) - (y1 - 1)),
        )
    return {
        "changedPixels": changed_pixels,
        "outsideChangedPixels": outside_changed,
        "bleedDistance": int(bleed_distance),
        "shapeMismatch": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and audit KFPS hover, press, and focus states.")
    parser.add_argument("--theme", choices=sorted(KNOWN_THEME_NAMES), required=True)
    parser.add_argument("--page", action="append", choices=PAGES, dest="pages")
    parser.add_argument("--community-tab", choices=("browse", "upload", "profile"))
    parser.add_argument("--size", type=parse_size, default=(1360, 820))
    parser.add_argument("--output", type=Path, default=UI / "Previews" / "interaction-audit")
    args = parser.parse_args()

    pages = args.pages or PAGES
    width, height = args.size
    output = args.output.resolve() / "themes" / theme_slug(args.theme) / f"{width}x{height}"
    output.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("QSG_RHI_BACKEND", "software")
    if os.name == "nt":
        env.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"))
    env["KFPS_APP_ROOT"] = str(ROOT)

    process_failures = []
    controls = []
    for page in pages:
        page_label = (
            f"{page}-{args.community_tab}"
            if page == "community" and args.community_tab
            else page
        )
        page_dir = output / page_label
        command = [
            sys.executable,
            str(UI / "app.py"),
            "--allow-unsupported-python",
            "--demo",
            "--page", page,
            "--width", str(width),
            "--height", str(height),
            "--theme-preview", args.theme,
            "--interaction-capture-dir", str(page_dir),
        ]
        if page == "community" and args.community_tab:
            command.extend(["--community-tab", args.community_tab])
        run = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        manifest_path = page_dir / "manifest.json"
        if run.returncode or not manifest_path.is_file():
            process_failures.append({"page": page_label, "exit": run.returncode, "output": run.stdout})
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for control in manifest.get("controls", []):
            control_dir = page_dir / control.get("folder", "")
            idle_path = control_dir / "idle.png"
            states = {}
            for state in ("hover-early", "hover", "pressed", "focus"):
                state_path = control_dir / f"{state}.png"
                if idle_path.is_file() and state_path.is_file():
                    states[state] = compare_state(control, idle_path, state_path)
            controls.append({
                "page": page_label,
                "name": control["name"],
                "class": control["class"],
                "enabled": control["enabled"],
                "auditAllowOutsideFeedback": control.get("auditAllowOutsideFeedback", False),
                "hoverStateAvailable": control.get("hoverStateAvailable", False),
                "hoverReached": control.get("hoverReached", False),
                "pressStateAvailable": control.get("pressStateAvailable", False),
                "pressReached": control.get("pressReached", False),
                "folder": str(control_dir),
                "states": states,
            })

    bleed_failures = []
    no_hover_feedback = []
    no_press_feedback = []
    for control in controls:
        hover_states = [control["states"].get("hover-early"), control["states"].get("hover")]
        hover_states = [state for state in hover_states if state]
        hover_target_reached = (
            not control.get("hoverStateAvailable", False)
            or control.get("hoverReached", False)
        )
        if (control["enabled"] and hover_states and hover_target_reached
                and max(state["changedPixels"] for state in hover_states) < 4):
            no_hover_feedback.append({"page": control["page"], "name": control["name"], "folder": control["folder"]})
        pressed = control["states"].get("pressed")
        press_target_reached = (
            not control.get("pressStateAvailable", False)
            or control.get("pressReached", False)
        )
        if (control["enabled"] and pressed and press_target_reached
                and pressed["changedPixels"] < 4):
            no_press_feedback.append({"page": control["page"], "name": control["name"], "folder": control["folder"]})
        for state_name in ("hover-early", "hover"):
            state = control["states"].get(state_name)
            if (state
                    and not control.get("auditAllowOutsideFeedback", False)
                    and state["outsideChangedPixels"] >= 8
                    and state["bleedDistance"] > 1):
                bleed_failures.append({
                    "page": control["page"],
                    "name": control["name"],
                    "state": state_name,
                    "folder": control["folder"],
                    **state,
                })

    summary = {
        "theme": args.theme,
        "size": {"width": width, "height": height},
        "scaling": "native",
        "pages": pages,
        "controlCount": len(controls),
        "processFailures": process_failures,
        "bleedFailures": bleed_failures,
        "noHoverFeedback": no_hover_feedback,
        "noPressFeedback": no_press_feedback,
        "controls": controls,
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Audited {len(controls)} visible controls across {len(pages)} page(s).")
    print(f"Hover bleed failures: {len(bleed_failures)}")
    print(f"No hover feedback: {len(no_hover_feedback)}")
    print(f"No press feedback: {len(no_press_feedback)}")
    if process_failures or bleed_failures or no_hover_feedback or no_press_feedback:
        print(f"FAILED: see {summary_path}")
        return 1
    print(f"PASS: no hover-state painting escaped control bounds. Report: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
