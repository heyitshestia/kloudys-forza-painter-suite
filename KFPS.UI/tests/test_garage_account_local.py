"""Opt-in real account workflow, with isolated settings and no save writes."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT)]
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from kfps_ui.models import DictListModel


@unittest.skipUnless(os.environ.get("KFPS_GARAGE_REAL_DISCOVERY") == "1", "Opt-in local FH6 account workflow")
class GarageLocalAccountTests(unittest.TestCase):
    def test_discover_select_and_restore_with_installed_reader(self):
        self.assertTrue((ROOT / "tools/garage-reader/manifest.json").is_file(), "Garage support missing")
        app = QCoreApplication.instance() or QCoreApplication([])
        evidence = Path(os.environ.get("KFPS_GARAGE_LOCAL_EVIDENCE", ROOT / "runtime/garage-accounts-20261103"))
        evidence.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="local-account-check-", dir=evidence) as folder:
            root = Path(folder)
            paths = AppPaths(ROOT, ROOT / "KFPS.UI", ROOT / "KFPS.UI/qml", ROOT / "KFPS.UI/assets",
                             root / "runtime", Path(sys.executable))
            (paths.runtime_root / "garage").mkdir(parents=True)
            log = LogService()
            liveries = SimpleNamespace(sourceModel=DictListModel(["path", "carId", "modelCode", "title"]))
            real_cars = os.environ.get("KFPS_GARAGE_REAL_CARS") == "1"
            if real_cars:
                from tools.livery.vehicle_assets import discover_fh6_game_folder
                game = discover_fh6_game_folder()
                self.assertIsNotNone(game, "No installed FH6 car catalogue")
                liveries.gameFolder = str(game)
            service = GarageService(paths, log, liveries)
            restored = None
            try:
                def wait(target):
                    deadline = time.monotonic() + 65
                    while (target.busy or target.catalogueBusy) and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(.005)
                    self.assertFalse(target.busy, "Local Garage workflow exceeded its deadline")
                    self.assertFalse(target.catalogueBusy, "Local catalogue exceeded its deadline")
                started = time.perf_counter()
                service.enter()
                wait(service)
                self.assertFalse(service.hasSource)
                if real_cars:
                    self.assertTrue(service._catalogue, service.catalogueStatus)
                    self.assertFalse(service.ownershipKnown)
                    self.assertEqual(len(service._catalogue), service.browseTotal)
                rows = [row for row in service.accountOptions if row["available"]]
                self.assertTrue(rows, "No readable FH6 accounts found")
                discovery_ms = round((time.perf_counter() - started) * 1000)
                checks = []
                for row in rows[:4]:
                    started = time.perf_counter()
                    service.selectAccount(row["id"])
                    wait(service)
                    self.assertEqual(row["id"], service.selectedAccountId, service.status)
                    self.assertIsNotNone(service._state)
                    self.assertEqual(service.total, service.summary["cars"])
                    checks.append({"cars": service.total, "elapsedMs": round((time.perf_counter() - started) * 1000)})
                service.setSort("livery")
                service.setFilter("owned")
                restored = GarageService(paths, log, liveries)
                restored.enter()
                wait(restored)
                self.assertEqual(service.selectedAccountId, restored.selectedAccountId)
                self.assertEqual(service.total, restored.total)
                self.assertTrue(restored.diagnosticSummary["lastScanReused"])
                self.assertEqual(service.sortIndex, restored.sortIndex)
                self.assertEqual(service.filterIndex, restored.filterIndex)
                self.assertEqual(service.total, restored.visibleCount)
                self.assertEqual(service._catalogue, restored._catalogue)
                (evidence / "local-account-workflow.json").write_text(json.dumps({
                    "passed": True, "discovered": len(service.accountOptions), "available": len(rows),
                    "discoveryMs": discovery_ms, "selections": checks, "restartReused": True,
                    "isolatedSettings": True, "gameWrites": False,
                    "catalogueCars": len(service._catalogue),
                    "stockThumbnails": service.diagnosticSummary["stockThumbnailCount"],
                    "namedAccounts": sum(not row["label"].startswith("FH6 account ") for row in service.accountOptions),
                    "viewRestored": True,
                }, indent=2), encoding="utf-8")
            finally:
                closed = service.close()
                if restored:
                    closed = restored.close() and closed
                log.close()
                self.assertTrue(closed, "Garage worker did not stop")


if __name__ == "__main__":
    unittest.main()
