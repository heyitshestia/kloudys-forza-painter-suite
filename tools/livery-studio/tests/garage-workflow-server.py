"""Isolated real Studio server; reuse frozen geometry, never open game saves."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'KFPS.UI/src'), str(ROOT / 'KFPS.UI/tests'),
                str(ROOT / 'tools/livery-studio/src')]
from kfps_livery_lab import host_bridge, server, car_workspace
from kfps_livery_lab.diagnostics import DiagnosticLog
from kfps_livery_lab.garage_build import resolve_prepared_build
from kfps_livery_lab.prepare import atomic_json
from kfps_livery_lab.project_storage import ProjectStore
from kfps_ui.garage_notes import inspect_project, read_linked_project
from tools.kfps_release_announcement import ReleaseAnnouncement
from test_garage_studio_workflow import project
from test_studio_package_handoff import make_package

RUN = ROOT / 'tools/livery-studio/runs/garage-workflow-20261104/browser'
RUN.mkdir(parents=True, exist_ok=True)
source = json.loads((ROOT / 'tools/livery-studio/runs/garage-preview-refresh-fairlady-20261103/preparation.json').read_bytes())
prepared_root = Path(source['readonly_descriptor']).parent
prepared = json.loads((prepared_root / 'prepared.json').read_bytes())
workspace = RUN / 'car'
workspace.mkdir(exist_ok=True)
for file, _ in car_workspace.prepared_assets(prepared, prepared_root).values():
    target = workspace / file.relative_to(prepared_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file, target)
atomic_json(workspace / 'prepared.json', prepared)
fixture = json.loads((ROOT / 'runtime/garage-builds-20261102/body-fixtures.json').read_bytes())['records'][0]
vehicle, build = fixture['vehicle'], fixture['garage_build']
assert all(prepared['editor_config']['vehicle'][key] == value for key, value in vehicle.items())
assets = car_workspace.prepared_assets(prepared, workspace)
parts = resolve_prepared_build(build, prepared, assets)
value = project()
value['vehicle'] = vehicle
value['vehicle_parts'] = parts
store = ProjectStore(RUN / 'linked-projects')
entry = store.save(vehicle, {'name': 'Linked ' + str(time.time_ns()), 'project': value})['entry']
linked = inspect_project(next(store.root.rglob(entry['file_name'])), vehicle['car_id'], ROOT)
frozen = read_linked_project(linked, ROOT)
server.DiagnosticLog = lambda: DiagnosticLog(root=RUN / 'diagnostics')
host_bridge.HANDOFF_ROOT = RUN / 'handoffs'
host_bridge.launcher.CONTROL = RUN / 'control'
studio = server.LiveryLabServer(prepared, workspace, ROOT, session_data_root=RUN / 'session',
    activity_counter=False, release_announcement=ReleaseAnnouncement(RUN / 'session'))
switch_studio = None
try:
    url = studio.start()
    handoffs = {'linked': host_bridge.stage_handoff({'name': 'Linked project', 'project': frozen}),
                'stock': host_bridge.stage_handoff(host_bridge.request_for_stock(vehicle))}
    fixture_root = RUN / 'fixtures'
    fixture_root.mkdir(exist_ok=True)
    raw = bytearray(make_package(fixture_root / 'source-fixture.kfpslivery'))
    raw[16:20] = vehicle['car_id'].to_bytes(4, 'little')
    save = fixture_root / 'C_livery'
    save.write_bytes(raw)
    artwork = host_bridge.request_for_garage_artwork(vehicle, build, save, 'save')
    handoffs['artwork'] = host_bridge.stage_handoff(artwork)
    bad = copy.deepcopy(frozen)
    bad['vehicle_parts']['RearWing'] = 2147483647
    handoffs['invalid'] = host_bridge.stage_handoff({'name': 'Invalid parts', 'project': bad})
    previous = copy.deepcopy(prepared)
    for identity in (previous['editor_config']['vehicle'], previous['manifest']['vehicle']):
        identity.update(car_id=999999, model_code='QA_PREVIOUS', archive_name='QA_PREVIOUS.zip')
    switch_studio = server.LiveryLabServer(previous, workspace, ROOT, session_data_root=RUN / 'switch-session',
        activity_counter=False, release_announcement=ReleaseAnnouncement(RUN / 'switch-session'))
    car_id = 'e' * 32
    archive = fixture_root / 'car-switch.zip'
    archive.write_bytes(b'Isolated car-switch identity fixture; geometry is prevalidated separately.')
    prepared['signature']['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    row = {'id': car_id, 'archive': prepared['editor_config']['vehicle']['archive_name'],
           **vehicle, 'name': 'Target fixture', '_path': archive}
    (RUN / 'no-game').mkdir(exist_ok=True)
    with patch.object(car_workspace, 'catalogue', return_value={car_id: row}):
        manager = car_workspace.CarWorkspace(RUN / 'switch-session', ROOT, RUN / 'no-game')
    switch_studio.car_workspace = manager

    def prepare_fixture(record):
        for file, _ in assets.values():
            target = record['root'] / file.relative_to(workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        atomic_json(record['root'] / 'prepared.json', prepared)
        return car_workspace.validate_prepared(record['root'], record['car'])

    manager._prepare = prepare_fixture
    switch_url = switch_studio.start()
    handoffs['switch'] = host_bridge.stage_handoff({'name': 'Linked target', 'project': frozen}, startup_session=switch_url)
    handoffs['switchInvalid'] = host_bridge.stage_handoff({'name': 'Invalid target', 'project': bad}, startup_session=switch_url)
    atomic_json(RUN / 'browser-info.json', {'pid': __import__('os').getpid(), 'url': url, 'switchUrl': switch_url,
        'handoffs': handoffs, 'project': frozen, 'build': build, 'artwork': artwork['layout']})
    print('Isolated Studio handoff server ready', flush=True)
    deadline = time.monotonic() + 240
    while not (RUN / 'stop').exists() and time.monotonic() < deadline:
        time.sleep(.1)
finally:
    studio.close()
    if switch_studio:
        switch_studio.close()
