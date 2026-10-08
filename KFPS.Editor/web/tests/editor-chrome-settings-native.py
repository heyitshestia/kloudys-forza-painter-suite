"""Both real launch paths consume the persisted switch; no personal data touched."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
from PySide6.QtCore import QCoreApplication

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src")]
from kfps_ui.settings_service import SettingsService
from kfps_ui.editor_launch import launch_editor
from kfps_editor.ipc import read_desktop_state, instance_name
from kfps_editor.browser_page import window_for_process


def main():
    stage, out = [Path(p).resolve() for p in sys.argv[1:3]]
    assert stage.is_relative_to(ROOT / 'runtime/test-runs') and (stage / 'editor-stage.json').is_file()
    assert out.is_relative_to(ROOT / 'runtime/test-runs') and not out.exists()
    out.mkdir(parents=True)
    shutil.copy2(ROOT / 'KFPS Editor.exe', stage / 'KFPS Editor.exe')
    app = QCoreApplication([])
    runtime = stage / 'runtime' / out.name / 'fabric-editor'
    (runtime / 'projects').mkdir(parents=True)
    project = runtime / 'projects/Chrome switch.fabric-project.json'
    project.write_text(json.dumps({'name': 'Chrome switch', 'shapes': [
        {'type': 1048677, 'data': [0, 0, .4, .4, 0, 0, 0], 'color': [40, 180, 120, 255]}]}))
    original = project.read_bytes()
    (runtime / 'startup-help-confirmed.json').write_text('{}')
    (runtime / 'preferences.json').write_text(json.dumps({'settings': {
        'kloudyFabricLanguage': 'en', 'kloudyFabricLanguageNoticeAcknowledged': '1',
        'kloudyFabricProjectSharingAcknowledged': '1', 'kloudyFabricEditorUpdateAcknowledged': 'modernization-1'}}))
    settings = SettingsService(stage / 'runtime/qml-shell-settings.json')
    paths = SimpleNamespace(app_root=stage, runtime_root=runtime.parent, python_executable=ROOT / 'python/python.exe')
    name = instance_name(stage, runtime)
    env = dict(os.environ, KFPS_PYTHON=str(ROOT / 'python/python.exe'), PYTHONDONTWRITEBYTECODE='1')
    user = ctypes.WinDLL('user32')
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    owned, children, results = [], [], []
    host = None
    personal = []
    for process in psutil.process_iter(['name', 'cmdline']):
        if (process.info['name'] or '').lower() == 'chrome.exe' and not any('KFPS' in a for a in process.info['cmdline'] or []):
            personal.append(process)

    def wait(check, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            value = check()
            if value:
                return value
            time.sleep(.04)
        raise TimeoutError('Chrome settings qualification timed out')

    def ready():
        state = read_desktop_state(runtime, name)
        return state if state.get('state') == 'ready' else None

    def exe(extra=(), project_id=True, missing_chrome=False):
        command = [str(stage / 'KFPS Editor.exe')]
        if missing_chrome:
            # Hide only Chrome discovery files from this child's read calls.
            # Windows may restore PROGRAMFILES, so environment edits are not a
            # reliable missing-install fixture. No installation files are moved.
            probe = (
                'import sys,runpy\nfrom pathlib import Path\nfrom unittest.mock import patch\n'
                'entry=sys.argv.pop(1)\nsys.path[:0]=[str(Path(entry).parent.parent),str(Path(entry).parent/"src")]\n'
                'original=Path.is_file\n'
                'with patch.object(Path,"is_file",lambda p: False if p.name=="chrome.exe" else original(p)):\n'
                ' runpy.run_path(entry,run_name="__main__")\n')
            command = [str(ROOT / 'python/python.exe'), '-B', '-c', probe, str(stage / 'KFPS.Editor/editor.py')]
        with (out / f'launch-{len(owned)}.log').open('wb') as stream:
            process = subprocess.Popen([*command, '--runtime-root', str(runtime),
                *(['--project-id', project.name] if project_id else []), '--background', '--from-kfps', *extra], cwd=stage,
                env=env, stdout=stream, stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW)
        owned.append(process)
        return process

    def close_owner(chrome):
        processes = host.children(recursive=True)
        children.extend(processes)
        if chrome:
            owner = json.loads((runtime / 'browser-profile/kfps-owner.json').read_text())
            hwnd = wait(lambda: window_for_process(owner['pid']))
            user.PostMessageW(hwnd, 0x10, 0, 0)
        else:
            @callback_type
            def close(hwnd, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == host.pid:
                    user.PostMessageW(hwnd, 0x10, 0, 0)
                return True
            user.EnumWindows(close, 0)
        wait(lambda: not host.is_running(), 30)
        wait(lambda: not any(p.is_running() for p in processes), 15)
        assert not (runtime / 'desktop.json').exists()
        assert project.read_bytes() == original

    try:
        for origin, chrome in (('exe', True), ('exe', False), ('bridge', True)):
            settings.editorUseChrome = chrome
            if origin == 'exe':
                exe()
            else:
                launch_editor(paths, project.name, background=True)
            state = wait(ready)
            host = psutil.Process(state['pid'])
            children.append(host)
            log = [json.loads(line) for line in (runtime / 'desktop.log').read_text().splitlines() if line.startswith('{')]
            launch = next(e for e in reversed(log) if e.get('event') == 'launch-request')
            assert launch['display_host'] == ('chrome' if chrome else 'desktop'), launch
            policy = next(e for e in reversed(log) if e.get('event') == 'graphics-policy')
            assert (policy['requested_backend'] == 'chrome') is chrome, policy
            if chrome:
                browser = next(e for e in reversed(log) if e.get('event') == 'browser-start')
                assert browser['browser'].startswith('Chrome/'), browser
            settings.editorUseChrome = not chrome
            launch_editor(paths, background=True)
            assert ready()['pid'] == host.pid
            duplicate = exe(project_id=False)
            wait(lambda: duplicate.poll() is not None)
            assert duplicate.returncode == 0 and ready()['pid'] == host.pid
            close_owner(chrome)
            for process in owned:
                if process.poll() is None:
                    assert process.wait(15) == 0
            results.append({'origin': origin, 'chrome': chrome, 'savedChoice': True,
                            'reuseAcrossToggle': True, 'closedAllOwnedProcesses': True})
            print(json.dumps(results[-1]), flush=True)
        settings.editorUseChrome = True
        child = exe(missing_chrome=True)
        wait(lambda: child.poll() is not None)
        assert child.returncode != 0
        error = json.loads((runtime / 'desktop-startup-error.json').read_text())
        assert 'Google Chrome was not found' in error['error'], error
        assert not ready() and project.read_bytes() == original
        assert all(p.is_running() for p in personal), 'An unrelated Chrome process exited during the test'
        results.append({'missingChromeExplicit': True, 'personalChromeProcessesPreserved': len(personal)})
        print(json.dumps(results[-1]), flush=True)
    finally:
        state = read_desktop_state(runtime, name)
        if state.get('pid'):
            try:
                current = psutil.Process(state['pid'])
                if any(str(stage / 'KFPS.Editor/editor.py') == arg for arg in current.cmdline()):
                    children.extend([current, *current.children(recursive=True)])
            except psutil.Error:
                pass
        if host and host.is_running():
            children.extend(host.children(recursive=True))
        for process in reversed(children):
            try:
                if process.is_running():
                    process.kill()
                    process.wait(10)
            except psutil.Error:
                pass
        for child in owned:
            if child.poll() is None:
                child.kill()
            child.wait(10)
        (out / 'results.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
