"""Read-only Studio bridge for livery preview preparation, not save operations."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import time
import zipfile

import psutil


def studio_package(app_root):
    root = Path(app_root).absolute()
    package = root / 'tools/livery-studio'
    boundary = root
    for path in (package, *package.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Studio discovery cannot follow redirected paths.')
    if not package.exists():
        if root.name != 'repo':
            raise ValueError('Livery Studio is required for this preview. The installation is incomplete.')
        package, boundary = root.parent / 'livery', root.parent
        config = package / 'settings/local-launch.json'
        for path in (config, *config.parents):
            if path.is_symlink() or path.is_junction():
                raise ValueError('Studio discovery cannot follow redirected paths.')
        with config.open('rb') as stream:
            body = stream.read(65537)
        value = json.loads(body) if len(body) <= 65536 else None
        if not isinstance(value, dict) or Path(value.get('kfpsRoot', '')).resolve() != root.resolve():
            raise ValueError('Studio is configured for a different KFPS installation.')
    for relative in ('src/kfps_livery_lab/readonly_prepare.py', 'src/kfps_livery_lab/readonly_server.py',
                     'src/web/livery-scene.js', 'src/web/readonly.html'):
        path = package / relative
        for item in (path, *path.parents):
            if item.is_symlink() or item.is_junction():
                raise ValueError('Studio discovery cannot follow redirected paths.')
            if item == boundary:
                break
        if not path.is_file():
            raise ValueError('The Studio read-only renderer is missing. Repair this KFPS installation.')
    return package.resolve()


def studio_module(app_root, module):
    if module not in ('readonly_prepare', 'readonly_server', 'readonly_cache'):
        raise ValueError('Unsupported Studio preview module.')
    package = studio_package(app_root)
    current = sys.modules.get('kfps_livery_lab')
    if current is not None and Path(current.__file__).resolve().parent != package / 'src/kfps_livery_lab':
        raise ValueError('Another Studio package is already loaded in this process.')
    source = str(package / 'src')
    if source not in sys.path:
        sys.path.insert(0, source)
    return importlib.import_module('kfps_livery_lab.' + module)


def prepare_mesh(paths, payload, cancel_event, progress=None):
    from tools.livery.package import validate_livery_inspection_artifact, _decode_livery_contract
    from tools.livery.vehicle_assets import load_or_build_vehicle_asset_index, sha256_file
    from tools.cgroup.forza_source_decoder import unwrap_forza_container, inspect_clivery_privacy
    from .jobs import _preview_target

    started = time.perf_counter()
    package = Path(str(payload.get('package_path') or '')).resolve()
    manifest = validate_livery_inspection_artifact(package)
    car_id = int(payload.get('car_id') or 0)
    if car_id != manifest['livery']['target_car_id']:
        raise ValueError('The preview request does not match the package car.')
    if str(payload.get('package_id') or '') != str(manifest.get('package_id') or ''):
        raise ValueError('The preview request does not match the package identity.')
    if cancel_event.is_set():
        raise InterruptedError('Local preview preparation was cancelled.')
    game = str(payload.get('game_folder') or '')
    if progress:
        progress('Checking local car assets')
    asset = load_or_build_vehicle_asset_index(game, paths.vehicle_index).get(car_id)
    if asset is None:
        raise ValueError(f'The local FH6 installation has no car archive for target ID {car_id}.')
    warnings = []
    expected_model = str(payload.get('expected_model_code') or '')
    if expected_model and asset.model_code.casefold() != expected_model.casefold():
        warnings.append('The local model code differs from the package model.')
    expected_hash = str(payload.get('expected_archive_sha256') or '')
    if expected_hash and sha256_file(Path(asset.archive_path)) != expected_hash:
        warnings.append('The local car archive is a different game revision.')

    def local_layers():
        validate_livery_inspection_artifact(package)
        if package.suffix.casefold() == '.kfpspreview':
            source = Path(str(payload.get('source_path') or '')).resolve()
            expected, _ = _preview_target(paths, source, game)
            if expected.resolve() != package:
                raise ValueError('The local livery changed. Scan saves and reopen it before rendering High quality.')
            decoded = unwrap_forza_container(source)
            if not inspect_clivery_privacy(decoded)['source_owned']:
                raise ValueError('This preview does not grant access to another player\'s source layers.')
            return _decode_livery_contract(decoded)[0]['layers']
        with zipfile.ZipFile(package) as bundle:
            return json.loads(bundle.read('livery/layers.json'))['layers']

    owned = (manifest.get('sharing') or {}).get('local_unowned_preview') is not True
    can_rerender = owned and (package.suffix.casefold() == '.kfpslivery' or bool(payload.get('source_path')))
    quality = 2 if payload.get('quality_scale') == 2 else 1
    if quality == 2 and psutil.virtual_memory().available < 2 * 1024**3:
        quality = 1
        warnings.append('Standard preview quality used because less than 2 GB of RAM was available.')
    adapter = studio_module(paths.app_root, 'readonly_prepare')
    result = adapter.prepare_readonly(paths.app_root, Path(game), asset, package,
        quality_scale=quality, layer_provider=local_layers if can_rerender else None,
        cancel_event=cancel_event, progress=progress)
    warnings.extend(result.pop('quality_notes', []))
    return {**result, 'package_id': manifest['package_id'], 'package_path': str(package),
            'model_code': asset.model_code, 'revision_warning': '; '.join(warnings),
            'timings_seconds': {'complete': round(time.perf_counter() - started, 4)}}


def clear_studio_cache(app_root):
    try:
        module = studio_module(app_root, 'readonly_cache')
    except (FileNotFoundError, ValueError):
        # A missing optional installation must not prevent clearing legacy caches.
        return {'removed_files': 0, 'removed_bytes': 0}
    with module.installation_cache_lease(app_root, create=True):
        return module.prune_cache(app_root, clear=True)
