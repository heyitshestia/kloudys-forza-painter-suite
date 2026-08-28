from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .contracts import LocatorRequest
from .diagnostics import build_diagnostic, persist_diagnostic
from .engine import LiveMemoryLocatorEngine


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="KFPS versioned live-memory locator engine")
    parser.add_argument("--root", default=Path.cwd())
    parser.add_argument("--game", required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--layer-count", type=int, required=True)
    parser.add_argument("--purpose", choices=("import", "export", "diagnostic"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit-mb", type=int, default=2048)
    parser.add_argument("--max-matches", type=int, default=500000)
    parser.add_argument("--inspect-radius", type=parse_int, default=0x800)
    parser.add_argument("--fast-seconds", type=int, default=45)
    parser.add_argument("--research-seconds", type=int, default=90)
    args = parser.parse_args()

    request = LocatorRequest(
        game=args.game,
        pid=args.pid,
        layer_count=args.layer_count,
        purpose=args.purpose,
        output_path=Path(args.output),
        limit_mb=args.limit_mb,
        max_matches=args.max_matches,
        inspect_radius=args.inspect_radius,
        fast_seconds=args.fast_seconds,
        research_seconds=args.research_seconds,
    )
    try:
        report = LiveMemoryLocatorEngine(args.root).locate(request)
    except Exception as exc:
        report = build_diagnostic(
            request=request,
            root=args.root,
            process={"pid": request.pid, "name": "", "started": 0.0, "executable": ""},
            profile={"game": request.game, "strategy": "unavailable", "profile_id": ""},
            status="error",
            reason=f"Locator engine failed before scanning completed: {exc}",
            authoritative=True,
            attempts=[{"name": "engine", "status": "error", "error": str(exc)}],
            selection=None,
        )
        report = persist_diagnostic(args.root, request.output_path, report)
    status = report["outcome"]["status"]
    print(f"Locator outcome: {status}. {report['outcome'].get('reason') or ''}", flush=True)
    print(f"Locator diagnostic: {request.output_path}", flush=True)
    return {"located": 0, "refused": 2, "no_match": 3, "error": 4}.get(status, 4)


if __name__ == "__main__":
    raise SystemExit(main())
