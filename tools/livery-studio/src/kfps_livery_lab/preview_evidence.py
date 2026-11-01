"""Bounded, path-free evidence for the read-only preview; no file or UI access.

build_preview_evidence(prepared, render_contract) returns quality_scale (int or
None), paint_size/mask_size ([width, height] or None), mesh_cache_hit (bool or
None), geometry/materials ([{label, value, tone}]), warnings ([str]), sections
([{name, slot_index}]), and limitation_count (int or None). Row values are text;
tones are neutral or warning, never a claim of game equivalence. Missing or
malformed counts are omitted, not coerced. Final render facts never fall back to
the preparation contract. limitation_count counts the supplied limitation records
only when the entire bounded list is valid; it is not a count of all preview gaps.

Only known vocabulary and validated integers leave this boundary. Free-form
diagnostics, limitations, quality notes, resource identities and paths never do.
Large lists are sampled explicitly, with unknown totals rather than invented ones.
"""
from __future__ import annotations

from collections import Counter

MAX_ROWS = 24
MAX_WARNINGS = 16
MAX_SECTIONS = 16
MAX_OMISSION_REASONS = 6
MAX_TEXT = 180
MAX_SCAN_ITEMS = 4096
MAX_INTEGER = 2**31 - 1

SECTION_NAMES = frozenset(('Front', 'Back', 'Top', 'Left', 'Right', 'Spoiler',
                           'FrontWindshield', 'BackWindshield', 'TopWindow',
                           'LeftWindow', 'RightWindow'))

# These codes come from our material_preview producer, not converter log text.
OMISSION_REASONS = {
    'no-native-material': 'no native material',
    'unsupported-material-template': 'unsupported template',
    'unsupported-alpha-or-decal-state': 'unsupported alpha or decal state',
    'unresolved-instance-overrides': 'unresolved instance overrides',
    'invalid-native-material': 'invalid material data',
    'invalid-parameter': 'invalid material parameter',
    'unsupported-or-invalid-parameter': 'unsupported or invalid parameter',
    'unsupported-damage-switch': 'unsupported damage switch',
    'invalid-scalar': 'invalid scalar parameter',
    'invalid-native-texture-path': 'invalid texture reference',
    'ambiguous-parameter': 'ambiguous material parameter',
    'missing-basecolor-texture': 'missing base-color texture',
    'invalid-material-tiling': 'invalid material tiling',
    'invalid-source-uv-transform': 'invalid source UV transform',
    'unverified-uv-pipeline': 'unverified UV pipeline',
    'missing-or-invalid-native-uv0': 'missing or invalid native UV0',
    'unverified-material-declaration': 'unverified declaration',
    'asset-limit-reached': 'texture asset limit reached',
    'texture-unavailable-unsafe-or-unsupported': 'texture unavailable, unsafe or unsupported',
}

_PREVIEW_WARNING = 'Local inspection preview only; game equivalence is not established.'
_LIMITATIONS = {
    'UV fingerprints verify importer-to-GLB copy integrity, not the game parser or shader.':
        'UV fingerprints verify importer-to-GLB copy integrity, not the game parser or shader.',
    'Manifest references include alternate LOD files; partial entries are not automatically missing visible parts.':
        'Manifest references include alternate LOD files; partial entries are not automatically missing visible parts.',
    'A declared empty option is distinct from a failed or unresolved model.':
        'A declared empty option is distinct from a failed or unresolved model.',
    'No in-game geometry, fitment, texture, mask or projection equivalence has been established.':
        _PREVIEW_WARNING,
    **{f'Optional wheel/body reference is unavailable ({reason}).':
       'Optional wheel/body reference is unavailable.'
       for reason in ('missing-reference', 'unreadable-reference', 'invalid-reference')},
}

