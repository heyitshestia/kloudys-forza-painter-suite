"""Exercise the native livery browser with isolated settings and no game writes."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"

from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
import app as application


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--theme", default="Night Blossom")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--thumbnail-root", type=Path,
                        help="Optional ContainersRoot, sampled read-only for up to 12 real thumbnails")
    options = parser.parse_args()
    if options.scale not in (1.0, 1.25, 1.5, 2.0):
        parser.error("scale must be 1, 1.25, 1.5 or 2")
    os.environ["QT_SCALE_FACTOR"] = str(options.scale)
    out = options.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = {"cases": [], "errors": [], "qml_errors": [], "screenshots": []}
    results.update(theme=options.theme, display_scale=options.scale)
    refresh_packages = FullLiveryService.refreshPackages

    def messages(kind, context, message):
        if any(token in message for token in (
            "ReferenceError", "TypeError", "Cannot assign", "Binding loop", "is not a type",
            "Detected recursive rearrange",
        )):
            results["qml_errors"].append(message)

    with tempfile.TemporaryDirectory(prefix="kfps-livery-grid-", dir=out) as temporary:
        isolated = Path(temporary)
        for variable, folder in (("LOCALAPPDATA", "local"), ("APPDATA", "roaming"),
                                 ("TEMP", "tmp"), ("TMP", "tmp")):
            profile = isolated / folder
            profile.mkdir(exist_ok=True)
            os.environ[variable] = str(profile)
        shutil.copy2(ROOT / "VERSION", isolated / "VERSION")
        paths = AppPaths(isolated, UI, UI / "qml", UI / "assets",
                         isolated / "runtime", Path(sys.executable))
        samples = []
        if options.thumbnail_root:
            for container in sorted(options.thumbnail_root.glob("Livery_*")):
                candidate = container / "bigThumb.webp"
                if candidate.is_file():
                    samples.append(candidate)
                    if len(samples) == 12:
                        break
            assert samples, "No original thumbnails at the explicitly supplied ContainersRoot"

        rows = []
        for index in range(18):
            folder = isolated / "fixtures" / f"Livery with spaces #{index:02d}"
            folder.mkdir(parents=True)
            source = folder / "C_livery"
            source.write_bytes(b"synthetic source, never parsed or exported")
            if index < 12:
                if samples:
                    shutil.copy2(samples[index % len(samples)], folder / "bigThumb.webp")
                else:
                    image = QImage(670, 376, QImage.Format_RGB32)
                    image.fill(QColor.fromHsv(index * 25, 150, 160))
                    assert image.save(str(folder / "bigThumb.webp"))
            elif index == 13:
                (folder / "bigThumb.webp").write_bytes(b"broken thumbnail fixture")
            rows.append(dict(
                path=str(source), title=f"Livery {index + 1:02d}" + (
                    " - A very long title with <markup> & literal characters" if index == 0 else ""),
                modelCode="TEST_CAR", carId=1296 + index, placementCount=50 + index,
                exportable=index != 2, privacyDetail="Preview only" if index == 2 else "",
                modified="2026-09-09", hasHeader=True,
            ))
        results["original_thumbnail_samples"] = len(samples)

        def install(app, window, controller, community, settings, jsons, args):
            context = QQmlEngine.contextForObject(window)
            service = context.contextProperty("fullLiveryService")
            editor = context.contextProperty("editorService")

            def items():
                pending = [window.contentItem()]
                found = []
                while pending:
                    item = pending.pop()
                    found.append(item)
                    pending.extend(item.childItems())
                return found

            def find(name):
                matches = [item for item in items() if item.objectName() == name]
                # GridView retains recycled delegates with their previous identity.
                # Interact with the live item, never its off-grid pooled copy.
                item = next((item for item in matches if item.isVisible()
                             and item.property("pooled") is not True), matches[0] if matches else None)
                assert item is not None, "Missing native item: " + name
                return item

            def click(item):
                if isinstance(item, str):
                    item = find(item)
                assert item.isEnabled() and item.isVisible(), "Disabled or hidden: " + item.objectName()
                point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
                assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), item.objectName()
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                                 QPoint(round(point.x()), round(point.y())))

            def capture(name):
                QTest.mouseMove(window, QPoint(4, 4))
                target = out / (name + ".png")
                assert window.grabWindow().save(str(target))
                results["screenshots"].append(target.name)

            def evaluate(item, expression):
                expr = QQmlExpression(QQmlEngine.contextForObject(item), item, expression)
                value, undefined = expr.evaluate()
                assert not undefined and not expr.hasError(), str(expr.error())
                return value

            def choose(name, index):
                control = find(name)
                click(control)
                QTest.qWait(60)
                QTest.keyClick(window, Qt.Key_Home)
                for _ in range(index):
                    QTest.keyClick(window, Qt.Key_Down)
                QTest.keyClick(window, Qt.Key_Return)
                assert control.property("currentIndex") == index, name

            def apply_rows(values):
                service._apply_result({"kind": "scan", "ok": True, "payload": {"rows": values}})

            def image_status(item):
                expression = QQmlExpression(QQmlEngine.contextForObject(item), item, "Number(status)")
                value, undefined = expression.evaluate()
                assert not undefined and not expression.hasError()
                return int(value)

            def steps():
                try:
                    with ExitStack() as stack:
                        start = stack.enter_context(patch.object(service._tasks, "start", return_value=True))
                        if options.theme == "Original Xbox":
                            click("XboxDashboardRoute:liveries")
                        elif options.theme == "Original PS2":
                            click("Ps2HomeBrowser")
                            yield 150
                            click("Ps2DashboardRoute:liveries")
                        elif options.theme == "NieR Automata":
                            click("NierCategory:1")
                            yield 150
                            click("NierDashboardRoute:liveries")
                        else:
                            controller.navigate("liveries")
                        yield 500
                        page = find("LiveryPage")
                        if not page.property("wide"):
                            window.resize(1920, 1080)
                            yield 200
                        assert page.property("wide"), "Desktop test requires the wide details layout"
                        assert not any(item.objectName() == "liveryWipPreviewOverlay" and item.isVisible()
                                       for item in items()), "Blocking first-use overlay remains"
                        apply_rows(rows)
                        yield 800
                        grid = find("liveryThumbnailGrid")
                        assert grid.property("count") == len(rows)
                        image = find("liveryThumbnailImage:" + rows[0]["path"])
                        assert image_status(image) == 1, "Original WebP did not reach Image.Ready"
                        assert image.property("source").hasQuery(), "Thumbnail revision missing"
                        start.assert_not_called()
                        results["cases"].append("Real QML grid loads revisioned, escaped local WebP URLs without a worker")

                        click("liveryThumbnailTile:" + rows[0]["path"])
                        yield 100
                        assert service.selectedSource == rows[0]["path"]
                        assert not find("openSelectedLiveryStudioButton").isVisible()
                        start.assert_not_called()
                        QTest.keyClick(window, Qt.Key_Right)
                        yield 100
                        assert service.selectedSource == rows[1]["path"], "Keyboard and detail selection diverged"
                        QTest.keyClick(window, Qt.Key_End)
                        yield 100
                        assert service.selectedSource == rows[-1]["path"], "End did not select final livery"
                        QTest.keyClick(window, Qt.Key_Home)
                        yield 100
                        assert service.selectedSource == rows[0]["path"], "Home did not select first livery"
                        start.assert_not_called()
                        results["cases"].append("Arrow/Home/End navigation synchronizes selection without rendering")
                        assert not find("openSelectedLiveryPreviewButton").isEnabled()
                        service._game_folder = str(isolated / "fixture-game")
                        service.changed.emit()
                        yield 100
                        capture(f"grid-desktop-{window.width()}x{window.height()}")
                        click("openSelectedLiveryPreviewButton")
                        yield 150
                        assert not page.property("showGallery")
                        assert start.call_count == 1 and start.call_args.args[0] == "preview-source"
                        assert start.call_args.args[1]["source"] == rows[0]["path"]
                        click("returnToLiveryGridButton")
                        yield 100
                        assert page.property("showGallery") and not service.viewerUrl
                        assert service.selectedSource == rows[0]["path"]
                        results["cases"].append("Tile selects only; linked-folder Open 3D Preview routes to existing worker; Back retains selection")

                        tile = find("liveryThumbnailTile:" + rows[0]["path"])
                        point = tile.mapToScene(QPointF(tile.width() / 2, tile.height() / 2))
                        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier,
                                          QPoint(round(point.x()), round(point.y())))
                        yield 150
                        assert not page.property("showGallery") and start.call_count == 2
                        assert service._source_preview_serial == start.call_args.kwargs["metadata"]["request_serial"]
                        click("returnToLiveryGridButton")
                        yield 100
                        find("liveryThumbnailTile:" + rows[0]["path"]).forceActiveFocus()
                        QTest.keyClick(window, Qt.Key_Return)
                        yield 150
                        assert not page.property("showGallery") and start.call_count == 3
                        failed_source = dict(start.call_args.kwargs["metadata"])
                        service._apply_result({"kind": "preview", "ok": False,
                                               "error": "Fixture source preparation failed.", **failed_source})
                        yield 100
                        assert "source preparation failed" in find("liveryPreviewSummary").property("text")
                        assert not service.selectedPackageInstallable
                        source_retry_count = start.call_count
                        click("retryLiveryPreviewButton")
                        yield 150
                        assert start.call_count == source_retry_count + 1
                        assert start.call_args.args[0] == "preview-source"
                        assert start.call_args.args[1]["source"] == rows[0]["path"]
                        click("returnToLiveryGridButton")
                        yield 100
                        results["cases"].append("Double-click and keyboard Return open the selected livery exactly once")
                        results["cases"].append("Failed source preview remains readable and retries only after explicit action")

                        with patch.object(service._tasks, "start", return_value=True) as export_jobs, \
                                patch.object(service, "refreshPackages", side_effect=lambda: refresh_packages(service)):
                            click("PrimaryButton:Export Selected")
                            yield 100
                            assert export_jobs.call_count == 1
                            assert export_jobs.call_args.args[0] == "export-package"
                            package = Path(export_jobs.call_args.args[1]["output"])
                            package.write_bytes(b"simulated export-worker result")
                            service._apply_result({"ok": True, "kind": "export", "payload": {"path": str(package)}})
                            yield 100
                            assert export_jobs.call_count == 2
                            assert export_jobs.call_args.args[0] == "refresh-packages"
                            metadata = export_jobs.call_args.kwargs.get("metadata") or {}
                            assert not metadata.get("open_package")
                            service._apply_result({
                                "ok": True, "kind": "refresh-packages", **metadata,
                                "payload": {"rows": [dict(path=str(package), title="Exported livery", carId=1296,
                                                          modelCode="TEST_CAR", placementCount=50, portableMesh=False)]},
                            })
                            yield 250
                            assert export_jobs.call_count == 2
                            assert page.property("showGallery") and not service.viewerUrl
                            assert service.selectedSource == rows[0]["path"]
                            assert not service.selectedPackage and not service.running
                            assert service.packageModel.row(0)["path"] == str(package)
                            capture("grid-after-export")
                        results["cases"].append("Export Selected refreshes Saved packages without opening 3D or changing the selected source")

                        search = find("liveryGridSearch")
                        search.setProperty("text", "lIvErY 02")
                        service.changed.emit()
                        yield 300
                        assert grid.property("count") == 1
                        assert search.property("text") == "lIvErY 02", "A status update overwrote the pending query"
                        click("liveryThumbnailTile:" + rows[1]["path"])
                        yield 80
                        assert service.selectedSource == rows[1]["path"]
                        search.setProperty("text", ".*")
                        yield 300
                        assert grid.property("count") == 0
                        capture("grid-no-matches")
                        search.setProperty("text", "")
                        yield 300
                        assert grid.property("count") == len(rows)
                        results["cases"].append("Actual search field filters literally without selection/path drift")

                        choose("liveryCarFilter", 2)
                        yield 200
                        assert service.sourceCarId == rows[1]["carId"] and grid.property("count") == 1
                        choose("liveryAvailabilityFilter", 2)
                        yield 150
                        assert service.sourceAvailability == "preview" and grid.property("count") == 0
                        click("resetLiveryFiltersButton")
                        yield 200
                        assert grid.property("count") == len(rows) and search.property("text") == ""
                        choose("liveryAvailabilityFilter", 2)
                        yield 200
                        assert grid.property("count") == 1
                        click("liveryThumbnailTile:" + rows[2]["path"])
                        yield 100
                        assert not find("PrimaryButton:Export Selected").isEnabled()
                        choose("liverySortOrder", 3)
                        yield 150
                        click("resetLiveryFiltersButton")
                        yield 200
                        assert service.sourceSort == "placements" and grid.property("count") == len(rows)
                        choose("liverySortOrder", 0)
                        yield 200
                        results["cases"].append("Native car/availability/sort controls intersect; reset preserves sort; preview-only export remains disabled")

                        tabs = find("liveryLibraryTabs")
                        click(evaluate(tabs, "itemAt(1)"))
                        yield 200
                        assert not grid.isVisible() and find("fullLiveryPackageList").isVisible()
                        assert find("fullLiveryPackageList").property("count") == 1
                        capture("packages-tab")
                        calls_before_browse = start.call_count
                        click("liveryPackageRow:" + str(package))
                        yield 200
                        assert start.call_count == calls_before_browse, "Package selection started expensive verification"
                        assert page.property("showGallery") and service.browsedPackage == str(package)
                        assert not service.selectedPackageInstallable
                        assert service.packageDetails["title"] == "Exported livery"
                        with patch.object(editor, "_start_thread") as studio_launch:
                            button = find("openSelectedLiveryStudioButton")
                            preview_button = find("openSelectedLiveryPreviewButton")
                            assert button.isVisible() and button.isEnabled()
                            assert button.mapToScene(QPointF(0, 0)).y() >= preview_button.mapToScene(QPointF(0, preview_button.height())).y()
                            click(button)
                            yield 100
                            assert studio_launch.call_count == 1
                            assert studio_launch.call_args.kwargs["args"][0] == str(package)
                            assert not button.isEnabled() and page.property("showGallery")
                            assert start.call_count == calls_before_browse
                            editor._finish_studio_launch(False, "Package contains an unsupported decal; nothing was replaced.")
                            yield 100
                            assert find("liveryStudioPackageStatus").isVisible()
                            assert "unsupported decal" in find("liveryStudioPackageStatus").property("text")
                            assert button.isEnabled()
                        results["cases"].append("Package-only Studio action follows Preview, queues one handoff and retains actionable failure status")
                        click("openSelectedLiveryPreviewButton")
                        yield 200
                        assert start.call_args.args[0] == "open-package" and not page.property("showGallery")
                        rejected = dict(start.call_args.kwargs["metadata"])
                        service._apply_result({"kind": "open-package", "ok": False,
                                               "error": "Package integrity check failed in the test fixture.", **rejected})
                        yield 100
                        assert "integrity check failed" in find("liveryPreviewSummary").property("text")
                        assert not find("installExactCarFullLiveryButton").isEnabled()
                        retry_count = start.call_count
                        click("retryLiveryPreviewButton")
                        yield 150
                        assert start.call_count == retry_count + 1 and start.call_args.args[0] == "open-package"
                        click("returnToLiveryGridButton")
                        yield 150
                        assert page.property("libraryTab") == 1
                        assert service.browsedPackage == str(package)
                        package_rows = [dict(path=str(package), title="Exported livery", carId=1296,
                                             modelCode="TEST_CAR", placementCount=50, portableMesh=False,
                                             created="2026-10-29")]
                        for number, car_id in ((2, 1297), (3, 1296)):
                            extra = isolated / f"Package #{number}.kfpslivery"
                            extra.write_bytes(b"synthetic package, verified only by mocked worker")
                            package_rows.append(dict(path=str(extra), title=f"0{number} Package <literal>",
                                                     carId=car_id, modelCode="TEST_CAR", placementCount=number * 10,
                                                     portableMesh=False, created="2026-10-29"))
                        service._apply_result({"kind": "refresh-packages", "ok": True, "payload": {"rows": package_rows}})
                        yield 150
                        package_list = find("fullLiveryPackageList")
                        package_search = find("liveryPackageSearch")
                        package_search.setProperty("text", "02 Package")
                        service.changed.emit()
                        yield 250
                        assert package_list.property("count") == 1 and package_search.property("text") == "02 Package"
                        before_package_filters = start.call_count
                        choose("liveryPackageCarFilter", 1)
                        yield 150
                        assert package_list.property("count") == 0
                        choose("liveryPackageSortOrder", 2)
                        yield 100
                        click("resetLiveryPackageFiltersButton")
                        yield 200
                        assert package_list.property("count") == 3 and service.packageSort == "placements"
                        assert service.sourceCarId == 0 and service.sourceSearch == "" and service.sourceSort == "modified"
                        assert start.call_count == before_package_filters
                        click("liveryPackageRow:" + str(package))
                        yield 100
                        QTest.keyClick(window, Qt.Key_Down)
                        yield 100
                        assert service.browsedPackage == package_rows[2]["path"]
                        QTest.keyClick(window, Qt.Key_End)
                        yield 100
                        assert service.browsedPackage == package_rows[1]["path"]
                        QTest.keyClick(window, Qt.Key_Home)
                        yield 100
                        assert service.browsedPackage == str(package)
                        assert start.call_count == before_package_filters and not service.selectedPackageInstallable
                        QTest.keyClick(window, Qt.Key_Return)
                        yield 150
                        assert start.call_count == before_package_filters + 1 and start.call_args.args[0] == "open-package"
                        click("returnToLiveryGridButton")
                        yield 150
                        package_search.setProperty("text", "02 Package")
                        yield 250
                        click(evaluate(tabs, "itemAt(0)"))
                        yield 100
                        assert search.property("text") == "" and grid.property("count") == len(rows)
                        click(evaluate(tabs, "itemAt(1)"))
                        yield 100
                        assert package_search.property("text") == "02 Package" and package_list.property("count") == 1
                        click("resetLiveryPackageFiltersButton")
                        yield 150
                        tile = find("liveryPackageRow:" + package_rows[1]["path"])
                        point = tile.mapToScene(QPointF(tile.width() / 2, tile.height() / 2))
                        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier,
                                          QPoint(round(point.x()), round(point.y())))
                        yield 150
                        assert not page.property("showGallery") and start.call_args.args[0] == "open-package"
                        click("returnToLiveryGridButton")
                        yield 150
                        click("liveryPackageRow:" + str(package))
                        yield 100
                        assert service.browsedPackage == str(package)
                        assert not service.selectedPackageInstallable
                        results["cases"].append("Independent package filters, keyboard/double-click preview and verification-failure retry preserve safety")
                        capture("packages-selected-details")
                        for width, height in ((960, 600), (1920, 1080)):
                            window.resize(width, height)
                            yield 250
                            if width == 960:
                                click("liverySelectionDetailsButton")
                                yield 100
                                assert "Package details" in [item.property("text") for item in items()]
                                with patch.object(editor, "_start_thread") as studio_launch:
                                    click("openSelectedLiveryStudioButton")
                                    yield 100
                                    assert studio_launch.call_count == 1
                                    assert studio_launch.call_args.kwargs["args"][0] == str(package)
                                    assert not any(item.objectName() == "openSelectedLiveryStudioButton"
                                                   and item.isVisible() for item in items())
                                    editor._finish_studio_launch(False, "Compact package validation failed; nothing was replaced.")
                                    yield 100
                                    assert find("liveryLibraryStatus").isVisible()
                                    assert "Compact package validation failed" in find("liveryLibraryStatus").property("text")
                                click("liverySelectionDetailsButton")
                                yield 100
                                capture("compact-package-details")
                                QTest.keyClick(window, Qt.Key_Escape)
                                yield 100
                                click("compactLiveryPreviewButton")
                                yield 150
                                assert not page.property("showGallery")
                                click("returnToLiveryGridButton")
                                yield 150
                        # Exercise reuse without opening any of the synthetic paths.
                        many_packages = [dict(package_rows[0], path=f"package-{i}.kfpslivery", title=f"Package {i}")
                                         for i in range(5000)]
                        service._apply_result({"kind": "refresh-packages", "ok": True, "payload": {"rows": many_packages}})
                        yield 200
                        for fraction in (0, 0.5, 1, 0):
                            package_list.setProperty("contentY", fraction * (float(package_list.property("contentHeight")) - package_list.height()))
                            yield 100
                        package_delegates = len([item for item in items() if item.objectName().startswith("liveryPackageRow:")])
                        assert 0 < package_delegates < 100, package_delegates
                        assert not service.browsedPackage and not service.packageDetails
                        results["package_delegates"] = package_delegates
                        service._apply_result({"kind": "refresh-packages", "ok": True, "payload": {"rows": package_rows}})
                        yield 100
                        evaluate(package_list, "(positionViewAtBeginning(), true)")
                        yield 100
                        # Retained source selection must not become a missing package's retry target.
                        click(evaluate(tabs, "itemAt(0)"))
                        yield 100
                        click("liveryThumbnailTile:" + rows[1]["path"])
                        yield 100
                        click(evaluate(tabs, "itemAt(1)"))
                        yield 100
                        click("liveryPackageRow:" + package_rows[1]["path"])
                        yield 100
                        Path(package_rows[1]["path"]).unlink()
                        unavailable_calls = start.call_count
                        click("openSelectedLiveryPreviewButton")
                        yield 100
                        assert page.property("showGallery"), "Missing package entered an unrelated source's retry screen"
                        assert start.call_count == unavailable_calls
                        assert service.selectedSource == rows[1]["path"]
                        click("liveryPackageRow:" + package_rows[1]["path"])
                        yield 100
                        assert not service.browsedPackage and not service.selectedPackageInstallable
                        assert not find("openSelectedLiveryPreviewButton").isEnabled()
                        click("liveryPackageRow:" + str(package))
                        yield 100
                        click("liveryMoreButton")
                        yield 100
                        click("clearFullLiveryCacheButton")
                        yield 100
                        assert start.call_args.args[0] == "clear-cache"
                        cache_metadata = dict(start.call_args.kwargs["metadata"])
                        assert not cache_metadata["reopen_source"] and not cache_metadata["reopen_package"]
                        clearing_calls = start.call_count
                        service._apply_result({"kind": "clear-cache", "ok": True, **cache_metadata,
                                               "payload": {"files": 0, "bytes": 0}})
                        yield 100
                        assert start.call_count == clearing_calls and page.property("showGallery")
                        assert service.browsedPackage == str(package) and service.selectedSource == rows[1]["path"]
                        results["cases"].append("Missing-before-open and gallery cache cleanup never reopen a retained source selection")
                        results["cases"].append("Compact package actions and 5000-row reuse work; removed/missing packages clear unsafe selection")
                        click(evaluate(tabs, "itemAt(0)"))
                        yield 150
                        evaluate(grid, "(positionViewAtBeginning(), true)")
                        yield 100
                        click("liveryThumbnailTile:" + rows[1]["path"])
                        yield 100
                        assert service.selectedSource == rows[1]["path"], "Reused tile swallowed selection after double-click/Back"
                        results["cases"].append("Package selection only reads cached details; explicit preview verifies; Back retains its library tab")

                        click("liveryMoreButton")
                        yield 150
                        assert find("clearFullLiveryCacheButton").isVisible()
                        capture("library-more-menu")
                        QTest.keyClick(window, Qt.Key_Escape)
                        yield 100
                        assert not any(item.objectName() == "clearFullLiveryCacheButton" and item.isVisible()
                                       for item in items())
                        click("liveryMoreButton")
                        yield 100
                        click("liveryGridSearch")
                        yield 150
                        assert not any(item.objectName() == "clearFullLiveryCacheButton" and item.isVisible()
                                       for item in items()), "More menu survived an outside click"
                        results["cases"].append("Themed maintenance menu opens and dismisses without triggering cleanup")

                        grid.setProperty("contentY", float(grid.property("contentHeight")) - grid.height())
                        yield 500
                        missing = find("liveryThumbnailImage:" + rows[12]["path"])
                        broken = find("liveryThumbnailImage:" + rows[13]["path"])
                        assert image_status(missing) == 0 and image_status(broken) == 3
                        capture("grid-missing-broken-thumbnails")
                        results["cases"].append("Missing and corrupt thumbnails remain browsable with a placeholder")

                        evaluate(grid, "(positionViewAtBeginning(), true)")
                        for width, height in ((1024, 720), (960, 600), (1920, 1080)):
                            window.resize(width, height)
                            yield 350
                            assert grid.width() > 200 and grid.height() > 150
                            origin = grid.mapToScene(QPointF(0, 0))
                            assert origin.x() + grid.width() <= window.width() + 1
                            assert origin.y() + grid.height() <= window.height() + 1
                            capture(f"grid-{width}x{height}")
                            if width == 960:
                                click("liverySelectionDetailsButton")
                                yield 150
                                preview = find("openSelectedLiveryPreviewButton")
                                assert preview.isVisible() and preview.isEnabled()
                                capture("compact-selection-details")
                                click(preview)
                                yield 150
                                assert not page.property("showGallery")
                                click("returnToLiveryGridButton")
                                yield 150
                                assert page.property("showGallery")
                                click("compactLiveryPreviewButton")
                                yield 150
                                assert not page.property("showGallery")
                                click("returnToLiveryGridButton")
                                yield 150
                        results["cases"].append("Grid remains inside the native window at compact and wide sizes")

                        thumbnail_file = Path(rows[0]["path"]).parent / "bigThumb.webp"
                        original_bytes = thumbnail_file.read_bytes()
                        replacement = QImage(670, 376, QImage.Format_RGB32)
                        replacement.fill(QColor("#25a673"))
                        assert replacement.save(str(thumbnail_file))
                        apply_rows(rows)
                        yield 500
                        refreshed = find("liveryThumbnailImage:" + rows[0]["path"])
                        assert image_status(refreshed) == 1
                        center = refreshed.mapToScene(QPointF(refreshed.width() / 2, refreshed.height() / 2))
                        pixels = window.grabWindow()
                        pixel = pixels.pixelColor(round(center.x() * pixels.width() / window.width()),
                                                  round(center.y() * pixels.height() / window.height()))
                        assert abs(pixel.green() - 166) < 8 and abs(pixel.red() - 37) < 8, pixel.name()
                        thumbnail_file.write_bytes(original_bytes)
                        apply_rows(rows)
                        yield 300
                        results["cases"].append("Replacing a thumbnail refreshes actual displayed pixels while C_livery is unchanged")

                        # Simulated worker responses exercise the real service/QML
                        # acceptance path without loading game assets or a GPU view.
                        service.previewSelectedSource()
                        manifest = {"package_id": "evidence-fixture", "vehicle": {"model_code": "TEST_CAR"},
                                    "livery": {"title": "Preview evidence fixture", "target_car_id": 1297,
                                               "logical_placement_count": 51, "decoded_layer_count": 49,
                                               "section_counts": {"Left": 25, "Right": 26, "Top": 0}},
                                    "sharing": {"preview_only": True, "exportable": False}}
                        with patch.object(service, "_prepare_local_mesh"):
                            service._apply_result({"kind": "preview", "ok": True,
                                                   "source_path": service.selectedSource,
                                                   "request_serial": service._source_preview_serial,
                                                   "payload": {"path": str(package), "manifest": manifest}})
                        evidence = {"quality_scale": 2, "paint_size": [8192, 4096], "mask_size": [2048, 1024],
                                    "mesh_cache_hit": True, "limitation_count": None,
                                    "geometry": [{"label": "Livery primitives missing UV3", "value": "2", "tone": "warning"}],
                                    "materials": [{"label": "Meshes with staged native textures", "value": "14", "tone": "neutral"}],
                                    "warnings": [f"Evidence warning {i}: source material coverage still needs visual comparison."
                                                 for i in range(16)],
                                    "sections": [{"name": "Right", "slot_index": 1}]}
                        with patch.object(service._inspector, "start"):
                            service._apply_mesh_result({"ok": True, "request_serial": service._mesh_serial,
                                                       "package_path": service.selectedPackage,
                                                       "payload": {"package_path": service.selectedPackage,
                                                                   "package_id": manifest["package_id"],
                                                                   "preview_evidence": evidence}})
                        page.setProperty("showGallery", False)
                        service._running = False
                        service.changed.emit()
                        yield 200
                        texts = [item.property("text") for item in items()]
                        for expected in ("8192 x 4096", "Livery primitives missing UV3", "Reused", "Unknown"):
                            assert expected in texts, expected
                        assert not find("installExactCarFullLiveryButton").isEnabled()
                        capture("preview-evidence-details")
                        details_content = find("liveryDetailsContent")
                        details_bar = find("liveryDetailsScrollBar")
                        assert details_content.mapToScene(QPointF(details_content.width(), 0)).x() \
                            <= details_bar.mapToScene(QPointF()).x(), "Details text overlaps the theme scrollbar"
                        details_scroll = find("liveryDetailsScroll")
                        assert details_scroll.property("contentHeight") > details_scroll.height()
                        details_scroll.forceActiveFocus()
                        QTest.keyClick(window, Qt.Key_End)
                        yield 100
                        assert details_scroll.property("contentY") > 0
                        compatibility = find("liveryCompatibilityToggle")
                        compatibility.forceActiveFocus()
                        yield 100
                        position = compatibility.mapToScene(QPointF(0, compatibility.height()))
                        assert position.y() <= window.height()
                        QTest.keyClick(window, Qt.Key_Space)
                        yield 100
                        assert find("liveryPreviewDetails").property("compatibilityExpanded")
                        capture("preview-evidence-keyboard")
                        details_scroll.forceActiveFocus()
                        QTest.keyClick(window, Qt.Key_Home)
                        yield 100
                        assert details_scroll.property("contentY") == 0
                        click("returnToLiveryGridButton")
                        yield 100
                        assert service.previewEvidence == {} and service.sectionDetails == []
                        results["cases"].append("Accepted preparation evidence reaches the details UI; unknowns and install restrictions remain honest; Back clears it")

                        # Repeated model URLs isolate delegate lifetime from save-parser performance.
                        large = [dict(service.sourceModel.row(i % len(rows)), path=f"fixture-{i}", title=f"Stress {i}")
                                 for i in range(5000)]
                        service._sources.replace(large)
                        yield 500
                        count_before = len([item for item in items()
                                            if item.objectName().startswith("liveryThumbnailTile:")])
                        for fraction in (0.1, 0.5, 0.9, 1, 0):
                            grid.setProperty("contentY", fraction * (float(grid.property("contentHeight")) - grid.height()))
                            yield 150
                        count_after = len([item for item in items()
                                           if item.objectName().startswith("liveryThumbnailTile:")])
                        assert 0 < count_before < 80 and 0 < count_after < 80, (count_before, count_after)
                        results["delegate_counts"] = dict(rows=5000, before=count_before, after=count_after,
                                                          measurement="tiles attached to the visual tree")
                        results["cases"].append("5000 rows stay virtualized after long-distance scrolling")

                        apply_rows(rows)
                        yield 200
                        click("openSelectedLiveryPreviewButton")
                        yield 80
                        controller.navigate("tools")
                        yield 250
                        controller.navigate("liveries")
                        yield 300
                        page = find("LiveryPage")
                        apply_rows(rows)
                        yield 150
                        assert page.property("showGallery")
                        assert not service.viewerUrl and not service._active_source_preview
                        results["cases"].append("Leaving/reopening the page returns to the grid without restarting an old preview")
                        apply_rows([])
                        yield 150
                        assert find("liveryThumbnailGrid").property("count") == 0
                        assert not service.selectedSource
                        capture("grid-empty")
                        results["cases"].append("Empty scan clears vanished selection")
                except Exception:
                    results["errors"].append(traceback.format_exc())
                    capture("failure")
                finally:
                    app.exit(int(bool(results["errors"] or results["qml_errors"])))

            iterator = steps()

            def advance():
                try:
                    delay = next(iterator)
                except StopIteration:
                    return
                QTimer.singleShot(delay, advance)

            QTimer.singleShot(700, advance)

        sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", options.theme,
                    "--screenshot", str(out / "capture-mode.png"), "--skip-startup-index",
                    "--skip-startup-thumbnails", "--width", "1440", "--height", "900"]
        previous = qInstallMessageHandler(messages)
        try:
            with patch.object(AppPaths, "discover", return_value=paths), \
                    patch.object(FullLiveryService, "scanSaves"), \
                    patch.object(FullLiveryService, "refreshPackages"), \
                    patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
                    patch.object(application, "install_development_harness", side_effect=install):
                code = application.main()
        finally:
            qInstallMessageHandler(previous)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return code or int(bool(results["errors"] or results["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
