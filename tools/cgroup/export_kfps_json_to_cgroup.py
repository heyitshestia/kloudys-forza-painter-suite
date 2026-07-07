#!/usr/bin/env python3
"""Export KFPS JSON into a flat Forza C_group prototype file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .cgroup_codec import build_flat_cgroup_from_json, read_flat_cgroup, write_cgroup_file
except ImportError:  # pragma: no cover - direct script execution fallback
    from cgroup_codec import build_flat_cgroup_from_json, read_flat_cgroup, write_cgroup_file


def output_cgroup_path(output: Path) -> Path:
    if output.suffix:
        return output
    return output / "C_group"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", type=Path, help="KFPS JSON with a shapes list")
    parser.add_argument("output", type=Path, help="Output C_group file or folder")
    parser.add_argument("--report", type=Path, help="Optional parse-back report JSON")
    args = parser.parse_args()

    payload = build_flat_cgroup_from_json(args.json)
    cgroup_path = write_cgroup_file(output_cgroup_path(args.output), payload)
    parsed = read_flat_cgroup(cgroup_path)
    report = {
        "format": "kfps_cgroup_export_report_v1",
        "source_json": str(args.json),
        "cgroup": str(cgroup_path),
        "layers": parsed["count"],
        "payload_size": parsed["payload_size"],
        "shape_ids_first_32": [layer["shape_id"] for layer in parsed["layers"][:32]],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

