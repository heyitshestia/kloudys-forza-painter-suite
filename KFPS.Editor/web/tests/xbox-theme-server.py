"""Private headless theme test hosts. No native window, game access or telemetry."""
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'KFPS.Editor/src'), str(ROOT / 'tools/livery-studio/src'), str(ROOT)]
from kfps_editor.server import EditorServer, Handler, ServerPaths
from kfps_livery_lab.server import LiveryLabServer
from kfps_livery_lab import diagnostics
from tools.kfps_release_announcement import ReleaseAnnouncement


class NoActivity:
    def status(self):
        return {'enabled': False, 'consent': False}

    def start(self, *args, **kwargs):
        return self.status()

    def close(self, *args, **kwargs):
        pass


profile = Path(sys.argv[1]).resolve()
if not profile.is_relative_to(ROOT / 'KFPS.Editor/runtime'):
    raise ValueError('Test profiles must remain inside KFPS.Editor/runtime')
profile.mkdir(parents=True, exist_ok=True)
studio_profile = ROOT / 'tools/livery-studio/runs' / profile.name
studio_profile.mkdir(parents=True, exist_ok=True)
diagnostics.DEFAULT_ROOT = studio_profile / 'diagnostics'
# The browser fixture exercises the real theme UI, not the game renderer. These
# bounded placeholder assets satisfy server mounting only and are never rendered.
for name in ['mesh.glb', 'paint.png', 'mask.png']:
    (studio_profile / name).write_bytes(b'theme-test-placeholder')
prepared = {'files': {'mesh': 'mesh.glb', 'paint': 'paint.png', 'masks': ['mask.png'] * 3},
            'editor_config': {'vehicle': {'car_id': 1, 'model_code': 'THEME_TEST'}, 'sections': []},
            'manifest': {}}
notice = ReleaseAnnouncement(ROOT, state_root=profile / 'notices', clock=lambda: 0)
paths = ServerPaths.for_runtime(ROOT, profile, exports=profile / 'exports')
paths.startup_help.write_text('{"confirmed":true}', encoding='utf-8')
editor = EditorServer(('127.0.0.1', 0), Handler, paths=paths,
                      release_announcement=notice, activity_counter=NoActivity())
studio = LiveryLabServer(prepared, studio_profile, ROOT, renderer=object(),
                        session_data_root=studio_profile / 'data',
                        release_announcement=notice, activity_counter=NoActivity())
thread = threading.Thread(target=editor.serve_forever, daemon=True)
thread.start()
try:
    print(json.dumps({'editor': f'http://127.0.0.1:{editor.server_address[1]}/tools/fabric-editor/index.html#session={editor.editor_session_token}',
                      'studio': studio.start(), 'studioProfile': str(studio_profile)}), flush=True)
    sys.stdin.readline()
finally:
    studio.close()
    editor.shutdown()
    editor.server_close()
    thread.join(timeout=5)
