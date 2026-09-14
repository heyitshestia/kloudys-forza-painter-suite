"""Real QtWebEngine review with a local OAuth/delivery fixture; no Discord sends."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import json
import logging
from logging.handlers import RotatingFileHandler
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
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kfps_ui.support_log_bundle import collect_retained_log_bundle
from kfps_ui.support_report import build_support_report, save_handoff
from kfps_ui.support_window import ReportWindow, ReportPage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--browser-mode", choices=("direct", "handler", "manual", "silent", "real-browser"), default="direct")
    parser.add_argument("--display-language", choices=("en", "ko"), default="en")
    parser.add_argument("--clock-offset-ms", type=int, default=-2000)
    parser.add_argument("--initial-auth-failure", action="store_true")
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
    editor = fixture / "runtime/fabric-editor"
    editor.mkdir(parents=True)
    (editor / "desktop.log").write_text("Synthetic editor startup failure\n")
    (editor / "desktop.json").write_text(json.dumps({"pid":4294967294,"state":"starting"}))
    (editor / "desktop.lock").write_text("4294967294\nPRIVATE_NAME\nPRIVATE_HOST\n")
    report = build_support_report(fixture,{"page":"editor","version":"test","log":""},since=time.time(),collect=lambda:{})
    attachment = collect_retained_log_bundle(fixture, snapshot=report["technical"], session_logs={"app":"Synthetic pending app event"})
    report["private_logs"] = attachment[0]
    save_handoff(fixture,report,log_attachment=attachment)
    package = fixture / "runtime/support-reports" / report["id"] / "report.kfps-report.json.gz"
    assert package.stat().st_size > 750 * 1024, "Must exercise the old manual-only path"
    public = ROOT / "tools/support_worker/public"
    auth_log = fixture / "runtime/support-reports/report-window.log"
    log_handler = RotatingFileHandler(auth_log, maxBytes=1000000, backupCount=2, encoding="utf-8")
    logger = logging.getLogger("kfps-report-window")
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    events = []
    ticket = str(uuid.uuid4())
    approved = False
    browser_attempts = []
    manual_clicked = False
    auth_start_count = 0
    retried_auth = False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            nonlocal approved
            path = self.path.split("?",1)[0]
            if self.path == '/auth/native?ticket=' + ticket:
                approved = True
                events.append('sign-in')
                browser_attempts.append({'route':'real-browser-request','userAgent':self.headers.get('User-Agent','')})
                body = b'<!doctype html><title>KFPS Browser Launch Test</title><h1>Default browser launch verified</h1><p>This is a local synthetic test, not Discord. No report was sent. You can close this tab.</p>'
                self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body)
                return
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
            nonlocal auth_start_count
            if self.path == '/api/native-auth/start':
                auth_start_count += 1
                if args.initial_auth_failure and auth_start_count == 1:
                    self.send_response(429)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"error":"Synthetic rate limit"}')
                    return
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
    console_errors=[]
    class FixturePage(ReportPage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if level == self.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                console_errors.append({"message":message,"line":line,"source":source})
            super().javaScriptConsoleMessage(level,message,line,source)
    page_patch=patch('kfps_ui.support_window.ReportPage',FixturePage)
    page_patch.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    with patch('kfps_ui.support_window.is_korean_display_language',return_value=args.display_language=='ko'):
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
        evaluate("({ready:!!window.KFPSReportTransfer,logsReady:!document.getElementById('download-private-logs')?.hidden,language:document.documentElement?.lang,identity:document.getElementById('identity')?.textContent||'',description:document.getElementById('description')?.value||'',notice:document.getElementById('notice')?.textContent||'',url:location.href,pending:!document.getElementById('native-signin')?.hidden,link:document.getElementById('native-link')?.value||'',href:document.getElementById('native-reopen')?.getAttribute('href')||''})",advance)
    def advance(value):
        nonlocal phase,busy,window,expected_epoch,manual_clicked,retried_auth
        busy = False
        try:
            if not isinstance(value,dict) or not value.get("ready") or not value.get("logsReady"):
                return
            if window.epoch<expected_epoch or window.timer.isActive():
                return
            if phase == 0:
                check(value['language']==args.display_language,'Windows display language selects the entire form')
                check(window.korean==(args.display_language=='ko'),'native chrome matches display language')
                check("#" not in value["url"],"large report never placed in URL")
                check(not events,"automatic attachment does not upload logs")
                check(not window.retry.isVisible(),"native handoff finishes without retry or file selection")
                window.view.grab().save(str(output / "native-large-ready.png"))
                phase = 1
                expected_epoch=window.epoch
                evaluate("(()=>{const wallNow=Date.now;Date.now=()=>wallNow()+" + str(args.clock_offset_ms) + ";document.getElementById('description').value='Edited native report text';document.getElementById('description').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('login').click();return true;})()",lambda _:None)
            elif phase == 1 and args.initial_auth_failure and not retried_auth:
                if 'result=rate-limited http_status=429' not in auth_log.read_text(encoding='utf-8'):
                    return
                check(('너무 여러 번' if args.display_language=='ko' else 'Too many') in value['notice'],'localized native sign-in failure is specific')
                check(value['description']=='Edited native report text','failed sign-in preserves report text')
                window.view.grab().save(str(output / 'native-signin-error.png'))
                retried_auth = True
                evaluate("(()=>{document.getElementById('login').click();return true;})()",lambda _:None)
            elif phase == 1 and args.browser_mode in ('manual','silent') and not manual_clicked and browser_attempts and value['pending']:
                check(value['description']=='Edited native report text','blocked/silent browser launch preserves the edited draft')
                check(value['href']==origin+'/auth/native?ticket='+ticket and value['link']==value['href'],'manual and copyable links retain the same approval ticket')
                window.view.grab().save(str(output / 'native-browser-fallback.png'))
                manual_clicked = True
                def click(value):
                    if isinstance(value,dict):
                        QTest.mouseClick(window.view.focusProxy() or window.view, Qt.MouseButton.LeftButton,
                                         Qt.KeyboardModifier.NoModifier, QPoint(value['x'],value['y']))
                evaluate("(()=>{const a=document.getElementById('native-reopen');a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};})()",click)
            elif phase == 1 and "Native Test" in value["identity"]:
                if 'stage=session result=authenticated' not in auth_log.read_text(encoding='utf-8'):
                    return
                check('stage=start result=ready' in auth_log.read_text(encoding='utf-8'),'real native bridge retains sign-in stages')
                check(value["description"]=="Edited native report text","report text and all logs survive sign-in")
                check(window.epoch==expected_epoch,"default-browser authorization never navigates the native report")
                check(not value['pending'] and not value['link'] and not value['href'],'completed sign-in removes stale approval links')
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
                check("Native Test" in value["identity"],"Discord-style session persists across reviewer restart")
                check(value['language']==args.display_language,'display language persists across reviewer restart')
                check(value['description']=='Edited native report text','edited report survives native reviewer restart')
                check(package.is_file(),"closing reviewer preserves local report package")
                app.quit()
        except Exception as error:
            failure.append(str(error))
            app.quit()
    def reopen():
        nonlocal phase,window,expected_epoch
        with patch('kfps_ui.support_window.is_korean_display_language',return_value=args.display_language=='ko'):
            window=ReportWindow(fixture,origin=origin,background=True)
        window.open_report(report["id"],confirm=False)
        phase=5
        expected_epoch=0
    timer=QTimer()
    timer.setInterval(150)
    timer.timeout.connect(tick)
    timer.start()
    def open_browser(url,route):
        nonlocal approved
        check(url.toString()==origin+'/auth/native?ticket='+ticket,'native sign-in uses system default browser with approval URL only')
        browser_attempts.append({'route':route,'manual':manual_clicked})
        if route=='direct' and args.browser_mode=='handler':
            return False
        if args.browser_mode in ('manual','silent') and not manual_clicked:
            return args.browser_mode=='silent'
        events.append('sign-in')
        approved=True
        return True
    def direct_browser(executable,arguments):
        from PySide6.QtCore import QUrl
        check(executable=='C:/Synthetic Browser/browser.exe' and len(arguments)==1,'explicit default executable receives a single URL argument')
        return open_browser(QUrl(arguments[0]),'direct'),42
    try:
        with ExitStack() as stack:
            if args.browser_mode!='real-browser':
                stack.enter_context(patch('kfps_ui.support_browser.default_browser_executable',return_value='C:/Synthetic Browser/browser.exe'))
                stack.enter_context(patch('kfps_ui.support_browser.QProcess.startDetached',side_effect=direct_browser))
                stack.enter_context(patch('kfps_ui.support_browser.QDesktopServices.openUrl',side_effect=lambda url:open_browser(url,'handler')))
            app.exec()
    finally:
        timer.stop()
        window.shutdown()
        server.shutdown()
        server.server_close()
        page_patch.stop()
        log_handler.flush()
        logger.removeHandler(log_handler)
        log_handler.close()
    if not failure:
        text = auth_log.read_text(encoding='utf-8')
        check(all(secret not in text for secret in (ticket,'1234-ABCD',origin,'Native Test')),'native diagnostics omit links, codes and identity')
        retained = json.loads(gzip.decompress(collect_retained_log_bundle(fixture)[1]))
        collected = '\n'.join(file['text'] for file in retained['files'] if file['name'].startswith('report-window-'))
        check('stage=session result=authenticated' in collected,'next automatic log bundle retains sign-in diagnostics')
    if console_errors:
        failure.append('Unexpected JavaScript console errors')
    result={"passed":not failure,"checks":checks,"failures":failure,"consoleErrors":console_errors,"packageBytes":package.stat().st_size,"logFiles":attachment[0]["files"],"realDiscordPosts":0,"fixtureEvents":events,"browserMode":args.browser_mode,"displayLanguage":args.display_language,"browserAttempts":browser_attempts,"clockOffsetMs":args.clock_offset_ms,"initialAuthFailure":args.initial_auth_failure}
    (output / "results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
