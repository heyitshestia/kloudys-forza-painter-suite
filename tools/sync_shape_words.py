"""Generate the editor's numeric slot catalog from the shared native identities."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kfps_shapes.identity import VINYL_TYPE_BASES
from tools.editor_manifest import editor_web_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = editor_web_root(ROOT) / "shape-words.json"
    payload = {
        "format": "fh6_fabric_shape_words_v1",
        "identity_schema": "kfps_native_slots_v1",
        "families": {
            family: {str(index): (base & 0xFFFF) + index - 1 for index in range(1, 41)}
            for family, base in VINYL_TYPE_BASES.items()
        },
    }
    if args.check:
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != payload:
            print("Shape catalog is out of date. Run tools/sync_shape_words.py.")
            return 1
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
