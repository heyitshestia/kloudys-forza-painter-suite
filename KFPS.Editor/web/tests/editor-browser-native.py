"""Real installed-browser lifecycle qualification in an isolated DIRTY runtime."""
import base64
import json
import os
from pathlib import Path
import sys
import time
import subprocess
import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(sys.argv[1]).resolve()
assert OUT.is_relative_to(ROOT/'runtime/test-runs'), 'Use an isolated test run'
KIT = Path(sys.argv[sys.argv.index('--kit')+1]).resolve() if '--kit' in sys.argv else None
if '--public-root' in sys.argv:
    ROOT = Path(sys.argv[sys.argv.index('--public-root')+1]).resolve()
BACKGROUND = '--foreground' not in sys.argv
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT/'KFPS.Editor/src'))
sys.path.insert(0, str(ROOT))
os.environ.pop('QT_QPA_PLATFORM', None)
from PySide6.QtWidgets import QApplication, QMessageBox
if KIT:
    sys.path.insert(0, str(KIT))
    import launch as kit_launch
    kit_launch.validate_root(ROOT, KIT)
    BrowserDesktop = kit_launch.load_host(ROOT, KIT)
else:
    from kfps_editor.browser_host import BrowserDesktop
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
runtime = OUT/'runtime'
runtime.mkdir(parents=True, exist_ok=True)
(runtime/'preferences.json').write_text(json.dumps({'theme':'classic', 'settings':{
    'kloudyFabricLanguage':'en', 'kloudyFabricLanguageNoticeAcknowledged':'1',
    'kloudyFabricProjectSharingAcknowledged':'1', 'kloudyFabricEditorUpdateAcknowledged':'modernization-1'}}))
