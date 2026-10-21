"""Saved-package paint on the same prepared cars/materials used by Studio."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import zipfile
import tempfile
import shutil

from PIL import Image

from .prepare import file_hash, prepare_car, within, workspace_lock
from .readonly_cache import (cache_root, cache_lease, installation_cache_lease, prune_cache, verify_inventory,
                             seal_inventory, file_inventory, admit_artifact, enforce_budget)
from .readonly_preview import FORMAT, make_display_manifest, ordinary_path, write_descriptor
from .file_io import atomic_stream, io_path


def save_png_exclusive(image, path):
    path = ordinary_path(path, Path(path).parent)
    with atomic_stream(path) as stream:
        image.save(stream, format='PNG')


def build_saved_atlas(package, prepared, asset, output, root, *, quality, layer_provider,
                      game_root, cancel_event, progress):
    """Inherited fixed-name writers only run inside a fresh private staging dir."""
    from tools.livery.render_contract import build_local_livery_atlases
    io_path(output.parent).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.a-', dir=io_path(root)) as name:
        staging = Path(name)
        if io_path(output).exists():
            for child in io_path(output).iterdir():
                ordinary_path(child, root)
                if not child.is_file() or child.stat().st_nlink != 1:
                    raise ValueError('Saved atlas cache contains an unexpected file.')
                shutil.copy2(child, staging / child.name)
        if prepared['manifest']['inspection_runtime']['render_contract']['mask_size'] == [2048, 1024]:
            contract = build_local_livery_atlases(package, asset, staging,
                mesh_path=within(root / prepared['files']['mesh'], root),
                mesh_validation=prepared['validation'], quality_scale=quality,
                layer_provider=layer_provider, game_folder=game_root, cancel_event=cancel_event, progress=progress)
        else:
            contract = square_mask_atlas(package, prepared, staging)
        files = file_inventory(staging)
        if sum(row[0] for row in files.values()) > 192 * 1024**2:
            raise ValueError('Saved livery atlas exceeds the reserved cache allowance.')
        if io_path(output).exists():
            if (set(files) != {p.name for p in io_path(output).iterdir()}
                    or any(file_hash(staging / path) != file_hash(output / path) for path in files)):
                raise ValueError('Immutable saved atlas changed. Clear the viewer cache and reopen this livery.')
        else:
            staging.replace(io_path(output))
        return contract


def square_mask_atlas(package, prepared, output):
    """Match Studio sectionToPaint, including non-2048 native mask dimensions."""
    from tools.livery import render_contract as native
    config = prepared['editor_config']
    contract = copy.deepcopy(prepared['manifest']['inspection_runtime']['render_contract'])
    size = contract['mask_size']
    tiles, records = [], []
    with zipfile.ZipFile(package) as bundle:
        names = {name.casefold(): name for name in bundle.namelist()}
        for section in config['sections']:
            name = names.get(f'projection/rendered/{section["section"]}.png'.casefold())
            if not name:
                continue
            bounds = [round(n * size[i % 2]) for i, n in enumerate(section['source_region'])]
            # Studio's affine consumes normalized virtual 2048x1024 atlas pixels.
            a, b, c, d, e, f = section['atlasToLocal']
            sx, sy = 2048 / size[0], 1024 / size[1]
            with bundle.open(name) as stream, Image.open(stream) as image:
                if image.size != (2048, 1024):
                    raise ValueError('Saved section artwork must be 2048 x 1024.')
                warped = image.convert('RGBA').transform(tuple(size), Image.Transform.AFFINE,
                    (a * sx, b * sy, c, d * sx, e * sy, f), Image.Resampling.BILINEAR,
                    fillcolor=(0, 0, 0, 0))
            tile = warped.crop(tuple(bounds))
            tiles.append({'section': section['section'], 'slot_index': section['slot_index'], 'image': tile})
            records.append(copy.deepcopy(section))
    if not tiles:
        raise ValueError('The package and local car have no shared livery sections.')
    atlas, placements = native._pack_paint_tiles(tiles)
    output.mkdir(parents=True, exist_ok=True)
    save_png_exclusive(atlas, output / 'section-paint.png')
    for row in records:
        left, top, width, height = placements[row['section']]
        row['paint_region'] = [left / atlas.width, top / atlas.height,
                               (left + width) / atlas.width, (top + height) / atlas.height]
    contract.update(sections=records, paint_size=list(atlas.size), quality_scale=1,
                    quality_source='package-section-images', files={'paint': 'section-paint.png'},
                    quality_notes=['Native square masks retain the saved original resolution.'])
    return contract


def prepare_readonly(kfps_root, game_root, asset, package, *, quality_scale=1,
                     layer_provider=None, cancel_event=None, progress=None):
    from tools.livery.package import validate_livery_inspection_artifact

    def phase(message):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('Local preview preparation was cancelled.')
        if progress:
            progress(message)

    package = Path(package).absolute()
    manifest = validate_livery_inspection_artifact(package)
    if int(manifest['livery']['target_car_id']) != asset.car_id:
        raise ValueError('The selected car does not match this livery.')
    package_hash = file_hash(package)
    with installation_cache_lease(kfps_root, create=True):
        cache = cache_root(kfps_root)
        key = hashlib.sha256((asset.model_code + ':' + str(asset.archive_mtime_ns)).encode('utf-8')).hexdigest()[:32]
        root = ordinary_path(cache / 'cars' / key, cache)
        io_path(root).mkdir(parents=True, exist_ok=True)
        verify_inventory(root, create=True)
        # Reserve before conversion. The atlas writer's own encoded-size check
        # includes private staging; active/recent handoffs are not evicted.
        reserve = (1024 if not io_path(root / 'prepared.json').exists() else 384) * 1024**2
        admit_artifact(kfps_root, reserve, protected=[root])
        verify_inventory(root)
        with cache_lease(root), workspace_lock(root):
            try:
                phase('Preparing Studio geometry, native materials and UV masks')
                prepared = prepare_car(Path(kfps_root), Path(game_root), asset.archive_name, root)
                if prepared['manifest']['vehicle']['car_id'] != asset.car_id:
                    raise ValueError('Prepared car identity changed.')
                phase('Preparing saved livery paint')
                quality = 2 if quality_scale == 2 and layer_provider else 1
                signature = hashlib.sha256(json.dumps({'source': prepared['signature'],
                    'adapter': file_hash(Path(__file__))}, sort_keys=True).encode()).hexdigest()[:16]
                output = ordinary_path(root / 'saved-atlases' / f'{package_hash[:24]}-{signature}-q{quality}', root)
                mesh = within(root / prepared['files']['mesh'], root)
                contract = build_saved_atlas(package, prepared, asset, output, root, quality=quality,
                    layer_provider=layer_provider, game_root=game_root, cancel_event=cancel_event, progress=progress)
                shared = prepared['manifest']['inspection_runtime']['render_contract']
                contract['uv_contract'] = copy.deepcopy(shared['uv_contract'])
                contract['assembly'] = copy.deepcopy(shared['assembly'])
                contract['world_projection_fallback'] = False
                files = copy.deepcopy(prepared['files'])
                files['paint'] = (output / contract['files']['paint']).relative_to(root).as_posix()
                if contract['files'].get('masks'):
                    files['masks'] = [(output / name).relative_to(root).as_posix() for name in contract['files']['masks']]
                metadata = {key: copy.deepcopy(contract[key]) for key in
                            ('format', 'uv_contract', 'assembly', 'paint_size', 'mask_size', 'filters',
                             'sections', 'quality_scale', 'quality_source')}
                names = [files['mesh'], files['paint'], files['coverage'], *files['masks'], *files['native_textures'].values()]
                descriptor = {'format': FORMAT, 'manifest': make_display_manifest(manifest, prepared, metadata),
                              'files': files, 'file_sha256': {name: file_hash(within(root / name, root)) for name in names}}
                phase('Verifying read-only preview assets')
                if file_hash(package) != package_hash:
                    raise ValueError('Livery package changed during preview preparation.')
                path = write_descriptor(root, descriptor)
                os.utime(io_path(root), None)
            finally:
                seal_inventory(root)
                enforce_budget(kfps_root, root)
        usage = prune_cache(kfps_root, protected=[root], protected_outputs=[output])
        if usage['bytes'] > usage['budget_bytes']:
            raise ValueError('Prepared preview exceeded its cache reservation. Clear the viewer cache before retrying.')
    phase('Starting shared Studio renderer')
    return {'readonly_descriptor': str(path), 'readonly_descriptor_sha256': file_hash(path),
            'mesh_path': str(mesh), 'render_root': str(output),
            'render_contract': contract, 'mesh_cache_hit': bool(prepared['cache']['mesh']),
            'cache_usage': usage, 'quality_notes': contract.get('quality_notes', [])}
