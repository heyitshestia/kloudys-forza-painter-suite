"""Native package action boundary; no visible launches or game writes."""
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from kfps_ui.app_paths import AppPaths
from kfps_ui.editor_service import EditorService
from kfps_ui.experimental.full_livery.paths import FullLiveryPaths


UI = Path(__file__).resolve().parents[1]


class LiveryStudioPackageActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="studio-package-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                             self.root / "runtime", self.root / "python/python.exe")
        self.packages = FullLiveryPaths.for_app(self.paths).package_root
        self.packages.mkdir(parents=True)
        self.package = self.packages / "Artwork.kfpslivery"
        self.package.write_bytes(b"package boundary fixture")
        with patch.object(EditorService, "refresh"):
            self.service = EditorService(self.paths, Mock(), Mock(), Mock())
        self.addCleanup(self.service.close)

    def test_action_snapshots_path_and_theme_then_queues_background_work(self):
        theme = {"name": "Custom", "variables": {"--accent": "#ee4477"}}
        with patch.object(self.service, "_start_thread") as start:
            self.service.launchPackageInLiveryStudio(str(self.package), theme)
            self.assertTrue(self.service.studioLaunching)
            self.assertEqual(self.service.studioPackagePath, str(self.package))
            self.assertIn("package", self.service.studioStatus.lower())
            target, snapshot = start.call_args.kwargs["args"]
            self.assertEqual(Path(target), self.package)
            theme["variables"]["--accent"] = "changed"
            self.assertEqual(snapshot["variables"]["--accent"], "#ee4477")
            self.assertEqual(start.call_args.kwargs["target"], self.service._launch_package_studio_worker)

    def test_duplicate_and_closed_launches_do_not_queue(self):
        with patch.object(self.service, "_start_thread") as start:
            self.service.launchPackageInLiveryStudio(str(self.package))
            self.service.launchPackageInLiveryStudio(str(self.package))
            self.service.close()
            self.service.launchPackageInLiveryStudio(str(self.package))
            self.assertEqual(start.call_count, 1)

    def test_rejects_missing_wrong_type_directory_and_outside_library(self):
        outside = self.root / "outside.kfpslivery"
        outside.write_bytes(b"outside")
        wrong_type = self.packages / "C_livery"
        wrong_type.write_bytes(b"in-game save must not be accepted")
        with patch.object(self.service, "_start_thread") as start:
            for path in ("", self.packages, wrong_type, outside,
                         self.packages / "missing.kfpslivery", "x" * 32769):
                with self.subTest(path=str(path)[:100]):
                    self.service.launchPackageInLiveryStudio(str(path))
                    self.assertFalse(self.service.studioLaunching)
            start.assert_not_called()

    def test_rejects_hardlinked_and_redirected_package(self):
        alias = self.packages / "alias.kfpslivery"
        os.link(self.package, alias)
        with patch.object(self.service, "_start_thread") as start:
            self.service.launchPackageInLiveryStudio(str(alias))
            self.assertFalse(self.service.studioLaunching)
            start.assert_not_called()
        alias.unlink()
        with patch.object(Path, "is_symlink", return_value=True), \
                patch.object(self.service, "_start_thread") as start:
            self.service.launchPackageInLiveryStudio(str(self.package))
            start.assert_not_called()

    def test_rejects_invalid_and_oversized_theme_without_starting(self):
        with patch.object(self.service, "_start_thread") as start:
            for theme in ({"bad": float("nan")}, {"name": "a" * 32769}):
                self.service.launchPackageInLiveryStudio(str(self.package), theme)
                self.assertFalse(self.service.studioLaunching)
            start.assert_not_called()

    def bridge(self, request=None, error=None):
        return SimpleNamespace(request_for_package=Mock(return_value=request, side_effect=error),
                               validate_request=Mock(side_effect=lambda value: value))

    def run_worker(self, bridge):
        spec = SimpleNamespace(loader=Mock())
        with patch("kfps_ui.editor_service._studio_module_path", return_value=Path("host_bridge.py")), \
                patch("kfps_ui.editor_service.importlib.util.spec_from_file_location", return_value=spec), \
                patch("kfps_ui.editor_service.importlib.util.module_from_spec", return_value=bridge), \
                patch.object(self.service, "_launch_studio_worker") as launch:
            self.service._launch_package_studio_worker(str(self.package), {"name": "Custom"})
            return launch

    def test_worker_uses_validated_layout_and_preserves_package(self):
        before = self.package.read_bytes()
        bridge = self.bridge({"name": "Artwork", "layout": {"vehicle": {"car_id": 1296}}})
        launch = self.run_worker(bridge)
        bridge.request_for_package.assert_called_once_with(self.package)
        bridge.validate_request.assert_called_once()
        request = launch.call_args.args[0]
        self.assertEqual(request["layout"]["vehicle"]["car_id"], 1296)
        self.assertEqual(request["ui_theme"], {"name": "Custom"})
        self.assertNotIn("path", request)
        self.assertEqual(before, self.package.read_bytes())

    def test_worker_rechecks_missing_package_before_decoding(self):
        self.package.unlink()
        bridge = self.bridge()
        self.run_worker(bridge).assert_not_called()
        bridge.request_for_package.assert_not_called()
        self.assertFalse(self.service.studioLaunching)

    def test_worker_rejects_validation_errors_and_cancellation(self):
        bridge = self.bridge(error=ValueError("Package artwork is unsupported."))
        self.run_worker(bridge).assert_not_called()
        self.assertIn("unsupported", self.service.studioStatus)
        bridge = self.bridge({"name": "Artwork", "layout": {}})
        self.service._cancel_event.set()
        self.run_worker(bridge).assert_not_called()
        bridge.request_for_package.assert_not_called()

    def test_cancellation_during_decode_does_not_launch(self):
        bridge = self.bridge({"name": "Artwork", "layout": {}})
        def cancelled(_path):
            self.service._cancel_event.set()
            return {"name": "Artwork", "layout": {}}
        bridge.request_for_package.side_effect = cancelled
        self.run_worker(bridge).assert_not_called()

    def test_qml_action_is_package_only_and_directly_below_preview(self):
        details = (UI / "qml/components/LiveryPreviewDetails.qml").read_text(encoding="utf-8")
        start = details.index('objectName: "openSelectedLiveryStudioButton"')
        action = details[start:details.index("\n        }", start)]
        self.assertIn("!root.viewingPreview && !root.sourceMode && root.hasSelection", action)
        self.assertIn("!editorService.studioLaunching", action)
        self.assertIn("root.studioRequested()", action)
        self.assertLess(details.index('objectName: "openSelectedLiveryPreviewButton"'), start)
        self.assertLess(start, details.index('text: fullLiveryService.running ? "Working..." : "Export Selected"'))
        page = (UI / "qml/pages/LiveryPage.qml").read_text(encoding="utf-8")
        self.assertIn("launchPackageInLiveryStudio(fullLiveryService.browsedPackage", page)
        self.assertIn("editorService.studioPackagePath === fullLiveryService.browsedPackage", page)
        self.assertIn("root.hasStudioPackageStatus", page)

    def test_status_remains_bound_to_package_after_failure_and_clears_for_other_launches(self):
        with patch.object(self.service, "_start_thread"):
            self.service.launchPackageInLiveryStudio(str(self.package))
            self.service._finish_studio_launch(False, "This package cannot be edited exactly.")
            self.assertEqual(self.service.studioPackagePath, str(self.package))
            self.assertIn("cannot be edited", self.service.studioStatus)
            self.service.launchLiveryStudio()
            self.assertEqual(self.service.studioPackagePath, "")


if __name__ == "__main__":
    unittest.main()