(runtime/'startup-help-confirmed.json').write_text('{}')
(runtime/'projects').mkdir(exist_ok=True)
project = {'shapes':[{'type':1048677 + i%3, 'data':[(i%10-5)*50,(i//10-2)*50,.2,.2,0,0,0],
                     'color':[40+i%180,110,180,255],'editor_id':f'browser-{i}'} for i in range(40)]}
(runtime/'projects/Browser-Test.fabric-project.json').write_text(json.dumps(project))
host = BrowserDesktop(ROOT, runtime, background=BACKGROUND, export_root=OUT/'exports')
results = []


def wait(predicate, timeout=30):
    until = time.monotonic()+timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise TimeoutError('Browser qualification checkpoint not reached')


def js(expression):
    r = host.page.sync('Runtime.evaluate', {'expression': expression, 'returnByValue':True}, timeout=30000)
    assert not r.get('exceptionDetails'), r.get('exceptionDetails')
    return r.get('result', {}).get('value')


def start_host(request):
    assert host.start(request)
    # Exercise foreground editing without raising a window over the user's work.
    # Otherwise Chromium intentionally suspends rAF in fully occluded windows.
    if BACKGROUND:
        host.page.sync('Emulation.setFocusEmulationEnabled', {'enabled':True})


def async_js(body):
    js("window.__qualification = null; (async()=>{" + body +
       "})().then(value=>window.__qualification={ok:true,value},error=>window.__qualification={error:String(error)})")
    wait(lambda: js('window.__qualification') is not None, 45)
    value = js('window.__qualification')
    assert value.get('ok'), value
    return value.get('value')


def click(selector):
    async_js("await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))); return true;")
    point = js("(()=>{const e=document.querySelector("+json.dumps(selector)+
               ");e.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
    assert js("document.querySelector("+json.dumps(selector)+
              ").contains(document.elementFromPoint("+str(point['x'])+","+str(point['y'])+"))"), (selector, point)
    host.page.sync('Input.dispatchMouseEvent', {'type':'mousePressed', 'button':'left','clickCount':1,**point})
    host.page.sync('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','clickCount':1,**point})


def key(value):
    host.page.sync('Input.dispatchKeyEvent', {'type':'keyDown','key':value})
    host.page.sync('Input.dispatchKeyEvent', {'type':'keyUp','key':value})


def idle():
    wait(lambda: js('!editorCommands.busy && !projectSaveInProgress && !exportSaveInProgress'))


def prompt(value):
    wait(lambda: js("document.getElementById('textPromptDialog').open"))
    click('#textPromptInput')
    js("document.getElementById('textPromptInput').select()")
    host.page.sync('Input.insertText', {'text':value})
    click('#textPromptConfirm')
    idle()


def nudge():
    js("selectObjects([vinylObjects()[0]]); canvas.upperCanvasEl.focus()")
    before=js('JSON.stringify(snapshotShapes())')
    key('ArrowRight')
    wait(lambda: js('JSON.stringify(snapshotShapes())') != before)
    async_js('flushPendingNudgeHistory(); return true;')
    assert js('isDocumentDirty()')


dialogs=[]
choice=QMessageBox.StandardButton.Cancel
def message(kind, title, text, *args):
    dialogs.append({'kind':kind,'title':title})
    return choice


def user_close():
    # CDP Page.close follows Chromium's ordinary beforeunload path.
    host.page.call('Page.close')


def check(name):
    results.append({'case':name,'passed':True})
    print(name, flush=True)


def stress_selection(count):
    js(f"""selectObjects(vinylObjects().slice(-{count}));
      canvas.setViewportTransform([.7,0,0,.7,canvas.width/2,canvas.height/2]);
      canvas.getActiveObject().setCoords(); styleActiveTransformControls(); canvas.renderAll();
      window.__stressBefore=JSON.stringify(snapshotShapes());
      window.__stressUntouched=JSON.stringify(snapshotShapes().slice(0,-{count}));
      window.__stressCount={count};""")
    assert js('selectedVinylObjects().length') == count
    began = time.monotonic()
    point = js("""(()=>{const a=canvas.getActiveObject(), p=a.getCenterPoint(), r=canvas.upperCanvasEl.getBoundingClientRect();
      return {x:p.x*.7+canvas.width/2+r.left,y:p.y*.7+canvas.height/2+r.top}})()""")
    host.page.sync('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','buttons':1,'clickCount':1,**point})
    for i in range(1, 17):
        host.page.sync('Input.dispatchMouseEvent', {'type':'mouseMoved','button':'left','buttons':1,
            'x':point['x']+i*3,'y':point['y']+i})
    host.page.sync('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','buttons':0,'clickCount':1,
        'x':point['x']+48,'y':point['y']+16})
    idle()
    assert js('JSON.stringify(snapshotShapes()) !== __stressBefore'), 'Large selection drag did not edit'
    assert js('JSON.stringify(snapshotShapes().slice(0,-__stressCount)) === __stressUntouched'), 'Drag changed unrelated shapes'
    js('window.__stressAfter=JSON.stringify(snapshotShapes())')
    for _ in range(3):
        click('#undoBtn')
        wait(lambda: js('!editorCommands.busy && JSON.stringify(snapshotShapes()) === __stressBefore'))
        click('#redoBtn')
        wait(lambda: js('!editorCommands.busy && JSON.stringify(snapshotShapes()) === __stressAfter'))
    js('canvas.upperCanvasEl.focus()')
    for value in ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'] * 8:
        key(value)
    async_js('flushPendingNudgeHistory(); return true;')
    assert js('snapshotShapes().every(s=>s.data.every(Number.isFinite))')
    js('fitSelectedView(); window.__resizeBefore=JSON.stringify(snapshotShapes()); canvas.getActiveObject().setCoords(); styleActiveTransformControls(); canvas.renderAll(); true')
    corner = js("""(()=>{const p=canvas.getActiveObject().oCoords.br, r=canvas.upperCanvasEl.getBoundingClientRect();
      return {x:p.x+r.left,y:p.y+r.top}})()""")
    host.page.sync('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','buttons':1,'clickCount':1,**corner})
    for i in range(1, 9):
        host.page.sync('Input.dispatchMouseEvent', {'type':'mouseMoved','button':'left','buttons':1,
            'x':corner['x']+i*2,'y':corner['y']+i})
    host.page.sync('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','buttons':0,
        'x':corner['x']+16,'y':corner['y']+8})
    idle()
    assert js('JSON.stringify(snapshotShapes()) !== __resizeBefore'), 'Large selection resize did not edit'
    js('window.__resizeAfter=JSON.stringify(snapshotShapes())')
    click('#undoBtn')
    wait(lambda: js('!editorCommands.busy && JSON.stringify(snapshotShapes()) === __resizeBefore'))
    click('#redoBtn')
    wait(lambda: js('!editorCommands.busy && JSON.stringify(snapshotShapes()) === __resizeAfter'))
    results.append({'largeSelection':count,'pointerDragSteps':16,'keyboardMoves':32,'exactUndoRedoCycles':3,
                    'handleResizeExactUndoRedo':True,'durationSeconds':round(time.monotonic()-began,2)})
    check(f'{count}-shape drag, handle resize, repeated exact undo/redo and keyboard movement')