_GEOMETRY_COUNTS = (
    ('mesh_primitives', 'Mesh primitives', False),
    ('declared_parts', 'Manifest components', False),
    ('converted_options', 'Converted upgrade options', False),
    ('missing_local_model_references', 'Missing local model references', True),
    ('external_model_references', 'External model references', True),
    ('unrepresented_options', 'Unrepresented upgrade options', True),
    ('blocked_options', 'Blocked upgrade options', True),
    ('model_membership_mismatches', 'Model membership mismatches', True),
    ('blocked_model_membership_omissions', 'Blocked model membership omissions', True),
    ('direct_uv3_primitives', 'Livery primitives with UV3', False),
    ('missing_uv3_primitives', 'Livery primitives missing UV3', True),
    ('unsupported_livery_surface_primitives', 'Unsupported livery surface primitives', True),
    ('verified_uv_channels', 'UV channels with verified copy integrity', False),
    ('uv_integrity_errors', 'UV copy-integrity errors', True),
    ('uv_channel_omissions', 'Omitted UV channels', True),
)
_CONVERSION_COUNTS = (
    ('mesh_count', 'Converted meshes', False),
    ('unresolved_instance_count', 'Unresolved required model instances', True),
    ('skipped_optional_instance_count', 'Skipped optional model instances', True),
)
_MATERIAL_COUNTS = (
    ('total_meshes', 'Meshes checked for native textures', False),
    ('staged_meshes', 'Meshes with staged native textures', False),
    ('omitted_meshes', 'Meshes with omitted native textures', True),
    ('ignored_meshes', 'Meshes outside the native texture profile', True),
    ('distinct_assets', 'Distinct staged native textures', False),
)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _integer(value, minimum=0):
    return value if type(value) is int and minimum <= value <= MAX_INTEGER else None


def _known(value, vocabulary):
    return vocabulary.get(value) if type(value) is str and len(value) <= MAX_TEXT else None


def _size(value):
    if isinstance(value, list) and len(value) == 2 and all(_integer(n, 1) is not None for n in value):
        return list(value)
    return None


def _row(label, value, warning=False):
    return {'label': label[:MAX_TEXT], 'value': str(value)[:MAX_TEXT],
            'tone': 'warning' if warning else 'neutral'}


def _counts(source, fields):
    return [_row(label, source[key], caution and source[key] > 0)
            for key, label, caution in fields if _integer(source.get(key)) is not None]


