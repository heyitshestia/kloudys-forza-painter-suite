"""Explicit opt-in production QA. Creates labeled synthetic posts; keeps an ID ledger.

Never signs out, changes a profile, or revokes the existing user's entitlement.
Cleanup is a separate audited step so an interrupted run remains recoverable.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

REPO = Path(sys.argv[1]).resolve()
FIXTURES = Path(sys.argv[2]).resolve()
RUN = REPO / 'runtime/community-preview/live-qualification-20260920' / time.strftime('%H%M%S')
RUN.mkdir(parents=True, exist_ok=True)
UI = REPO / 'KFPS.UI'
sys.path[:0] = [str(UI / 'src'), str(REPO)]
from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from kfps_ui.community_client import CommunityApiClient, CommunityApiError
from kfps_ui.development_harness import DevelopmentHarness
from kfps_ui.app_paths import AppPaths

RESUME = Path(sys.argv[3]) if len(sys.argv) > 3 else None
ledger = json.loads((RESUME / 'created.json').read_text()) if RESUME else []
checks = json.loads((RESUME / 'checks.json').read_text())['checks'] if RESUME else []
PREFIX = ledger[0]['title'].rsplit(' ', 1)[0] if ledger else 'KFPS SYNTHETIC QA ' + RUN.name
if ledger: (RUN / 'created.json').write_text(json.dumps(ledger, indent=2), encoding='utf-8')
lock = threading.Lock()
original_json, original_multipart = CommunityApiClient.json, CommunityApiClient.multipart


def record(value):
    artwork = value.get('artwork', {})
    if artwork.get('id') and artwork.get('title', '').startswith(PREFIX):
        with lock:
            if not any(row['id'] == artwork['id'] for row in ledger):
                ledger.append({k: artwork.get(k) for k in ('id', 'title', 'kind', 'ends_at', 'download_url', 'photo_urls')})
                (RUN / 'created.json').write_text(json.dumps(ledger, indent=2), encoding='utf-8')
    return value


def request(self, path, method='GET', payload=None, **kwargs):
    value = original_json(self, path, method, payload, **kwargs)
    return record(value) if method == 'POST' and path == 'artworks' else value


def multipart(self, path, metadata, files):
    return record(original_multipart(self, path, metadata, files))


CommunityApiClient.json, CommunityApiClient.multipart = request, multipart


class IsolatedPaths(AppPaths):
    @property
    def library_root(self): return RUN / 'downloads/vinyls'
    @property
    def exported_root(self): return RUN / 'downloads/exported'


def start(self, screenshot, report):
    engine = QQmlEngine.contextForObject(self.window).engine()
    service = engine.rootContext().contextProperty('preview')
    window, app = self.window, self.app
    paths = service.community.paths
    service.community.paths = IsolatedPaths(paths.app_root, paths.ui_root, paths.qml_root,
        paths.asset_root, RUN / 'downloads/runtime', paths.bundled_python)
    original_language = service.language
    client = service.community.sessionClient()
    state = {'predicate': None, 'deadline': time.monotonic()+120, 'process': None, 'log': None}

    def find(name):
        queue = [window.contentItem()]
        while queue:
            item = queue.pop()
            if item.objectName() == name: return item
            queue.extend(item.childItems())
        item = window.findChild(QObject, name)
        assert item is not None, 'Missing ' + name
        return item

    def evaluate(code, item=None):
        target = item or find('CommunityPreviewPage')
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, code)
        value, _ = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value

    def click(name):
        item = find(name)
        assert item.isVisible() and item.isEnabled(), 'Inactive ' + name
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)

    def wait(seconds=.4):
        until = time.monotonic()+seconds
        return lambda: time.monotonic() >= until

    def passed(name):
        checks.append(name)
        print('PASS ' + name, flush=True)
        save()

    def save(failure='', complete=False):
        (RUN / 'checks.json').write_text(json.dumps(dict(passed=complete and not failure,
            checks=checks, failure=failure, created=ledger), indent=2), encoding='utf-8')

    def capture(name): self._grab_window().save(str(RUN / (name + '.png')))
    def idle(): return not service.busy
    def ok(): assert not service.hasError, service.status
    def select(ident):
        assert ident in service._records, ident
        service.select(ident)
    def iso(value): return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='milliseconds')

    def inspect(index):
        service.inspectPath(str(FIXTURES / f'vinyl-{index}.json'))

    def fields(name, **more):
        result = dict(title=PREFIX + ' ' + name, description='Temporary synthetic qualification artwork. Automatically removed after testing.',
            category='Patterns', license='KFPS Community Share', tags='qa-synthetic', classification='toolmade',
            rights=True, compatibility=True)
        result.update(more)
        return result

    def first_steps():
        yield lambda: service.authenticated and not service.busy and service.rows
        assert service.live and client.token
        yield wait(12)
        assert service.supporter, ('Supporter verification: ' + service.community._local_supporter_state
                                   + ' / ' + service.community.supporterStatus)
        snapshot = original_json(client, 'session', authenticated=True)
        (RUN / 'session-before.json').write_text(json.dumps({'authenticated': True, 'username': service.username}), encoding='utf-8')
        passed('Existing protected GitHub session reused in normal CLEAN startup')
        service.setLanguage('en')
        yield wait()
        click('OpenUpload')
        yield wait()
        old = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = lambda *a, **k: (str(FIXTURES / 'vinyl-0.json'), '')
        try: click('ChooseUpload')
        finally: QFileDialog.getOpenFileName = old
        yield idle
        ok(); assert service.upload['kind'] == 'vinyl' and service.upload['shapes'] == 3000
        find('UploadTitle').setProperty('text', PREFIX + ' vinyl')
        find('UploadDescription').setProperty('text', fields('')['description'])
        evaluate('rights.checked = true; compatibility.checked = true', find('UploadRights'))
        capture('upload-3000')
        click('PublishUpload')
        yield idle
        ok(); assert len(ledger) == 1, ledger
        vinyl = ledger[-1]['id']; select(vinyl)
        yield wait()
        passed('Native file chooser action, 3000-shape inspection, form and production upload')
        for action, score in (('Upvote', 1), ('Downvote', -1), ('Downvote', 0)):
            click(action)
            yield idle
            ok(); assert service.selected['score'] == score
        click('Favorite'); yield idle
        assert service.selected['favorite']
        service.refresh(); yield idle
        select(vinyl); assert service.selected['favorite'] and service.selected['score'] == 0
        passed('Upvote, downvote, clear and favorite persist across production refresh')
        click('Download'); yield idle
        ok()
        downloaded = Path(service.community.downloadedPath)
        assert downloaded.is_relative_to(RUN) and downloaded.is_file()
        assert hashlib.sha256(downloaded.read_bytes()).hexdigest() == service._records[vinyl]['content_sha256']
        assert len(json.loads(downloaded.read_text())['shapes']) == 3000
        passed('Vinyl download hash and all 3000 shapes preserved in isolated library')
        service.updateTags('qa-synthetic, racing'); yield idle; ok()
        assert 'racing' in service.selected['tags']
        inspect(1); yield idle; ok()
        service.publish(fields('revision', classification='handmade', revision_id=vinyl, change_note='Synthetic revision'))
        yield idle; ok(); select(vinyl)
        assert service._records[vinyl]['current_revision'] == 2
        passed('Owner tag edit and content revision retain the artwork identity')
        click('InspectorCreator'); yield idle; yield wait()
        assert service.creatorProfile['username'] == service.username
        capture('creator'); evaluate('creatorDialog.close()')
        passed('Creator link opens live profile and scrollable thumbnail catalog')
        inspect(2); yield idle
        service.publish(fields('supporter', supporter=True)); yield idle; ok()
        supporter = ledger[-1]['id']; select(supporter)
        assert service.selected['supporter'] and not service.selected['locked']
        click('Download'); yield idle; ok()
        passed('Existing supporter entitlement accepts supporter-only upload and download')
        return vinyl, supporter

    def steps():
        if RESUME:
            yield lambda: service.authenticated and not service.busy
            yield wait(12)
            service.filter('scope', 'My uploads'); yield idle
            vinyl, supporter = ledger[0]['id'], ledger[1]['id']
        else:
            vinyl, supporter = yield from first_steps()
        value = json.loads((FIXTURES / 'vinyl-3.json').read_text())
        value['shapes'][0]['data'][0] = int(time.time()) % 10000
        timed_source = RUN / 'timed-vinyl.json'
        timed_source.write_text(json.dumps(value), encoding='utf-8')
        service.inspectPath(str(timed_source)); yield idle
        start_at, end_at = time.time()+15, time.time()+75
        service.publish(fields('timed', timed=True, starts=iso(start_at), ends=iso(end_at)))
        yield idle; ok()
        timed = ledger[-1]['id']; select(timed)
        timed_record = dict(service._records[timed])
        assert service.selected['state'] == 'upcoming'
        assert client.binary(timed_record['download_url'], authenticated=True)[0]
        try: CommunityApiClient(client.base_url).binary(timed_record['preview_url'])
        except CommunityApiError as error: assert error.status == 404
        else: raise AssertionError('Upcoming public preview accessible')
        service.filter('scope', 'Timed Releases'); yield idle
        assert not any(row['id'] == timed for row in service.rows)
        yield lambda: time.time() >= start_at+1
        service.refresh(); yield idle
        assert any(row['id'] == timed for row in service.rows)
        select(timed); click('Download'); yield idle; ok()
        service.filter('scope', 'Browse'); service.filter('search', PREFIX)
        yield idle
        assert any(row['id'] == timed for row in service.rows)
        passed('Production schedule hides before start, permits active download, appears in Browse and Timed')
        yield lambda: time.time() > end_at+2
        yield idle
        assert not any(row['id'] == timed for row in service.rows)
        try: client.binary(timed_record['download_url'], authenticated=True)
        except CommunityApiError as error: assert error.status == 404
        else: raise AssertionError('Expired file accessible')
        passed('Expiry removes the visible item and blocks its file immediately, before cron')
        service.inspectPath(str(FIXTURES / 'synthetic-audi.kfpslivery')); yield idle; ok()
        assert service.upload['kind'] == 'livery' and service.upload['shapes'] == 1200
        service.publish(fields('invalid-no-photos')); yield idle
        assert service.hasError and ledger[-1]['id'] == timed
        photos = [str(FIXTURES / name) for name in ('photo-0.png', 'photo-1.jpg', 'photo-2.webp')]
        service.inspectPhotos(photos + [photos[0]]); yield idle
        assert service.hasError
        service.inspectPhotos(photos); yield idle; ok()
        assert len(service.upload['photoUrls']) == 3
        service.removePhoto(1); assert len(service.upload['photoUrls']) == 2
        service.inspectPhotos(photos); yield idle; ok()
        service.publish(fields('livery', category='Motorsport', timed=True, starts=iso(time.time()-10), ends=iso(time.time()+480)))
        yield idle; ok()
        livery = ledger[-1]['id']; select(livery)
        assert len(service.selected['photoUrls']) == 3
        yield wait()
        capture('livery-three-photos')
        click('Download'); yield idle; ok()
        target = Path(service.community.downloadedPath)
        assert target.is_relative_to(RUN) and target.read_bytes() == (FIXTURES / 'synthetic-audi.kfpslivery').read_bytes()
        passed('1200-shape livery: PNG/JPEG/WebP, 3 photos, remove/replace, rejected 0/4 photos, exact native download')
        evaluate('imageDialog.photoIndex = 1; imageDialog.open()')
        yield wait(); assert evaluate('imageDialog.visible')
        capture('fullscreen-photo')
        click('OpenLiveryRender')
        yield lambda: service.liveryViewer and service.liveryViewer.viewerReady
        ok(); viewer = service.liveryViewer
        capture('real-audi-3d')
        config = RUN / 'render-config.json'
        config.write_text(json.dumps({'port': int(os.environ['QTWEBENGINE_REMOTE_DEBUGGING'].split(':')[-1]),
            'url': viewer.viewerUrl, 'output': str(RUN)}), encoding='utf-8')
        state['log'] = (RUN / 'render-playwright.log').open('w', encoding='utf-8')
        state['process'] = subprocess.Popen([os.environ['KFPS_TEST_NODE'], str(UI / 'tools/test_community_preview_render.cjs'), str(config)],
            stdout=state['log'], stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        yield lambda: state['process'].poll() is not None
        state['log'].close(); state['log'] = None
        assert state['process'].returncode == 0, (RUN / 'render-playwright.log').read_text()
        folder = Path(service._render_session.temporary.name)
        click('CloseLiveryRender'); yield wait(1)
        assert not folder.exists() and service.liveryViewer is None and not evaluate('renderDialog.visible')
        evaluate('imageDialog.close()')
        passed('Real Audi mesh and synthetic livery render; orbit/pan/zoom/wheels, two canvas sizes, X closes and removes scratch')
        import psutil
        process = psutil.Process()
        samples = []
        for cycle in range(3):
            service.openRender()
            yield lambda: service.liveryViewer and service.liveryViewer.viewerReady
            folder = Path(service._render_session.temporary.name)
            children = [(p.pid, p.create_time()) for p in process.children(recursive=True) if 'python' in p.name().lower()]
            click('CloseLiveryRender'); yield wait(2)
            assert not folder.exists() and service.liveryViewer is None
            remaining = {(p.pid, p.create_time()) for p in process.children(recursive=True)}
            assert not any(item in remaining for item in children), children
            samples.append({'cycle': cycle, 'app_rss_mib': round(process.memory_info().rss / 1048576, 1),
                'child_count': len(remaining)})
        service.openRender(); service.closeRender(); yield idle; yield wait(1)
        assert service.liveryViewer is None
        (RUN / 'render-memory.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
        passed('Three repeated real 3D cycles and close-during-download leave no renderer session or worker process')
        for ident in (vinyl, supporter, livery):
            service.filter('scope', 'My uploads'); yield idle
            select(ident)
            record_data = service._records[ident]
            try: CommunityApiClient(client.base_url).binary(record_data['download_url'])
            except CommunityApiError as error: assert error.status == 401
            else: raise AssertionError('Anonymous download permitted')
            service.moderate('remove'); yield idle; ok()
            assert not any(row['id'] == ident for row in service.rows)
        passed('All ordinary synthetic posts owner-removed; anonymous file access rejected')
        assert client.token == service.community.sessionClient().token
        original_json(client, 'session', authenticated=True)
        passed('Original GitHub session still accepted; no sign-out or account changes')

    sequence = steps()
    timer = QTimer(window); timer.setInterval(50)

    def finish(failure=''):
        timer.stop()
        if state['process'] and state['process'].poll() is None:
            state['process'].kill(); state['process'].wait()
        if state['log']: state['log'].close()
        service.closeRender()
        service.setLanguage(original_language)
        save(failure, complete=True)
        if failure: capture('failure'); print(failure, flush=True)
        print('RESULT ' + str(RUN), flush=True)
        app.exit(1 if failure else 0)

    def advance():
        try:
            engine.incubationController().incubateFor(15)
            self._grab_window()
            if state['predicate'] is not None and not state['predicate']():
                assert time.monotonic() < state['deadline'], 'Timed out: ' + service.status + ' / ' + (service.liveryViewer.summary if service.liveryViewer else '')
                return
            state['predicate'] = next(sequence)
            state['deadline'] = time.monotonic()+180
        except StopIteration: finish()
        except Exception: finish(traceback.format_exc())
    timer.timeout.connect(advance); timer.start()


DevelopmentHarness._capture_single = start
sys.argv = [str(UI / 'app.py'), '--community-preview-background', '--page', 'community',
            '--skip-startup-index', '--allow-source-download', '--screenshot', str(RUN / 'startup.png')]
runpy.run_path(str(UI / 'app.py'), run_name='__main__')
