"""Read-only component and UV evidence; never a claim of game-renderer parity."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
UV_CHANNEL = re.compile(r'(?:0|[1-9][0-9]{0,9})\Z')


def _uv_fingerprints(extras: dict, key: str) -> dict[str, str]:
    value = extras.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 64:
        raise ValueError('Invalid recorded UV channel evidence.')
    result = {}
    for channel, digest in value.items():
        if (not isinstance(channel, str) or not UV_CHANNEL.fullmatch(channel)
                or int(channel) > 0xffffffff or not isinstance(digest, str)
                or not re.fullmatch(r'[0-9a-fA-F]{64}', digest)):
            raise ValueError('Invalid recorded UV channel evidence.')
        result[channel] = digest.lower()
    return result


def _normal(path: str) -> str:
    return str(path).replace('\\', '/').casefold()


def inventory_manifest(data: bytes, archive_names: list[str], model_code: str) -> dict:
    if len(data) > MAX_MANIFEST_BYTES or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported car manifest size or entity declaration.')
    available = {}
    for name in archive_names:
        normalized = _normal(name)
        if normalized in available:
            raise ValueError('Ambiguous case-insensitive car archive path.')
        available[normalized] = name.replace('\\', '/')
    root = ET.fromstring(data)
    prefix = f'game:/media/cars/{model_code.casefold()}/'
    parts = []
    for element in root.iter():
        if element.tag not in ('NonUpgradeablePart', 'UpgradeablePart'):
            continue
        part_id = element.get('PartId')
        try:
            part_id = int(part_id) if part_id is not None else None
        except ValueError as exc:
            raise ValueError('Invalid manifest part identity.') from exc
        models = []
        for model in element.iter('Model'):
            source = (model.get('path') or '').replace('\\', '/')
            normalized = _normal(source)
            local = normalized[len(prefix):] if normalized.startswith(prefix) else None
            resolved = available.get(local) if local is not None else None
            models.append({'path': source, 'entry': resolved, 'lods': model.get('LODs'),
                           'resolution': 'local' if resolved else 'missing' if local is not None else 'external',
                           'slod_variant': '__slod' in normalized})
        parts.append({'part_type': element.get('PartEnum') or '', 'id': part_id,
                      'upgradeable': element.tag == 'UpgradeablePart', 'models': models})
    if len(parts) > 4096 or sum(len(p['models']) for p in parts) > 32768:
        raise ValueError('Car manifest exceeds the supported inventory size.')
    return {'model_code': model_code, 'manifest_sha256': hashlib.sha256(data).hexdigest(), 'parts': parts}


def read_inventory(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        if len(bundle.infolist()) > 65536:
            raise ValueError('Car archive exceeds the inventory entry limit.')
        entries = [info.filename for info in bundle.infolist() if not info.is_dir()]
        matches = [name for name in entries if _normal(name) == 'manifest.xml']
        if len(matches) != 1:
            raise ValueError('Car archive must have exactly one Manifest.xml.')
        info = bundle.getinfo(matches[0])
        if info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError('Car manifest is too large.')
        with bundle.open(info) as source:
            data = source.read(MAX_MANIFEST_BYTES + 1)
    return inventory_manifest(data, entries, archive.stem)


def _uv_bytes(document: dict, binary: bytes, index: int, expected_count: int) -> bytes:
    try:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError('Invalid UV accessor index.')
        accessor = document['accessors'][index]
        view_id = accessor['bufferView']
        if isinstance(view_id, bool) or not isinstance(view_id, int) or view_id < 0:
            raise ValueError('Invalid UV view index.')
        view = document['bufferViews'][view_id]
        count = accessor['count']
        offset = accessor.get('byteOffset', 0)
        start = view.get('byteOffset', 0)
        length = view['byteLength']
        stride = view.get('byteStride', 8)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (count, offset, start, length, stride)):
            raise ValueError('Invalid UV accessor dimensions.')
        if (accessor['componentType'] != 5126 or accessor['type'] != 'VEC2'
                or accessor.get('normalized') or accessor.get('sparse')
                or view.get('buffer', 0) != 0 or not 0 < count <= 4_000_000
                or count != expected_count or min(offset, start) < 0
                or offset % 4 or start % 4
                or stride < 8 or stride % 4 or offset + (count - 1) * stride + 8 > length
                or start + length > len(binary)):
            raise ValueError('Invalid UV accessor layout or vertex count.')
        begin = start + offset
        data = binary[begin:begin + count * 8] if stride == 8 else b''.join(
            binary[begin + row * stride:begin + row * stride + 8] for row in range(count))
        if any(not math.isfinite(value[0]) for value in struct.iter_unpack('<f', data)):
            raise ValueError('UV accessor contains a non-finite value.')
        return data
    except (KeyError, IndexError, TypeError, struct.error) as exc:
        raise ValueError('Malformed converted UV data.') from exc


def audit_document(inventory: dict, document: dict, binary: bytes) -> dict:
    scene_index = document.get('scene', 0)
    scene_extras = document.get('scenes', [{}])[scene_index].get('extras', {})
    options = scene_extras.get('kfps_part_options', [])
    option_keys = {(str(option.get('part_type', '')).casefold(), option.get('id')) for option in options}
    blocked_keys = {(str(option.get('part_type', '')).casefold(), option.get('id'))
                    for option in options if option.get('supported') is False or option.get('available') is False}
    converted = set()
    memberships = {}
    rows = []
    direct = missing = verified = errors = channels = omissions = unsupported = 0
    for mesh_index, mesh in enumerate(document.get('meshes', [])):
        extras = mesh.get('extras') or {}
        entry = str(extras.get('kfps_source_entry') or '')
        converted.add(_normal(entry))
        family = str(extras.get('kfps_part_type') or '').casefold()
        ids = extras.get('kfps_part_option_ids', [])
        if not isinstance(ids, list) or any(type(value) is not int for value in ids):
            raise ValueError('Invalid converted component membership.')
        if mesh.get('primitives'):
            memberships.setdefault((_normal(entry), family), []).append(frozenset(ids))
        fingerprints = _uv_fingerprints(extras, 'kfps_uv_sha256')
        imported = _uv_fingerprints(extras, 'kfps_imported_uv_sha256')
        # Raw and transformed hashes differ; compare channel presence separately.
        expected_channels = set(imported) | set(fingerprints)
        for primitive_index, primitive in enumerate(mesh.get('primitives', [])):
            attributes = primitive.get('attributes', {})
            role = str(extras.get('kfps_role', 'unknown'))
            unpaintable = extras.get('kfps_unpaintable_surface_role')
            if unpaintable is not None and (unpaintable not in ('paint', 'glass') or role != 'trim'):
                raise ValueError('Invalid unmapped visual surface declaration.')
            unsupported += unpaintable is not None
            uv = {}
            for name, index in attributes.items():
                if not name.startswith('TEXCOORD_'):
                    continue
                channel = name[len('TEXCOORD_'):]
                if not UV_CHANNEL.fullmatch(channel) or int(channel) > 0xffffffff:
                    raise ValueError('Invalid converted UV channel name.')
                count = document['accessors'][attributes['POSITION']]['count']
                digest = hashlib.sha256(_uv_bytes(document, binary, index, count)).hexdigest()
                expected = fingerprints.get(channel)
                integrity = 'unverified' if expected is None else 'verified' if digest == expected else 'mismatch'
                uv[channel] = {'sha256': digest, 'vertices': count, 'copy_integrity': integrity}
                channels += 1
                verified += integrity == 'verified'
                errors += integrity == 'mismatch'
            omitted = sorted(expected_channels - set(uv), key=int)
            omissions += len(omitted)
            errors += len(omitted)
            if role in ('paint', 'glass'):
                direct += '3' in uv
                missing += '3' not in uv
            rows.append({'mesh': mesh_index, 'primitive': primitive_index, 'name': mesh.get('name', ''),
                         'source_entry': entry, 'part_type': extras.get('kfps_part_type', ''),
                         'option_ids': extras.get('kfps_part_option_ids', []), 'role': role, 'uv_channels': uv,
                         'unpaintable_surface_role': unpaintable,
                         'omitted_uv_channels': omitted})
    parts = []
    for part in inventory['parts']:
        models = []
        for model in part['models']:
            key = (_normal(model['entry'] or ''), part['part_type'].casefold())
            members = memberships.get(key, []) if model['entry'] else []
            member = 'unconditional' if any(not ids for ids in members) else (
                'option' if part['upgradeable'] and any(part['id'] in ids for ids in members) else None)
            models.append({**model, 'converted': member is not None, 'membership': member,
                           'entry_present_anywhere': bool(model['entry']) and key[0] in converted})
        represented = not part['upgradeable'] or (part['part_type'].casefold(), part['id']) in option_keys
        blocked = (part['part_type'].casefold(), part['id']) in blocked_keys
        if blocked:
            coverage = 'blocked-unresolved'
        elif not represented:
            coverage = 'not-converted'
        elif not models:
            coverage = 'declared-empty'
        elif all(model['converted'] for model in models):
            coverage = 'all-model-entries-present'
        elif any(model['converted'] for model in models):
            coverage = 'partial-model-entries'
        else:
            coverage = 'no-model-entries'
        parts.append({**part, 'models': models, 'option_represented': represented, 'blocked': blocked, 'coverage': coverage})
    summary = {
        'declared_parts': len(parts), 'declared_upgrade_options': sum(p['upgradeable'] for p in parts),
        'converted_options': len(option_keys - blocked_keys), 'blocked_options': len(blocked_keys),
        'unrepresented_options': sum(not p['option_represented'] for p in parts),
        'referenced_models': sum(len(p['models']) for p in parts),
        'external_model_references': sum(m['resolution'] == 'external' for p in parts for m in p['models']),
        'missing_local_model_references': sum(m['resolution'] == 'missing' for p in parts for m in p['models']),
        'model_membership_mismatches': sum(m['entry_present_anywhere'] and not m['converted'] for p in parts if not p['blocked'] for m in p['models']),
        'blocked_model_membership_omissions': sum(m['entry_present_anywhere'] and not m['converted'] for p in parts if p['blocked'] for m in p['models']),
        'converted_source_entries': len(converted - {''}), 'mesh_primitives': len(rows),
        'direct_uv3_primitives': direct, 'missing_uv3_primitives': missing,
        'uv_channels': channels, 'verified_uv_channels': verified, 'uv_integrity_errors': errors,
        'uv_channel_omissions': omissions,
        'unsupported_livery_surface_primitives': unsupported,
        'all_livery_surfaces_have_uv3': direct > 0 and missing == 0 and unsupported == 0,
    }
    return {'format': 'kfps-livery-component-coverage-v1', 'model_code': inventory['model_code'],
            'manifest_sha256': inventory['manifest_sha256'], 'summary': summary,
            'game_equivalence_verified': False, 'source_decoder_verified': False,
            'materials': 'neutral-inspection', 'wheels': 'inspection-stand-ins',
            'limitations': [
                'UV fingerprints verify importer-to-GLB copy integrity, not the game parser or shader.',
                'Manifest references include alternate LOD files; partial entries are not automatically missing visible parts.',
                'A declared empty option is distinct from a failed or unresolved model.',
                'No in-game geometry, fitment, texture, mask or projection equivalence has been established.',
            ], 'conversion': scene_extras.get('kfps_conversion_coverage', {}), 'parts': parts, 'meshes': rows}


def audit_components(archive: Path, glb: Path) -> dict:
    from tools.livery.portable_mesh_converter import _glb_payloads, validate_local_chassis_glb
    validate_local_chassis_glb(glb)
    document, binary = _glb_payloads(glb)
    return audit_document(read_inventory(archive), document, binary)
