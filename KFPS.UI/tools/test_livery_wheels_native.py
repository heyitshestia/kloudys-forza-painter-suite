"""Test the actual QML livery viewer with isolated synthetic cars and settings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]


def fixture(folder: Path, index: int):
    from PIL import Image
    from tools.livery.inspector_server import LiveryInspectorServer

    folder.mkdir(parents=True, exist_ok=True)
    positions, normals, indices = [], [], []
    for normal, corners in [
        ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
        ((-1, 0, 0), [(-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)]),
        ((0, 1, 0), [(-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)]),
        ((0, -1, 0), [(-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)]),
        ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),
    ]:
        base = len(positions) // 3
        for corner in corners:
            positions.extend(v * .5 for v in corner)
            normals.extend(normal)
        indices.extend(base + v for v in (0, 1, 2, 0, 2, 3))
    binary = struct.pack('<144f36H', *(positions + normals + indices))
    doc = {
        "asset": {"version": "2.0"}, "scene": 0,
        "scenes": [{"nodes": [0, 1, 2, 3], "extras": {"kfps_part_options": [
            {"part_type": "RearWing", "id": 1, "stock": True},
            {"part_type": "RearWing", "id": 2, "level": 1}]} }],
        "nodes": [
            {"name": "Synthetic test car body", "mesh": 0, "scale": [1.8, .6, 3.6 + index * .1], "translation": [0, .9, 0], "extras": {"kfps_role": "paint"}},
            {"name": "Cabin", "mesh": 0, "scale": [1.4, .55, 1.8], "translation": [0, 1.45, 0], "extras": {"kfps_role": "paint"}},
            {"name": "Stock wing", "mesh": 0, "scale": [1.7, .08, .35], "translation": [0, 1.3, -1.5], "extras": {"kfps_role": "dark", "kfps_part_type": "RearWing", "kfps_part_option_ids": [1], "kfps_stock_part": True}},
            {"name": "Alternate wing", "mesh": 0, "scale": [1.9, .08, .5], "translation": [0, 1.65, -1.5], "extras": {"kfps_role": "dark", "kfps_part_type": "RearWing", "kfps_part_option_ids": [2], "kfps_stock_part": False}},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 288}, {"buffer": 0, "byteOffset": 288, "byteLength": 288}, {"buffer": 0, "byteOffset": 576, "byteLength": 72}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 24, "type": "VEC3", "min": [-.5]*3, "max": [.5]*3}, {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"}, {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR"}],
    }
    encoded = json.dumps(doc).encode()
    encoded += b' ' * (-len(encoded) % 4)
    glb = struct.pack('<III', 0x46546C67, 2, 28 + len(encoded) + len(binary))
    glb += struct.pack('<II', len(encoded), 0x4E4F534A) + encoded
    glb += struct.pack('<II', len(binary), 0x004E4942) + binary
    mesh = folder / "synthetic.glb"
    mesh.write_bytes(glb)
    Image.new('RGBA', (16, 16), (25, 180, 150, 255)).save(folder / 'paint.png')
    Image.new('RGBA', (16, 16), (0, 0, 0, 0)).save(folder / 'mask.png')
    assembly = {"format": "kfps_fh6_local_vehicle_assembly_v1", "tire_radius": .37,
                "rim_radius": .24, "tire_width": .23,
                "wheel_centers": {f"{end}_{side}": [x, .37, z] for end, z in [('front', 1.25), ('rear', -1.25)] for side, x in [('left', -1.02), ('right', 1.02)]}}
    server = LiveryInspectorServer(ROOT / 'tools/livery-inspector')
    server._manifest = {"vehicle": {"model_code": f"Synthetic Car {index}"}, "livery": {"title": "Wheel toggle qualification", "target_car_id": index}}
    server.set_local_mesh(mesh)
    server.set_local_render_contract(folder, {"format": "kfps_fh6_section_render_contract_v3",
        "assembly": assembly if index != 3 else {}, "files": {"paint": "paint.png", "masks": ["mask.png"]*3},
        "sections": [], "filters": ["all", "top", "left", "right", "front", "back"]})
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-hidden', action='store_true')
    parser.add_argument('--profile', type=Path, help='Reuse an isolated test profile to verify a full process restart')
    parser.add_argument('--real-cases', type=Path, help='Private JSON list of package, mesh and render index paths; read-only')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    real_cases = json.loads(args.real_cases.read_text()) if args.real_cases else []
    source_hashes = {}
    for case in real_cases:
        contract = json.loads(Path(case['render']).read_text())
        files = [Path(case[key]) for key in ('package', 'mesh', 'render')]
        files.extend(Path(case['render']).parent / name for name in [contract['files']['paint'], *contract['files']['masks']])
        for file in files:
            source_hashes[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
        assert source_hashes[case['package']] == contract['signature']['package_sha256'], 'Package/render mismatch'
        assert Path(case['mesh']).stat().st_size == contract['signature']['mesh_size'], 'Mesh/render mismatch'
    if source_hashes:
        (out / 'read-only-input-hashes.json').write_text(json.dumps(source_hashes, indent=2))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = f'127.0.0.1:{port}'
    from PIL import Image, ImageChops
    from PySide6.QtCore import QCoreApplication, QTimer, Qt, QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQuick import QQuickView
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    from kfps_ui.app_paths import AppPaths
    from kfps_ui.log_service import LogService
    from kfps_ui.full_livery_service import FullLiveryService

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QtWebEngineQuick.initialize()
    app = QApplication([])
    paths = AppPaths(out, UI, UI / 'qml', UI / 'assets', (args.profile or out / 'profile').resolve(), Path(sys.executable))
    servers = []
    with patch('kfps_ui.full_livery_service.discover_fh6_game_folder', return_value=None), patch.object(FullLiveryService, 'scanSaves'), patch.object(FullLiveryService, 'refreshPackages'):
        service = FullLiveryService(paths, LogService(), demo=True)
        view = QQuickView()
        view.setFlags(Qt.Window | Qt.WindowStaysOnBottomHint | Qt.WindowDoesNotAcceptFocus)
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        view.engine().addImportPath(str(UI / 'qml'))
        view.rootContext().setContextProperty('fullLiveryService', service)
        view.resize(1600, 1000)
        view.setSource(QUrl.fromLocalFile(str(UI / 'qml/pages/LiveryPage.qml')))
        assert view.rootObject(), [str(e) for e in view.errors()]
        view.rootObject().setProperty('wipNoticeAcknowledged', True)
        view.show()
        sequence = 0

        def publish():
            state = {'sequence': sequence, 'url': service.viewerUrl, 'visible': service.viewerWheelsVisible,
                     'ready': service.viewerReady, 'port': port, 'expectHidden': args.expect_hidden}
            temporary = out / 'state.tmp'
            temporary.write_text(json.dumps(state))
            os.replace(temporary, out / 'state.json')

        def next_car():
            if real_cases:
                from tools.livery.inspector_server import LiveryInspectorServer
                from tools.livery.portable_mesh_converter import validate_local_chassis_glb
                case = real_cases[len(servers)]
                validate_local_chassis_glb(case['mesh'])
                server = LiveryInspectorServer(ROOT / 'tools/livery-inspector')
                manifest = server.set_package(case['package'])
                contract = json.loads(Path(case['render']).read_text())
                assert manifest['vehicle']['model_code'].casefold() == contract['signature']['model_code'].casefold()
                server.set_local_mesh(case['mesh'])
                server.set_local_render_contract(Path(case['render']).parent, contract)
            else:
                server = fixture(out / 'fixtures' / str(len(servers) + 1), len(servers) + 1)
            servers.append(server)
            service._active = True
            service._inspector_ready(server.start())
            publish()

        next_car()
        config = out / 'config.json'
        config.write_text(json.dumps({'output': str(out), 'port': port, 'expectHidden': args.expect_hidden, 'realCases': real_cases}))
        driver = subprocess.Popen(['node', str(Path(__file__).with_suffix('.cjs')), str(config)], creationflags=subprocess.CREATE_NO_WINDOW)
        service.changed.connect(publish)
        timer = QTimer()

        def tick():
            nonlocal sequence
            command = out / 'command.json'
            try:
                value = json.loads(command.read_text()) if command.exists() else {}
            except (OSError, ValueError):
                value = {}
            if isinstance(value.get('sequence'), int) and value['sequence'] > sequence:
                sequence = value['sequence']
                if value.get('operation') == 'next':
                    next_car()
            if driver.poll() is not None:
                app.exit(driver.returncode)

        timer.timeout.connect(tick)
        timer.start(100)
        QTimer.singleShot(360000 if real_cases else 180000, lambda: (driver.kill(), app.exit(1)))
        try:
            code = app.exec()
        finally:
            timer.stop()
            if driver.poll() is None:
                driver.kill()
            driver.wait(timeout=10)
            view.setSource(QUrl())
            service.close()
            for server in servers:
                server.close()
            view.close()
        if code == 0:
            before, after = [Image.open(out / f'wheels-{mode}.png').convert('RGB') for mode in ('on', 'off')]
            crop = (0, 150, before.width, before.height - 65)
            delta = ImageChops.difference(before.crop(crop), after.crop(crop))
            changed = sum(max(pixel) > 12 for pixel in delta.getdata())
            assert changed > 1000, f'No meaningful canvas change when hiding wheels: {changed}'
            real_pixels = []
            for index in range(2, len(real_cases) + 1):
                images = [Image.open(out / f'car-{index}-{mode}.png').convert('RGB') for mode in ('on', 'off')]
                region = (0, 150, images[0].width, images[0].height - 65)
                diff = ImageChops.difference(*(image.crop(region) for image in images))
                count = sum(max(pixel) > 12 for pixel in diff.getdata())
                assert count > 500, f'Car {index} wheel pixels did not change: {count}'
                real_pixels.append(count)
            assert all(hashlib.sha256(Path(file).read_bytes()).hexdigest() == digest for file, digest in source_hashes.items()), 'Read-only input changed during test'
            result = {'passed': True, 'changedCanvasPixels': changed, 'otherCarPixelChanges': real_pixels,
                      'newCars': len(servers), 'fullProcessRestart': args.expect_hidden, 'realFiles': bool(real_cases),
                      'unchangedInputFiles': len(source_hashes)}
            (out / 'native-results.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        return code


if __name__ == '__main__':
    raise SystemExit(main())
