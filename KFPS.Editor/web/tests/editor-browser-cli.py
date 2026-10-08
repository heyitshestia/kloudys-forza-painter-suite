"""Real CLI startup, abrupt host exit/job containment and restart, background only."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(sys.argv[1]).resolve()
assert OUT.is_relative_to(ROOT/'runtime/test-runs') and not OUT.exists()
OUT.mkdir(parents=True)
sys.path.insert(0,str(ROOT/'KFPS.Editor/src'))
from kfps_editor.browser_page import window_for_process
runtime=OUT/'runtime'
(runtime/'projects').mkdir(parents=True)
(runtime/'projects/CLI.fabric-project.json').write_text(json.dumps({'name':'CLI','shapes':[
    {'type':1048677,'data':[0,0,.4,.4,0,0,0],'color':[30,180,160,255]}]}))
(runtime/'startup-help-confirmed.json').write_text('{}')
(runtime/'preferences.json').write_text(json.dumps({'settings':{
    'kloudyFabricLanguage':'en','kloudyFabricLanguageNoticeAcknowledged':'1',
    'kloudyFabricProjectSharingAcknowledged':'1','kloudyFabricEditorUpdateAcknowledged':'modernization-1'}}))
results=[]
owned=[]
user=ctypes.WinDLL('user32')
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]


def wait(predicate,timeout=75):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=predicate()
        if result:
            return result
        time.sleep(.1)
    raise TimeoutError('CLI checkpoint timed out')


def ready():
    try:
        data=json.loads((runtime/'desktop.json').read_text())
        return data if data.get('state')=='ready' else None
    except (OSError,ValueError):
        return None


def start():
    stream=(OUT/f'launch-{len(results)}.log').open('wb')
    child=subprocess.Popen([sys.executable,'-I','-B',str(ROOT/'KFPS.Editor/editor.py'),
        '--browser','--background','--from-kfps','--runtime-root',str(runtime),'--project-id','CLI.fabric-project.json'],
        stdout=stream,stderr=stream,creationflags=subprocess.CREATE_NO_WINDOW)
    owned.append(child)
    state=wait(ready)
    host=psutil.Process(state['pid'])
    marker=json.loads((runtime/'browser-profile/kfps-owner.json').read_text())
    browser=psutil.Process(marker['pid'])
    owned.extend([host,browser])
    wait(lambda: (runtime/'autosave.json').is_file())
    stream.close()
    return child,host,browser


try:
    child,host,browser=start()
    children=browser.children(recursive=True)
    pids=[browser.pid,*[p.pid for p in children]]
    assert len(pids)>2
    host.kill()
    wait(lambda:not any(psutil.pid_exists(pid) for pid in pids),15)
    child.wait(15)
    results.append({'case':'real CLI host interruption terminates entire owned browser job','passed':True})
    (runtime/'desktop.json').unlink(missing_ok=True)
    child,host,browser=start()
    children=browser.children(recursive=True)
    hwnd=wait(lambda:window_for_process(browser.pid))
    user.PostMessageW(hwnd,0x10,0,0)
    child.wait(20)
    wait(lambda:not any(p.is_running() for p in [host,browser,*children]),15)
    assert not (runtime/'desktop.json').exists()
    results.append({'case':'real CLI restart and normal window close release host, children and marker','passed':True})
finally:
    for process in reversed(owned):
        try:
            if isinstance(process,subprocess.Popen):
                if process.poll() is None: process.kill()
                process.wait(10)
            elif process.is_running():
                process.kill()
        except psutil.Error:
            pass
    (OUT/'results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
