"""Managed backend lifetime follows OS owners, never browser activity timers."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import time

import psutil

from . import studio_window


class LifetimePolicy:
    def __init__(self, *, clock=time.monotonic, startup_grace=60, disconnect_grace=5):
        self.clock = clock
        self.started = clock()
        self.last_owner = self.started
        self.unknown_until = self.started
        self.startup_grace = startup_grace
        self.disconnect_grace = disconnect_grace
        self.seen_owner = False

    def observe(self, state):
        now = self.clock()
        if state in ('native', 'chrome'):
            self.seen_owner = True
            self.last_owner = now
            return None
        if state == 'unknown':
            self.unknown_until = now + self.disconnect_grace
            return None
        if state != 'none':
            raise ValueError('Unknown backend ownership state.')
        # Handoff publication briefly owns the same lock before a real window.
        # That reservation must not shorten the original startup allowance.
        deadline = max(self.started + self.startup_grace, self.last_owner + self.disconnect_grace)
        if now >= max(deadline, self.unknown_until):
            return 'owner_closed' if self.seen_owner else 'unclaimed'
        return None


class ChromeOwnership:
    def __init__(self, profile, executable, *, processes=None):
        self.profile = Path(profile).resolve()
        self.executable = Path(executable).resolve()
        self.processes = processes or self._fresh_processes
        self.cached = None

    @staticmethod
    def _fresh_processes():
        # Windows process names are cached; a recycled PID must get a fresh name.
        psutil.process_iter.cache_clear()
        return psutil.process_iter(['name'])

    def _matches(self, process):
        arguments = process.cmdline()
        if any(arg == '--type' or arg.startswith('--type=') for arg in arguments):
            return False
        profiles = []
        for index, argument in enumerate(arguments):
            if argument.startswith('--user-data-dir='):
                profiles.append(argument.split('=', 1)[1])
            elif argument == '--user-data-dir' and index + 1 < len(arguments):
                profiles.append(arguments[index + 1])
        return (len(profiles) == 1 and Path(profiles[0]).resolve() == self.profile
                and Path(process.exe()).resolve() == self.executable)

    def alive(self):
        if self.cached is not None:
            process, created = self.cached
            try:
                if process.is_running() and process.create_time() == created:
                    return True
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                pass
            except psutil.AccessDenied:
                return None
            self.cached = None
        unknown = False
        try:
            for process in self.processes():
                try:
                    if not process.is_running():
                        unknown = True
                        continue
                    name = process.info.get('name')
                    if not isinstance(name, str) or not name:
                        unknown = True
                        continue
                    if name.lower() != self.executable.name.lower():
                        continue
                    if self._matches(process):
                        self.cached = process, process.create_time()
                        return True
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                except (psutil.AccessDenied, OSError, ValueError):
                    unknown = True
        except psutil.Error:
            unknown = True
        return None if unknown else False


class BackendOwnership:
    def __init__(self, kfps_root, lab_root):
        self.lab_root = Path(lab_root).resolve()
        self.chrome = None
        self.acquire = None
        if os.name == 'nt':
            path = Path(kfps_root) / 'KFPS.Editor/src/kfps_editor/windows_lock.py'
            spec = importlib.util.spec_from_file_location('_studio_lifetime_windows_lock', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.acquire = module.acquire_file_lease

    def _chrome_alive(self):
        if self.chrome is None:
            from .launcher import chrome_path
            try:
                self.chrome = ChromeOwnership(self.lab_root / 'runs/studio-browser', chrome_path())
            except (OSError, ValueError):
                # Missing installation metadata does not prove an existing
                # browser process has exited.
                return None
        return self.chrome.alive()

    @contextmanager
    def observe(self, url, *, chrome_exposed):
        lease = None
        state = 'unknown'
        try:
            # Process inspection can be slow. Never hold the native admission
            # lease during it; the final HTTP quiet check guards launch handoffs.
            inspected_at = time.monotonic()
            chrome = self._chrome_alive() if chrome_exposed else False
            directory = studio_window.native_owner_directory(url)
            if self.acquire is not None:
                try:
                    # The existing OS lease is authoritative. Do not rewrite its
                    # marker or emit per-poll editor startup diagnostics.
                    lease = self.acquire(directory / 'desktop.lock', share=1)
                except OSError as error:
                    if getattr(error, 'winerror', None) not in (32, 33):
                        raise
                    state = 'native'
            else:
                from PySide6.QtCore import QLockFile
                directory.mkdir(parents=True, exist_ok=True)
                candidate = QLockFile(str(directory / 'desktop.lock'))
                candidate.setStaleLockTime(0)
                if candidate.tryLock(0):
                    lease = candidate
                elif candidate.error() == QLockFile.LockError.LockFailedError:
                    state = 'native'
            if lease is not None:
                if time.monotonic() - inspected_at >= 1:
                    chrome = None
                state = 'unknown' if chrome is None else 'chrome' if chrome else 'none'
        except (OSError, RuntimeError, ValueError, psutil.Error):
            state = 'unknown'
        try:
            yield state
        finally:
            if lease is not None:
                if self.acquire is not None:
                    lease.Close()
                else:
                    lease.unlock()
