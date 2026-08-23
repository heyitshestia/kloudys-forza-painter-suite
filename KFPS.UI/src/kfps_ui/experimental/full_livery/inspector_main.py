from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path

import psutil

from tools.livery.inspector_server import LiveryInspectorServer

from .protocol import write_json_atomic


def run(config_file: str | Path, ready_file: str | Path, stop_file: str | Path, parent_pid: int) -> int:
    config = json.loads(Path(config_file).read_text(encoding="utf-8"))
    server = LiveryInspectorServer(config["inspector_root"])
    try:
        server.set_package(config["package"])
        server.set_local_mesh(config["mesh"])
        server.set_local_render_contract(config["render_root"], config["render_contract"])
        url = server.start()
        write_json_atomic(ready_file, {"url": url, "pid": os.getpid()})
        stop = Path(stop_file)
        while not stop.exists() and (parent_pid <= 0 or psutil.pid_exists(parent_pid)):
            time.sleep(0.05)
        return 0
    except BaseException:
        Path(ready_file).parent.mkdir(parents=True, exist_ok=True)
        (Path(ready_file).parent / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return 2
    finally:
        server.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--stop", required=True)
    parser.add_argument("--parent-pid", type=int, default=os.getppid())
    args = parser.parse_args(argv)
    return run(args.config, args.ready, args.stop, args.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
