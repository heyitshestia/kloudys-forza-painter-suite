"""Saved-package paint on the same prepared cars/materials used by Studio."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import zipfile
import tempfile

from PIL import Image

from .prepare import file_hash, prepare_car, within, workspace_lock
from .readonly_cache import (cache_root, cache_lease, installation_cache_lease, prune_cache, verify_inventory,
                             seal_inventory, admit_artifact, enforce_budget, prepare_entry, preserve_failed_entry)
from .readonly_preview import FORMAT, make_display_manifest, ordinary_path, write_descriptor
from .file_io import atomic_stream, io_path
from .preview_evidence import build_preview_evidence
from . import saved_atlas_reuse as atlas_reuse
from .garage_build import validate_build, resolve_build, effective_options


def prepare_garage(kfps_root, game_root, asset, garage_build, *, cancel_event=None, progress=None):
    """A fitted body preview, using shared blank paint, without a synthetic livery."""
    return _prepare_body(kfps_root, game_root, asset, validate_build(garage_build),
                         cancel_event=cancel_event, progress=progress)


def prepare_stock(kfps_root, game_root, asset, *, cancel_event=None, progress=None):
    """Use the installed model's stock defaults, without inventing an owned build."""
    return _prepare_body(kfps_root, game_root, asset, None, cancel_event=cancel_event, progress=progress)


def _prepare_body(kfps_root, game_root, asset, build, *, cancel_event=None, progress=None):
    from tools.livery.portable_mesh_converter import _glb_payloads

    def phase(message):
        atlas_reuse.check_cancel(cancel_event)
        if progress:
            progress(message)

    with installation_cache_lease(kfps_root, create=True):
        cache = cache_root(kfps_root)
        key = hashlib.sha256((asset.model_code + ':' + str(asset.archive_mtime_ns)).encode('utf-8')).hexdigest()[:32]
        root = prepare_entry(cache, key, kfps_root=kfps_root, progress=phase)
        admit_artifact(kfps_root, (1024 if not io_path(root / 'prepared.json').exists() else 384) * 1024**2,
                       protected=[root])
        with cache_lease(root), workspace_lock(root), preserve_failed_entry(root):
            try:
                phase('Preparing fitted Garage body' if build else 'Preparing stock body')
                prepared = prepare_car(Path(kfps_root), Path(game_root), asset.archive_name, root,
                                       cancel_event=cancel_event)
                vehicle = prepared['manifest']['vehicle']
                if vehicle['car_id'] != asset.car_id or vehicle['model_code'] != asset.model_code:
                    raise ValueError('Prepared car identity changed.')
                files = copy.deepcopy(prepared['files'])
                mesh = within(root / files['mesh'], root)
                runtime = prepared['manifest']['inspection_runtime']
                if build:
                    document, _ = _glb_payloads(mesh)
                    options = document['scenes'][document.get('scene', 0)]['extras']['kfps_part_options']
                    options = effective_options(options, runtime.get('fidelity', {}).get('part_names'))
                    resolve_build(build, options, runtime.get('fidelity', {}).get('body_compatibility'))
                manifest = copy.deepcopy(prepared['manifest'])
                manifest['package_id'] = f"garage-body-{asset.car_id}-{build['fingerprint'] if build else 'stock'}"
                manifest['livery']['title'] = 'Garage body build' if build else 'Stock body'
                manifest['inspection_runtime'].update(readonly=True, renderer='livery-studio')
                manifest['inspection_runtime'].pop('garage_build', None)
                if build:
                    manifest['inspection_runtime']['garage_build'] = build
                names = [files['mesh'], files['paint'], files['coverage'], *files['masks'], *files['native_textures'].values()]
                descriptor = {'format': FORMAT, 'manifest': manifest, 'files': files,
                              'file_sha256': {name: file_hash(within(root / name, root)) for name in names}}
                phase('Verifying fitted Garage body')
                path = write_descriptor(root, descriptor)
                os.utime(io_path(root), None)
            finally:
                seal_inventory(root)
                enforce_budget(kfps_root, root)
        usage = prune_cache(kfps_root, protected=[root])
        if usage['bytes'] > usage['budget_bytes']:
            raise ValueError('Prepared preview exceeded its cache reservation. Clear the viewer cache before retrying.')
    phase('Starting shared Studio renderer')
    contract = runtime['render_contract']
    return {'readonly_descriptor': str(path), 'readonly_descriptor_sha256': file_hash(path),
            'mesh_path': str(mesh), 'render_root': str(root / 'render'),
            'render_contract': contract, 'mesh_cache_hit': bool(prepared['cache']['mesh']),
            'cache_usage': usage, 'quality_notes': [], 'preview_evidence': build_preview_evidence(prepared, contract)}


