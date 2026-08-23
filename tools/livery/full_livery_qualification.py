from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
UI_SOURCE = APP_ROOT / "KFPS.UI" / "src"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(UI_SOURCE) not in sys.path:
    sys.path.insert(0, str(UI_SOURCE))

from kfps_ui.app_paths import AppPaths  # noqa: E402
from kfps_ui.experimental.full_livery.paths import FullLiveryPaths  # noqa: E402
from kfps_ui.experimental.full_livery.qualification import (  # noqa: E402
    REQUIRED_CHECKS,
    evaluate_qualification,
    qualification_template,
)


def _version() -> str:
    try:
        return (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _paths() -> FullLiveryPaths:
    os.environ.setdefault("KFPS_APP_ROOT", str(APP_ROOT))
    return FullLiveryPaths.for_app(AppPaths.discover())


def _write_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Qualification evidence is not an object.")
    return value


def initialize(path: Path, *, reset: bool) -> int:
    if path.exists() and not reset:
        raise SystemExit(f"Evidence already exists: {path}\nUse --reset only after preserving the previous report.")
    if path.exists():
        archive = path.with_name(f"qualification-{time.strftime('%Y%m%d-%H%M%S')}.previous.json")
        os.replace(path, archive)
        print(f"Archived previous evidence: {archive}")
    _write_atomic(path, qualification_template(_version()))
    print(f"Initialized current qualification matrix: {path}")
    return 0


def record(path: Path, check_id: str, passed: bool, evidence: list[str]) -> int:
    value = _load(path)
    status = evaluate_qualification(path, app_version=_version())
    if status.invalid:
        raise SystemExit(
            "The evidence contract does not match this KFPS build. Initialize a new matrix first: "
            + ", ".join(status.invalid)
        )
    record_value = value["checks"][check_id]
    record_value["passed"] = bool(passed)
    record_value["evidence"] = [str(item).strip() for item in evidence if str(item).strip()]
    record_value["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_atomic(path, value)
    print(f"Recorded {check_id}: {'PASS' if passed else 'FAIL'}")
    return 0


def show_status(path: Path) -> int:
    status = evaluate_qualification(path, app_version=_version())
    print(status.detail)
    if status.invalid:
        print("Contract errors:")
        for item in status.invalid:
            print(f"  - {item}")
    if status.missing:
        print("Missing or failed checks:")
        for item in status.missing:
            print(f"  - {item}: {REQUIRED_CHECKS[item]}")
    return 0 if status.qualified else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintain full-livery release qualification evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("--reset", action="store_true")
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("check_id", choices=sorted(REQUIRED_CHECKS))
    outcome = record_parser.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--pass", dest="passed", action="store_true")
    outcome.add_argument("--fail", dest="passed", action="store_false")
    record_parser.add_argument("--evidence", action="append", default=[], required=True)
    subparsers.add_parser("status")
    args = parser.parse_args(argv)
    path = _paths().qualification_file
    if args.command == "initialize":
        return initialize(path, reset=args.reset)
    if args.command == "record":
        return record(path, args.check_id, args.passed, args.evidence)
    return show_status(path)


if __name__ == "__main__":
    raise SystemExit(main())
