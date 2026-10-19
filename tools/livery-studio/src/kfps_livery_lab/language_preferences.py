"""Private Studio language choice; host preferences are bounded read-only defaults."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import re
import sys
import time

from .confirmation_preferences import _ordinary, _try_lock, _unlock
from .model import ValidationError, decode_json
from .prepare import LAB_ROOT, atomic_json

SUPPORTED_LANGUAGES = ('en', 'ko', 'ja')
MAX_REQUEST_BYTES = 1024
MAX_FILE_BYTES = 4096
MAX_HOST_BYTES = 256 * 1024
LOCK_TIMEOUT_SECONDS = 2.0


class LanguageError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def system_language():
    """Use Windows display language, not number/date regional formatting."""
    if sys.platform == 'win32':
        try:
            import ctypes
            get_language = ctypes.WinDLL('kernel32', use_last_error=True).GetUserDefaultUILanguage
            get_language.argtypes = []
            get_language.restype = ctypes.c_ushort
            return {0x11: 'ja', 0x12: 'ko'}.get(get_language() & 0x03FF, 'en')
        except (AttributeError, OSError):
            return 'en'
    try:
        import locale
        return locale.getlocale()[0] or 'en'
    except (ValueError, OSError):
        return 'en'


def _locale(value):
    match = re.match(r'^(en|ko|ja)(?:[-_.]|$)', value, re.I) if isinstance(value, str) else None
    return match[1].lower() if match else 'en'


def _response(language, source):
    return {'version': 1, 'language': language, 'supported': list(SUPPORTED_LANGUAGES), 'source': source}


class LanguagePreferences:
    def __init__(self, root, kfps_root, *, system_locale=None):
        self.root = Path(root).absolute()
        self.path = self.root / 'studio-language.json'
        self.lock_path = self.root / 'studio-language.lock'
        self.host_root = Path(kfps_root).absolute()
        self.system_locale = _locale(system_language() if system_locale is None else system_locale)
        try:
            relative = self.root.relative_to(LAB_ROOT.absolute())
            if not relative.parts or '..' in relative.parts or '..' in Path(root).parts:
                raise ValueError()
        except ValueError as exc:
            raise LanguageError(500, 'Language storage must remain inside the isolated workspace.') from exc

    def _check_paths(self):
        current = LAB_ROOT.absolute()
        for part in self.root.relative_to(current).parts:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info, directory=True):
                raise LanguageError(500, 'Language storage is redirected or invalid.')
        if not self.root.resolve().is_relative_to(LAB_ROOT.resolve()):
            raise LanguageError(500, 'Language storage is outside the isolated workspace.')
        for path in (self.path, self.lock_path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info):
                raise LanguageError(500, 'Language storage is redirected or invalid.')

    def _default(self):
        path = self.host_root / 'runtime/fabric-editor/preferences.json'
        try:
            for directory in (self.host_root, path.parent.parent, path.parent):
                if not _ordinary(directory.lstat(), directory=True):
                    return _response(self.system_locale, 'system')
            if not path.resolve().is_relative_to(self.host_root.resolve()) or not _ordinary(path.lstat()):
                return _response(self.system_locale, 'system')
            with path.open('rb') as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > MAX_HOST_BYTES:
                    return _response(self.system_locale, 'system')
                raw = handle.read(MAX_HOST_BYTES + 1)
            if len(raw) <= MAX_HOST_BYTES:
                value = decode_json(raw)
                settings = value.get('settings') if isinstance(value, dict) else None
                selected = settings.get('kloudyFabricLanguage') if isinstance(settings, dict) else None
                if isinstance(selected, str) and selected in SUPPORTED_LANGUAGES:
                    return _response(selected, 'editor')
        except (OSError, ValidationError, ValueError, RecursionError):
            pass
        return _response(self.system_locale, 'system')

    def _read(self):
        try:
            with self.path.open('rb') as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info):
                    raise LanguageError(500, 'Language storage is redirected or invalid.')
                if info.st_size > MAX_FILE_BYTES:
                    raise ValidationError('Oversized preference.')
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ValidationError('Oversized preference.')
            value = decode_json(raw)
            if (not isinstance(value, dict) or set(value) != {'version', 'language'}
                    or type(value['version']) is not int or value['version'] != 1
                    or not isinstance(value['language'], str) or value['language'] not in SUPPORTED_LANGUAGES):
                raise ValidationError('Invalid preference.')
            return _response(value['language'], 'studio')
        except FileNotFoundError:
            return self._default()
        except ValidationError as exc:
            raise LanguageError(409, 'Studio language preferences are corrupt or incompatible and were not replaced.') from exc

    @contextmanager
    def _locked(self):
        try:
            self._check_paths()
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(descriptor, 'r+b') as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > 1:
                    raise LanguageError(500, 'Language lock storage is invalid.')
                deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        _try_lock(handle)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                            raise
                        time.sleep(.02)
                try:
                    if os.fstat(handle.fileno()).st_size == 0:
                        handle.write(b'0')
                        handle.flush()
                    self._check_paths()
                    yield
                finally:
                    _unlock(handle)
        except OSError as exc:
            raise LanguageError(503, 'Studio language preferences are unavailable or busy.') from exc

    def get(self):
        # Atomic replacement lets readers observe one complete version without
        # creating a directory/lock or writing inherited preferences on GET.
        try:
            self._check_paths()
            return self._read()
        except OSError as exc:
            raise LanguageError(503, 'Studio language preferences are unavailable or busy.') from exc

    def update(self, value):
        if (not isinstance(value, dict) or set(value) != {'language'}
                or not isinstance(value['language'], str) or value['language'] not in SUPPORTED_LANGUAGES):
            raise LanguageError(422, 'Expected exactly language: en, ko or ja.')
        with self._locked():
            self._read()  # Preserve corrupt/future files rather than overwriting unknown settings.
            atomic_json(self.path, {'version': 1, 'language': value['language']})
        return _response(value['language'], 'studio')

    def configuration(self):
        metadata = {'version': 1, 'enabled': True, 'storage_status': 'available'}
        try:
            result = self.get()
        except LanguageError as exc:
            result = self._default()
            metadata.update(storage_status='unavailable', error=str(exc))
        metadata['source'] = result['source']
        return {'language': result['language'], 'supported_languages': result['supported'],
                'language_preferences': metadata}
