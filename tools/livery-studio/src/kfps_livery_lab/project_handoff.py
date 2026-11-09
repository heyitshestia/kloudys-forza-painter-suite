"""Full Studio projects, separate from the narrow package-section contract."""
import json
from pathlib import PurePosixPath, PureWindowsPath

from .model import validate_shapes
from .recovery import MAX_PROJECT_BYTES, _project, _vehicle

SHAPE_KEYS = frozenset(('type', 'type_word', 'type_word_hex', 'data', 'color', 'mask', 'score', 'name', 'id', 'shape_name',
    'source_format', 'source_shape_index', 'source_offset', 'source_marker', 'source_game',
    'source_raw_type', 'source_raw_type_word', 'source_raw_type_word_hex', 'source_section',
    'resource_family', 'resource_index', 'resource_normalized_for_game', 'display_name',
    'editor_group_path', 'editor_group_id', 'editor_group_name', 'editor_shape_id',
    'editor_id', 'editor_name', 'editor_hidden', 'editor_locked', 'editor_pixel_art_generated',
    'is_raster_logo', 'raster_id', 'shape_word_ambiguous_resources'))


def _no_paths(value):
    if isinstance(value, str):
        if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute() or value.lower().startswith('file:'):
            raise ValueError('Filesystem paths are not part of a Studio project handoff.')
    elif isinstance(value, dict):
        for key, item in value.items():
            _no_paths(key)
            _no_paths(item)
    elif isinstance(value, list):
        for item in value:
            _no_paths(item)


def validate_project(value, resolve_resource=None):
    vehicle = _vehicle(value.get('vehicle') if isinstance(value, dict) else None)
    if set(value['vehicle']) != {'car_id', 'model_code'}:
        raise ValueError('The project must contain only its exact car identity.')
    body = _project(value, vehicle)
    if len(body) > MAX_PROJECT_BYTES - 1024:
        raise ValueError('Studio project exceeds the 32 MiB transfer limit.')
    # Recovery owns the project schema. Reject unknown source metadata instead of
    # silently dropping it or exposing caller-supplied filesystem locations.
    _no_paths(value)
    for source in value['vinyls']:
        for shape in source['shapes']:
            if set(shape) - SHAPE_KEYS:
                raise ValueError('The project contains unsupported shape metadata.')
            groups = shape.get('editor_group_path', [])
            if (not isinstance(groups, list) or len(groups) > 64
                    or any(not isinstance(group, dict) or set(group) != {'id', 'name'}
                           or any(not isinstance(text, str) or not text.strip() or len(text) > 160
                                  or any(ord(c) < 32 for c in text) for text in group.values()) for group in groups)):
                raise ValueError('The project contains invalid source groups.')
            if groups and (shape.get('editor_group_id') != groups[-1]['id'] or shape.get('editor_group_name') != groups[-1]['name']):
                raise ValueError('The project source groups are inconsistent.')
            resources = shape.get('shape_word_ambiguous_resources', [])
            if (not isinstance(resources, list) or len(resources) > 8
                    or any(not isinstance(row, dict) or set(row) != {'family', 'index', 'name'}
                           or type(row['index']) is not int or not isinstance(row['family'], str)
                           or not isinstance(row['name'], str) for row in resources)):
                raise ValueError('The project contains invalid source resource metadata.')
            for key, item in shape.items():
                if key in {'data', 'color', 'editor_group_path', 'shape_word_ambiguous_resources'}:
                    continue
                if not (item is None or type(item) in (int, float, bool) or isinstance(item, str) and len(item) <= 512):
                    raise ValueError('The project contains invalid shape metadata.')
        if resolve_resource is not None:
            validate_shapes({'shapes': source['shapes']}, resolve_resource)
    return json.loads(body)


def request_for_stock(identity):
    if not isinstance(identity, dict) or set(identity) != {'car_id', 'model_code'}:
        raise ValueError('The stock car requires an exact identity only.')
    identity = _vehicle(identity)
    return {'name': 'Stock car', 'project': validate_project({
        'format': 'kfps-livery-layout-v1', 'vehicle': identity, 'vinyls': [], 'placements': []})}


def validate_prepared_project(value, prepared, assets):
    """Reject incompatible components before committing a different car session."""
    from .garage_build import effective_options
    from tools.livery.portable_mesh_converter import _glb_payloads
    value = validate_project(value)
    config = prepared['editor_config']
    if _vehicle(config['vehicle']) != value['vehicle']:
        raise ValueError('The prepared car does not match the Studio project.')
    sections = {row['section'] for row in config['sections']}
    if any(row['section'] not in sections for row in value['placements']):
        raise ValueError('The project uses an unavailable section. The current car is unchanged.')
    parts = value.get('vehicle_parts', {})
    if not parts:
        return
    document, _ = _glb_payloads(assets['api/local-mesh'][0])
    options = document['scenes'][document.get('scene', 0)]['extras']['kfps_part_options']
    fidelity = prepared['manifest']['inspection_runtime'].get('fidelity', {})
    options = effective_options(options, fidelity.get('part_names'))
    chosen = {}
    for part, ident in parts.items():
        rows = [row for row in options if row.get('part_type') == part]
        matches = [row for row in rows if row.get('id') == ident and row.get('supported') is True]
        if not rows or (ident is not None and len(matches) != 1):
            raise ValueError('The project has an unavailable component. The current car is unchanged.')
        if matches:
            chosen[part] = matches[0]
    parents = {}
    for row in fidelity.get('body_compatibility', {}).get('parent_map', []):
        parent, body = row.get('parent_upgrade_id'), row.get('body_option_id')
        if parent in parents and parents[parent] != body:
            raise ValueError('The project body compatibility is ambiguous. The current car is unchanged.')
        parents[parent] = body
    body = parts.get('CarBody')
    if 'CarBody' not in parts:
        defaults = [row for row in options if row.get('part_type') == 'CarBody' and row.get('baseline') is True and row.get('supported') is True]
        if not defaults:
            defaults = [row for row in options if row.get('part_type') == 'CarBody' and row.get('stock') is True and row.get('supported') is True]
        body = defaults[0]['id'] if len(defaults) == 1 else None
    for part, row in chosen.items():
        required = parents.get(row.get('car_body_id'))
        if part != 'CarBody' and required is not None and required != body:
            raise ValueError('The project component does not fit its body. The current car is unchanged.')