try:
    start_host({'mode':'activate','project':'Browser-Test.fabric-project.json'})
    wait(lambda: host._ready, 60)
    try:
        wait(lambda: js('vinylObjects().length') == 40, 10)
    except TimeoutError:
        print(json.dumps(js("({count:vinylObjects().length, dialogs:[...document.querySelectorAll('dialog[open]')].map(x=>x.innerText),status:document.getElementById('status')?.innerText})")))
        raise
    results.append({'startupAndProjectOpen':True, 'shapes':40})
    screenshot = host.page.sync('Page.captureScreenshot', {'format':'png'})['data']
    (OUT/'editor.png').write_bytes(base64.b64decode(screenshot))
    state=[]
    host.command('state', {}, state.append)
    wait(lambda: bool(state))
    assert state[0]['ok'] and state[0]['value']['dirty'] is False, state
    results.append({'existingNativeCommandBridge':True})
    if '--smoke' not in sys.argv:
        host._message_box=message
        nudge()
        click('#saveProject')
        idle()
        saved=json.loads((runtime/'projects/Browser-Test.fabric-project.json').read_text())
        assert saved['shapes']==js('snapshotShapes()') and not js('isDocumentDirty()')
        check('trusted keyboard edit and Save preserve exact shapes')
        async_js("""
          const c=document.createElement('canvas');c.width=64;c.height=96;
          c.getContext('2d').fillRect(0,0,64,96);
          await editorReference.loadOverlayImageFromUrl(c.toDataURL(),'qualification.png');
          return true;
        """)
        click('#saveProjectAs')
        prompt('Browser saved copy')
        copy=runtime/'projects/Browser saved copy.fabric-project.json'
        expected=json.loads(copy.read_text())
        assert expected['shapes']==js('snapshotShapes()') and expected.get('editor_source_overlay')
        check('Save As retains reference image and shape metadata')
        click('#exportJson')
        idle()
        exported=list((OUT/'exports').rglob('*.fh6-import.json'))
        assert len(exported)==1, exported
        assert json.loads(exported[0].read_text())['shapes']==js('vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false}))')
        if KIT:
            export_id = host.module._safe_relpath(exported[0])
            assert host.module._resolve_browser_id(export_id, paths=host._server_paths) == exported[0].resolve()
            for bad_id in ('__browser_test_exports__/../runtime/preferences.json',
                           '__browser_test_exports__/C:/Windows/win.ini'):
                try:
                    host.module._resolve_browser_id(bad_id, paths=host._server_paths)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Test export traversal was accepted')
        check('Export JSON uses existing server export path')
        nudge()
        user_close()
        wait(lambda: bool(dialogs) and not host._closing)
        assert not host._allow_close and host.page.process.poll() is None
        assert dialogs[-1]['title']=='Save before closing?', dialogs
        check('browser close Cancel keeps document and process alive')
        dialogs.clear()
        choice=QMessageBox.StandardButton.Discard
        async_js('window.__realFlush=KfpsEditorPreferences.flush;KfpsEditorPreferences.flush=async()=>false;')
        user_close()
        wait(lambda: any(d['title']=='Could not finish saving' for d in dialogs) and not host._closing)
        assert not host._allow_close
        async_js('KfpsEditorPreferences.flush=window.__realFlush; await KfpsEditorPreferences.flush();')
        check('failed close flush keeps editor open')
        dialogs.clear()
        choice=QMessageBox.StandardButton.Save
        browser_pid=host.page.process.pid
        owned_children=[p.pid for p in psutil.Process(browser_pid).children(recursive=True)]
        expected_shapes=js('snapshotShapes()')
        user_close()
        wait(lambda: host._allow_close)
        assert json.loads(copy.read_text())['shapes']==expected_shapes
        assert (runtime/'autosave.json').is_file()
        assert host.shutdown()
        wait(lambda: not any(psutil.pid_exists(p) for p in [browser_pid,*owned_children]))
        check('browser close Save writes project/recovery and terminates owned processes')
        host=BrowserDesktop(ROOT,runtime,background=BACKGROUND,export_root=OUT/'exports')
        start_host({'mode':'activate','project':copy.name})
        wait(lambda: host._ready)
        wait(lambda: js('vinylObjects().length')==40)
        assert js('snapshotShapes()')==expected_shapes
        assert js('editorReference.sourceOverlayProjectState().data_url')==expected['editor_source_overlay']['data_url']
        check('same persistent profile restarts and reopens saved project/reference')
        host._message_box=message
        # A second launcher must forward to this host, never create another browser.
        if not KIT:
            process=subprocess.Popen([sys.executable,'-B',str(ROOT/'KFPS.Editor/editor.py'),
                '--browser','--background','--from-kfps','--runtime-root',str(runtime)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            wait(lambda: process.poll() is not None)
            assert process.returncode==0
            check('second CLI launch forwards to existing browser instance')
        # Large realistic scene with masks, opacity, mirrors, skew and nested groups.
        async_js("""
          const shapes=Array.from({length:3000},(_,i)=>({type:[1048677,1048678,1048706][i%3],
            data:[i%60*16-480,Math.floor(i/60)*16-400,i%7?.07:-.07,.08,i%360,i%5*.02,i===3?1:0],
            color:[80+i%160,140,190,i%3?230:120],mask:i===3,editor_id:`dense-${i}`,
            editor_group_id:`g-${Math.floor(i/100)}`,editor_group_name:'Child',
            editor_group_path:[{id:'parent',name:'Parent'},{id:`g-${Math.floor(i/100)}`,name:'Child'}]}));
          await loadProjectPayload({name:'Dense browser',shapes});
        """)
        if '--stress' in sys.argv:
            reference = async_js("""
              const source=document.createElement('canvas'); source.width=2048; source.height=2048;
              const context=source.getContext('2d'), pixels=context.createImageData(2048,2048);
              let seed=1234567;
              for(let i=0;i<pixels.data.length;i+=4){
                seed^=seed<<13; seed^=seed>>>17; seed^=seed<<5;
                pixels.data[i]=seed&255; pixels.data[i+1]=(seed>>>8)&255;
                pixels.data[i+2]=(seed>>>16)&255; pixels.data[i+3]=255;
              }
              context.putImageData(pixels,0,0);
              const c=document.createElement('canvas'); c.width=5888; c.height=2816;
              const ctx=c.getContext('2d'); ctx.imageSmoothingEnabled=false;
              ctx.drawImage(source,0,0,c.width,c.height);
              const url=c.toDataURL();
              await editorReference.loadOverlayImageFromUrl(url,'large-stress-reference.png');
              source.width=source.height=c.width=c.height=1;
              return {width:editorReference.image.width,height:editorReference.image.height,encodedBytes:url.length};
            """)
            results.append({'largeReference':reference})
        click('#saveProjectAs')
        prompt('Dense browser')
        dense_path=runtime/'projects/Dense browser.fabric-project.json'
        dense=json.loads(dense_path.read_text())
        assert len(dense['shapes'])==3000 and dense['shapes']==js('snapshotShapes()')
        host.activate_request({'mode':'activate','project':copy.name,'background':True})
        wait(lambda: js('vinylObjects().length')==40 and not host._commands)
        host.activate_request({'mode':'activate','project':dense_path.name,'background':True})
        wait(lambda: js('vinylObjects().length')==3000 and not host._commands)
        assert js('snapshotShapes()')==dense['shapes']
        check('3000-shape project with masks/nested groups saves and reopens exactly')
        if '--stress' in sys.argv:
            assert dense_path.stat().st_size > 10 * 1024 * 1024
            assert js('editorReference.sourceOverlayProjectState().data_url') == dense['editor_source_overlay']['data_url']
            for count in (1000, 2000, 3000):
                stress_selection(count)
            expected_heavy = js('snapshotShapes()')
            click('#saveProject')
            idle()
            assert json.loads(dense_path.read_text())['shapes'] == expected_heavy
            host.activate_request({'mode':'activate','project':copy.name,'background':True})
            wait(lambda: js('vinylObjects().length')==40 and not host._commands)
            host.activate_request({'mode':'activate','project':dense_path.name,'background':True})
            wait(lambda: js('vinylObjects().length')==3000 and not host._commands, 60)
            assert js('snapshotShapes()') == expected_heavy
            results.append({'heavyProjectBytes':dense_path.stat().st_size,'exactReopenAfterStress':True})
            check('large project and embedded reference survive heavy editing and exact reopen')
        (OUT/'dense-editor.png').write_bytes(base64.b64decode(host.page.sync('Page.captureScreenshot',{'format':'png'})['data']))
        nudge()
        discarded=js('snapshotShapes()')
        unchanged=dense_path.read_bytes()
        choice=QMessageBox.StandardButton.Discard
        user_close()
        wait(lambda: host._allow_close)
        assert dense_path.read_bytes()==unchanged
        recovery=json.loads((runtime/'autosave.json').read_text())
        assert recovery
        assert host.shutdown()
        check('Discard preserves saved project and retains latest recovery')
        host=BrowserDesktop(ROOT,runtime,background=BACKGROUND,export_root=OUT/'exports')
        start_host({'mode':'activate','project':''})
        wait(lambda: host._ready)
        # Recovery is offered through the existing startup prompt.
        wait(lambda: js("document.getElementById('autosaveRecoveryDialog').open"))
        click('#recoverAutosave')
        wait(lambda: js('vinylObjects().length === 3000 && recoveryAutosavePayload === null && !recoveryRestoreDepth'))
        assert js('snapshotShapes()')==discarded and js('isDocumentDirty()')
        click('#saveProject')
        idle()
        assert json.loads(dense_path.read_text())['shapes']==discarded
        check('restart recovery restores exact unsaved changes and saves to original project')
        # Sudden browser loss must release the host and retain disk recovery.
        nudge()
        interrupted=js('snapshotShapes()')
        async_js('await flushPendingAutosave(); return true;')
        host.page.process.kill()
        wait(lambda: host.page.disconnected)
        assert host.shutdown()
        host=BrowserDesktop(ROOT,runtime,background=BACKGROUND,export_root=OUT/'exports')
        start_host({'mode':'activate','project':''})
        wait(lambda: host._ready)
        wait(lambda: js("document.getElementById('autosaveRecoveryDialog').open"))
        click('#recoverAutosave')
        wait(lambda: js('vinylObjects().length === 3000 && recoveryAutosavePayload === null && !recoveryRestoreDepth'))
        assert js('snapshotShapes()')==interrupted
        check('abrupt browser loss restarts safely with exact recovered changes')
        host._message_box=message
        click('#saveProject')
        idle()
        host.activate_request({'mode':'new','project':'','background':True})
        wait(lambda: not host._commands and js('vinylObjects().length')==0)
        async_js('await loadPayload('+json.dumps(project)+');')
        nudge()
        host.close_timer.setInterval(1000)
        choice=QMessageBox.StandardButton.Save
        user_close()
        wait(lambda: js("document.getElementById('textPromptDialog').open"))
        began=time.monotonic()
        wait(lambda:time.monotonic()-began>2.5)
        assert host._closing and host._close_phase=='user-wait' and not host._allow_close
        click('#textPromptCancel')
        wait(lambda:not host._closing)
        assert not host._allow_close
        check('close Save name prompt can wait past deadline and be cancelled safely')
        user_close()
        prompt('Close saved new project')
        wait(lambda:host._allow_close)
        assert len(json.loads((runtime/'projects/Close saved new project.fabric-project.json').read_text())['shapes'])==40
        check('retry close Save writes a previously unnamed project')
    host.close()
    wait(lambda: host._allow_close)
    assert host.shutdown()
    results.append({'cleanCloseHandshake':True, 'browserExit':host.page is None})
except Exception:
    if host.page and not host._stopped:
        try:
            detail=js("({layers:vinylObjects().length,dirty:documentDirty,busy:editorCommands.busy,save:projectSaveInProgress,status:document.getElementById('status')?.innerText,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({id:d.id,text:d.innerText})),active:document.activeElement?.id})")
            (OUT/'failure.json').write_text(json.dumps(detail,indent=2))
            (OUT/'failure.png').write_bytes(base64.b64decode(host.page.sync('Page.captureScreenshot',{'format':'png'})['data']))
            print(json.dumps(detail),flush=True)
        except Exception:
            pass
    raise
finally:
    (OUT/'results.json').write_text(json.dumps(results, indent=2))
    if not host._stopped:
        host._allow_close=True
        host.shutdown()
    app.processEvents()
print(json.dumps(results, indent=2))
