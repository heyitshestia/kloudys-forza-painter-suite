#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.livery.package import create_full_livery_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an FH6 C_livery folder as a shareable KFPS livery package.")
    parser.add_argument("source", type=Path, help="Livery_* folder or its C_livery file")
    parser.add_argument("output", type=Path, help="Destination .kfpslivery file")
    parser.add_argument("--game-folder", type=Path, help="FH6 install or Content folder used to resolve the matching car")
    parser.add_argument("--vehicle-index-cache", type=Path)
    args = parser.parse_args()
    result = create_full_livery_package(
        args.source,
        args.output,
        game_folder=args.game_folder,
        vehicle_index_cache=args.vehicle_index_cache,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
