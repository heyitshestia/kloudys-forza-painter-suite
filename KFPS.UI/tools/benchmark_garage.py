"""Headless Garage service benchmark using synthetic saves and no game access."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Frozen kfps_ui module directory")
    parser.add_argument("--cars", type=int, default=344)
    parser.add_argument("--liveries", type=int, default=500)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory", action="store_true")
    args = parser.parse_args()
    import kfps_ui
    if args.baseline:
        kfps_ui.__path__.insert(0, str(args.baseline.resolve(strict=True)))
    from PySide6.QtCore import QCoreApplication
    from kfps_ui.app_paths import AppPaths
    from kfps_ui.garage_index import REQUIRED, GarageStore, profile_identity
    from kfps_ui.garage_service import GarageService
    from kfps_ui.log_service import LogService
    from kfps_ui.models import DictListModel

    app = QCoreApplication.instance() or QCoreApplication([])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metrics = {}
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=args.output.parent) as temp:
        root = Path(temp)
        source = root / "saves/Profile/garage.json"
        source.parent.mkdir(parents=True)
        raw = [{"Id": n, "CarId": n % 172 + 1, **{p: n % 172 * 1000 for p in REQUIRED},
                "LiveryFileName": f"Livery_{n % args.liveries:06d}"} for n in range(args.cars)]
        source.write_text(json.dumps(raw), encoding="utf-8")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        catalogue = root / "vehicles.json"
        catalogue.write_text(json.dumps({"format": "kfps_fh6_vehicle_asset_index_v1",
            "vehicles": {str(n): {"model_code": f"MODEL_{n:04d}"} for n in range(1, 683)}}))
        source_rows = [{"path": str(root / f"saves/Livery_{n:06d}/C_livery"),
                       "carId": n % 172 + 1, "modelCode": f"CAR_{n % 172 + 1:04d}",
                       "title": f"Livery {n}", "available": True} for n in range(args.liveries)]
        if args.memory:
            gc.collect()
            tracemalloc.start()
        paths = AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", Path(sys.executable))
        sources = DictListModel(["path", "carId", "modelCode", "title", "available"])
        sources.replace(source_rows)
        log = LogService()
        service = GarageService(paths, log, SimpleNamespace(sourceModel=sources,
            _experiment_paths=SimpleNamespace(vehicle_index=catalogue)))
        resets = []
        service.cars.modelReset.connect(lambda: resets.append(True))

        def wait():
            deadline = time.monotonic() + 45
            while service.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.001)
            assert not service.busy, service.status
            assert service.status.startswith(("Garage refreshed /", "Garage unchanged /")), service.status
            assert service.total == args.cars, service.status

        def measure(name, operation, count=1):
            samples = []
            before = len(resets)
            for _ in range(count):
                started = time.perf_counter()
                operation()
                samples.append((time.perf_counter() - started) * 1000)
            metrics[name] = {"medianMs": statistics.median(samples), "samplesMs": samples,
                             "modelResets": len(resets) - before}

        try:
            measure("firstScan", lambda: (service.scanSource(str(source)), wait()))
            service.select(str(args.cars - 1))
            if not args.memory:
                measure("details100", lambda: [service.details for _ in range(100)], 3)
                def selections():
                    for n in range(100):
                        service.select(str(n * args.cars // 100))
                        assert service.details["parts"]
                measure("select100", selections, 3)
                def searches():
                    for text in ("CAR", "CAR_0", "CAR_001", "CAR_0010", "Copy", "Copy 25", "absent", ""):
                        service.setSearch(text)
                    assert service.visibleCount == args.cars
                measure("search8", searches, 3)
                measure("reactivate", service.activate, 7)
                measure("unchangedScan", lambda: (service.refresh(), wait()), 3)
                assert service.diagnosticSummary["lastScanReused"]
                sources.set_row_value(0, "title", "Changed livery")
                service.select("0")
                assert service.details["livery"] == "Changed livery"
                sources.replace([])
                assert not service.details["matched"]
                assert GarageStore(service.store.root).load(profile_identity(source))["cars"]
            else:
                service.details
                service.activate()
                gc.collect()
                retained, peak = tracemalloc.get_traced_memory()
                metrics["pythonMemory"] = {"retainedBytes": retained, "peakBytes": peak}
                other = root / "other/Profile/garage.json"
                other.parent.mkdir(parents=True)
                other.write_bytes(source.read_bytes())
                for path in (source, other, source, other):
                    service.select("0")
                    service.details
                    service.scanSource(str(path))
                    wait()
                gc.collect()
                retained, peak = tracemalloc.get_traced_memory()
                metrics["pythonMemoryAfterSwitching"] = {"retainedBytes": retained, "peakBytes": peak}
                tracemalloc.stop()
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        finally:
            assert service.close()
            log.close()
        result = {"implementation": str(args.baseline or "working-tree"), "cars": args.cars,
                  "liveries": args.liveries, "metrics": metrics, "sourceUnchanged": True,
                  "module": sys.modules["kfps_ui.garage_service"].__file__}
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
