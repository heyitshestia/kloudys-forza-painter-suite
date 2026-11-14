"""Real Garage ownership, pending incubation, and shutdown regressions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from test_garage_ui import ROOT, SCRIPT


CONTROLLED_INCUBATION = '''\
    from PySide6.QtQml import QQmlIncubationController
    incubation = QQmlIncubationController()
    engine.setIncubationController(incubation)
    incubation_timer = QTimer()
    incubation_timer.timeout.connect(lambda: incubation.incubateFor(1))
    incubation_timer.start(5)
'''

LOADER_POLICY_FIXTURE = r'''
# Only the test profile is written. All other page content stays current.
from PySide6.QtQml import QQmlAbstractUrlInterceptor
page_path = Path.cwd() / 'KFPS.UI/qml/pages/LiveryPage.qml'
page_source = page_path.read_text(encoding='utf-8')
if fixture_policy == 'original':
    start = page_source.index('id: garageLoader')
    end = page_source.index('sourceComponent: GarageBrowser', start)
    page_source = page_source[:start] + ''' + repr('''id: garageLoader
                        objectName: "GarageBrowserLoader"
                        anchors.fill: parent
                        active: root.pageActive && root.showGallery && root.libraryTab === 2 && root.garage !== null
                        ''') + r''' + page_source[end:]
elif fixture_policy == 'coalescing-only':
    cancellation = 'if (item) item.prepareForUnload()'
    assert page_source.count(cancellation) == 1
    page_source = page_source.replace(cancellation, '// Test fixture: original delegate cancellation omission', 1)
else:
    assert fixture_policy == 'no-release'
    start = page_source.index('function releaseIfHidden()')
    end = page_source.index('onRequestedChanged:', start)
    page_source = page_source[:start] + 'function releaseIfHidden() {}\n                        ' + page_source[end:]
components_url = QUrl.fromLocalFile(str(page_path.parent.parent / 'components')).toString()
page_source = page_source.replace('import "../components"', 'import "' + components_url + '"')
fixture_page = profile / 'LiveryPage.qml'
fixture_page.write_text(page_source, encoding='utf-8')
class OriginalLoader(QQmlAbstractUrlInterceptor):
    def intercept(self, url, kind):
        if url.isLocalFile() and Path(url.toLocalFile()).resolve() == page_path.resolve():
            return QUrl.fromLocalFile(str(fixture_page))
        return url
original_loader = OriginalLoader()
current_make_engine = module.QQmlApplicationEngine
def original_engine():
    engine = current_make_engine()
    engine.addUrlInterceptor(original_loader)
    return engine
module.QQmlApplicationEngine = original_engine
'''

LIFETIME_RUN = textwrap.dedent(r'''
def run(app, engine, shutdown):
    from PySide6.QtCore import QElapsedTimer, QEvent, QObject
    import shiboken6
    import threading
    assert app.platformName() == 'offscreen'
    window = engine.rootObjects()[0]
    context = engine.rootContext()
    context.setContextProperty('screenshotMode', True)
    garage = context.contextProperty('garageService')
    liveries = context.contextProperty('fullLiveryService')
    editor = context.contextProperty('editorService')
    controller = context.contextProperty('appController')
    discovery.side_effect = None
    discovery.return_value = accounts
    stage = [0]
    held, trace = {}, []
    timer = QTimer()
    elapsed = QElapsedTimer()
    elapsed.start()

    def find(name):
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError('Missing ' + name)

    def js(item, expression):
        command = QQmlExpression(qmlContext(item), item, expression)
        value = command.evaluate()[0]
        assert not command.hasError(), command.error().toString()
        return value

    def remember_panel(loader):
        panel = loader.property('item')
        assert panel is not None and shiboken6.isValid(panel)
        held['panel'] = panel
        held['release_loader'] = loader
        held['search'] = find('garageSearch')
        held['panel_context'] = qmlContext(held['search'])
        assert held['panel_context'].contextObject() is panel
        held['search_timer'] = next(obj for obj in held['search'].findChildren(QObject)
                                    if 'QQmlTimer' in obj.metaObject().className())

    def assert_released(loader):
        assert not loader.property('active') and loader.property('item') is None
        panel_context = held['panel_context']
        trace.append({'release_context_wrapper': shiboken6.isValid(panel_context),
                      'release_context_valid': panel_context.isValid() if shiboken6.isValid(panel_context) else False})
        assert not shiboken6.isValid(panel_context) or not panel_context.isValid()
        for name in ('panel', 'search', 'search_timer'):
            assert not shiboken6.isValid(held[name]), name + ' survived panel release'
        assert not garage.searchText, 'Hidden search debounce changed the service'
        assert not garage.busy and not garage.catalogueBusy
        assert not liveries._viewer_memory_timer.isActive()
        assert not liveries.running and not editor.studioLaunching
        assert discovery.call_count == held['discovery_count']

    def record_release(label):
        loader = held.get('release_loader')
        panel_context = held.get('panel_context')
        trace.append({'release': label, 'stage': stage[0], 'elapsed_ms': elapsed.elapsed(),
                      'handles_valid': {name: shiboken6.isValid(held[name])
                                        for name in ('panel', 'search', 'search_timer') if name in held},
                      'context_valid': bool(panel_context is not None and shiboken6.isValid(panel_context)
                                            and panel_context.isValid()),
                      'loader_active': loader.property('active') if loader is not None and shiboken6.isValid(loader) else None,
                      'loader_has_item': loader.property('item') is not None if loader is not None and shiboken6.isValid(loader) else None,
                      'incubating': incubation.incubatingObjectCount(),
                      'qml_errors': list(qml_errors)})

    def save_trace():
        (profile / 'trace.json').write_text(json.dumps({'trace': trace, 'checked': checked,
                                                     'errors': errors, 'qml_errors': qml_errors}, indent=2))

    def release_ready(loader):
        # Neither callLater nor DeferredDelete is ordered before the next timer tick.
        assert not qml_errors, qml_errors
        assert not loader.property('visible'), 'Inactive Garage remained visible'
        assert not garage.searchText, 'Hidden search debounce changed the service'
        assert not garage.busy and not garage.catalogueBusy
        assert not liveries._viewer_memory_timer.isActive()
        assert not liveries.running and not editor.studioLaunching
        assert discovery.call_count == held['discovery_count']
        panel_context = held['panel_context']
        context_valid = shiboken6.isValid(panel_context) and panel_context.isValid()
        if loader.property('active') or loader.property('item') is not None or context_valid:
            record_release('release-not-started')
            return False
        if scenario == 'pending':
            assert held.get('cancelled_before_context_release'), 'Buffered delegates were not cancelled before context release'
            assert incubation.incubatingObjectCount() == 0, 'Buffered delegates survived release'
        ready = all(not shiboken6.isValid(held[name]) for name in ('panel', 'search', 'search_timer'))
        record_release('ready' if ready else 'released-awaiting-deferred-delete')
        return ready

    class ReleaseControl(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.DeferredDelete:
                trace.append({'control': release_control, 'event': 'DeferredDelete', 'elapsed_ms': elapsed.elapsed()})
                return release_control == 'retained'
            return False

        def after_deactivation(self):
            loader = held['release_loader']
            if loader.property('active') or held.get('control_observed'):
                return
            held['control_observed'] = True
            try:
                record_release('control-before-deferred-delete')
                assert not release_ready(loader), 'Control missed the queued deletion state'
                try:
                    assert_released(loader)
                except AssertionError as error:
                    assert str(error) == 'panel survived panel release', str(error)
                    trace.append({'control': release_control, 'timing_assertion_red': str(error)})
                else:
                    raise AssertionError('Unchanged destruction assertion did not fail in the control')
            except BaseException:
                errors.append(traceback.format_exc())
                record_release('control-error-before-quit')
                save_trace()
                timer.stop()
                app.quit()

    def check():
        try:
            assert not qml_errors, (stage[0], qml_errors)
            host = find('CachedPageHost')
            if stage[0] == 0:
                assert not discovery.called
                if scenario == 'cancel':
                    incubation_timer.stop()
                    for _ in range(8):
                        controller.navigate('liveries')
                        assert js(host, 'currentLoader.status') == 2, 'Page was not pending'
                        pending_loader = js(host, 'currentLoader')
                        controller.navigate('create')
                        assert not pending_loader.property('active')
                        assert pending_loader.property('item') is None
                    checked.append('cancel-eight-pending-page-loads')
                controller.navigate('liveries')
                incubation_timer.start(5)
            elif stage[0] == 1:
                if js(host, 'currentLoader.status') != 1 or garage.busy:
                    return
                js(find('garageAccountPicker'), 'activated(1)')
            elif stage[0] == 2:
                if garage.busy:
                    return
                assert garage.total == 80 and garage.selectedAccountId == accounts[0]['id']
                garage.select('1')
                page = find('LiveryPage')
                loader = find('GarageBrowserLoader')
                remember_panel(loader)
                held['discovery_count'] = discovery.call_count
                if release_control:
                    observer = ReleaseControl()
                    held['release_control_observer'] = observer
                    held['panel'].installEventFilter(observer)
                    for name in ('panel', 'search', 'search_timer'):
                        held[name].destroyed.connect(lambda *_, name=name: trace.append(
                            {'destroyed': name, 'elapsed_ms': elapsed.elapsed()}))
                    loader.activeChanged.connect(observer.after_deactivation)
                if scenario == 'pending':
                    incubation_timer.stop()
                    cars = find('garageCars')
                    assert js(cars, 'count >= 80 && cacheBuffer > 0 && width > 0 && height > 0')
                    # Grow the real buffer after rows are ready so pooled tiles
                    # cannot satisfy the scroll without new delegate incubation.
                    js(cars, 'cacheBuffer = 12 * cellHeight; positionViewAtIndex(40, GridView.Center)')
                    stage[0] = 9
                    return
                tabs = find('liveryLibraryTabs')
                action_started = elapsed.elapsed()
                for _ in range(40):
                    js(tabs, 'setCurrentIndex(0); setCurrentIndex(2)')
                    assert loader.property('item') is held['panel'], 'Garage panel destroyed inside one navigation action'
                    assert shiboken6.isValid(held['panel_context'])
                    assert held['panel_context'].isValid()
                checked.append('same-turn-tab-panel-identity')
                js(held['search'], "text = 'discarded tab search'; textEdited()")
                assert held['search_timer'].property('running')
                js(tabs, 'setCurrentIndex(0)')
                assert not loader.property('visible'), 'Hidden tab remained visible for one turn'
                trace.append({'toggle_action_ms': elapsed.elapsed() - action_started,
                              'timer_remaining_ms': timer.remainingTime()})
            elif stage[0] == 9:
                assert engine.incubationController() is incubation
                pending = incubation.incubatingObjectCount()
                assert pending > 0, 'Buffered grid did not schedule incubation after scrolling'
                cars = find('garageCars')
                trace.append({'pending_delegates_at_release': pending,
                              'grid': json.loads(js(cars, 'JSON.stringify({count, width, height, cacheBuffer, cellHeight, contentY})'))})
                loader = find('GarageBrowserLoader')
                held['cars'] = cars
                def model_changed():
                    if cars.property('model') is None:
                        held['cancelled_before_context_release'] = (
                            shiboken6.isValid(held['panel'])
                            and held['panel_context'].isValid()
                            and incubation.incubatingObjectCount() == 0)
                        trace.append({'model_cleared_with_live_context':
                                      held['cancelled_before_context_release']})
                def resume_before_deferred_delete():
                    if not loader.property('active'):
                        trace.append({'incubating_after_deactivation': incubation.incubatingObjectCount()})
                        # Exercise the vulnerable scheduling order while the old
                        # view still exists but its context has been invalidated.
                        incubation.incubateFor(10)
                        trace.append({'warnings_after_deactivation_pump': list(qml_errors)})
                cars.modelChanged.connect(model_changed)
                loader.activeChanged.connect(resume_before_deferred_delete)
                held['deactivation_observer'] = resume_before_deferred_delete
                garage.select('2')
                js(find('liveryLibraryTabs'), 'setCurrentIndex(0)')
                checked.append('release-with-delegates-still-incubating')
                stage[0] = 7
                return
            elif stage[0] == 3:
                loader = find('GarageBrowserLoader')
                if not release_ready(loader):
                    return
                assert_released(loader)
                checked.append('settled-tab-releases-context-and-search-work')
                garage.select('2')
                js(find('liveryLibraryTabs'), 'setCurrentIndex(2)')
                assert loader.property('active')
            elif stage[0] == 4:
                loader = find('GarageBrowserLoader')
                assert loader.property('item') is not held['panel']
                assert garage.selectedId == '2'
                assert js(find('garageCars'), 'currentItem.instanceId') == '2'
                js(find('garageCars'), 'navigate({key: Qt.Key_Home, accepted: false}, currentIndex)')
                assert garage.selectedId == garage.cars.rows[0]['instanceId']
                assert js(find('garageOpenPreview'), 'enabled')
                checked.append('tab-return-current-selection-and-keyboard')
                remember_panel(loader)
                js(held['search'], "text = 'discarded route search'; textEdited()")
                assert held['search_timer'].property('running')
                controller.navigate('create')
                assert not loader.property('visible')
            elif stage[0] == 5:
                loader = find('GarageBrowserLoader')
                assert not find('LiveryPage').property('pageActive')
                if not release_ready(loader):
                    return
                assert_released(loader)
                checked.append('settled-navigation-releases-context-and-search-work')
                garage.select('2')
                controller.navigate('liveries')
            elif stage[0] == 6:
                loader = find('GarageBrowserLoader')
                assert js(find('garageCars'), 'currentItem.instanceId') == '2'
                checked.append('navigation-return-current-selection')
                remember_panel(loader)
                js(find('liveryLibraryTabs'), 'setCurrentIndex(0)')
                assert loader.property('active'), 'No deferred release pending at close'
                checked.append('close-with-release-callback-pending')
                timer.stop()
                record_release('before-close')
                save_trace()
                window.close()
                return
            elif stage[0] == 7:
                loader = find('GarageBrowserLoader')
                if not release_ready(loader):
                    return
                assert held.get('cancelled_before_context_release'), 'Buffered delegates were not cancelled before context release'
                loader.activeChanged.disconnect(held['deactivation_observer'])
                assert_released(loader)
                assert incubation.incubatingObjectCount() == 0, 'Buffered delegates survived release'
                checked.append('buffered-incubation-drained-before-resuming')
                incubation_timer.start(5)
                js(find('liveryLibraryTabs'), 'setCurrentIndex(2)')
            elif stage[0] == 8:
                if incubation.incubatingObjectCount():
                    return
                assert js(find('garageCars'), 'currentItem.instanceId') == '2'
                assert js(find('garageOpenPreview'), 'enabled')
                checked.append('pending-cancellation-return-usable')
                remember_panel(find('GarageBrowserLoader'))
                timer.stop()
                record_release('before-close')
                save_trace()
                window.close()
                return
            trace.append({'stage': stage[0], 'incubating': incubation.incubatingObjectCount()})
            stage[0] += 1
        except BaseException:
            errors.append(traceback.format_exc())
            window.grabWindow().save(str(profile / 'failure.png'))
            timer.stop()
            record_release('error-before-quit')
            save_trace()
            app.quit()

    timer.timeout.connect(check)
    timer.start(350)
    def timed_out():
        errors.append(f'Timed out at stage {stage[0]}, incubation {incubation.incubatingObjectCount()}, QML {qml_errors}')
        timer.stop()
        record_release('timeout-before-quit')
        save_trace()
        app.quit()
    QTimer.singleShot(25000, timed_out)
    result = execute(app, engine, shutdown)
    incubation_timer.stop()
    record_release('after-engine-cleanup')
    save_trace()
    assert not shiboken6.isValid(engine)
    assert not shiboken6.isValid(context)
    assert not shiboken6.isValid(window)
    for name in ('panel', 'panel_context', 'search_timer'):
        if name in held:
            assert not shiboken6.isValid(held[name]), name + ' survived close'
    assert incubation.incubatingObjectCount() == 0
    assert garage._closed and garage._cancel.is_set() and garage._catalogue_cancel.is_set()
    assert not any(t and t.is_alive() for t in (garage._thread, garage._catalogue_thread))
    assert editor._closed and not editor._change_timer.isActive()
    assert not any(t.is_alive() for t in editor._threads)
    assert liveries._closed and not liveries._viewer_memory_timer.isActive()
    assert not any(t.name.startswith('kfps-') and t.is_alive() for t in threading.enumerate()), threading.enumerate()
    checked.append('close-destroys-contexts-and-stops-owned-work')
    save_trace()
    return result
''').replace('    window = engine.rootObjects()[0]', CONTROLLED_INCUBATION + '    window = engine.rootObjects()[0]', 1)


def lifecycle_script(scenario, fixture_policy='current', release_control=''):
    assert release_control in ('', 'queued', 'retained')
    assert not release_control or scenario == 'lifetime'
    # Share the audited real-app fixtures and launch boundary, not copied services.
    prelude, separator, workflow = SCRIPT.partition('def run(app, engine, shutdown):')
    assert separator
    _, separator, launch = workflow.rpartition("real_catalogue = sys.argv[5]")
    assert separator
    launch = (separator + launch).partition('logging.shutdown()')[0]
    ending = '''
logging.shutdown()
assert not errors, (errors, qml_errors)
assert not qml_errors, qml_errors
assert not resource_requests, resource_requests
assert len(checked) == {'pending': 4, 'cancel': 8, 'lifetime': 7}[scenario], checked
(profile / 'result.json').write_text(json.dumps({'scenario': scenario, 'checked': checked}))
'''
    return (prelude + (f'\nfixture_policy = {fixture_policy!r}\n' + LOADER_POLICY_FIXTURE
                      if fixture_policy != 'current' else '')
            + f'\nscenario = {scenario!r}\nrelease_control = {release_control!r}\n' + LIFETIME_RUN + launch + ending)


class GarageLoaderLifetimeTests(unittest.TestCase):
    def run_workflow(self, script, label, expected_count):
        with tempfile.TemporaryDirectory(prefix='garage-lifetime-', dir=os.environ.get('KFPS_GARAGE_TEST_TEMP')) as folder:
            root = Path(folder)
            env = {key: value for key, value in os.environ.items() if not key.startswith('KFPS_')}
            env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QML_DISABLE_DISK_CACHE='1',
                       QT_SCALE_FACTOR='2', KFPS_QML_GRAPHICS='software', KFPS_ACTIVITY_DISABLED='1',
                       KFPS_STARTUP_MUTED='1', QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-background-networking')
            for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
                location = root / name.lower()
                location.mkdir()
                env[name] = str(location)
            script_path = root / 'workflow.py'
            script_path.write_text(script, encoding='utf-8')
            sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                'KFPS.UI/qml/pages/LiveryPage.qml', 'KFPS.UI/qml/components/GarageBrowser.qml',
                'KFPS.UI/tests/test_garage_ui.py', 'KFPS.UI/tests/test_garage_loader_lifetime.py')}
            result = subprocess.run([sys.executable, '-I', '-B', str(script_path), str(root),
                                     'Night City 2077', '1280', '800', ''], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=35,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            evidence = os.environ.get('KFPS_GARAGE_EVIDENCE')
            if evidence:
                target = Path(evidence) / label
                target.mkdir(parents=True, exist_ok=True)
                for name in ('workflow.py', 'LiveryPage.qml', 'result.json', 'trace.json', 'failure.png', 'garage.png', 'catalogue.png', 'comparison-dialog.png'):
                    if (root / name).is_file():
                        shutil.copy2(root / name, target / name)
                (target / 'process.log').write_text(result.stdout + result.stderr, encoding='utf-8')
                (target / 'source-manifest.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            saved = json.loads((root / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['checked']), expected_count)

    def test_same_turn_identity_settled_release_return_and_close(self):
        policy = 'original' if os.environ.get('KFPS_GARAGE_LOADER_ORIGINAL') == '1' else 'current'
        control = os.environ.get('KFPS_GARAGE_RELEASE_CONTROL', '')
        self.run_workflow(lifecycle_script('lifetime', policy, control), 'lifetime', 7)

    def test_pending_page_creation_cancellation(self):
        self.run_workflow(lifecycle_script('cancel'), 'pending-page', 8)

    def test_buffered_delegate_context_cancellation(self):
        policy = os.environ.get('KFPS_GARAGE_LOADER_POLICY', 'current')
        self.run_workflow(lifecycle_script('pending', policy), 'pending-incubation', 4)

    def test_controlled_preview_gallery_studio_handoffs(self):
        script = SCRIPT.replace('    window = engine.rootObjects()[0]',
                                CONTROLLED_INCUBATION + '    window = engine.rootObjects()[0]', 1)
        script = script.replace('    return execute(app, engine, shutdown)', '''    result = execute(app, engine, shutdown)
    incubation_timer.stop()
    assert incubation.incubatingObjectCount() == 0
    return result''', 1)
        self.run_workflow(script, 'controlled-handoffs', 42)


if __name__ == '__main__':
    unittest.main()
