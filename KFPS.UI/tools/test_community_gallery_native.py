"""Real QML + native account service + isolated local Worker integration checks."""
import hashlib
import json
import time
import traceback
import uuid
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QImage


def run_gallery_checks(app, window, service, state, errors):
    state.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "checks": [], "qml_errors": errors}
    engine = QQmlEngine.contextForObject(window).engine()
    engine.incubationController().incubateFor(100)

    def find(name):
        queue = [window.contentItem()]
        while queue:
            item = queue.pop()
            if item.objectName() == name: return item
            queue.extend(item.childItems())
        found = window.findChild(QObject, name)
        if found is not None: return found
        raise AssertionError('Missing control: ' + name)

    def evaluate(code, item=None):
        target = item or find('CommunityPreviewPage')
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, code)
        value, _ = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value

    def click(name):
        item = find(name)
        assert item.isVisible() and item.isEnabled(), 'Inactive control: ' + name
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
        assert item.width() > 0 and item.height() > 0
        print(f'CLICK {name}: {point.x()},{point.y()}', flush=True)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point, 0)

    def checked(name):
        result['checks'].append(name)
        print('PASS ' + name, flush=True)

    def settled(seconds=.3):
        deadline = time.monotonic() + seconds
        return lambda: time.monotonic() >= deadline

    def present(name):
        def available():
            try: return find(name).isVisible()
            except AssertionError: return False
        return available

    def steps():
        yield lambda: service.community.connected and not service.busy
        yield settled(1)
        window.grabWindow().save(str(state / 'before-account.png'))
        assert evaluate('liveMode') is True
        assert not find('TestAccount').isVisible()
        click('CommunityAccount')
        yield lambda: evaluate('accountDialog.visible')
        assert find('GitHubSignIn').isVisible()
        window.grabWindow().save(str(state / 'account.png'))
        evaluate('accountDialog.close()')
        checked('Real account dialog; no mock accounts')
        service.community.connectAccountWith('local-test')
        yield lambda: service.community.authenticated and not service.community.authenticationInProgress
        if service.community.usernameRequired:
            name = 'Gallery' + str(time.time_ns())[-10:]
            service.community.chooseUsername(name, name)
        yield lambda: service.authenticated and not service.busy
        checked('Native auth/session and username through real local Worker')
        from kfps_ui.community_service import CommunityService
        existing = service.community
        reopened = CommunityService(existing.paths, existing.desktop, existing.log,
                                    app_version=existing._app_version)
        try:
            assert reopened._token and reopened._token == existing._token
            reopened.activate()
            yield lambda: reopened.connected and reopened.authenticated
            assert reopened.username == service.username
        finally:
            reopened.close()
        checked('Saved protected session reloaded by a fresh native service without sign-in')
        source = state / 'vinyl.json'
        salt = int(time.time()) % 100000
        color = [salt % 251, (salt // 251) % 251, salt * 47 % 251, 255]
        source.write_text(json.dumps({'shapes': [{'type': 16, 'color': color, 'data': [salt, 50, 80, 120, 15]}]}), encoding='utf-8')
        service.inspectPath(str(source))
        yield lambda: not service.busy
        assert service.upload.get('kind') == 'vinyl', service.status
        fields = dict(title='Gallery native ' + str(salt), description='Isolated real Worker test', category='Patterns',
                      license='KFPS Community Share', tags='test, racing', classification='handmade', supporter=False,
                      rights=True, compatibility=True, timed=False)
        service.publish(fields)
        yield lambda: not service.busy and service.scope == 'My uploads' and len(service.rows) > 0
        assert not service.hasError, service.status
        ident = service.rows[0]['id']
        service.select(ident)
        yield settled()
        window.grabWindow().save(str(state / 'before-vote.png'))
        checked('Vinyl inspection, real R2 upload and My uploads discovery')
        click('Upvote')
        yield lambda: service.selected.get('score') == 1 and not service.busy
        click('Downvote')
        yield lambda: service.selected.get('score') == -1 and not service.busy
        click('Downvote')
        yield lambda: service.selected.get('score') == 0 and not service.busy
        click('Favorite')
        yield lambda: service.selected.get('favorite') and not service.busy
        checked('Native upvote/downvote/clear and favorite buttons')
        click('Download')
        yield lambda: not service.busy and bool(service.community.downloadedPath)
        download = Path(service.community.downloadedPath)
        assert download.is_file() and str(download).startswith(str(state))
        assert hashlib.sha256(download.read_bytes()).hexdigest() == service._records[ident]['content_sha256']
        checked('Authenticated download validates hash and writes isolated library')
        click('InspectorCreator')
        yield lambda: service.creatorModel.rowCount() > 0 and not service.busy
        assert service.creatorProfile['username'] == service.username
        assert evaluate('creatorDialog.title') == '@' + service.username
        window.grabWindow().save(str(state / 'creator.png'))
        evaluate('creatorDialog.close()')
        checked('Creator profile uses live catalog and image tiles')
        original_package = service.repo / 'runtime/community-preview/timed-livery-fixture/audi.kfpslivery'
        assert original_package.is_file()
        package = state / 'audi-test.kfpslivery'
        with zipfile.ZipFile(original_package) as source_package, zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as target_package:
            for name in source_package.namelist():
                raw = source_package.read(name)
                if name == 'manifest.json':
                    manifest = json.loads(raw); manifest['package_id'] = str(uuid.uuid4())
                    raw = json.dumps(manifest).encode()
                target_package.writestr(name, raw)
        service.inspectPath(str(package))
        yield lambda: not service.busy
        assert service.upload.get('kind') == 'livery', service.status
        photo = QImage(800, 500, QImage.Format_RGBA8888)
        photo.fill(QColor.fromRgb(salt * 3571 % 0xffffff))
        photo.save(str(state / 'synthetic-photo.png'))
        service.inspectPhotos([str(state / 'synthetic-photo.png')])
        yield lambda: not service.busy
        assert len(service.upload.get('photoUrls', [])) == 1, service.status
        fields.update(title='Gallery Audi ' + str(salt), category='Motorsport')
        service.publish(fields)
        yield lambda: not service.busy
        assert not service.hasError, service.status
        yield lambda: any(row['kind'] == 'livery' for row in service.rows)
        livery = next(row for row in service.rows if row['kind'] == 'livery')
        service.select(livery['id'])
        yield settled()
        click('Download')
        yield lambda: not service.busy and service.community.downloadedPath.endswith('.kfpslivery')
        assert Path(service.community.downloadedPath).read_bytes() == package.read_bytes()
        checked('Real Audi package/photos multipart upload and validated native download')
        service.setLanguage('ko')
        yield present('Scope:Browse')
        yield settled()
        window.grabWindow().save(str(state / 'gallery-ko.png'))
        service.setLanguage('en')
        yield present('Scope:Browse')
        yield settled()
        window.grabWindow().save(str(state / 'gallery-en.png'))
        assert abs(find('Download').width() - find('Favorite').width()) < 1
        checked('Equal actions and EN/KO live gallery screenshots')
        original_size = (window.width(), window.height())
        for width, height in ((1280, 820), (1000, 720)):
            window.resize(width, height)
            yield settled()
            for name in ('CommunityAccount', 'CommunitySearch', 'OpenUpload', 'Download', 'Favorite'):
                item = find(name)
                corner = item.mapToScene(QPointF(item.width(), item.height()))
                assert corner.x() <= window.width() + 1 and corner.y() <= window.height() + 1, name
            window.grabWindow().save(str(state / f'gallery-{width}.png'))
        window.resize(*original_size)
        yield settled()
        yield present('Scope:Browse')
        checked('Live account controls and equal actions fit medium and narrow windows')
        service.openRender()
        yield lambda: service._render_session is not None
        render_folder = Path(service._render_session.temporary.name)
        assert render_folder.exists()
        service.closeRender()
        yield lambda: service._render_session is None and not render_folder.exists()
        checked('Authenticated livery opens an isolated renderer; closing removes the session and scratch files')
        service.select(ident)
        service.updateTags('test, updated')
        yield lambda: not service.busy and 'updated' in service.selected.get('tags', [])
        checked('Owner tag editing survives a real server round trip')
        source.write_text(json.dumps({'shapes': [{'type': 16, 'color': color, 'data': [salt, 50, 81, 120, 15]}]}), encoding='utf-8')
        service.inspectPath(str(source))
        yield lambda: not service.busy
        revision_fields = dict(fields, title='Revised native ' + str(salt), category='Patterns',
                              revision_id=ident, change_note='Integration revision')
        service.publish(revision_fields)
        yield lambda: not service.busy
        assert not service.hasError, service.status
        service.select(ident)
        assert service.selected['title'] == revision_fields['title']
        assert service.selected['category'] == 'Patterns'
        checked('Ordinary vinyl revision retains its identity and updates through the existing endpoint')
        from datetime import datetime, timezone
        source.write_text(json.dumps({'shapes': [{'type': 16, 'color': color[::-1], 'data': [salt, 50, 70, 110, 25]}]}), encoding='utf-8')
        service.inspectPath(str(source))
        yield lambda: not service.busy
        fields.update(title='Timed native ' + str(salt), timed=True,
            starts=datetime.fromtimestamp(time.time()-10, timezone.utc).isoformat(),
            ends=datetime.fromtimestamp(time.time()+8, timezone.utc).isoformat())
        service.publish(fields)
        yield lambda: not service.busy and any(row.get('ends') for row in service.rows)
        timed_id = next(row['id'] for row in service.rows if row.get('ends'))
        click('Scope:Browse')
        yield lambda: not service.busy and any(row['id'] == timed_id for row in service.rows)
        click('Scope:Timed Releases')
        yield lambda: not service.busy and any(row['id'] == timed_id for row in service.rows)
        yield lambda: not service.busy and all(row['id'] != timed_id for row in service.rows)
        checked('Timed release appears in Browse and Timed Releases, then disappears at expiry')
        service.community.signOut()
        yield lambda: not service.authenticated and not service.busy
        assert all(key.startswith(str(service._epoch) + '/') for key in service._image_sources)
        assert service._render_session is None
        assert not find('OpenUpload').isEnabled()
        checked('Sign-out clears account state and protected renderer')

    sequence = steps()
    current = {'predicate': None, 'deadline': time.monotonic() + 60}
    timer = QTimer(window)
    timer.setInterval(50)

    def finish(failure=''):
        timer.stop()
        result['passed'] = not failure and not errors
        if failure: result['failure'] = failure
        if failure:
            window.grabWindow().save(str(state / 'failure.png'))
            result['selection'] = {key: value for key, value in service.selected.items() if key not in ('previewUrl', 'photoUrls')}
        (state / 'gallery-checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)
        app.exit(0 if result['passed'] else 1)

    def advance():
        try:
            engine.incubationController().incubateFor(10)
            if current['predicate'] is not None and not current['predicate']():
                assert time.monotonic() < current['deadline'], 'Wait timed out: ' + service.status
                return
            current['predicate'] = next(sequence)
            current['deadline'] = time.monotonic() + 60
        except StopIteration: finish()
        except Exception: finish(traceback.format_exc())

    timer.timeout.connect(advance)
    timer.start()
