"""Opt-in hidden process qualification; no game files, user profiles or GPU scene."""
from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener
import uuid

import psutil

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / 'tools/livery-studio'
sys.path[:0] = [str(LAB / 'src'), str(ROOT / 'KFPS.Editor/src')]
HTTP = build_opener(ProxyHandler({}))
PAGE = '''<!doctype html><html lang="en"><body>Studio lifecycle fixture
<script>window.dirty=true;window.__liveryLab={ready:true,getProject:()=>({})};
addEventListener('beforeunload',e=>{if(window.dirty){e.preventDefault();e.returnValue='';}});
</script></body></html>'''


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def wait_for(predicate, *, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError('Lifecycle condition timed out')


def foreground_pid():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def child_backend(lab, startup, disconnect):
    from kfps_livery_lab import backend_lifetime, diagnostics, server, studio_window
    workspace = lab / 'runs/session'
    workspace.mkdir(parents=True)
    web = lab / 'web'
    web.mkdir()
    (web / 'index.html').write_text(PAGE, encoding='utf-8')
    for name in ('mesh.glb', 'paint.png', 'm0.png', 'm1.png', 'm2.png'):
        (workspace / name).write_bytes(b'fixture')
    prepared = dict(files=dict(mesh='mesh.glb', paint='paint.png', masks=['m0.png','m1.png','m2.png']),
                    manifest=dict(inspection_runtime=dict(local_mesh=True)),
                    editor_config=dict(paint_size=[64,64], sections=[], vehicle=dict(car_id=1,archive_name='test.zip')))
    actual_server, actual_policy = server.LiveryLabServer, backend_lifetime.LifetimePolicy
    def factory(*args, **kwargs):
        return actual_server(*args, **kwargs, web_root=web, renderer=lambda _: {},
                             session_data_root=workspace / 'session-data')
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, 'prepare_car', return_value=prepared))
        stack.enter_context(patch.object(server, 'LiveryLabServer', factory))
        stack.enter_context(patch.object(server, 'LAB_ROOT', lab))
        stack.enter_context(patch.object(studio_window, 'LAB', lab))
        stack.enter_context(patch.object(diagnostics, 'DEFAULT_ROOT', lab / 'diagnostics'))
        stack.enter_context(patch.object(backend_lifetime, 'LifetimePolicy', lambda: actual_policy(startup_grace=startup, disconnect_grace=disconnect)))
        server.run(SimpleNamespace(kfps_root=ROOT, game_root=None, archive='test.zip', workspace=workspace,
                                   port=0, prepare_only=False, template=None, managed_lifetime=True))


def child_native(lab, url):
    from kfps_livery_lab import native_host, studio_window
    studio_window.LAB = lab
    native_host.LAB = lab
    sys.argv = [__file__, '--root', str(ROOT), '--url', url, '--run', str(lab / 'runs/native'),
                '--offscreen', '--test-control']
    raise SystemExit(native_host.main())


