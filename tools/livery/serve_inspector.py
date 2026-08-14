#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .inspector_server import LiveryInspectorServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve one verified KFPS full-livery package for local inspection.")
    parser.add_argument("package", type=Path)
    parser.add_argument("--static-root", type=Path, default=Path(__file__).resolve().parents[1] / "livery-inspector")
    parser.add_argument("--url-file", type=Path)
    args = parser.parse_args()

    server = LiveryInspectorServer(args.static_root)
    server.set_package(args.package)
    url = server.start()
    print(url, flush=True)
    if args.url_file:
        args.url_file.parent.mkdir(parents=True, exist_ok=True)
        args.url_file.write_text(url + "\n", encoding="utf-8")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
