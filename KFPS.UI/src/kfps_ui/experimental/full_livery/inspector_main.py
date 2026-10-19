from __future__ import annotations

import argparse
import json
import os
import re
import time
import traceback
from pathlib import Path

import psutil

from .protocol import write_json_atomic
from .operations import studio_module


def run(config_file: str | Path, ready_file: str | Path, stop_file: str | Path, parent_pid: int) -> int:
    config = json.loads(Path(config_file).read_text(encoding="utf-8"))
    server = None
    try:
        descriptor = str(config.get("readonly_descriptor") or "")
        if not descriptor:
            raise ValueError("The shared Studio renderer was not prepared. Reopen this livery.")
        expected_id = str(config.get("package_id") or "")
        expected_hash = str(config.get("readonly_descriptor_sha256") or "")
        if not expected_id or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
            raise ValueError("The prepared viewer identity is missing. Reopen this livery.")
        module = studio_module(config["app_root"], "readonly_server")
        server = module.ReadonlyPreviewServer(descriptor, Path(config["app_root"]),
            expected_package_id=expected_id, expected_descriptor_sha256=expected_hash)
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
        if server is not None:
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
