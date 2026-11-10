"""Exercise Update confirmation in the real app without updating or taking focus."""
import argparse
import ctypes
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument('--legacy', action='store_true')
parser.add_argument('--windows', action='store_true')
parser.add_argument('--width', type=int, default=1400)
parser.add_argument('--height', type=int, default=950)
parser.add_argument('--scale', type=float, default=1)
args = parser.parse_args()
ROOT, RUN = args.source_root.resolve(), args.output.resolve()
RUN.mkdir(parents=True, exist_ok=False)
os.environ.update(QT_QPA_PLATFORM='windows' if args.windows else 'offscreen',
    QT_SCALE_FACTOR=str(args.scale),
    QT_QUICK_BACKEND='software', KFPS_QML_GRAPHICS='software', QSG_RENDER_LOOP='basic',
    KFPS_ACTIVITY_DISABLED='1', KFPS_SKIP_STARTUP_INDEX='1', KFPS_SKIP_STARTUP_THUMBNAILS='1',
    QML_DISABLE_DISK_CACHE='1', QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu',
    APPDATA=str(RUN/'profile/roaming'), LOCALAPPDATA=str(RUN/'profile/local'))
sys.path[:0] = [str(ROOT), str(ROOT/'KFPS.UI'), str(ROOT/'KFPS.UI/src'), str(ROOT/'KFPS.Editor/src')]
from PySide6.QtCore import Q_ARG, QMetaObject, QPoint, QPointF, Qt, QTimer, Slot, qInstallMessageHandler
from PySide6.QtTest import QTest

