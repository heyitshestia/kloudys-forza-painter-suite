"""Bounded immutable receipts for saved Preview atlases; no resident image cache."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .file_io import atomic_stream, io_path
from .readonly_preview import ordinary_path

MAX_BYTES = 192 * 1024**2
MAX_RECEIPT_BYTES = 1024**2
MAX_FILES = 8
PREFIX = 'saved-atlas-'
FORMAT = 'kfps-saved-atlas-reuse-v1'
IMMUTABLE_ERROR = 'Immutable saved atlas changed. Clear the viewer cache and reopen this livery.'


def check_cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError('Livery texture preparation was cancelled.')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def fingerprint(path, *, cancel_event=None, maximum=MAX_BYTES):
    """Hash bounded regular files in chunks, detecting replacement or modification."""
    check_cancel(cancel_event)
    with io_path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= maximum):
            raise ValueError('Saved atlas input is not a bounded regular file.')
        digest, count = hashlib.sha256(), 0
        while chunk := stream.read(1024**2):
            check_cancel(cancel_event)
            count += len(chunk)
            if count > before.st_size:
                raise ValueError(IMMUTABLE_ERROR)
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    current = io_path(path).stat()
    def stamp(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink
    # Windows path stat and handle fstat can expose different ctime semantics.
    if (count != before.st_size or stamp(before) != stamp(after) or stamp(after) != stamp(current)
            or before.st_ctime_ns != after.st_ctime_ns):
        raise ValueError(IMMUTABLE_ERROR)
    check_cancel(cancel_event)
    return {'size': count, 'sha256': digest.hexdigest()}


def stable_contract(contract):
    return {key: value for key, value in contract.items() if key not in ('root', 'cache_hit')}


def _names(folder, root):
    names = set()
    for path in io_path(folder).iterdir():
        info = path.stat()
        if (path.is_symlink() or path.is_junction() or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1 or len(names) >= MAX_FILES):
            raise ValueError(IMMUTABLE_ERROR)
        names.add(path.name)
    return names


def _asset_names(contract):
    files = contract['files']
    names = [files['paint'], *files.get('masks', [])]
    if (not 1 <= len(names) <= 4 or len(set(names)) != len(names)
            or any(not isinstance(name, str) or not name or Path(name).name != name
                   or '/' in name or '\\' in name for name in names)):
        raise ValueError(IMMUTABLE_ERROR)
    return set(names)


def read_receipt(output, root, signature, *, cancel_event=None):
    """Caller already holds the car lease and verified the ownership inventory."""
    check_cancel(cancel_event)
    output = ordinary_path(output, root)
    if not io_path(output).exists():
        return None
    try:
        names = _names(output, root)
        receipts = [name for name in names if name.startswith(PREFIX) and name.endswith('.json')]
        if len(receipts) != 1:
            raise ValueError(IMMUTABLE_ERROR)
        path = ordinary_path(output / receipts[0], root)
        info = fingerprint(path, cancel_event=cancel_event, maximum=MAX_RECEIPT_BYTES)
        if path.name != PREFIX + info['sha256'] + '.json':
            raise ValueError(IMMUTABLE_ERROR)
        with io_path(path).open('rb') as stream:
            body = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(body) != info['size'] or hashlib.sha256(body).hexdigest() != info['sha256']:
            raise ValueError(IMMUTABLE_ERROR)
        receipt = json.loads(body)
        if receipt['format'] != FORMAT or receipt['signature'] != signature:
            raise ValueError(IMMUTABLE_ERROR)
        files, contract = receipt['files'], receipt['contract']
        assets = _asset_names(contract)
        if (set(files) not in (assets, assets | {'index.json'})
                or names != set(files) | {path.name}
                or sum(row['size'] for row in files.values()) + len(body) > MAX_BYTES):
            raise ValueError(IMMUTABLE_ERROR)
        for name, row in files.items():
            if (type(row['size']) is not int or row['size'] <= 0
                    or fingerprint(ordinary_path(output / name, root), cancel_event=cancel_event) != row):
                raise ValueError(IMMUTABLE_ERROR)
        check_cancel(cancel_event)
        return receipt
    except (OSError, KeyError, TypeError, ValueError, RecursionError) as exc:
        # InterruptedError is an OSError but must retain cancellation semantics.
        if isinstance(exc, InterruptedError):
            raise
        raise ValueError(IMMUTABLE_ERROR) from exc


def write_receipt(staging, root, signature, contract, *, cancel_event=None):
    staging = ordinary_path(staging, root)
    names = _names(staging, root)
    assets = _asset_names(contract)
    if names not in (assets, assets | {'index.json'}):
        raise ValueError(IMMUTABLE_ERROR)
    files = {name: fingerprint(ordinary_path(staging / name, root), cancel_event=cancel_event)
             for name in sorted(names)}
    receipt = {'format': FORMAT, 'signature': signature,
               'contract': stable_contract(contract), 'files': files}
    body = canonical(receipt)
    if len(body) > MAX_RECEIPT_BYTES or sum(row['size'] for row in files.values()) + len(body) > MAX_BYTES:
        raise ValueError('Saved livery atlas exceeds the reserved cache allowance.')
    check_cancel(cancel_event)
    path = ordinary_path(staging / (PREFIX + hashlib.sha256(body).hexdigest() + '.json'), root)
    with atomic_stream(path) as stream:
        stream.write(body)
    return receipt