def save_png_exclusive(image, path):
    path = ordinary_path(path, Path(path).parent)
    with atomic_stream(path) as stream:
        image.save(stream, format='PNG')


def build_saved_atlas(package, prepared, asset, output, root, *, quality, layer_provider,
                      game_root, cancel_event, progress):
    """Verify immutable hits in place; fixed-name writers only see fresh staging."""
    from tools.livery import render_contract as native
    atlas_reuse.check_cancel(cancel_event)
    output = ordinary_path(output, root)
    shared = prepared['manifest']['inspection_runtime']['render_contract']
    quality = quality if quality in (2, 4) and layer_provider is not None else 1
    layers, reusable = None, True
    if quality > 1:
        # The provider also verifies private-source identity and ownership. A disk
        # hit must not bypass it. External raster artwork is not bound by the ZIP.
        layers = list(layer_provider())
        atlas_reuse.check_cancel(cancel_event)
        reusable = not any(layer.get('is_raster_logo') for layer in layers)
        layer_provider = lambda: layers
    package_stamp = atlas_reuse.fingerprint(package, cancel_event=cancel_event, maximum=1024**3)
    mesh = within(root / prepared['files']['mesh'], root)
    mesh_stat = io_path(mesh).stat()
    inputs = {'package': package_stamp, 'prepared': prepared['signature'],
              'contract': atlas_reuse.stable_contract(shared), 'sections': prepared['editor_config']['sections'],
              'validation': prepared['validation'], 'quality': quality, 'layers': layers,
              'asset': [asset.model_code, asset.archive_size, asset.archive_mtime_ns],
              'mesh': [mesh_stat.st_size, mesh_stat.st_mtime_ns],
              'native': file_hash(Path(native.__file__))}
    signature = hashlib.sha256(atlas_reuse.canonical(inputs)).hexdigest()
    cached = atlas_reuse.read_receipt(output, root, signature, cancel_event=cancel_event)
    if cached is not None and reusable:
        atlas_reuse.check_cancel(cancel_event)
        return {**cached['contract'], 'root': str(output), 'cache_hit': True}
    io_path(output.parent).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.a-', dir=io_path(root)) as name:
        staging = Path(name)
        if shared['mask_size'] == [2048, 1024]:
            contract = native.build_local_livery_atlases(package, asset, staging,
                mesh_path=mesh,
                mesh_validation=prepared['validation'], quality_scale=quality,
                layer_provider=layer_provider, game_folder=game_root, cancel_event=cancel_event, progress=progress)
        else:
            contract = square_mask_atlas(package, prepared, staging, quality_scale=quality,
                layer_provider=layer_provider, game_folder=game_root, cancel_event=cancel_event, progress=progress)
        atlas_reuse.check_cancel(cancel_event)
        if atlas_reuse.fingerprint(package, cancel_event=cancel_event, maximum=1024**3) != package_stamp:
            raise ValueError('Livery package changed during preview preparation.')
        receipt = atlas_reuse.write_receipt(staging, root, signature, contract, cancel_event=cancel_event)
        if cached is not None:
            if receipt != cached:
                raise ValueError(atlas_reuse.IMMUTABLE_ERROR)
        else:
            atlas_reuse.check_cancel(cancel_event)
            staging.replace(io_path(output))
        return {**contract, 'root': str(output), 'cache_hit': False}


