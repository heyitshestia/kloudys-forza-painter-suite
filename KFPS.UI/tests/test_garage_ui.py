"""Real native Garage tab, isolated and offscreen, without graphics or network work."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = textwrap.dedent(r'''
import importlib.util
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import Mock, patch

profile = Path(sys.argv[1]).resolve()
theme, width, height = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
        raise AssertionError("External activity is forbidden")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing and not Path(args[0]).resolve().is_relative_to(profile):
            raise AssertionError("Write outside isolated test")
sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location("garage_test_app", Path.cwd() / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from PySide6.QtCore import QPointF, QTimer, QUrl
from PySide6.QtQml import QQmlExpression, qmlContext, QQmlNetworkAccessManagerFactory
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QFileDialog
sys.path.insert(0, str(Path.cwd() / 'tools/livery-studio/src'))
paths = replace(module.AppPaths.discover(), app_root=profile / "app", runtime_root=profile / "runtime")
paths.runtime_root.mkdir()
paths.settings_file.write_text(json.dumps({"theme": theme, "reducedMotion": True, "ambientMotion": False,
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True}))
source = profile / "saves" / "Profile" / "garage.json"
source.parent.mkdir(parents=True)
fixture = [{"Id": n, "CarId": 123 if n < 3 else 456, "CarBody": 2, "RearWing": n + 3,
    "FrontBumper": 4, "RearBumper": 5, "Hood": 6, "SideSkirts": 7, "ChassisStiffness": 8,
    "LiveryFileName": "Livery_0123_test", "TuneFileName": ""} for n in range(1, 81)]
def save_fixture():
    source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "a" * 64, "cars": fixture}))
save_fixture()
second_source = profile / "second-account" / "garage.json"
second_source.parent.mkdir()
second_source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "b" * 64,
                                   "cars": [fixture[0]]}))
accounts = [{"id": "a" * 64, "label": "FH6 account Alpha", "available": True,
             "directory": str(source.parent), "source": str(source)},
            {"id": "b" * 64, "label": "FH6 account Beta", "available": True,
             "directory": str(second_source.parent), "source": str(second_source)}]
discovery = Mock(side_effect=OSError("isolated discovery failure"))
resolve_account = Mock(side_effect=lambda directory: source if directory == str(source.parent) else second_source)
linked_project = profile / 'linked-project.json'
linked_project.write_text(json.dumps({'format': 'kfps-livery-layout-v1',
    'vehicle': {'car_id': 123, 'model_code': 'QA_CAR'}, 'vinyls': [], 'placements': []}))
supporter = module.SupporterService
module.SupporterService = lambda root: supporter(root, endpoint="")
execute = module.exec_qml_application
errors, checked, qml_errors = [], [], []
resource_requests = []
class Network(QNetworkAccessManager):
    def createRequest(self, operation, request, outgoing=None):
        if request.url().scheme() in ('http', 'https'):
            resource_requests.append(request.url().toString())
            request = QNetworkRequest(QUrl('data:,'))
        return super().createRequest(operation, request, outgoing)
class NetworkFactory(QQmlNetworkAccessManagerFactory):
    def create(self, parent): return Network(parent)
network_factory = NetworkFactory()
engine_type = module.QQmlApplicationEngine
def make_engine():
    engine = engine_type()
    engine.setNetworkAccessManagerFactory(network_factory)
    engine.warnings.connect(lambda messages: qml_errors.extend(message.toString() for message in messages))
    return engine
module.QQmlApplicationEngine = make_engine
def run(app, engine, shutdown):
    assert app.platformName() == "offscreen"
    window = engine.rootObjects()[0]
    context = engine.rootContext()
    context.setContextProperty("screenshotMode", True)
    garage = context.contextProperty("garageService")
    liveries = context.contextProperty("fullLiveryService")
    editor = context.contextProperty("editorService")
    from kfps_livery_lab import host_bridge
    editor._garage_studio_bridge = lambda: host_bridge
    controller = context.contextProperty("appController")
    timer = QTimer()
    stage = [-8]
    held = {}
    def find(name):
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            held[id(item)] = item
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError("Missing " + name)
    def js(item, expression):
        command = QQmlExpression(qmlContext(item), item, expression)
        value = command.evaluate()[0]
        assert not command.hasError(), command.error().toString()
        return value
    def check():
        try:
            assert not qml_errors, qml_errors
            if js(find("CachedPageHost"), "currentLoader.status") != 1:
                return
            if stage[0] == -8:
                assert garage._thread is None and garage.total == 0
                assert not discovery.called, "Garage discovery ran at app startup"
                if theme == 'NieR Automata':
                    js(find('NierDashboard'), "choose('liveries')")
                else:
                    controller.navigate("liveries")
                stage[0] += 1
                return
            page = find("LiveryPage")
            if stage[0] == -7:
                if garage.busy: return
                assert page.property("libraryTab") == 2
                assert not garage.selectedAccountId and not garage.hasSource
                assert garage.accountsDiscovered and "could not be checked" in garage.accountStatus
                assert js(find("garageAccountPicker"), "currentIndex") == 0
                assert js(find("garageAccountPicker"), "displayText") == "Choose an account"
                assert js(find("garageRescanAccounts"), "enabled")
                assert js(find("garageChooseSource"), "enabled")
                assert js(find("garageRefreshButton"), "enabled")
                assert js(find("garageEmptyTitle"), "text") == "Choose an FH6 account"
                assert js(find("garageEmptyStatus"), "text") == "No account selected"
                assert window.grabWindow().save(str(profile / "discovery-failure.png"))
                js(find("garageSavedLiveriesTab"), "clicked()")
                assert page.property("libraryTab") == 0
                js(find("garagePackagesTab"), "clicked()")
                assert page.property("libraryTab") == 1
                assert js(find("addFullLiveryPackageButton"), "visible")
                js(find("garageMyCarsTab"), "clicked()")
                assert page.property("libraryTab") == 2
                js(find("liveryLibraryTabs"), "setCurrentIndex(0)")
                assert page.property("libraryTab") == 0
                js(find("liveryLibraryTabs"), "setCurrentIndex(2)")
                assert page.property("libraryTab") == 2
                assert discovery.call_count == 1
                discovery.side_effect = None
                discovery.return_value = []
                js(find("garageRescanAccounts"), "clicked()")
            elif stage[0] == -6:
                if garage.busy: return
                assert not garage.accountOptions and not garage.selectedAccountId
                assert js(find("garageEmptyStatus"), "text") == "No account selected"
                assert "No FH6 accounts found" in js(find("garageAccountStatus"), "text")
                discovery.return_value = accounts
                js(find("garageRescanAccounts"), "clicked()")
            elif stage[0] == -5:
                if garage.busy: return
                assert len(garage.accountOptions) == 2 and not garage.selectedAccountId
                assert js(find("garageAccountPicker"), "currentIndex") == 0
                assert window.grabWindow().save(str(profile / "first-use.png"))
                js(find("garageAccountPicker"), "activated(1)")
                assert garage.busy and not garage.selectedAccountId
                assert not js(find("garageAccountPicker"), "enabled")
                assert not js(find("garageRescanAccounts"), "enabled")
                assert not js(find("garageChooseSource"), "enabled")
                assert js(find("garageAccountPicker"), "currentIndex") == 0
            elif stage[0] == -4:
                if garage.busy: return
                assert garage.selectedAccountId == accounts[0]["id"]
                assert js(find("garageAccountPicker"), "currentIndex") == 1
                assert garage.summary["cars"] == 80 and garage.summary["models"] == 2
                assert js(find("garageSummary"), "visible")
                assert "Snapshot:" in js(find("garageSnapshotDate"), "text")
                assert "UTC" in js(find("garageSnapshotDate"), "text")
                assert js(find("garageRefreshButton"), "enabled")
                js(find("garageAccountPicker"), "activated(2)")
                assert js(find("garageAccountPicker"), "currentIndex") == 1
            elif stage[0] == -3:
                if garage.busy: return
                assert garage.total == 1 and garage.selectedAccountId == accounts[1]["id"]
                assert js(find("garageAccountPicker"), "currentIndex") == 2
                discovery.return_value = accounts[:1]
                js(find("garageRescanAccounts"), "clicked()")
            elif stage[0] == -2:
                if garage.busy: return
                assert garage.selectedAccountId == accounts[1]["id"] and garage.total == 1
                assert "(unavailable)" in js(find("garageAccountPicker"), "displayText")
                assert "snapshot kept" in js(find("garageAccountStatus"), "text")
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
                    js(find("garageChooseSource"), "clicked()")
            elif stage[0] == -1:
                if garage.busy: return
                assert garage.total == 80 and garage.selectedAccountId.startswith("manual:")
                assert "Manually selected" in js(find("garageAccountPicker"), "displayText")
                discovery.return_value = accounts + [{"id": "c" * 64, "label": "Unavailable account",
                    "available": False, "directory": str(profile / "unavailable"), "source": ""}]
                js(find("garageRescanAccounts"), "clicked()")
            elif stage[0] == 0:
                if garage.busy: return
                assert garage.total == 80 and garage.selectedAccountId.startswith("manual:")
                assert js(find("garageAccountPicker"), "currentIndex") > 0
                assert js(find("garageAccountPicker"), "contentItem.textFormat === Text.PlainText")
                manual_id = garage.selectedAccountId
                js(find("garageAccountPicker"), "activated(count - 1)")
                assert garage.selectedAccountId == manual_id and not garage.busy
                assert "unavailable" in garage.accountStatus
                assert "Manually selected" in js(find("garageAccountPicker"), "displayText")
            elif stage[0] == 1:
                if garage.busy: return
                assert garage.total == 80, garage.status
                assert find("garageCars").property("visible")
                garage.select("1")
                js(find("garageSaveComparison"), "clicked()")
                js(find("garageComparisonName"), "text = 'Before wing change'; comparisonName.accept()")
                assert garage.savedComparisonId
                assert len(garage.savedComparisons) == 1
                garage.saveComparison('<img src="https://garage-test.invalid/pixel.png">')
                js(find('garageSavedComparisons'), 'popup.open()')
                assert js(find('garageSavedComparisons'), 'contentItem.textFormat === Text.PlainText')
                js(find("garageCompare"), "clicked()")
                garage.select("2")
                assert garage.differences[0]["field"] == "RearWing"
                garage.setSearch("Car 123")
                assert garage.visibleCount == 2
                garage.setHistoryEnabled(True)
                fixture[0]["RearWing"] = 70
                save_fixture()
                js(find("garageRefreshButton"), "clicked()")
            elif stage[0] == 2:
                if garage.busy: return
                assert not resource_requests, resource_requests
                js(find('garageSavedComparisons'), 'popup.close()')
                assert len(garage.history) == 1
                garage.select("1")
                garage.setSearch("")
                target = profile / "saves" / "Livery_0123_test" / "C_livery"
                target.parent.mkdir(parents=True)
                target.write_bytes(b"fixture")
                row = dict(path=str(target), title="Saved artwork", carId=123, modelCode="QA_CAR", placementCount=1,
                           modified="2026-11-02", detail="", hasHeader=True, exportable=False, privacyDetail="", thumbnailUrl="", searchText="")
                liveries._replace_source_rows([row])
                held['saved_livery_row'] = row
                garage.activate()
                assert garage.details["matched"]
                garage.chooseComparison(next(e['id'] for e in garage.savedComparisons if e['name'] == 'Before wing change'))
                with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(linked_project), '')):
                    js(find('garageLinkProject'), 'clicked()')
            elif stage[0] == 3:
                if garage.busy: return
                assert garage.projectLinked, garage.projectStatus
                js(find('garageCheckProject'), 'clicked()')
            elif stage[0] == 4:
                if garage.busy: return
                assert 'matches' in garage.projectStatus, garage.projectStatus
                assert garage.differences[0]['after'] == '70'
                js(find("garageOpenLivery"), "clicked()")
                assert page.property("libraryTab") == 0
                assert liveries.selectedSource == str(profile / "saves" / "Livery_0123_test" / "C_livery")
                assert not liveries.running
                js(page, "libraryTab = 1")
                js(page, "libraryTab = 2")
            elif stage[0] == 5:
                from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
                liveries._gate = FullLiveryFeatureGate('candidate', 'offscreen test')
                liveries._game_folder = str(profile / 'game')
                liveries._tasks.start = Mock(return_value=True)
                editor._start_thread = Mock()
                assert js(find('garageOpenPreview'), 'enabled')
                assert js(find('garageOpenStudio'), 'enabled')
                js(find('garageOpenPreview'), 'clicked()')
            elif stage[0] == 6:
                if garage.busy: return
                args = liveries._tasks.start.call_args
                assert args.args[0] == 'prepare-garage', (args, garage.status)
                assert args.args[1]['garage_build']['parts']['RearWing'] == 70
                assert args.args[1]['identity'] == {'car_id': 123, 'model_code': 'QA_CAR'}
                assert not liveries.selectedPackage and not liveries._current_manifest
                assert not page.property('showGallery')
                assert 'No artwork' in liveries.selectedCounts
                js(page, 'returnToGallery()')
                garage.select('2')
                js(find('garageOpenStudio'), 'clicked()')
            elif stage[0] == 7:
                if garage.busy: return
                request = editor._start_thread.call_args.kwargs
                assert request['target'] == editor._launch_garage_studio_worker
                identity, snapshot, name, theme_context = request['args']
                assert identity == {'car_id': 123, 'model_code': 'QA_CAR'}
                assert snapshot['parts']['RearWing'] == 5
                assert snapshot['parts']['ChassisStiffness'] == 8
                assert theme_context and name == 'Garage body build'
                assert not editor.studioPackagePath
                assert not js(find('garageOpenStudio'), 'enabled')
                editor._finish_studio_launch(True, 'Garage body build staged')
                garage.select('1')
            elif stage[0] == 8:
                for name in ("garageAccountPicker", "garageRescanAccounts", "garageChooseSource",
                             "garageSummary", "garageSnapshotDate", "garageRefreshButton", "liveryMoreButton"):
                    item = find(name)
                    point = item.mapToScene(QPointF(0, 0))
                    assert point.x() >= -1 and point.x() + item.width() <= window.width() + 1, (
                        name, point.x(), item.width(), window.width())
                    assert point.y() >= 0 and point.y() + item.height() <= window.height(), name
                assert window.grabWindow().save(str(profile / "garage.png"))
                assert garage.selectedId == "1"
                assert garage._thread is None or not garage._thread.is_alive()
                assert not liveries._viewer_memory_timer.isActive()
                discovery.return_value = []
                from kfps_ui.garage_service import GarageService
                restored = GarageService(paths, garage.log, liveries)
                restored.enter()
                held["restored"] = restored
            elif stage[0] == 9:
                restored = held["restored"]
                if restored.busy: return
                assert restored.total == garage.total == 80
                assert restored.selectedAccountId == garage.selectedAccountId
                assert restored.summary == garage.summary
                assert restored.accountOptions[0]["id"] == restored.selectedAccountId
                restored.close()
                visits = discovery.call_count
                js(page, "pageActive = false; libraryTab = 0; libraryTab = 2")
                assert discovery.call_count == visits
                js(page, "pageActive = true")
                assert discovery.call_count == visits
                checked.extend(["on-demand", "scan", "search", "comparison", "history", "exact-livery-handoff", "tab-return", "idle",
                                "named-comparison-dialog", "project-link-picker", "project-integrity-check",
                                "garage-preview-button", "garage-studio-button", "garage-theme-handoff", "duplicate-build-selection",
                                "startup-no-discovery", "discovery-failure-recovery", "empty-discovery", "explicit-account-choice",
                                "busy-controls", "account-switch", "unavailable-account", "manual-file-fallback", "snapshot-timestamp",
                                "account-independent-tabs", "manual-snapshot-restore", "inactive-page-entry-guard", "keyboard-tab-identity"])
                from PySide6.QtGui import QImage, QColor
                thumbnail = profile / "stock-fixture.png"
                pixels = QImage(320, 180, QImage.Format_RGBA8888)
                pixels.fill(QColor("#ea5476"))
                assert pixels.save(str(thumbnail))
                garage._catalogue_cancel.clear()
                garage._apply_catalogue({"game": liveries.gameFolder, "status": "3 catalogue cars",
                    "cars": [{"carId": ident, "modelCode": code, "title": title,
                              "thumbnailUrl": QUrl.fromLocalFile(str(thumbnail)).toString()}
                             for ident, code, title in ((123, "QA_CAR", "Zeta Coupe"),
                                (456, "QA_SECOND", "Beta Saloon"), (789, "QA_STOCK", "Alpha Roadster"))]})
                spare = profile / 'saves/Livery_spare/C_livery'
                spare.parent.mkdir(parents=True)
                spare.write_bytes(b'spare livery not currently applied')
                liveries._replace_source_rows([held['saved_livery_row'], dict(path=str(spare),
                    carId=789, title='Unapplied saved livery', modelCode='QA_STOCK')])
                assert garage.browseTotal == 81 and garage.total == 80
                garage.select("catalogue:789")
            elif stage[0] == 10:
                # Image decoding and scaled layout polish may finish on separate turns.
                # Keep polling within the overall timeout, never accept a settled rectangle.
                if not js(find('garageStockThumbnail'), 'status === Image.Ready'): return
                if not js(find('garageSquareThumbnail'), 'width > 0 && width === height'): return
                if not js(find('garageCars'), 'currentItem && currentItem.width === currentItem.height'): return
                assert js(find('garageOpenPreview'), 'enabled')
                assert js(find('garageOpenStudio'), 'enabled')
                assert not js(find('garageCompare'), 'enabled')
                assert not js(find('garageSaveComparison'), 'enabled')
                assert garage.details['ownership'] == 'Not owned'
                assert js(find('garageStockThumbnail'), 'status === Image.Ready')
                assert js(find('garageSquareThumbnail'), 'width > 0 && width === height'), js(find('garageSquareThumbnail'), 'JSON.stringify({width, height})')
                assert js(find('garageCars'), 'columns >= 2'), js(find('garageCars'), 'columns')
                assert js(find('garageCars'), 'currentItem.width === currentItem.height'), js(find('garageCars'), 'JSON.stringify({width:currentItem.width, height:currentItem.height})')
                js(find('garageCars'), 'navigate({key: Qt.Key_Right, accepted: false}, 0)')
                assert garage.selectedId == garage.cars.rows[1]['instanceId']
                js(find('garageCars'), 'navigate({key: Qt.Key_Home, accepted: false}, currentIndex)')
                assert garage.selectedId == garage.cars.rows[0]['instanceId']
                js(find('garageCars'), 'navigate({key: Qt.Key_Down, accepted: false}, currentIndex)')
                columns = js(find('garageCars'), 'columns')
                assert garage.selectedId == garage.cars.rows[columns]['instanceId']
                js(find('garageCars'), 'navigate({key: Qt.Key_End, accepted: false}, currentIndex)')
                assert garage.selectedId == garage.cars.rows[-1]['instanceId']
                js(find('garageCars'), 'navigate({key: Qt.Key_Home, accepted: false}, currentIndex)')
                assert garage.selectedId == garage.cars.rows[0]['instanceId']
                for name in ('garageFilter', 'garageSort', 'garageSearch'):
                    item = find(name)
                    point = item.mapToScene(QPointF(0, 0))
                    assert point.x() >= -1 and point.x() + item.width() <= window.width() + 1, name
                    assert point.y() >= 0 and point.y() + item.height() <= window.height(), name
                js(find('garageSort'), 'currentIndex = 1; activated(1)')
                assert garage.cars.rows[-1]['instanceId'] == 'catalogue:789'
                js(find('garageSort'), 'currentIndex = 2; activated(2)')
                js(find('garageFilter'), 'currentIndex = 1; activated(1)')
                assert {r['instanceId'] for r in garage.cars.rows} == {'1', '2', 'catalogue:789'}
                js(find('garageFilter'), 'currentIndex = 3; activated(3)')
                assert garage.visibleCount == 80
                from kfps_ui.garage_service import GarageService
                restored = GarageService(paths, garage.log, liveries)
                restored.activate()
                assert restored.sortIndex == 2 and restored.filterIndex == 3
                restored.close()
                js(find('garageFilter'), 'currentIndex = 0; activated(0)')
                js(find('garageSort'), 'currentIndex = 0; activated(0)')
                assert garage.visibleCount == 81
                garage.select('catalogue:789')
            elif stage[0] == 11:
                assert window.grabWindow().save(str(profile / 'catalogue.png'))
                checked.extend(['stock-thumbnail', 'unowned-comparison-disabled', 'catalogue-owned-copy-merge',
                                'owned-sort', 'livery-sort', 'view-preference-restart', 'catalogue-compact-controls',
                                'square-thumbnail-grid', 'grid-keyboard-navigation', 'unapplied-saved-livery-filter'])
                js(find('garageOpenPreview'), 'clicked()')
            elif stage[0] == 12:
                if garage.busy: return
                request = liveries._tasks.start.call_args.args[1]
                assert request['identity'] == {'car_id': 789, 'model_code': 'QA_STOCK'}
                assert request['stock'] is True and 'garage_build' not in request
                js(page, 'returnToGallery()')
                js(find('garageOpenStudio'), 'clicked()')
            elif stage[0] == 13:
                if garage.busy: return
                request = editor._start_thread.call_args.kwargs['args'][0]
                assert request.get('project', {}).get('vehicle') == {'car_id': 789, 'model_code': 'QA_STOCK'}, (request, editor.studioStatus)
                assert not request['project']['vinyls'] and not request['project']['placements']
                assert 'garage_build' not in request['project']
                editor._finish_studio_launch(True, 'Stock car staged')
                garage.select('1')
                liveries._replace_source_rows([{**held['saved_livery_row'], 'exportable': True}])
                assert len(garage.artworkOptions) == 1
                js(find('garageArtworkPicker'), 'currentIndex = 1; activated(1)')
                assert js(find('garageArtworkPicker'), 'contentItem.textFormat === Text.PlainText')
                assert js(find('garageOpenArtwork'), 'enabled')
                js(find('garageOpenArtwork'), 'clicked()')
            elif stage[0] == 14:
                if garage.busy: return
                identity, snapshot, path, kind, theme_context, expected = editor._start_thread.call_args.kwargs['args']
                assert identity == {'car_id': 123, 'model_code': 'QA_CAR'}
                assert snapshot['parts']['RearWing'] == 70
                assert path == held['saved_livery_row']['path'] and kind == 'save'
                assert theme_context
                import hashlib
                assert expected == hashlib.sha256(b'fixture').hexdigest()
                editor._finish_studio_launch(True, 'Artwork staged')
                assert js(find('garageOpenProject'), 'enabled')
                editor._start_thread.reset_mock()
                js(find('garageOpenProject'), 'clicked()')
            elif stage[0] == 15:
                if garage.busy: return
                assert editor._start_thread.called, editor.studioStatus
                assert editor.studioLaunching
                editor._finish_studio_launch(True, 'Linked project staged')
                checked.extend(['stock-preview-button', 'stock-studio-button', 'current-build-artwork-button',
                                'linked-project-open-button'])
                if real_catalogue:
                    held['real_catalogue'] = json.loads(Path(real_catalogue).read_text(encoding='utf-8'))
                    garage._apply_catalogue({**held['real_catalogue'], 'game': liveries.gameFolder})
                    assert len(garage._catalogue) == len(held['real_catalogue']['cars'])
                    assert garage.cars.rows
                    garage.select(garage.cars.rows[0]['instanceId'])
                    named = [row for row in held['real_catalogue']['cars'] if row.get('manufacturer')]
                    if named:
                        garage.setSort('name')
                        makes = {row['carId']: row['manufacturer'].casefold() for row in named}
                        order = [makes[row['carId']] for row in garage.cars.rows if row['carId'] in makes]
                        assert order == sorted(order), order
                        assert js(find('garageSort'), 'currentText') == 'Manufacturer: A to Z'
                    s660 = next((row for row in named if row['modelCode'].lower() == 'hon_s660_16'), None)
                    if s660:
                        garage.setSearch('Honda S660')
                        assert [row['carId'] for row in garage.cars.rows] == [s660['carId']]
                        garage.select(garage.cars.rows[0]['instanceId'])
                else:
                    timer.stop()
                    app.quit()
                    return
            elif stage[0] == 16:
                image_status = js(find('garageStockThumbnail'), 'status')
                if image_status == 2: return  # Async local image decoding is still running.
                assert js(find('garageStockThumbnail'), 'status === Image.Ready'), image_status
                assert window.grabWindow().save(str(profile / 'installed-catalogue.png'))
                assert not garage.catalogueBusy
                checked.append('installed-stock-catalogue')
                timer.stop()
                app.quit()
                return
            stage[0] += 1
        except BaseException:
            errors.append(traceback.format_exc())
            window.grabWindow().save(str(profile / "failure.png"))
            timer.stop()
            app.quit()
    timer.timeout.connect(check)
    timer.start(350)
    def timed_out():
        errors.append(f"Timed out at stage {stage[0]}, route {controller.currentPage}, QML warnings {qml_errors}")
        window.grabWindow().save(str(profile / "failure.png"))
        timer.stop()
        app.quit()
    QTimer.singleShot(25000, timed_out)
    return execute(app, engine, shutdown)
real_catalogue = sys.argv[5] if len(sys.argv) > 5 else ''
module.exec_qml_application = run
sys.argv = ["app.py", "--demo", "--skip-startup-index", "--page", "create", "--width", str(width), "--height", str(height)]
with patch.object(module.AppPaths, "discover", return_value=paths), patch.object(module.FullLiveryService, "_resolve_initial_game_folder", return_value=""), patch.object(module.FullLiveryService, "scanSaves"), patch.object(module.FullLiveryService, "refreshPackages"), patch('kfps_ui.garage_service.resolve_body_vehicle', side_effect=lambda game, index, car_id, **kw: SimpleNamespace(car_id=car_id, model_code=kw.get('model_code') or 'QA_CAR')), patch('kfps_ui.garage_service.discover_accounts', discovery), patch('kfps_ui.garage_service.resolve_account', resolve_account), patch('kfps_ui.garage_service.account_for_source', return_value=None):
    assert module.main() == 0
logging.shutdown()
assert not errors, (errors, qml_errors)
assert len(checked) == (43 if real_catalogue else 42), checked
assert not qml_errors, qml_errors
assert not resource_requests, resource_requests
(profile / "result.json").write_text(json.dumps({"checked": checked, "theme": theme, "size": [width, height]}))
''')


class GarageUITests(unittest.TestCase):
    def test_native_workflow(self):
        cases = [("Night Blossom", 1440, 900, "1"), ("Command Prompt", 1024, 768, "1.25"),
                 ("Night City 2077", 1280, 800, "2"), ("Night Blossom", 960, 600, "1"),
                 ("NieR Automata", 1440, 900, "1")]
        if os.environ.get("KFPS_GARAGE_TEST_THEME"):
            cases = [case for case in cases if case[0] == os.environ["KFPS_GARAGE_TEST_THEME"]]
            self.assertTrue(cases, "Unknown Garage test theme")
        for theme, width, height, scale in cases:
            with self.subTest(theme=theme), tempfile.TemporaryDirectory(prefix="garage-ui-", dir=os.environ.get("KFPS_GARAGE_TEST_TEMP")) as folder:
                root = Path(folder)
                env = {k: v for k, v in os.environ.items() if not k.startswith("KFPS_")}
                env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1",
                           QT_SCALE_FACTOR=scale, KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1",
                           KFPS_STARTUP_MUTED="1", QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-background-networking")
                for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                    location = root / name.lower()
                    location.mkdir()
                    env[name] = str(location)
                result = subprocess.run([sys.executable, "-I", "-B", "-c", SCRIPT, str(root), theme, str(width), str(height),
                                         os.environ.get("KFPS_GARAGE_REAL_CATALOGUE", "")],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=35,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                evidence = os.environ.get("KFPS_GARAGE_EVIDENCE")
                if evidence:
                    label = theme.replace(" ", "-") + (f"-{width}x{height}" if width == 960 else "")
                    target = Path(evidence) / label
                    target.mkdir(parents=True, exist_ok=True)
                    for name in ("garage.png", "catalogue.png", "installed-catalogue.png", "first-use.png", "discovery-failure.png", "failure.png", "result.json"):
                        if (root / name).is_file():
                            shutil.copy2(root / name, target / name)
                        elif (target / name).is_file():
                            (target / name).unlink()
                    (target / "process.log").write_text(result.stdout + result.stderr, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
