"""Normal production startup, existing account, background capture, no mutations."""
import json
from pathlib import Path
import runpy
import sys
import time

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / 'src'), str(UI.parent)]
from PySide6.QtCore import QTimer
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickItem
from kfps_ui.development_harness import DevelopmentHarness

OUTPUT = UI.parent / 'runtime/community-preview/integration-20260920'
OUTPUT.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
ready_at = None


def capture(self, screenshot, report):
    global ready_at
    try:
        engine = QQmlEngine.contextForObject(self.window).engine()
        # Hidden Windows surfaces do not drive the normal render-loop incubator.
        engine.incubationController().incubateFor(25)
        page = self.window.findChild(QQuickItem, 'CommunityPreviewPage')
        gallery = engine.rootContext().contextProperty('preview')
        if page is not None and gallery.authenticated and gallery.artworkModel.rowCount() > 0:
            self._grab_window()
            if ready_at is None:
                ready_at = time.monotonic()
            if (time.monotonic() - ready_at > 3 and not gallery._image_pending
                    and engine.incubationController().incubatingObjectCount() == 0):
                assert gallery.live
                assert not gallery.hasError, gallery.status
                assert gallery.images._bytes > 0
                self._grab_window().save(str(screenshot))
                (OUTPUT / 'clean-live-native.json').write_text(json.dumps(dict(
                    passed=True, authenticated=True, live=True,
                    visible_catalog=gallery.artworkModel.rowCount(),
                    loaded_image_bytes=gallery.images._bytes,
                    elapsed_seconds=round(time.monotonic() - started, 2)), indent=2), encoding='utf-8')
                self.app.quit()
                return
        assert time.monotonic() - started < 60, 'Live gallery startup timed out'
        QTimer.singleShot(100, lambda: capture(self, screenshot, report))
    except Exception as error:
        (OUTPUT / 'clean-live-native.json').write_text(json.dumps(dict(passed=False, error=str(error))), encoding='utf-8')
        self.app.exit(1)


DevelopmentHarness._capture_single = capture
sys.argv = [str(UI / 'app.py'), '--community-preview-background', '--page', 'community',
            '--skip-startup-index', '--allow-source-download', '--screenshot', str(OUTPUT / 'clean-live.png')]
runpy.run_path(str(UI / 'app.py'), run_name='__main__')
