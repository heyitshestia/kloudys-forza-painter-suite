"""Explicit named build references; never an automatic owned-car association."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import uuid

from .garage_index import GarageError, TOKEN, atomic_json, digest, read_json, validate_rows

IDENTIFIER = re.compile(r'[a-f0-9]{32}\Z')
MANAGED_FILE = re.compile(r'([a-f0-9]{32})-[a-f0-9]{16}\.json\Z')
MAX_NOTES = 100


def _name(value):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 80 or any(ord(c) < 32 for c in value):
        raise GarageError('Enter a single-line comparison name of 1 to 80 characters.')
    return value.strip()


def _plain_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise GarageError('Redirected project locations are not supported.')
    if path.is_file() and path.stat().st_nlink != 1:
        raise GarageError('Choose a regular Studio project file.')
    return path


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Project check cancelled')


def _project_info(path, car_id, app_root, cancel=None, *, include_project=False):
    _check_cancel(cancel)
    # Reuse Studio's project contract without constructing a renderer or store.
    source = str(Path(app_root) / 'tools/livery-studio/src')
    if source not in sys.path:
        sys.path.insert(0, source)
    from kfps_livery_lab.recovery import MAX_PROJECT_BYTES, _project, _vehicle
    from kfps_livery_lab.model import decode_json
    path = _plain_path(path)
    if path.suffix.lower() != '.json':
        raise GarageError('Choose a saved Studio project JSON.')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise GarageError('Choose a regular Studio project file.')
        if not 0 < before.st_size <= MAX_PROJECT_BYTES:
            raise GarageError('The Studio project exceeds its size limit.')
        body = stream.read(MAX_PROJECT_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = _plain_path(path).stat()
    stamps = [(p.st_size, p.st_mtime_ns, p.st_ino, p.st_dev) for p in (before, after, current)]
    if stamps[0] != stamps[1] or stamps[0] != stamps[2] or len(body) != before.st_size:
        raise GarageError('The project changed while reading. Wait for saving to finish and retry.')
    value = decode_json(body)
    _check_cancel(cancel)
    vehicle = _vehicle(value.get('vehicle') if isinstance(value, dict) else None)
    if vehicle['car_id'] != car_id:
        raise GarageError('This Studio project belongs to a different car model.')
    _project(value, vehicle)
    _check_cancel(cancel)
    info = {'path': str(path), 'vehicle': vehicle, 'revision': hashlib.sha256(body).hexdigest(),
            'managedRoot': '', 'managedId': ''}
    return (info, value, len(body)) if include_project else info


def freeze_project_reference(info):
    """Copy only bounded reference metadata; performs no filesystem I/O."""
    if not isinstance(info, dict) or not isinstance(info.get('vehicle'), dict):
        raise GarageError('The saved project reference is invalid.')
    _validate_project(info, {'carId': info['vehicle'].get('car_id')})
    if len(info['managedRoot']) > 32768:
        raise GarageError('The saved project reference is invalid.')
    return json.loads(json.dumps(info, allow_nan=False))


def read_linked_project(info, app_root, *, cancel=None):
    """Freeze the current saved revision without writing or repairing its store."""
    try:
        _check_cancel(cancel)
        # Detach the reference as well as the body before any asynchronous launch.
        info = freeze_project_reference(info)
        path = Path(info['path'])
        managed = None
        if info['managedId']:
            managed = _managed_path(info['managedRoot'], info['managedId'], info['vehicle'], cancel)
            path = managed[0]
        current, project, size = _project_info(path, info['vehicle']['car_id'], app_root, cancel,
                                              include_project=True)
        if current['vehicle'] != info['vehicle']:
            raise GarageError('The project car identity changed.')
        if managed is not None:
            after = _managed_path(info['managedRoot'], info['managedId'], info['vehicle'], cancel)
            if after != managed or current['revision'] != managed[1] or size != managed[2]:
                raise GarageError('The managed project is changing. Retry after saving.')
        _check_cancel(cancel)
        return project
    except (GarageError, InterruptedError):
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, sqlite3.Error):
        raise GarageError('The Studio project is missing, busy or unsupported.') from None


def _managed_path(root, ident, vehicle, cancel=None):
    _check_cancel(cancel)
    root = _plain_path(root)
    database = _plain_path(root / 'storage.sqlite3')
    if database.stat().st_size > 64 * 1024 * 1024:
        raise GarageError('The Studio project catalogue exceeds its size limit.')
    # A read-only connection must not initialize or repair Studio's catalogue.
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=0.3)) as db:
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > deadline or bool(cancel and cancel.is_set())), 1000)
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        objects = db.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') LIMIT 8").fetchall()
        if dict(objects) != {'cars': 'table', 'projects': 'table', 'files': 'table'}:
            raise GarageError('The Studio project catalogue schema is unsupported.')
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise GarageError('The Studio project catalogue is unsupported.')
        row = db.execute('SELECT c.car_id,c.model_code,c.folder,p.file_name,p.revision,p.bytes '
                         'FROM projects p JOIN cars c ON c.key=p.car_key WHERE p.id=?', (ident,)).fetchone()
    _check_cancel(cancel)
    if row is None:
        raise FileNotFoundError()
    car_id, code, folder, filename, revision, size = row
    if (vehicle != {'car_id': car_id, 'model_code': code} or not isinstance(folder, str)
            or not re.fullmatch(r'[a-z0-9-]{1,70}', folder)
            or not isinstance(filename, str) or not MANAGED_FILE.fullmatch(filename)
            or not filename.startswith(ident + '-') or not isinstance(revision, str) or not TOKEN.fullmatch(revision)
            or type(size) is not int or not 0 < size <= 32 * 1024 * 1024):
        raise GarageError('The Studio project reference is inconsistent.')
    path = _plain_path(root / folder / 'projects' / filename)
    if not path.is_relative_to(root):
        raise GarageError('The Studio project is outside its managed folder.')
    return path, revision, size


def inspect_project(path, car_id, app_root, *, cancel=None):
    try:
        info = _project_info(path, car_id, app_root, cancel)
        candidate = Path(info['path'])
        managed = MANAGED_FILE.fullmatch(candidate.name)
        if managed and candidate.parent.name == 'projects':
            root = candidate.parent.parent.parent
            if (root / 'storage.sqlite3').is_file():
                expected, revision, size = _managed_path(root, managed[1], info['vehicle'], cancel)
                if (expected != candidate or revision != info['revision'] or candidate.stat().st_size != size):
                    raise GarageError('The managed project changed. Choose its current saved revision.')
                info.update(managedRoot=str(root), managedId=managed[1])
        return info
    except (GarageError, InterruptedError):
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
        raise GarageError('The Studio project is missing, busy or unsupported.') from None


def resolve_project(info, app_root, *, cancel=None):
    try:
        _check_cancel(cancel)
        path = Path(info['path'])
        if info['managedId']:
            path, revision, size = _managed_path(info['managedRoot'], info['managedId'], info['vehicle'], cancel)
        current = _project_info(path, info['vehicle']['car_id'], app_root, cancel)
        if current['vehicle'] != info['vehicle']:
            raise GarageError('The project car identity changed.')
        if info['managedId'] and (current['revision'] != revision or path.stat().st_size != size):
            raise GarageError('The managed project is changing. Retry after saving.')
        return {'status': 'current' if current['revision'] == info['revision'] else 'changed', 'path': str(path)}
    except InterruptedError:
        raise
    except FileNotFoundError:
        return {'status': 'missing', 'path': ''}
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
        return {'status': 'unavailable', 'path': ''}


def _validate_project(info, car):
    if info is None:
        return
    if (not isinstance(info, dict) or set(info) != {'path', 'vehicle', 'revision', 'managedRoot', 'managedId'}
            or not isinstance(info['path'], str) or not Path(info['path']).is_absolute()
            or len(info['path']) > 32768 or any(ord(c) < 32 for c in info['path'])
            or not isinstance(info['vehicle'], dict) or set(info['vehicle']) != {'car_id', 'model_code'}
            or info['vehicle']['car_id'] != car['carId']
            or not isinstance(info['vehicle']['model_code'], str) or not 0 < len(info['vehicle']['model_code']) <= 160
            or not isinstance(info['revision'], str) or not TOKEN.fullmatch(info['revision'])
            or not isinstance(info['managedRoot'], str) or not isinstance(info['managedId'], str)
            or bool(info['managedRoot']) != bool(info['managedId'])
            or info['managedId'] and (not IDENTIFIER.fullmatch(info['managedId'])
                                      or not Path(info['managedRoot']).is_absolute())):
        raise GarageError('The saved project reference is invalid.')


class GarageNotes:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            value = read_json(self.path)
            if (not isinstance(value, dict) or set(value) != {'format', 'entries', 'checksum'}
                    or value['format'] != 1 or not isinstance(value['entries'], list)
                    or len(value['entries']) > MAX_NOTES
                    or value['checksum'] != digest({'format': 1, 'entries': value['entries']})):
                raise ValueError()
            seen = set()
            for entry in value['entries']:
                if (not isinstance(entry, dict) or set(entry) != {'id', 'name', 'car', 'savedAt', 'project'}
                        or not isinstance(entry['id'], str) or not IDENTIFIER.fullmatch(entry['id'])
                        or entry['id'] in seen or not isinstance(entry['savedAt'], str) or len(entry['savedAt']) > 40):
                    raise ValueError()
                seen.add(entry['id'])
                _name(entry['name'])
                validate_rows([entry['car']])
                _validate_project(entry['project'], entry['car'])
            return value['entries']
        except FileNotFoundError:
            return []
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            raise GarageError('Saved comparisons could not be read. The existing file was left unchanged.') from None

    def _write(self, entries):
        value = {'format': 1, 'entries': entries}
        value['checksum'] = digest(value)
        atomic_json(self.path, value)

    def add(self, name, car):
        name = _name(name)
        validate_rows([car])
        entries = self.load()
        if len(entries) >= MAX_NOTES:
            raise GarageError('The 100 saved-comparison limit has been reached.')
        if any(e['name'].casefold() == name.casefold() for e in entries):
            raise GarageError('That comparison name is already in use.')
        entry = {'id': uuid.uuid4().hex, 'name': name, 'car': json.loads(json.dumps(car)),
                 'savedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'project': None}
        self._write([entry, *entries])
        return entry

    def link(self, ident, project):
        entries = self.load()
        entry = next((e for e in entries if e['id'] == ident), None)
        if entry is None:
            raise GarageError('Choose a saved comparison first.')
        _validate_project(project, entry['car'])
        entry['project'] = project
        self._write(entries)

    def remove(self, ident):
        self._write([e for e in self.load() if e['id'] != ident])
