#!/usr/bin/env python3
"""Convert a flat C_group prototype/import fixture into KFPS JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .cgroup_codec import read_flat_cgroup
    from .shape_identity import TYPE_CODE_BASE
except ImportError:  # pragma: no cover - direct script execution fallback
    from cgroup_codec import read_flat_cgroup
    from shape_identity import TYPE_CODE_BASE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cgroup", type=Path, help="C_group file or containing folder")
    parser.add_argument("output", type=Path, help="Output KFPS JSON")
    args = parser.parse_args()

    parsed = read_flat_cgroup(args.cgroup)
    shapes = []
    for layer in parsed["layers"]:
        word = int(layer["shape_id"]) & 0xFFFF
        data = list(layer["data"])
        data.append(1 if layer.get("mask") else 0)
        shapes.append(
            {
                "type": TYPE_CODE_BASE + word,
                "type_word": word,
                "type_word_hex": f"0x{word:04x}",
                "data": data,
                "color": list(layer["color_rgba"]),
                "mask": bool(layer.get("mask")),
                "score": 0,
                "source_format": "cgroup_flat",
            }
        )
    payload = {
        "format": "kfps_cgroup_flat_json_v1",
        "source_cgroup": str(args.cgroup),
        "shapes": shapes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "layers": len(shapes)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