def square_mask_atlas(package, prepared, output, *, quality_scale=1, layer_provider=None,
                      game_folder=None, cancel_event=None, progress=None):
    """Match Studio sectionToPaint, including non-2048 native mask dimensions."""
    from tools.livery import render_contract as native
    config = prepared['editor_config']
    contract = copy.deepcopy(prepared['manifest']['inspection_runtime']['render_contract'])
    size = contract['mask_size']
    tiles, records = [], []
    scale = quality_scale if quality_scale in (2, 4) and layer_provider is not None else 1
    section_layers, notes = {}, []
    if scale > 1:
        for layer in layer_provider():
            section_layers.setdefault(str(layer.get('source_section') or ''), []).append(layer)
    with zipfile.ZipFile(package) as bundle:
        names = {name.casefold(): name for name in bundle.namelist()}
        for section in config['sections']:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('Livery texture preparation was cancelled.')
            name = names.get(f'projection/rendered/{section["section"]}.png'.casefold())
            if not name:
                continue
            bounds = [round(n * size[i % 2]) for i, n in enumerate(section['source_region'])]
            # Studio's affine consumes normalized virtual 2048x1024 atlas pixels.
            a, b, c, d, e, f = section['atlasToLocal']
            sx, sy = 2048 / size[0], 1024 / size[1]
            affine = (a * sx, b * sy, c, d * sx, e * sy, f)
            tile = None
            if progress:
                progress(f'Preparing {section["section"].lower()} livery texture')
            if scale > 1:
                tile = native._vector_paint_affine(section_layers.get(section['section'], []),
                    section['section'], bounds, affine, scale, game_folder, cancel_event)
                if tile is None:
                    notes.append(f'{section["section"]}: retained original resolution because referenced artwork is unavailable locally')
            if tile is None:
                with bundle.open(name) as stream, Image.open(stream) as image:
                    if image.size != (2048, 1024):
                        raise ValueError('Saved section artwork must be 2048 x 1024.')
                    warped = image.convert('RGBA').transform(tuple(size), Image.Transform.AFFINE,
                        affine, Image.Resampling.BILINEAR, fillcolor=(0, 0, 0, 0))
                tile = warped.crop(tuple(bounds))
            tiles.append({'section': section['section'], 'slot_index': section['slot_index'], 'image': tile})
            records.append(copy.deepcopy(section))
    if not tiles:
        raise ValueError('The package and local car have no shared livery sections.')
    width = max(native.PAINT_ATLAS_WIDTH * scale,
                max(item['image'].width + native.PAINT_PADDING * 2 for item in tiles))
    atlas, placements = native._pack_paint_tiles(tiles, width=width, quality_scale=scale)
    output.mkdir(parents=True, exist_ok=True)
    save_png_exclusive(atlas, output / 'section-paint.png')
    for row in records:
        left, top, width, height = placements[row['section']]
        row['paint_region'] = [left / atlas.width, top / atlas.height,
                               (left + width) / atlas.width, (top + height) / atlas.height]
    contract.update(sections=records, paint_size=list(atlas.size), quality_scale=scale,
                    quality_source=('mixed-original-and-vector' if notes else
                                    'native-vector-crops' if scale > 1 else 'package-section-images'),
                    files={'paint': 'section-paint.png'}, quality_notes=notes)
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
        root = prepare_entry(cache, key, kfps_root=kfps_root, progress=phase)
        # Reserve before conversion. The atlas writer's own encoded-size check
        # includes private staging; active/recent handoffs are not evicted.
        reserve = (1024 if not io_path(root / 'prepared.json').exists() else 384) * 1024**2
        admit_artifact(kfps_root, reserve, protected=[root])
        verify_inventory(root)
        with cache_lease(root), workspace_lock(root), preserve_failed_entry(root):
            try:
                phase('Preparing Studio geometry, native materials and UV masks')
                prepared = prepare_car(Path(kfps_root), Path(game_root), asset.archive_name, root,
                                       cancel_event=cancel_event)
                if prepared['manifest']['vehicle']['car_id'] != asset.car_id:
                    raise ValueError('Prepared car identity changed.')
                phase('Preparing saved livery paint')
                quality = quality_scale if quality_scale in (2, 4) and layer_provider is not None else 1
                signature = hashlib.sha256(json.dumps({'source': prepared['signature'],
                    'adapter': file_hash(Path(__file__)), 'atlas_reuse': file_hash(Path(atlas_reuse.__file__))},
                    sort_keys=True).encode()).hexdigest()[:16]
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
            'cache_usage': usage, 'quality_notes': contract.get('quality_notes', []),
            'preview_evidence': build_preview_evidence(prepared, contract)}
