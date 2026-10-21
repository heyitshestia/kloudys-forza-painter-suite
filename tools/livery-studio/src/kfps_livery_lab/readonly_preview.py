"""Validated, display-only assets for the embedded KFPS livery viewer."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import re

from .prepare import atomic_json, file_hash
from .file_io import io_path, logical_path, resolved_path

FORMAT = 'kfps-livery-readonly-preview-v1'
MAX_DESCRIPTOR_BYTES = 16 * 1024**2
MAX_ASSET_BYTES = 512 * 1024**2
MAX_TOTAL_BYTES = 1024**3


def ordinary_path(path, root):
    if '..' in Path(path).parts:
        raise ValueError('Preview asset is outside its registered root.')
    root, path = logical_path(root), logical_path(path)
    if path == root or not path.is_relative_to(root):
        raise ValueError('Preview asset is outside its registered root.')
    for item in (path, *path.parents):
        native = io_path(item)
        if native.is_symlink() or native.is_junction():
            raise ValueError('Redirected preview assets are not supported.')
        if item == root:
            break
    if not resolved_path(path).is_relative_to(resolved_path(root)):
        raise ValueError('Preview asset is outside its registered root.')
    return path


def verified_bytes(path, expected_hash, root, maximum=MAX_ASSET_BYTES):
    path = ordinary_path(path, root)
    with io_path(path).open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise ValueError('Preview asset is not a bounded regular file.')
        body = stream.read(info.st_size + 1)
        after = os.fstat(stream.fileno())
    if (len(body) != info.st_size or after.st_mtime_ns != info.st_mtime_ns
            or hashlib.sha256(body).hexdigest() != expected_hash):
        raise ValueError('Preview asset changed after preparation.')
    return body


def make_display_manifest(package, prepared, contract):
    # Rights are carried over verbatim, never inferred from rendering success.
    result = {key: copy.deepcopy(package[key]) for key in
              ('format', 'format_version', 'package_id', 'livery', 'vehicle', 'sharing') if key in package}
    result['inspection_runtime'] = copy.deepcopy(prepared['manifest']['inspection_runtime'])
    result['inspection_runtime'].update(local_mesh=True, world_projection_fallback=False,
                                        readonly=True, renderer='livery-studio',
                                        render_contract=copy.deepcopy(contract))
    return result


def descriptor_assets(value, root):
    from .car_workspace import prepared_assets
    if not isinstance(value, dict) or value.get('format') != FORMAT:
        raise ValueError('Unsupported read-only preview descriptor.')
    if not isinstance(value.get('manifest'), dict):
        raise ValueError('Missing preview display manifest.')
    assets = prepared_assets(value, Path(root))
    hashes = value.get('file_sha256')
    if not isinstance(hashes, dict) or len(hashes) > 48:
        raise ValueError('Invalid preview asset hashes.')
    total = 0
    for path, _ in assets.values():
        ordinary_path(path, root)
        info = io_path(path).stat()
        total += info.st_size
        if not 0 < info.st_size <= MAX_ASSET_BYTES or info.st_nlink != 1 or total > MAX_TOTAL_BYTES:
            raise ValueError('Preview assets exceed their size budget.')
        name = path.relative_to(root).as_posix()
        if hashes.get(name) != file_hash(path):
            raise ValueError('Preview asset integrity check failed.')
    return assets


def write_descriptor(root, value):
    root = logical_path(root)
    descriptor_assets(value, root)
    if len(json.dumps(value).encode('utf-8')) > MAX_DESCRIPTOR_BYTES:
        raise ValueError('Preview metadata is too large.')
    body = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('utf-8')
    path = ordinary_path(root / ('readonly-' + hashlib.sha256(body).hexdigest() + '.json'), root)
    if io_path(path).exists():
        if read_descriptor(path) != value:
            raise ValueError('An immutable preview descriptor changed.')
    else:
        atomic_json(path, value)
    return path


def read_descriptor(path):
    path = logical_path(path)
    ordinary_path(path, path.parent)
    with io_path(path).open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Preview descriptor is not an ordinary file.')
        body = stream.read(MAX_DESCRIPTOR_BYTES + 1)
    if len(body) > MAX_DESCRIPTOR_BYTES:
        raise ValueError('Preview metadata is too large.')
    from .model import decode_json
    value = decode_json(body)
    match = re.fullmatch(r'readonly-([a-f0-9]{64})\.json', path.name)
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('utf-8')
    if match and hashlib.sha256(canonical).hexdigest() != match[1]:
        raise ValueError('Immutable preview descriptor identity changed.')
    descriptor_assets(value, path.parent)
    return value
