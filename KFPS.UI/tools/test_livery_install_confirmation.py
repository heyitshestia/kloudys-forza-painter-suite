"""Exercise the real Garage install dialog offscreen, without any save installation."""
import argparse
import copy
import ctypes
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import traceback
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--legacy', action='store_true')
parser.add_argument('--baseline-ref', help='Restore only the historical install dialog in a disposable page copy')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[2]
RUN = args.output.resolve()
RUN.mkdir(parents=True, exist_ok=False)
for name in ('temp', 'roaming', 'local'):
    (RUN / name).mkdir()
os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
    KFPS_QML_GRAPHICS='software', QSG_RENDER_LOOP='basic', QT_SCALE_FACTOR='1',
    KFPS_ACTIVITY_DISABLED='1', KFPS_SKIP_STARTUP_INDEX='1', KFPS_SKIP_STARTUP_THUMBNAILS='1',
    KFPS_FULL_LIVERY_STAGE='candidate', QML_DISABLE_DISK_CACHE='1',
    QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu', PYTHONDONTWRITEBYTECODE='1',
    TEMP=str(RUN/'temp'), TMP=str(RUN/'temp'), APPDATA=str(RUN/'roaming'),
    LOCALAPPDATA=str(RUN/'local'), XDG_CACHE_HOME=str(RUN/'local'))
sys.path[:0] = [str(ROOT), str(ROOT/'KFPS.UI'), str(ROOT/'KFPS.UI/src'),
               str(ROOT/'KFPS.Editor/src'), str(ROOT/'KFPS.UI/tests')]
from PySide6.QtCore import Q_ARG, QMetaObject, QPoint, QPointF, Qt, QTimer, QUrl, Slot, qInstallMessageHandler
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlExpression, qmlContext
from PySide6.QtTest import QTest

