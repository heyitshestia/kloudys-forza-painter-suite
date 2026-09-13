"""Real Qt/WebChannel close, modal wait, recovery failure and dropped-reply tests."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
output = Path(sys.argv[1]).resolve()
if not output.is_relative_to(ROOT / "runtime/test-runs"):
    raise ValueError("Use an isolated test-run output")
output.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_editor.host import EditorDesktop

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
host = EditorDesktop(ROOT, output / "profile")
from native_window_policy import keep_in_background
keep_in_background(host)
results = []
dialogs = []
choice = QMessageBox.StandardButton.Cancel


def pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)


def wait(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise TimeoutError("Native close test condition did not finish")


def js(expression):
    values = []
    host.page.runJavaScript(f"JSON.stringify(({expression}))", values.append)
    wait(lambda: bool(values), timeout=10)
    return json.loads(values[0]) if values[0] else None


def async_js(body):
    js("(() => { window.__closeTest = null; (async () => { " + body
       + " })().then(() => window.__closeTest = {ok:true}, error => window.__closeTest = {error:String(error)}); return true; })()")
    wait(lambda: js("window.__closeTest") is not None, timeout=40)
    result = js("window.__closeTest")
    assert result.get("ok"), result


def message(kind, title, text, *args):
    dialogs.append({"kind": kind, "title": title})
    return choice


def begin_case():
    dialogs.clear()
    host._allow_close = False
    host.show()


try:
    assert host.start({"mode": "activate", "project": ""})
    host.resize(1440, 950)
    host.show()
    wait(lambda: host._ready, timeout=60)
    host._message_box = message
    async_js("""
      localStorage.setItem('kloudyFabricStartupHelpConfirmed', 'true');
      KfpsEditorPreferences.setItem('kloudyFabricProjectSharingAcknowledged', '1');
      KfpsEditorPreferences.setItem('kloudyFabricLanguageNoticeAcknowledged', '1');
      await KfpsEditorPreferences.flush(); await writeStartupHelpConfirmed();
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    """)
    pump(.8)
    js("""(() => {
      window.__originalCompleted = KfpsDesktopBridge.completed;
      window.__dropReplies = true;
      KfpsDesktopBridge.completed = (...args) => { if (!window.__dropReplies) window.__originalCompleted(...args); };
      return true;
    })()""")
    host.activate_request({"mode": "new", "project": ""})
    open_id = host._open_request_id
    wait(lambda: js(f"KfpsDesktop.outcome({json.dumps(open_id)}).state") == "complete")
    host._open_deadline()
    wait(lambda: not host._commands)
    assert not host._open_uncertain and not dialogs
    js("(() => { window.__dropReplies = false; KfpsDesktopBridge.completed = window.__originalCompleted; return true; })()")
    results.append({"case":"lost open reply recovered from outcome without replay", "passed":True})
    host.activate_request({"mode": "activate", "project": "missing-test-project.fabric-project.json"})
    wait(lambda: not host._commands)
    assert any(item["title"] == "Could not open in editor" for item in dialogs)
    results.append({"case":"failed open presented and queue released", "passed":True})
    dialogs.clear()
    async_js("""
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      documentDirty = false; await startBlankCanvas();
      await loadPayload({shapes:Array.from({length:300}, (_, i) => ({type:1048677,
        data:[(i%20)*15-150,Math.floor(i/20)*15-100,.15,.15,i%90,0,0],
        color:[60+i%180,130,200,255]}))});
      const ref = document.createElement('canvas'); ref.width=64; ref.height=96;
      ref.getContext('2d').fillRect(0,0,64,96);
      await editorReference.loadOverlayImageFromUrl(ref.toDataURL(), 'close-test-reference.png');
      window.__expectedCloseShapes = JSON.stringify(snapshotShapes());
      window.__expectedCloseReference = editorReference.sourceOverlayProjectState().data_url;
      documentDirty = true;
    """)
    host.close_timer.setInterval(1500)
    choice = QMessageBox.StandardButton.Save
    host.close()
    wait(lambda: js("document.getElementById('textPromptDialog').open"))
    pump(3.5)
    assert host.isVisible() and host._closing and host._close_phase == "user-wait"
    assert [item["title"] for item in dialogs] == ["Save before closing?"], dialogs
    host.grab().save(str(output / "live-save-name-prompt.png"))
    js("(() => { document.getElementById('textPromptCancel').click(); return true; })()")
    wait(lambda: not host._closing)
    assert host.isVisible() and not host._commands and not host._allow_close
    assert not list((output / "profile/projects").glob("*.fabric-project.json"))
    results.append({"case":"cancel live name prompt then retry", "passed":True})
    host.close()
    wait(lambda: js("document.getElementById('textPromptDialog').open"))
    js("(() => { document.getElementById('textPromptInput').value='Native close lifecycle'; document.getElementById('textPromptDialog').querySelector('form').requestSubmit(); return true; })()")
    wait(lambda: not host.isVisible(), timeout=25)
    assert host._allow_close and not host._commands
    projects = list((output / "profile/projects").glob("*.fabric-project.json"))
    assert len(projects) == 1, projects
    saved = json.loads(projects[0].read_text(encoding="utf-8"))
    assert len(saved["shapes"]) == 300
    results.append({"case":"save with live name wait", "passed":True, "dialogWaitSeconds":3.5, "deadlineMs":1500, "shapes":300})

    begin_case()
    async_js("""
      documentDirty = false; await startBlankCanvas();
      const data = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent('Native close lifecycle.fabric-project.json')}`);
      await loadProjectPayload(data.payload, data.name, { receipt: data.receipt });
      if (JSON.stringify(snapshotShapes()) !== window.__expectedCloseShapes || !editorReference.image
          || editorReference.sourceOverlayProjectState().data_url !== window.__expectedCloseReference)
        throw Error('Saved shapes/reference did not reopen');
      fitDesignView();
    """)
    pump(1)
    host.grab().save(str(output / "reopened-project.png"))
    results.append({"case":"saved project reopened through editor", "passed":True})

    begin_case()
    js("documentDirty = true")
    choice = QMessageBox.StandardButton.Discard
    async_js("window.__realFlush = KfpsEditorPreferences.flush; KfpsEditorPreferences.flush = async () => false;")
    host.close()
    wait(lambda: not host._closing)
    assert host.isVisible() and not host._allow_close
    assert any(item["title"] == "Could not finish saving" for item in dialogs), dialogs
    async_js("KfpsEditorPreferences.flush = window.__realFlush; await KfpsEditorPreferences.flush();")
    results.append({"case":"settings failure keeps window open", "passed":True})

    begin_case()
    js("(() => { window.__realExecute = KfpsDesktop.execute; KfpsDesktop.execute = function(id, operation, payload) { if (operation === 'close') { window.__droppedRequest = id; return; } return window.__realExecute.call(this,id,operation,payload); }; return true; })()")
    host.close()
    wait(lambda: any(item["title"] == "Editor is not responding" for item in dialogs))
    assert host.isVisible() and not host._closing and not host._commands
    js("(() => { KfpsDesktopBridge.completed(window.__droppedRequest, JSON.stringify({ok:true,value:{ok:true}})); KfpsDesktop.execute = window.__realExecute; return true; })()")
    pump(.3)
    assert host.isVisible() and not host._allow_close
    results.append({"case":"lost final reply and late success after keep-open", "passed":True})

    begin_case()
    js("(() => { KfpsDesktop.execute = function(id, operation, payload) { if (operation === 'state') return; return window.__realExecute.call(this,id,operation,payload); }; return true; })()")
    host.close()
    wait(lambda: any(item["title"] == "Editor is not responding" for item in dialogs))
    assert host.isVisible() and not host._closing and not host._commands
    js("(() => { KfpsDesktop.execute = window.__realExecute; return true; })()")
    results.append({"case":"lost state reply", "passed":True})

    begin_case()
    choice = QMessageBox.StandardButton.Discard
    host.close()
    wait(lambda: not host.isVisible())
    assert host._allow_close and not host._commands
    recovery = json.loads((output / "profile/autosave.json").read_text(encoding="utf-8"))
    assert recovery, "Discard must retain recovery"
    results.append({"case":"retry then discard keeps recovery", "passed":True})
finally:
    (output / "results.json").write_text(json.dumps({"results":results,"dialogs":dialogs},indent=2),encoding="utf-8")
    host.shutdown()
    host.hide()
print(json.dumps(results))
