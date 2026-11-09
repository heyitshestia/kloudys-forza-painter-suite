"""Real isolated Preview/Studio endpoints for the owned-body browser check."""
import json
from pathlib import Path
import sys
import time
import shutil
import hashlib
import os
import re
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/livery-studio/src')]
from kfps_livery_lab import host_bridge
from kfps_livery_lab.prepare import atomic_json
from kfps_livery_lab.readonly_prepare import prepare_garage
from kfps_livery_lab.readonly_server import ReadonlyPreviewServer
from kfps_livery_lab.server import LiveryLabServer
from kfps_livery_lab import server
from kfps_livery_lab.car_workspace import prepared_assets
from kfps_livery_lab.diagnostics import DiagnosticLog
from tools.kfps_release_announcement import ReleaseAnnouncement
from tools.livery.vehicle_assets import load_or_build_vehicle_asset_index

qa_name = os.environ.get('KFPS_GARAGE_QA_NAME', '')
if qa_name and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', qa_name):
    raise ValueError('Invalid QA run name')
RUN = ROOT / 'tools/livery-studio/runs' / (qa_name or (
    'garage-catalogue-20261102' if os.environ.get('KFPS_GARAGE_CATALOGUE_QA') == '1'
    else 'garage-builds-20261102'))
RUN.mkdir(parents=True, exist_ok=True)
GAME = Path(os.environ.get('KFPS_GARAGE_REAL_GAME', 'C:/XboxGames/Forza Horizon 6/Content'))
fixture_path = Path(os.environ.get('KFPS_GARAGE_REAL_FIXTURE', ROOT / 'runtime/garage-builds-20261102/body-fixtures.json'))
fixture = json.loads(fixture_path.read_bytes())['records'][0]
asset = load_or_build_vehicle_asset_index(GAME, RUN / 'vehicle-index.json')[fixture['vehicle']['car_id']]
result = prepare_garage(ROOT, GAME, asset, fixture['garage_build'], progress=lambda text: print(text, flush=True))
atomic_json(RUN / 'preparation.json', result)
descriptor = Path(result['readonly_descriptor'])
preview = ReadonlyPreviewServer(descriptor, ROOT, expected_descriptor_sha256=result['readonly_descriptor_sha256'])
prepared = json.loads((descriptor.parent / 'prepared.json').read_bytes())
# Only test geometry/assets are copied; the shared preview cache is immutable.
workspace = RUN / 'studio-car'
workspace.mkdir(exist_ok=True)
for source, _ in prepared_assets(prepared, descriptor.parent).values():
    destination = workspace / source.relative_to(descriptor.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
        shutil.copy2(source, destination)
server.DiagnosticLog = lambda: DiagnosticLog(root=RUN / 'diagnostics')
host_bridge.HANDOFF_ROOT = RUN / 'host-handoffs'
host_bridge.HANDOFF_ROOT.mkdir(exist_ok=True)
studio = LiveryLabServer(prepared, workspace, ROOT, session_data_root=RUN / 'session', activity_counter=False,
                        release_announcement=ReleaseAnnouncement(RUN / 'session'))
switch_studio = None
try:
    layout = {'format': 'kfps-livery-layout-v1', 'vehicle': fixture['vehicle'], 'vinyls': [], 'placements': [],
              'garage_build': fixture['garage_build']}
    identifier = host_bridge.stage_handoff({'name': 'Owned body QA', 'layout': layout})
    retry_identifier = host_bridge.stage_handoff({'name': 'Owned body QA repeat', 'layout': layout})
    invalid = json.loads(json.dumps(layout))
    invalid['garage_build']['parts']['RearWing'] = 2147483647
    invalid['garage_build']['fingerprint'] = hashlib.sha256(json.dumps(
        {key: invalid['garage_build'][key] for key in ('version', 'parts')},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    invalid_identifier = host_bridge.stage_handoff({'name': 'Unavailable body QA', 'layout': invalid})
    preview_url, studio_url = preview.start(), studio.start()
    switching = {}
    if qa_name:
        from kfps_livery_lab import car_workspace
        # Reuse verified geometry but simulate a different starting identity. This
        # tests real handoff/HTTP/commit behavior, not another car's visual fidelity.
        previous = json.loads(json.dumps(prepared))
        for vehicle in (previous['editor_config']['vehicle'], previous['manifest']['vehicle']):
            vehicle.update(car_id=999999, model_code='QA_PREVIOUS', archive_name='QA_PREVIOUS.zip')
        switch_studio = LiveryLabServer(previous, workspace, ROOT, session_data_root=RUN / 'switch-session',
            activity_counter=False, release_announcement=ReleaseAnnouncement(RUN / 'switch-session'))
        archive = GAME / 'media/Cars' / asset.archive_name
        stat = archive.stat()
        car_id = 'e' * 32
        row = {'id': car_id, 'archive': asset.archive_name, 'car_id': asset.car_id,
               'name': asset.model_code, 'model_code': asset.model_code,
               '_path': archive, '_size': stat.st_size, '_mtime': stat.st_mtime_ns}
        with patch.object(car_workspace, 'catalogue', return_value={car_id: row}):
            manager = car_workspace.CarWorkspace(RUN / 'switch-session', ROOT, GAME)
        switch_studio.car_workspace = manager

        def prepare_fixture(record):
            for source, _ in prepared_assets(prepared, descriptor.parent).values():
                target = record['root'] / source.relative_to(descriptor.parent)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            atomic_json(record['root'] / 'prepared.json', prepared)
            return car_workspace.validate_prepared(record['root'], record['car'])

        manager._prepare = prepare_fixture
        switch_url = switch_studio.start()
        switching = {'switchStudio': switch_url,
            'switchValid': host_bridge.stage_handoff({'name': 'Valid target body', 'layout': layout}, startup_session=switch_url),
            'switchInvalid': host_bridge.stage_handoff({'name': 'Invalid target body', 'layout': invalid}, startup_session=switch_url)}
    atomic_json(RUN / 'browser-info.json', {'pid': __import__('os').getpid(), 'preview': preview_url,
        'studio': studio_url, 'handoff': identifier, 'retry': retry_identifier, 'invalid': invalid_identifier,
        'build': fixture['garage_build'], 'vehicle': fixture['vehicle'],
        'partNames': prepared['manifest']['inspection_runtime']['fidelity'].get('part_names'), **switching})
    print('Servers ready', flush=True)
    # Parent browser owns the stop marker, with a bounded emergency lifetime.
    deadline = time.monotonic() + 240
    while not (RUN / 'stop').exists() and time.monotonic() < deadline:
        time.sleep(.1)
finally:
    preview.close()
    studio.close()
    if switch_studio is not None:
        switch_studio.close()
