"""Real shared-window theme regression, isolated and without desktop focus."""
import argparse
import ctypes
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--width', type=int, default=1600)
parser.add_argument('--height', type=int, default=1000)
parser.add_argument('--scale', type=float, default=1)
parser.add_argument('--rhi', action='store_true')
args = parser.parse_args()
run = args.output.resolve()
run.mkdir(parents=True, exist_ok=False)
profile = run / 'profile'
profile.mkdir()
os.environ.update(QT_QPA_PLATFORM='windows' if args.rhi else 'offscreen',
    QT_QUICK_BACKEND='rhi' if args.rhi else 'software', QT_SCALE_FACTOR=str(args.scale),
    KFPS_QML_GRAPHICS='d3d11' if args.rhi else 'software', QSG_RHI_PREFER_SOFTWARE_RENDERER='1',
    QSG_RENDER_LOOP='basic', KFPS_ACTIVITY_DISABLED='1', KFPS_SKIP_STARTUP_INDEX='1',
    KFPS_SKIP_STARTUP_THUMBNAILS='1', PYTHONDONTWRITEBYTECODE='1',
    APPDATA=str(profile/'roaming'), LOCALAPPDATA=str(profile/'local'),
    QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu', KFPS_STARTUP_MUTED='1')
sys.path[:0] = [str(ROOT), str(ROOT/'KFPS.UI'), str(ROOT/'KFPS.UI/src'), str(ROOT/'KFPS.Editor/src')]
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, Qt, QTimer, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PIL import Image
from kfps_ui.theme_catalog import THEME_PRESETS

messages, results = [], []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location('workspace_theme_app', ROOT/'KFPS.UI/app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_paths = module.AppPaths.discover()
sample = profile/'app'
sample.mkdir()
shutil.copy2(ROOT/'VERSION', sample/'VERSION')
paths = replace(original_paths, app_root=sample, runtime_root=sample/'runtime')
paths.runtime_root.mkdir()
paths.settings_file.write_text(json.dumps({'theme':'Redline', 'reducedMotion':True, 'ambientMotion':False,
    'supportUpscalerNoticeAcknowledged':True, 'communityJoinNoticeAcknowledged':True,
    'backgroundRemoverNoticeAcknowledged':True,
    'dcinsideKoreanNotice202609Acknowledged':True}), encoding='utf-8')
module.AppPaths.discover = classmethod(lambda cls: paths)
runtime = SimpleNamespace(baseline={'status':'development'}, graphics=SimpleNamespace(backend='software'),
                          borrow_guard=lambda:SimpleNamespace(Close=lambda:None))


def errors():
    return [m for m in messages if any(s in m for s in ('ReferenceError', 'TypeError', 'SyntaxError',
        'Unexpected token', 'Expected token', 'Cannot assign', 'Unable to assign', 'Binding loop', 'is not a type'))]


def install(app, window, controller, community, settings, jsons, app_args):
    from kfps_ui.workspace_host import WorkspaceWindow
    shell = next(w for w in app.topLevelWidgets() if isinstance(w, WorkspaceWindow))
    shell.resize(args.width, args.height)
    foreground = ctypes.windll.user32.GetForegroundWindow
    foreground.restype = ctypes.c_void_p
    routes = ('create', 'outputs', 'liveries', 'community', 'editor', 'tools', 'settings', 'help', 'support', 'update')
    cases = [(preset.name, page) for preset in THEME_PRESETS for page in routes]
    captured = set()
    loaded_routes = set()
    slow_cold_loads = []

    def all_items():
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    def find(name):
        return next((item for item in all_items() if item.objectName() == name), None)

    def finish(error=None):
        report = {'passed':error is None, 'error':repr(error) if error else None, 'checks':results,
                  'messages':sorted(set(messages)), 'dimensions':[args.width,args.height],
                  'scale':args.scale, 'graphics':str(window.rendererInterface().graphicsApi()),
                  'slow_cold_loads':slow_cold_loads,
                  'load_budgets_seconds':{'cold':30, 'cached':12}}
        (run/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'passed':report['passed'], 'error':report['error'], 'checks':len(results)}), flush=True)
        shell.close()
        app.exit(1 if error else 0)

    def check_case(index):
        if index == len(cases):
            finish()
            return
        theme, route = cases[index]
        settings.theme = theme
        started = time.monotonic()
        cold_load = route not in loaded_routes

        def navigate():
            try:
                dashboard = next((item for item in all_items() if item.objectName() in
                    ('XboxDashboard','Ps2Dashboard','NierDashboard','ApexDashboard')), None)
                if dashboard and dashboard.isVisible():
                    assert QMetaObject.invokeMethod(dashboard, 'choose', Q_ARG('QVariant', route))
                else:
                    controller.navigate(route)
                QTimer.singleShot(100, inspect)
            except Exception as error:
                finish(error)

        def inspect():
            try:
                assert not errors(), errors()
                assert not any(obj.property('modal') and obj.property('opened')
                               for obj in window.findChildren(QObject)), 'Unexpected modal blocks navigation'
                host = find('CachedPageHost')
                page = host.property('item') if host else None
                if page is None or host.property('currentPage') != route:
                    # Cold QML compilation on an inactive software-rendered
                    # Windows runner is not a cached-navigation latency check.
                    # Keep slow cold loads visible rather than hiding the cost.
                    elapsed = time.monotonic()-started
                    budget = 30 if cold_load else 12
                    assert elapsed < budget, (theme,route,'load timeout',{
                        'seconds':round(elapsed,3), 'cold':cold_load,
                        'host_page':host.property('currentPage') if host else None,
                        'controller_page':controller.currentPage,
                        'item_present':page is not None})
                    QTimer.singleShot(100, inspect)
                    return
                assert controller.currentPage == route and settings.theme == theme
                assert window.property('inWorkspace') and shell._selected == 'KFPS'
                assert page.isVisible() and page.width() > 300 and page.height() > 180, (theme,route,'hidden page')
                assert shell.tabs.count() == 3 and not shell.owners, 'Lazy tools opened during navigation'
                active_handle = foreground()
                foreground_pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(active_handle, ctypes.byref(foreground_pid))
                assert foreground_pid.value != os.getpid(), ('Test took focus', active_handle, foreground_pid.value)
                assert 'QTabBar' in shell.styleSheet()
                if route == 'outputs':
                    tabs = [i for i in all_items() if i.isVisible() and i.objectName() == 'OutputCategoryTabs']
                    assert len(tabs) == 1, (theme,'duplicate category bars')
                    assert find('OutputCategoryTab:3').isVisible()
                    for action in ('edit','place','export','show'):
                        button = find('OutputAction:'+action)
                        assert button and button.width()+1 >= button.implicitWidth(), (theme,action,'Clipped action label')
                if theme == 'Redline' and route == 'settings':
                    for key, expected in [('folders',1),('chrome',2),('session',0),('theme',0)]:
                        assert QMetaObject.invokeMethod(page,'focusSetting',Q_ARG('QVariant',key))
                        QTest.qWait(30)
                        assert page.property('selectedSection') == expected, (key,expected)
                    assert find('WorkspaceSessionToggle').isVisible()
                if route in ('create','outputs','settings'):
                    # QWidget.grab omits embedded native QQuickWindow content.
                    image = window.grabWindow()
                    target = run/(theme.replace(' ','-').replace("'",'')+'-'+route+'.png')
                    assert not image.isNull() and image.save(str(target))
                    with Image.open(target) as bitmap:
                        content = bitmap.convert('RGB').crop((20, 60, bitmap.width-20, bitmap.height-20))
                        assert content.entropy() > 1.8, (theme,route,'Blank native capture')
                    captured.add(str(target))
                elapsed = round(time.monotonic()-started,3)
                if cold_load and elapsed >= 12:
                    warning = {'theme':theme, 'route':route, 'seconds':elapsed}
                    slow_cold_loads.append(warning)
                    print(json.dumps({'slow_cold_load':warning}), flush=True)
                loaded_routes.add(route)
                results.append({'theme':theme,'route':route,'page_size':[page.width(),page.height()],
                                'seconds':elapsed, 'cold_load':cold_load,
                                'qt_active':shell.isActiveWindow(), 'native_foreground_owned':False})
                (run/'progress.json').write_text(json.dumps(results[-1]),encoding='utf-8')
                QTimer.singleShot(20,lambda:check_case(index+1))
            except Exception as error:
                finish(error)
        QTimer.singleShot(100,navigate)
    QTimer.singleShot(1200,lambda:check_case(0))


module.install_development_harness = install
sys.argv = [str(ROOT/'KFPS.UI/app.py'),'--demo','--theme-preview','Redline','--allow-source-download',
            '--skip-startup-index','--community-preview-background','--width',str(args.width),'--height',str(args.height)]
def timeout():
    (run/'timeout.json').write_text(json.dumps({'checks':results,'messages':messages[-50:]}),encoding='utf-8')
    os._exit(124)
watchdog = threading.Timer(300,timeout)
watchdog.daemon = True
watchdog.start()
raise SystemExit(module.main(workspace_runtime=runtime))