def run(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Evidence must stay inside DIRTY/runtime')
    output.mkdir(parents=True, exist_ok=False)
    lab = LAB / 'runs' / ('lifetime-validation-' + uuid.uuid4().hex)
    lab.mkdir(parents=True)
    processes, results = [], []
    failure = None
    environment = dict(os.environ, KFPS_ACTIVITY_DISABLED='1', KFPS_STARTUP_MUTED='1',
                       QT_QPA_PLATFORM='offscreen', QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu')
    for key in ('TEMP','TMP','APPDATA','LOCALAPPDATA'):
        folder = output / key.lower()
        folder.mkdir()
        environment[key] = str(folder)
    def spawn(command, name):
        with (output / (name+'.stdout.log')).open('wb') as stdout, (output / (name+'.stderr.log')).open('wb') as stderr:
            child = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(child)
        return child
    def stop_child(child):
        if child.poll() is None:
            children = psutil.Process(child.pid).children(recursive=True)
            child.terminate()
            child.wait(5)
            for process in children:
                try:
                    process.terminate()
                except psutil.Error:
                    pass
            _, alive = psutil.wait_procs(children, timeout=3)
            for process in alive:
                try:
                    process.kill()
                except psutil.Error:
                    pass
            psutil.wait_procs(alive, timeout=3)
    def backend(case, startup=10, disconnect=2):
        folder = lab / case
        folder.mkdir()
        child = spawn([sys.executable,'-I','-B',__file__,'--backend',str(folder),str(startup),str(disconnect)], case+'-backend')
        info_path = folder / 'runs/session/server-info.json'
        def ready():
            if child.poll() is not None:
                raise AssertionError(f'{case} backend exited before readiness')
            info = read(info_path)
            return info if info.get('status') == 'running' else None
        info = wait_for(ready)
        return folder, child, info, info_path
    def stopped(case, child, info_path, started, timeout=15):
        child.wait(timeout=timeout)
        assert child.returncode == 0, f'{case} backend failed'
        assert read(info_path).get('status') == 'stopped'
        results.append(dict(case=case, passed=True, exit_seconds=round(time.monotonic()-started,3)))
    try:
        folder, child, info, info_path = backend('unclaimed', startup=4)
        stopped('unclaimed', child, info_path, time.monotonic())
        for case in ('native-close', 'native-crash'):
            folder, child, info, info_path = backend(case)
            host = spawn([sys.executable,'-I','-B',__file__,'--native',str(folder),info['url']],case+'-host')
            host_path = folder / 'runs/native/host.json'
            wait_for(lambda: read(host_path).get('status') == 'ready')
            assert foreground_pid() not in {host.pid, child.pid}, 'Test took desktop focus'
            control = folder / 'runs/native/control.json'
            control.write_text(json.dumps(dict(close='reject',confirm=False)),encoding='utf-8')
            events = folder / 'runs/native/events.jsonl'
            wait_for(lambda: events.exists() and '"accepted": false' in events.read_text())
            time.sleep(11)
            assert child.poll() is None and host.poll() is None, 'Rejected close lost owner/backend'
            started = time.monotonic()
            if case == 'native-close':
                control.write_text(json.dumps(dict(close='accept',confirm=True)),encoding='utf-8')
                host.wait(12)
                assert host.returncode == 0 and read(host_path).get('status') == 'closed'
            else:
                stop_child(host)
            stopped(case, child, info_path, started)
        from kfps_livery_lab.launcher import chrome_path
        folder, child, info, info_path = backend('chrome-close')
        profile = folder / 'runs/studio-browser'
        assert not profile.exists()
        profile.mkdir()
        with HTTP.open(Request(info['url']+'api/chrome-session',data=b'',method='POST'),timeout=5) as response:
            assert json.load(response) == {'chrome_exposed':True}
        browser = spawn([str(chrome_path()),'--headless=new','--disable-gpu','--disable-background-mode',
                         '--no-first-run','--no-default-browser-check',f'--user-data-dir={profile}',info['url']], 'chrome-browser')
        time.sleep(12)
        assert browser.poll() is None and child.poll() is None, 'Hidden Chrome owner expired'
        assert foreground_pid() not in {browser.pid,child.pid}, 'Chrome test took focus'
        before = psutil.Process(child.pid).cpu_times()
        time.sleep(2)
        after = psutil.Process(child.pid).cpu_times()
        started = time.monotonic()
        stop_child(browser)
        stopped('chrome-close',child,info_path,started)
        results[-1]['idle_cpu_seconds_per_two_seconds'] = round(after.user+after.system-before.user-before.system,5)
        folder, child, info, info_path = backend('production-grace', startup=60, disconnect=5)
        started = time.monotonic()
        time.sleep(55)
        assert child.poll() is None, 'Shipped startup grace ended early'
        stopped('production-grace', child, info_path, started)
    except BaseException as error:
        failure = f'{type(error).__name__}: {error}'
        raise
    finally:
        for child in reversed(processes):
            stop_child(child)
        preserved = output / 'fixture'
        shutil.move(str(lab), str(preserved))
        report = dict(results=results, fixture_root=str(preserved), all_test_processes_exited=all(p.poll() is not None for p in processes),
                      failure=failure,
                      limitations='Lifecycle fixture, not full car rendering. Four cases shorten the grace; production-grace exercises the shipped 60/5-second policy.')
        (output / 'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert len(results) == 5
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--backend':
        child_backend(Path(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]))
    elif len(sys.argv) > 1 and sys.argv[1] == '--native':
        child_native(Path(sys.argv[2]),sys.argv[3])
    else:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--output',required=True,type=Path)
        run(parser.parse_args().output)
