"""Bounded external process-tree samples for an already running native test."""
import argparse
import faulthandler
import json
from pathlib import Path
import time

import psutil


def sample(process):
    try:
        memory = process.memory_info()
        cpu = process.cpu_times()
        arguments = process.cmdline()
        kind = next((argument[7:] for argument in arguments if argument.startswith("--type=")), "host")
        if process.name().lower() in ("node", "node.exe"):
            kind = "test-driver"
        return {"pid": process.pid, "kind": kind, "rss": memory.rss,
                "private": getattr(memory, "private", memory.vms),
                "cpuSeconds": cpu.user + cpu.system, "threads": process.num_threads()}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--stop-private-mib", type=float, default=0)
    parser.add_argument("--min-free-mib", type=float, default=0)
    parser.add_argument("--warn-free-mib", type=float, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    directory = args.run.resolve()
    if not directory.is_relative_to(root / "runtime" / "test-runs"):
        raise ValueError("Resource samples belong in an isolated test run")
    record = json.loads((directory / "process.json").read_text(encoding="utf-8"))
    parent = psutil.Process(record["pid"])
    if abs(parent.create_time() - record["started"]) > 30:
        raise ValueError("Native test PID was reused")
    target = directory / "native-resources.jsonl"
    started = time.monotonic()
    with target.open("x", encoding="utf-8") as stream:
        while parent.is_running() and time.monotonic() - started < 2100:
            # A blocked Windows process query must fail loudly, not stop sampling
            # indefinitely while the launcher continues to claim memory coverage.
            faulthandler.dump_traceback_later(20, exit=True)
            try:
                processes = [parent, *parent.children(recursive=True)]
            except psutil.NoSuchProcess:
                break
            values = [value for process in processes if (value := sample(process))]
            row = {"utc": time.time(), "seconds": time.monotonic() - started,
                   "logicalCpus": psutil.cpu_count(), "availableMemory": psutil.virtual_memory().available,
                   "processes": values}
            row["lowMemoryWarning"] = args.warn_free_mib > 0 and row["availableMemory"] < args.warn_free_mib * 1024**2
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            faulthandler.cancel_dump_traceback_later()
            private = sum(value["private"] for value in values if value["kind"] != "test-driver")
            over_budget = args.stop_private_mib > 0 and private > args.stop_private_mib * 1024**2
            low_memory = args.min_free_mib > 0 and row["availableMemory"] < args.min_free_mib * 1024**2
            signal = directory / "stop-test.json"
            if (over_budget or low_memory) and not signal.exists():
                signal.write_text(json.dumps({"reason": "private budget" if over_budget else "low available memory",
                    "private": private, "available": row["availableMemory"], "utc": row["utc"]}), encoding="utf-8")
            time.sleep(5)
    print(json.dumps({"path": str(target), "seconds": time.monotonic() - started}))


if __name__ == "__main__":
    main()
