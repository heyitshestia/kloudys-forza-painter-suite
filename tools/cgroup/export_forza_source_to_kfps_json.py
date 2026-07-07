#!/usr/bin/env python3
"""Export a Forza C_group/C_livery file artifact into KFPS JSON.

This is a prototype export-only path. It does not touch the running game and it
does not use KFPS JSON as input truth. Point it at a folder containing C_group or
C_livery, or directly at one of those files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .forza_source_decoder import DecodeError, decode_forza_source
except ImportError:  # pragma: no cover - direct script execution fallback
    from forza_source_decoder import DecodeError, decode_forza_source


def default_report_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="C_group/C_livery file or folder containing one")
    parser.add_argument("output", type=Path, help="Output KFPS JSON path")
    parser.add_argument("--report", type=Path, help="Optional decode report path")
    parser.add_argument(
        "--allow-locked",
        action="store_true",
        help="Development-only override for locked payload markers. Do not use for public builds.",
    )
    parser.add_argument(
        "--game",
        default="fh6",
        choices=("fh6", "fh5", "fm", "fm8"),
        help="Source game shape-word mapping to use before writing KFPS JSON.",
    )
    args = parser.parse_args()

    try:
        decoded = decode_forza_source(args.source, allow_locked=args.allow_locked, game=args.game)
    except DecodeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    payload = {
        "format": "kfps_forza_file_export_json_v1",
        "source_path": decoded.source_path,
        "source_kind": decoded.source_kind,
        "target_game": decoded.report.get("target_game"),
        "shapes": decoded.layers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report_path = args.report or default_report_path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(decoded.report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "source": decoded.source_path,
                "kind": decoded.source_kind,
                "target_game": decoded.report.get("target_game"),
                "layers": len(decoded.layers),
                "output": str(args.output),
                "report": str(report_path),
                "warnings": decoded.report.get("warnings", []) + decoded.report.get("identity_warnings", []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
