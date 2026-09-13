"""Real QtWebEngine review with a local OAuth/delivery fixture; no Discord sends."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import sys
import threading
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from kfps_ui.support_log_bundle import collect_retained_log_bundle
from kfps_ui.support_report import build_support_report, save_handoff
from kfps_ui.support_window import ReportWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "runtime/test-runs"):
        raise ValueError("Use a fresh isolated test-run directory.")
    output.mkdir(parents=True)
    fixture = output / "installation"
    logs = fixture / "runtime/qml-transfer-logs"
    logs.mkdir(parents=True)
    rng = random.Random(30178)
    for index in range(3):
        raw = rng.randbytes(1024 * 1024).hex()
        # Short synthetic words avoid intentionally triggering credential/hash redaction.
        lines = [" ".join(raw[word:word+8] for word in range(start,min(start+64,len(raw)),8))
                 for start in range(0,len(raw),64)]
        (logs / f"transfer-20260913-01000{index}.log").write_text("\n".join(lines) + "\n",encoding="ascii")
    report = build_support_report(fixture,{"page":"editor","version":"test","log":""},since=time.time(),collect=lambda:{})
    attachment = collect_retained_log_bundle(fixture)
    report["private_logs"] = attachment[0]
    save_handoff(fixture,report,log_attachment=attachment)
    package = fixture / "runtime/support-reports" / report["id"] / "report.kfps-report.json.gz"
    assert package.stat().st_size > 750 * 1024, "Must exercise the old manual-only path"
    public = ROOT / "tools/support_worker/public"
    events = []
    ticket = str(uuid.uuid4())
    approved = False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            path = self.path.split("?",1)[0]
            if path == "/auth/start":
                events.append("sign-in")
                self.send_response(303)
                self.send_header("Location","/")
                self.send_header("Set-Cookie","qa_user=1; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600")
                self.end_headers()
                return
            if path == "/api/config":
                body = json.dumps({"enabled":True,"join_url":"https://discord.gg/XT8dG8bDKy"}).encode()
                mime = "application/json"
            elif path == "/api/session":
                authenticated = "qa_user=1" in self.headers.get("Cookie","")
                body = json.dumps({"authenticated":authenticated,"name":"Native Test","csrf":"fixture"}).encode()
                mime = "application/json"
            elif path == "/" or path[1:] in {p.name for p in public.iterdir() if p.is_file()}:
                selected = public / (path[1:] or "index.html")
                body = selected.read_bytes()
                mime = "text/html" if selected.suffix==".html" else "text/css" if selected.suffix==".css" else "image/png" if selected.suffix==".png" else "text/javascript"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            if self.path == '/api/native-auth/start':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Set-Cookie', 'qa_pending=1; Path=/; HttpOnly; SameSite=Lax; Max-Age=300')
                self.end_headers()
                self.wfile.write(json.dumps({'id':ticket,'code':'1234-ABCD','expires_at':int(time.time()*1000)+300000,'url':f'http://127.0.0.1:{server.server_port}/auth/native?ticket={ticket}'}).encode())
                return
            if self.path == '/api/native-auth/poll':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                if approved:
                    self.send_header('Set-Cookie', 'qa_user=1; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600')
                self.end_headers()
                self.wfile.write(json.dumps({'status':'ready' if approved else 'pending'}).encode())
                return
            events.append("unexpected-upload")
            self.send_error(400)
    server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    origin = f"http://127.0.0.1:{server.server_port}"
    window = ReportWindow(fixture,origin=origin,background=True)
    window.open_report(report["id"],confirm=False)
    checks = []
    failure = []
    phase = 0
    expected_epoch = 0
    last_progress = None
    busy = False
    deadline = time.monotonic()+120
    def check(value,name):
        if not value:
            raise AssertionError(name)
        checks.append(name)
    def evaluate(script,callback):
        def completed(value):
            try:
                value = json.loads(value) if isinstance(value, str) else None
            except (TypeError, ValueError):
                value = None
            callback(value)
        window.page.runJavaScript('JSON.stringify((()=>{return ' + script + ';})())',completed)
    def tick():
        nonlocal busy,last_progress
        if time.monotonic()>deadline:
            failure.append(f"Timeout at phase {phase}")
            app.quit()
            return
        progress=(phase,window.epoch,window.retry.isVisible())
        if progress!=last_progress:
            last_progress=progress
            (output / 'progress.json').write_text(json.dumps({'phase':phase,'epoch':window.epoch,'retry':window.retry.isVisible(),'elapsed':round(time.monotonic()-(deadline-120),2)}))
        if phase == 4 or busy:
            return
        if window.retry.isVisible():
            failure.append(f'Reviewer requested retry at phase {phase}')
            app.quit()
            return
        busy = True
        evaluate("({ready:!!window.KFPSReportTransfer,logs:document.getElementById('private-log-state')?.textContent||'',identity:document.getElementById('identity')?.textContent||'',description:document.getElementById('description')?.value||'',url:location.href})",advance)
    def advance(value):
        nonlocal phase,busy,window,expected_epoch
        busy = False
        try:
            if not isinstance(value,dict) or not value.get("ready") or "3 retained" not in value.get("logs",""):
                return
            if window.epoch<expected_epoch or window.timer.isActive():
                return
            if phase == 0:
                check("#" not in value["url"],"large report never placed in URL")
                check(not events,"automatic attachment does not upload logs")
                check(not window.retry.isVisible(),"native handoff finishes without retry or file selection")
                window.view.grab().save(str(output / "native-large-ready.png"))
                phase = 1
                expected_epoch=window.epoch
                evaluate("(()=>{document.getElementById('description').value='Edited native report text';document.getElementById('description').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('login').click();return true;})()",lambda _:None)
            elif phase == 1 and "Signed in as" in value["identity"]:
                check(value["description"]=="Edited native report text","report text and all logs survive sign-in")
                check(window.epoch==expected_epoch,"default-browser authorization never navigates the native report")
                phase = 2
                expected_epoch=window.epoch+1
                window.reload_review()
            elif phase == 2:
                check(value["description"]=="Edited native report text","refresh preserves edited report")
                phase = 3
                expected_epoch=window.epoch+1
                evaluate("(()=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,t=db.transaction('bundle','readwrite');t.objectStore('bundle').clear();t.oncomplete=()=>{db.close();location.reload();};};})()",lambda _:None)
            elif phase == 3:
                # Native import restores a missing browser-local archive without losing edits.
                check(value["description"]=="Edited native report text","missing local archive restores automatically without overwriting edits")
                check(events==["sign-in"],"no unsolicited report submission")
                window.view.grab().save(str(output / "native-large-after-signin.png"))
                phase = 4
                window.shutdown()
                window.hide()
                QTimer.singleShot(500,reopen)
            elif phase == 5:
                check("Signed in as Native Test" in value["identity"],"Discord-style session persists across reviewer restart")
                check(value['description']=='Edited native report text','edited report survives native reviewer restart')
                check(package.is_file(),"closing reviewer preserves local report package")
                app.quit()
        except Exception as error:
            failure.append(str(error))
            app.quit()
    def reopen():
        nonlocal phase,window,expected_epoch
        window=ReportWindow(fixture,origin=origin,background=True)
        window.open_report(report["id"],confirm=False)
        phase=5
        expected_epoch=0
    timer=QTimer()
    timer.setInterval(150)
    timer.timeout.connect(tick)
    timer.start()
    def open_browser(url):
        nonlocal approved
        check(url.toString()==origin+'/auth/native?ticket='+ticket,'native sign-in uses system default browser with approval URL only')
        events.append('sign-in')
        approved=True
        return True
    try:
        with patch('kfps_ui.support_window.QDesktopServices.openUrl',side_effect=open_browser):
            app.exec()
    finally:
        timer.stop()
        window.shutdown()
        server.shutdown()
        server.server_close()
    result={"passed":not failure,"checks":checks,"failures":failure,"packageBytes":package.stat().st_size,"logFiles":3,"realDiscordPosts":0,"fixtureEvents":events}
    (output / "results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