messages, calls, checks, services = [], [], [], []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
page_path = ROOT/'KFPS.UI/qml/pages/LiveryPage.qml'
page_bytes = page_path.read_bytes()
page_hash = hashlib.sha256(page_bytes).hexdigest()
spec = importlib.util.spec_from_file_location('livery_install_confirmation_app', ROOT/'KFPS.UI/app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

baseline_info = None
baseline_path = None
if args.baseline_ref:
    historical = subprocess.run(['git', 'show', args.baseline_ref + ':KFPS.UI/qml/pages/LiveryPage.qml'],
        cwd=ROOT, check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    historical_text = historical.decode('utf-8')
    old_dialog = historical_text[historical_text.index('    MessageDialog {\n        id: installConfirm'):]
    current = page_bytes.decode('utf-8').replace('\r\n', '\n')
    marker = '    Dialog {\n        id: installConfirm'
    assert current.count(marker) == 1 and old_dialog.endswith('}\n')
    baseline = current[:current.index(marker)] + old_dialog
    baseline = 'import QtQuick.Dialogs 6.7\n' + baseline
    baseline = baseline.replace('"../components"', '"' + (ROOT/'KFPS.UI/qml/components').as_uri() + '"')
    baseline_path = RUN/'LiveryPage-baseline.qml'
    baseline_path.write_text(baseline, encoding='utf-8')
    baseline_info = {'ref': args.baseline_ref, 'historical_page_sha256': hashlib.sha256(historical).hexdigest(),
                     'copied_page_sha256': hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                     'scope': 'Only old install dialog and its import restored; current Garage loader retained'}

original = module.AppPaths.discover()
sample = RUN/'install'
sample.mkdir()
(sample/'VERSION').write_bytes((ROOT/'VERSION').read_bytes())
paths = replace(original, app_root=sample, runtime_root=sample/'runtime')
paths.runtime_root.mkdir()
paths.settings_file.write_text(json.dumps({'theme':'Night Blossom', 'reducedMotion':True,
    'ambientMotion':False, 'supportUpscalerNoticeAcknowledged':True,
    'communityJoinNoticeAcknowledged':True, 'backgroundRemoverNoticeAcknowledged':True,
    'dcinsideKoreanNotice202609Acknowledged':True}), encoding='utf-8')
module.AppPaths.discover = classmethod(lambda cls: paths)

package = RUN/'fixture.kfpslivery'
destination_root = RUN/'disposable-save-fixture-with-a-long-folder-name-for-confirmation-wrapping'
account = destination_root/'u_123_16D460'
containers = account/'1/ContainersRoot'
(containers/'User_7b').mkdir(parents=True)
(account/'1.json').write_text(json.dumps({'Manifest':{'UserId':'123', 'GameId':'16D460', 'Version':1}}), encoding='utf-8')
import _winapi
_winapi.CreateJunction(str(account/'1'), str(account/'current'))
destination_checks = []


class Liveries(module.FullLiveryService):
    def __init__(self, *values, **options):
        super().__init__(*values, **options)
        self._tasks.start = Mock(side_effect=self.route_test_task)
        self._game_folder = str(RUN/'synthetic-game')
        services.append(self)

    def route_test_task(self, operation, payload, *, kind=None, metadata=None, **options):
        if operation == 'resolve-install-destination':
            from kfps_ui.experimental.full_livery import jobs
            # Use the real read-only resolver, confined to this synthetic account.
            with patch.object(jobs, '_scan_roots', return_value=[destination_root]):
                result = jobs.resolve_install_destination(None, payload, threading.Event())
            destination_checks.append(result)
            QTimer.singleShot(0, lambda: self._route_worker_result(
                {'kind':kind, **metadata, 'ok':True, 'value':result}))
            return True
        assert operation == 'install-package', 'Unexpected worker operation: ' + operation
        assert payload['save_root'] == str(containers.resolve())
        assert payload['expected_destination'] == destination_checks[-1]['expected_destination']
        assert 'Destination: FH6 account 123, current save 1.' in self.summary
        assert 'Destination:' not in metadata['install_notice']['summary']
        assert Path(payload['package']) == package
        calls.append({'package':package.name, 'destination':payload['save_root'],
                      'installable':self.selectedPackageInstallable})
        QTimer.singleShot(0, self.release_test_task)
        return True

    def release_test_task(self):
        self._running = False
        self.changed.emit()

    def _resolve_initial_game_folder(self):
        return ''

    @Slot()
    def activate(self):
        self._active = True
        self.changed.emit()

class Garage(module.GarageService):
    @Slot()
    def enter(self):
        pass


module.FullLiveryService, module.GarageService = Liveries, Garage
runtime = None if args.legacy else SimpleNamespace(baseline={'status':'development'},
    graphics=SimpleNamespace(backend='software'), borrow_guard=lambda:SimpleNamespace(Close=lambda:None))


def install(app, window, controller, community, settings, jsons, app_args):
    # The shared fixture helpers reuse the app instead of creating a QCoreApplication.
    from test_studio_package_handoff import make_package
    from tools.livery.package import validate_full_livery_package
    from kfps_ui.workspace_host import WorkspaceWindow
    make_package(package)
    validate_full_livery_package(package)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    shell = next((w for w in app.topLevelWidgets() if isinstance(w, WorkspaceWindow)), None)

    def items():
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    def find(name):
        return next((item for item in items() if item.objectName() == name), None)

    def click(item, disabled=False):
        assert item is not None and item.isVisible() and (disabled or item.isEnabled())
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), point
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(point.x()), round(point.y())))
        QTest.qWait(100)

    def focus_check():
        if os.name == 'nt':
            foreground_pid = ctypes.c_ulong()
            foreground = ctypes.windll.user32.GetForegroundWindow
            foreground.restype = ctypes.c_void_p
            ctypes.windll.user32.GetWindowThreadProcessId(foreground(), ctypes.byref(foreground_pid))
            assert foreground_pid.value != os.getpid(), 'Offscreen test took desktop focus'

    def capture(name):
        path = RUN/(name+'.png')
        image = window.grabWindow()
        assert not image.isNull() and image.save(str(path))
        reopened = QImage(str(path))
        assert not reopened.isNull() and reopened.size() == image.size()
        colors = {reopened.pixelColor(x, y).rgba() for x in range(0, reopened.width(), 25)
                  for y in range(0, reopened.height(), 25)}
        assert len(colors) > 12, 'Blank offscreen capture'
        return {'image':path.name, 'sampled_colors':len(colors)}

    def inspect():
        error, images = None, []
        try:
            assert bool(shell) == (not args.legacy)
            service = services[0]
            for theme in ('Night Blossom', 'NieR Automata'):
                service._save_root = str(destination_root) if theme == 'Night Blossom' else ''
                settings.theme = theme
                QTest.qWait(250)
                dashboard = next((i for i in items() if i.objectName() == 'NierDashboard' and i.isVisible()), None)
                if dashboard:
                    assert QMetaObject.invokeMethod(dashboard, 'choose', Q_ARG('QVariant', 'liveries'))
                controller.navigate('liveries')
                QTest.qWait(250)
                if baseline_path:
                    loader = find('CachedPageHost').property('currentLoader')
                    if hasattr(loader, 'toQObject'):
                        loader = loader.toQObject()
                    assert loader is not None
                    loader.setProperty('asynchronous', False)
                    loader.setProperty('source', QUrl.fromLocalFile(str(baseline_path)))
                    QTest.qWait(200)
                page = find('LiveryPage')
                assert page is not None, 'Real Livery page did not load'
                with patch.object(service, '_prepare_local_mesh'):
                    service._accept_open_package(str(package), copy.deepcopy(manifest), remember=False)
                page.setProperty('libraryTab', 1)
                page.setProperty('showGallery', False)
                QTest.qWait(200)
                button = find('installExactCarFullLiveryButton')
                assert service.selectedPackageInstallable and not service.running
                for action in ('cancel', 'escape', 'outside', 'keyboard_cancel', 'keyboard_accept', 'accept'):
                    before = len(calls)
                    click(button)
                    body = find('LiveryInstallConfirmationText')
                    assert body is not None and body.isVisible() and body.window() == window, (
                        'Install confirmation is not visible inside the KFPS window', messages)
                    top = body.mapToScene(QPointF(0, 0))
                    assert top.x() >= 0 and top.y() >= 0
                    assert top.x()+body.width() <= window.width()+1
                    assert top.y()+body.height() <= window.height()+1
                    assert body.property('truncated') is not True
                    assert str(containers.resolve()) in body.property('text')
                    assert 'My Cars does not select this destination' in body.property('text')
                    assert ('Automatically selected' if not service._save_root else 'selected FH6 Save Folder') in body.property('text')
                    assert QQmlExpression(qmlContext(body), body, 'textFormat === Text.PlainText').evaluate()[0]
                    assert len(calls) == before, 'Opening confirmation invoked installation'
                    assert not any('must be a top level window' in message for message in messages)
                    if action == 'cancel':
                        click(find('CancelLiveryInstall'))
                    elif action == 'escape':
                        QTest.keyClick(window, Qt.Key.Key_Escape)
                    elif action == 'outside':
                        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 10))
                        QTest.qWait(50)
                        assert body.isVisible() and len(calls) == before
                        click(find('CancelLiveryInstall'))
                    elif action == 'keyboard_cancel':
                        assert find('CancelLiveryInstall').hasActiveFocus()
                        QTest.keyClick(window, Qt.Key.Key_Space)
                    elif action == 'keyboard_accept':
                        QTest.keyClick(window, Qt.Key.Key_Tab)
                        assert find('ConfirmLiveryInstall').hasActiveFocus()
                        QTest.keyClick(window, Qt.Key.Key_Space)
                    else:
                        images.append(capture(theme.replace(' ', '-')))
                        click(find('ConfirmLiveryInstall'))
                    QTest.qWait(100)
                    assert not body.isVisible()
                    assert len(calls) == before + (action in ('accept', 'keyboard_accept'))
                    if action in ('cancel', 'escape', 'outside', 'keyboard_cancel'):
                        assert service.status == 'Installation cancelled', (action, service.status)
                        assert service.summary == 'No installation was started.', (action, service.summary)
                        assert not service.installConfirmationCurrent
                    focus_check()
                    checks.append({'theme':theme, 'action':action, 'calls':len(calls),
                                   'status':service.status, 'summary':service.summary})
                for state in ('running', 'noninstallable'):
                    before = len(calls)
                    def set_guard(enabled):
                        service._running = enabled if state == 'running' else False
                        service._current_manifest = {} if enabled and state == 'noninstallable' else copy.deepcopy(manifest)
                        service.changed.emit()
                        QTest.qWait(80)
                    set_guard(True)
                    assert not button.isEnabled()
                    click(button, disabled=True)
                    closed_body = find('LiveryInstallConfirmationText')
                    assert closed_body is None or not closed_body.isVisible()
                    set_guard(False)
                    click(button)
                    set_guard(True)
                    confirm = find('ConfirmLiveryInstall')
                    assert not confirm.isEnabled()
                    click(confirm, disabled=True)
                    confirm.forceActiveFocus()
                    QTest.keyClick(window, Qt.Key.Key_Space)
                    QTest.qWait(80)
                    assert len(calls) == before
                    assert find('LiveryInstallConfirmationText').isVisible()
                    click(find('CancelLiveryInstall'))
                    set_guard(False)
                    focus_check()
                    checks.append({'theme':theme, 'action':'guard_'+state, 'calls':len(calls)})
            assert len(destination_checks) == 16 and service._tasks.start.call_count == 20
            qml_errors = [m for m in messages if any(s in m for s in
                ('ReferenceError', 'TypeError', 'SyntaxError', 'Unable to assign', 'Cannot assign', 'Binding loop'))]
            assert not qml_errors, qml_errors
            assert hashlib.sha256(page_path.read_bytes()).hexdigest() == page_hash
            assert hashlib.sha256(package.read_bytes()).hexdigest() == package_hash
        except Exception:
            error = traceback.format_exc()
            try:
                images.append(capture('failure'))
            except Exception:
                pass
        report = {'passed':error is None, 'error':error, 'checks':checks, 'calls':calls,
                  'messages':messages, 'legacy':args.legacy, 'offscreen':True,
                  'dimensions':[window.width(), window.height()], 'images':images,
                  'baseline':baseline_info, 'page_sha256':page_hash, 'package_sha256':package_hash,
                  'worker_calls':services[0]._tasks.start.call_count,
                  'destination_checks':len(destination_checks), 'install_worker_processes':0,
                  'scope':'Real page, service confirmation and read-only resolver on a disposable account; worker dispatch stubbed; no live save access or installation'}
        (RUN/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        assert json.loads((RUN/'results.json').read_text(encoding='utf-8')) == report
        print(json.dumps(report), flush=True)
        if shell:
            shell.close()
        else:
            window.close()
        app.exit(1 if error else 0)

    controller.navigate('liveries')
    QTimer.singleShot(1800, inspect)


module.install_development_harness = install
sys.argv = [str(ROOT/'KFPS.UI/app.py'), '--demo', '--theme-preview', 'Night Blossom',
            '--skip-startup-index', '--community-preview-background', '--page', 'liveries',
            '--width', '1680', '--height', '1000']
watchdog = threading.Timer(60, lambda: os._exit(124))
watchdog.daemon = True
watchdog.start()
raise SystemExit(module.main(workspace_runtime=runtime))
