from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.livery import PACKAGE_COMPILER_REVISION

from .paths import CACHE_REVISION


QUALIFICATION_FORMAT = "kfps_full_livery_qualification_v1"
REQUIRED_CHECKS = {
    "store.microsoft": "Microsoft Store/Xbox FH6 save and game installation",
    "store.steam": "Steam FH6 save and game installation",
    "gpu.amd": "AMD GPU repeated 3D inspection",
    "gpu.nvidia": "NVIDIA GPU repeated 3D inspection",
    "gpu.intel": "Intel GPU repeated 3D inspection",
    "car.coupe": "Coupe or sports-car chassis",
    "car.sedan": "Sedan or saloon chassis",
    "car.hatch": "Hatchback chassis",
    "car.suv": "SUV or off-road chassis",
    "car.utility": "Pickup, buggy, or unusual multi-part chassis",
    "render.masks": "Masked vinyl layers",
    "render.windows": "Window and windshield vinyl layers",
    "render.layer_order": "Overlaps, fades, gradients, and layer order",
    "lifecycle.cold": "First uncached scan, conversion, and render",
    "lifecycle.warm": "Restart with durable index and cached render",
    "lifecycle.switching": "At least 25 repeated package/car switches",
    "lifecycle.cancel": "Page leave and superseded work cancel cleanly",
    "lifecycle.recovery": "Worker failure, abandoned session, and recovery record",
    "package.round_trip": "Export, reopen, validate, install, and rescan exact-car package",
    "package.security": "Traversal, tamper, identity, and foreign-artwork checks",
}


@dataclass(frozen=True)
class QualificationStatus:
    qualified: bool
    missing: tuple[str, ...]
    invalid: tuple[str, ...]
    detail: str


def evaluate_qualification(
    path: str | Path,
    *,
    app_version: str,
) -> QualificationStatus:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except OSError:
        return QualificationStatus(False, tuple(REQUIRED_CHECKS), (), "No qualification evidence is recorded.")
    except ValueError:
        return QualificationStatus(False, tuple(REQUIRED_CHECKS), ("document",), "Qualification evidence is unreadable.")
    if not isinstance(value, dict):
        return QualificationStatus(False, tuple(REQUIRED_CHECKS), ("document",), "Qualification evidence is not an object.")

    invalid = []
    if value.get("format") != QUALIFICATION_FORMAT:
        invalid.append("format")
    if str(value.get("app_version") or "") != str(app_version):
        invalid.append("app_version")
    try:
        package_revision = int(value.get("package_compiler_revision"))
    except (TypeError, ValueError):
        package_revision = -1
    if package_revision != PACKAGE_COMPILER_REVISION:
        invalid.append("package_compiler_revision")
    try:
        cache_revision = int(value.get("cache_revision"))
    except (TypeError, ValueError):
        cache_revision = -1
    if cache_revision != CACHE_REVISION:
        invalid.append("cache_revision")

    checks = value.get("checks")
    if not isinstance(checks, dict):
        checks = {}
        invalid.append("checks")
    missing = []
    for check_id in REQUIRED_CHECKS:
        record = checks.get(check_id)
        if not isinstance(record, dict) or record.get("passed") is not True:
            missing.append(check_id)
            continue
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not any(str(item).strip() for item in evidence):
            missing.append(check_id)

    qualified = not missing and not invalid
    detail = (
        "The current full-livery validation matrix has passed."
        if qualified
        else f"Qualification incomplete: {len(missing)} checks missing, {len(invalid)} contract errors."
    )
    return QualificationStatus(qualified, tuple(missing), tuple(invalid), detail)


def qualification_template(app_version: str) -> dict[str, Any]:
    return {
        "format": QUALIFICATION_FORMAT,
        "app_version": str(app_version),
        "package_compiler_revision": PACKAGE_COMPILER_REVISION,
        "cache_revision": CACHE_REVISION,
        "checks": {
            check_id: {
                "description": description,
                "passed": False,
                "evidence": [],
            }
            for check_id, description in REQUIRED_CHECKS.items()
        },
    }