messages, calls, checks = [], [], []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location('update_confirmation_app', ROOT/'KFPS.UI/app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module.AppPaths.discover()
sample = RUN/'profile/install/KloudysFH6Painter'
sample.mkdir(parents=True)
(sample/'VERSION').write_bytes((ROOT/'VERSION').read_bytes())
(sample.parent/'KFPS-Updater.exe').write_bytes(b'test-only launch placeholder')
paths = replace(original, app_root=sample, runtime_root=sample/'runtime')
paths.runtime_root.mkdir()
paths.settings_file.write_text(json.dumps({'theme':'Night Blossom', 'reducedMotion':True,
    'ambientMotion':False, 'supportUpscalerNoticeAcknowledged':True,
    'communityJoinNoticeAcknowledged':True, 'backgroundRemoverNoticeAcknowledged':True,
    'dcinsideKoreanNotice202609Acknowledged':True}))
module.AppPaths.discover = classmethod(lambda cls: paths)


class Updates(module.UpdateService):
    @Slot()
    def startUpdate(self):
        # Exercise the real slot, suppressing only external launch and app exit.
        with patch('kfps_ui.update_service.subprocess.Popen') as launch, patch(
                'kfps_ui.update_service.QCoreApplication.quit') as quit_app:
            super().startUpdate()
        assert launch.call_count == 1 and quit_app.call_count == 1
        assert launch.call_args.args[0] == [str(sample.parent/'KFPS-Updater.exe'),
            '--root', str(sample.parent), '--relaunch', '--wait-pid', str(os.getpid())]
        assert launch.call_args.kwargs['cwd'] == sample.parent
        calls.append('update')


module.UpdateService = Updates
runtime = None if args.legacy else SimpleNamespace(baseline={'status':'development'},
    graphics=SimpleNamespace(backend='software'), borrow_guard=lambda:SimpleNamespace(Close=lambda:None))


def install(app, window, controller, community, settings, jsons, app_args):
    from kfps_ui.workspace_host import WorkspaceWindow
    shell = next((w for w in app.topLevelWidgets() if isinstance(w, WorkspaceWindow)), None)

    def items():
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    def find(name):
        return next((i for i in items() if i.objectName() == name), None)

    def click(item):
        assert item is not None and item.isVisible() and item.isEnabled()
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), point
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(point.x()), round(point.y())))
        QTest.qWait(100)

    def inspect():
        error = None
        try:
            for theme in ('Night Blossom', 'NieR Automata'):
                settings.theme = theme
                QTest.qWait(250)
                assert settings.theme == theme
                dashboard = next((i for i in items() if i.objectName() == 'NierDashboard' and i.isVisible()), None)
                if dashboard:
                    assert QMetaObject.invokeMethod(dashboard, 'choose', Q_ARG('QVariant', 'update'))
                controller.navigate('update')
                QTest.qWait(250)
                button = next(i for i in items() if i.objectName().startswith('PrimaryButton:')
                              and ('Updater' in str(i.property('text')) or 'Update to' in str(i.property('text'))))
                for action in ('cancel', 'escape', 'outside', 'keyboard_cancel', 'keyboard_update', 'accept'):
                    before = len(calls)
                    click(button)
                    body = find('UpdateConfirmationText')
                    assert body is not None and body.isVisible() and body.window() == window, (
                        'Update confirmation is not visible inside the KFPS window', messages)
                    top = body.mapToScene(QPointF(0, 0))
                    assert top.x() >= 0 and top.y() >= 0
                    assert top.x()+body.width() <= window.width()+1
                    assert top.y()+body.height() <= window.height()+1
                    assert body.property('truncated') is not True
                    assert not any('must be a top level window' in m for m in messages), messages
                    assert len(calls) == before, 'Opening confirmation launched the updater'
                    if action == 'cancel':
                        click(find('CancelUpdate'))
                    elif action == 'escape':
                        QTest.keyClick(window, Qt.Key.Key_Escape)
                    elif action == 'outside':
                        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 10))
                        QTest.qWait(50)
                        assert body.isVisible() and len(calls) == before
                        click(find('CancelUpdate'))
                    elif action == 'keyboard_cancel':
                        assert find('CancelUpdate').hasActiveFocus()
                        QTest.keyClick(window, Qt.Key.Key_Space)
                    elif action == 'keyboard_update':
                        QTest.keyClick(window, Qt.Key.Key_Tab)
                        assert find('ConfirmUpdate').hasActiveFocus()
                        QTest.keyClick(window, Qt.Key.Key_Space)
                    else:
                        assert window.grabWindow().save(str(RUN/(theme.replace(' ', '-')+'.png')))
                        click(find('ConfirmUpdate'))
                    QTest.qWait(150)
                    assert not body.isVisible(), 'Confirmation did not close'
                    assert len(calls) == before + (action in ('accept', 'keyboard_update')), calls
                    checks.append({'theme':theme, 'action':action, 'calls':len(calls)})
            if os.name == 'nt':
                foreground_pid = ctypes.c_ulong()
                foreground = ctypes.windll.user32.GetForegroundWindow
                foreground.restype = ctypes.c_void_p
                ctypes.windll.user32.GetWindowThreadProcessId(foreground(), ctypes.byref(foreground_pid))
                assert foreground_pid.value != os.getpid(), 'Test took desktop focus'
            qml_errors = [m for m in messages if any(s in m for s in
                ('ReferenceError', 'TypeError', 'SyntaxError', 'Unable to assign', 'Cannot assign', 'Binding loop'))]
            assert not qml_errors, qml_errors
        except Exception as exc:
            error = repr(exc)
        report = {'passed':error is None, 'error':error, 'checks':checks, 'calls':calls,
                  'messages':messages, 'legacy':args.legacy, 'windows':args.windows,
                  'scale':args.scale,
                  'dimensions':[window.width(), window.height()]}
        (RUN/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
        if shell:
            shell.close()
        else:
            window.close()
        app.exit(1 if error else 0)

    controller.navigate('update')
    QTimer.singleShot(1800, inspect)


module.install_development_harness = install
sys.argv = [str(ROOT/'KFPS.UI/app.py'), '--demo', '--theme-preview', 'Night Blossom',
            '--skip-startup-index', '--community-preview-background', '--page', 'update',
            '--width', str(args.width), '--height', str(args.height)]
watchdog = threading.Timer(60, lambda: os._exit(124))
watchdog.daemon = True
watchdog.start()
raise SystemExit(module.main(workspace_runtime=runtime))
