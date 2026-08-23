from __future__ import annotations

import argparse
import sys
from pathlib import Path


UI_ROOT = Path(__file__).resolve().parent
APP_ROOT = UI_ROOT.parent
for item in (str(UI_ROOT / "src"), str(APP_ROOT)):
    if item not in sys.path:
        sys.path.insert(0, item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    worker = subparsers.add_parser("worker")
    worker.add_argument("--request", required=True)
    worker.add_argument("--result", required=True)
    worker.add_argument("--parent-pid", type=int, required=True)

    inspector = subparsers.add_parser("inspector")
    inspector.add_argument("--config", required=True)
    inspector.add_argument("--ready", required=True)
    inspector.add_argument("--stop", required=True)
    inspector.add_argument("--parent-pid", type=int, required=True)

    args = parser.parse_args(argv)
    if args.mode == "worker":
        from kfps_ui.experimental.full_livery.worker_main import run_request

        return run_request(args.request, args.result, args.parent_pid)

    from kfps_ui.experimental.full_livery.inspector_main import run

    return run(args.config, args.ready, args.stop, args.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
