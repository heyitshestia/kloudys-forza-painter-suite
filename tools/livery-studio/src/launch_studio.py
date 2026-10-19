"""Standalone entrypoint for the existing Studio host bridge, not another app."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import sys

FORMAT = "kfps-studio-launch-check-v1"
STUDIO = Path(__file__).resolve().parent.parent
UNSAFE_PREFIXES = ("PYTHON", "QT_", "QTWEBENGINE", "QML", "PYSIDE", "SHIBOKEN", "QSG_")


def clean_environment():
    for key in list(os.environ):
        if key.upper().startswith(UNSAFE_PREFIXES) or key.upper() == "KFPS_PYTHON":
            del os.environ[key]
    os.environ.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True


def report_path(value):
    path = Path(value)
    if not path.is_absolute() or str(path).startswith("\\\\"):
        raise ValueError("The report requires an absolute local path.")
    if not path.parent.is_dir():
        raise ValueError("The report parent directory must already exist.")
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("The report cannot use redirected files or directories.")
    if path.exists():
        raise ValueError("The report already exists; choose a new path. Nothing was overwritten.")
    return path


def load_bridge():
    path = STUDIO / "src/kfps_livery_lab/host_bridge.py"
    spec = importlib.util.spec_from_file_location("_standalone_studio_bridge", path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    return bridge


def validate_setup(root, *, workspace_layout=False):
    root = Path(root).resolve(strict=True)
    expected = (root.parent / "livery" if workspace_layout else root / "tools/livery-studio").resolve()
    if STUDIO != expected or (workspace_layout and root.name != "repo"):
        raise ValueError("Studio does not belong to the selected installation layout.")
    runtime = (root / "python/python.exe").resolve(strict=True)
    if Path(sys.executable).resolve() != runtime or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise ValueError("Use this installation's bundled 64-bit Python 3.12 runtime.")
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError("The standalone entrypoint requires bundled Python -I -B.")
    for name in ("run_livery.py", "kfps_livery_lab/host_bridge.py", "kfps_livery_lab/launcher.py",
                 "kfps_livery_lab/server.py", "kfps_livery_lab/native_host.py", "web/livery-editor.mjs"):
        if not (STUDIO / "src" / name).is_file():
            raise ValueError("The Studio installation is incomplete: missing " + name)
    for name in ("json_preview_renderer.py", "tools/livery/render_contract.py", "tools/livery/portable_mesh_converter.py",
                 "tools/livery-inspector/vendor/three/build/three.module.min.js"):
        if not (root / name).is_file():
            raise ValueError("The shared KFPS installation is incomplete: missing " + name)
    # These imports perform no Qt initialization, rendering, network or server work.
    import psutil
    import PIL
    import numpy
    bridge = load_bridge()
    config = bridge.launcher.window_preflight(root)
    if Path(config["pythonExe"]).resolve() != runtime:
        raise ValueError("Studio settings select a different Python runtime. Use the bundled runtime for this installation.")
    mode = "chrome" if bridge.launcher._window_module().use_chrome(root) else "native"
    return bridge, {"application_root": str(root), "studio_root": str(STUDIO), "python": str(runtime),
                    "host": mode, "archive": config["archive"], "workspace_layout": workspace_layout,
                    "isolated_python": bool(sys.flags.isolated), "bytecode_disabled": bool(sys.dont_write_bytecode),
                    "checks": ["installation-layout", "bundled-python", "python-dependencies", "existing-studio-config", "selected-host"],
                    "scope": "Read-only setup preflight; no preparation, renderer, backend readiness or window test."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kfps-root", required=True, type=Path)
    parser.add_argument("--workspace-layout", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    if args.check != (args.report is not None):
        parser.error("Use --check with an explicit --report path.")
    clean_environment()
    destination = None
    result = {"format": FORMAT, "check": args.check, "ok": False, "stage": "studio-entrypoint",
              "server_started": False, "window_opened": False}
    try:
        if args.check:
            destination = report_path(args.report)
        bridge, details = validate_setup(args.kfps_root, workspace_layout=args.workspace_layout)
        result.update(details)
        if not args.check:
            launched = bridge.launch_from_host(args.kfps_root, open_window=True)
            result["window_opened"] = bool(launched.get("opened"))
            result["server_started"] = not bool(launched.get("reused"))
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)[:8192]
        print(result["error"], file=sys.stderr)
    if destination is not None:
        try:
            with destination.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.write("\n")
        except OSError as exc:
            print("Diagnostic report was not written: " + str(exc), file=sys.stderr)
            return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