def build_preview_evidence(prepared, render_contract):
    """Summarize existing data only; do not read assets or mutate either input."""
    prepared, contract = _mapping(prepared), _mapping(render_contract)
    runtime = _mapping(_mapping(prepared.get('manifest')).get('inspection_runtime'))
    fidelity = _mapping(runtime.get('fidelity'))
    summary = _mapping(fidelity.get('summary'))
    native = _mapping(runtime.get('native_textures'))
    material_summary = _mapping(native.get('summary'))
    report = _mapping(_mapping(_mapping(prepared.get('conversion')).get('process')).get('report'))
    warnings = [_PREVIEW_WARNING]

    def warn(text):
        if text not in warnings:
            warnings.append(text[:MAX_TEXT])

    geometry = _counts(summary, _GEOMETRY_COUNTS)
    if not geometry:
        warn('Geometry coverage evidence is unavailable.')
    geometry = _counts(report, _CONVERSION_COUNTS) + geometry
    if any(row['tone'] == 'warning' for row in geometry):
        warn('Preparation reports geometry or UV gaps; counts do not establish missing visible parts.')
    if _integer(summary.get('verified_uv_channels')) is not None:
        warn('UV fingerprints verify importer-to-GLB copy integrity, not the game parser or shader.')

    materials = []
    if _known(fidelity.get('materials'), {'neutral-inspection': True}):
        materials.append(_row('Material baseline', 'Neutral inspection'))
    fitment = _mapping(_mapping(contract.get('assembly')).get('wheel_fitment'))
    wheels = _known(fitment.get('status'), {
        'unavailable': 'No qualified wheel stand-ins',
        'reference-sized': 'Reference-sized inspection stand-ins',
    })
    if wheels is None and _known(fidelity.get('wheels'), {'inspection-stand-ins': True}):
        wheels = 'Inspection stand-in mode; fitment unverified'
    if wheels is not None:
        materials.append(_row('Wheel preview', wheels, True))
    staged = _counts(material_summary, _MATERIAL_COUNTS)
    if not staged:
        warn('Native texture staging evidence is unavailable.')
    materials.extend(staged)

    omissions = native.get('omissions')
    if isinstance(omissions, list):
        reasons = Counter(_known(_mapping(item).get('reason'), OMISSION_REASONS)
                          or 'unrecognized or invalid reason'
                          for item in omissions[:MAX_SCAN_ITEMS])
        ranked = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
        materials.extend(_row('Omitted: ' + reason, count, True)
                         for reason, count in ranked[:MAX_OMISSION_REASONS])
        remainder = sum(count for _, count in ranked[MAX_OMISSION_REASONS:])
        if remainder:
            materials.append(_row('Omitted: other reasons', remainder, True))
        if len(omissions) > MAX_SCAN_ITEMS:
            warn(f'Material omission reasons cover only the first {MAX_SCAN_ITEMS} records.')
    elif 'omissions' in native:
        warn('Material omission reason records are unavailable.')

    limitation_count = None
    limitations = fidelity.get('limitations')
    if isinstance(limitations, list) and len(limitations) <= MAX_SCAN_ITEMS:
        valid = True
        for item in limitations:
            if type(item) is not str or not item.strip():
                valid = False
                continue
            known = _known(item, _LIMITATIONS)
            warn(known or 'Additional preparation limitations are recorded; free-form details are not exposed.')
        if valid:
            limitation_count = len(limitations)
    if limitation_count is None:
        warn('Preparation limitation count is unavailable or exceeds the summary bounds.')

    quality = _integer(contract.get('quality_scale'), 1)
    quality = quality if quality in (1, 2, 4) else None
    if _known(contract.get('quality_source'), {'mixed-original-and-vector': True}):
        warn('Some livery sections retained original resolution because referenced artwork was unavailable locally.')
    elif isinstance(contract.get('quality_notes'), list) and contract['quality_notes']:
        warn('Render preparation reported additional quality notes; free-form details are not exposed.')

    sections, seen = [], set()
    source_sections = contract.get('sections')
    if isinstance(source_sections, list):
        if len(source_sections) > MAX_SCAN_ITEMS:
            warn('Section evidence is truncated to the summary bounds.')
        for item in source_sections[:MAX_SCAN_ITEMS]:
            item = _mapping(item)
            name, slot = item.get('section'), _integer(item.get('slot_index'))
            if type(name) is not str or len(name) > MAX_TEXT or name not in SECTION_NAMES or slot is None:
                warn('Some section evidence is unavailable or unrecognized.')
                continue
            identity = (name, slot)
            if identity in seen:
                continue
            if len(sections) >= MAX_SECTIONS:
                warn('Section evidence is truncated to the summary bounds.')
                break
            sections.append({'name': name, 'slot_index': slot})
            seen.add(identity)
    else:
        warn('Final rendered section evidence is unavailable.')

    cache_hit = _mapping(prepared.get('cache')).get('mesh')
    if len(warnings) > MAX_WARNINGS:
        warnings = warnings[:MAX_WARNINGS - 1] + ['Additional evidence warnings are omitted from this summary.']
    return {'quality_scale': quality, 'paint_size': _size(contract.get('paint_size')),
            'mask_size': _size(contract.get('mask_size')),
            'mesh_cache_hit': cache_hit if type(cache_hit) is bool else None,
            'geometry': geometry[:MAX_ROWS], 'materials': materials[:MAX_ROWS],
            'warnings': warnings, 'sections': sections, 'limitation_count': limitation_count}
