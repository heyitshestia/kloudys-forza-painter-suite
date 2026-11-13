"""Controlled failures against real form assets, never the live support service."""
from __future__ import annotations

import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src"),
                str(ROOT / "KFPS.Editor/web/tests"), str(ROOT)]
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kfps_ui.support_report import build_support_report, save_handoff
from kfps_ui.support_window import ReportWindow
from native_window_policy import keep_in_background


def main():
    output = Path(sys.argv[1]).resolve()
    if output.exists() or not output.is_relative_to(ROOT / "runtime/test-runs"):
        raise ValueError("Use a new runtime/test-runs directory")
    output.mkdir(parents=True)
    fixture = output / "installation"
    report = build_support_report(fixture, {"page": "editor", "version": "test", "log": ""},
                                  since=time.time(), collect=lambda: {})
    save_handoff(fixture, report)
    source = fixture / "runtime/support-reports" / report["id"] / "report.json"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    log_path = output / "report-window.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    logger = logging.getLogger("kfps-report-window")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    public = ROOT / "tools/support_worker/public"
    failures, checks, terminations, foreground, requests = [], [], [], [], []
    network_failure = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/" and network_failure:
                self.send_error(503)
                return
            if path == "/api/config":
                body, mime = b'{"enabled":true,"join_url":"https://example.invalid/support"}', "application/json"
            elif path == "/api/session":
                body, mime = b'{"authenticated":false}', "application/json"
            elif path == "/" or path[1:] in {p.name for p in public.iterdir() if p.is_file()}:
                selected = public / (path[1:] or "index.html")
                body = selected.read_bytes()
                mime = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                        ".png": "image/png"}.get(selected.suffix, "application/octet-stream")
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            requests.append(self.path)
            self.send_error(400)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = ReportWindow(fixture, origin=f"http://127.0.0.1:{server.server_port}", background=True)
    keep_in_background(window)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
    window.page.renderProcessTerminated.connect(
        lambda status, code: terminations.append({"status": status.name, "code": code}))
    window.open_report(report["id"], confirm=False)
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    started = time.monotonic()
    phase, busy, resume_at = 0, False, 0.0
    observations = {}
    owned_children = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def ready():
        return bool(window.identifier and not window.timer.isActive() and window.status.isHidden())

    def snapshot(name):
        window.grab().save(str(output / name))

    def draft_checked(value):
        nonlocal busy, phase, network_failure
        busy = False
        try:
            check(value == "Crash recovery draft", "draft survives renderer restart" if phase == 3
                  else "draft survives failed load and retry")
            if phase == 3:
                snapshot("03-renderer-recovered.png")
                network_failure = True
                phase = 4
                window.reload_review()
            else:
                snapshot("05-network-recovered.png")
                check(hashlib.sha256(source.read_bytes()).hexdigest() == original_hash,
                      "saved report is unchanged")
                check(not requests, "no submissions")
                phase = 6
                window.page.runJavaScript("const d=document.getElementById('description');d.value='lag';"
                                          "d.dispatchEvent(new Event('input',{bubbles:true}));true;",
                                          lambda _: window.reload_review())
        except Exception as error:
            failures.append(str(error))
            app.quit()

    def inspect_draft(value):
        nonlocal phase, busy, window
        busy = False
        try:
            value = json.loads(value)
            if phase == 6:
                check(value["description"] == "lag", "incomplete draft survives reload")
                observations["short_draft_after_reload"] = value
                snapshot("06-short-draft.png")
                phase = 7
                window.page.runJavaScript("const d=document.getElementById('description');"
                    "d.value='Preserve this description';document.getElementById('include').checked=false;"
                    "d.dispatchEvent(new Event('input',{bubbles:true}));true;", lambda _: window.reload_review())
            elif phase == 7:
                check(value["description"] == "Preserve this description" and value["version"] == "test"
                      and value["include"] is False, "unchecked consent preserves local technical context")
                observations["consent_off_after_reload"] = value
                snapshot("07-consent-off.png")
                phase = 8
                # The normal Report button creates a fresh report ID on every request.
                next_report = build_support_report(fixture, {"page": "editor", "version": "test", "log": ""},
                                                   since=time.time(), collect=lambda: {})
                save_handoff(fixture, next_report)
                window.shutdown()
                window.hide()
                window = ReportWindow(fixture, origin=f"http://127.0.0.1:{server.server_port}", background=True)
                keep_in_background(window)
                window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
                window.open_report(next_report["id"])
            elif phase == 8:
                observations["new_report_after_reopen"] = value
                check(value["description"] == "Preserve this description", "fresh-ID reopen preserves old draft")
                check(value["pending"], "fresh-ID reopen requires a recovery choice")
                snapshot("08-new-report.png")
                phase = 9
                window.page.runJavaScript("document.getElementById('resume-report').click()")
            else:
                check(value["description"] == "Preserve this description" and not value["pending"],
                      "resume keeps old draft and dismisses replacement")
                check(not foreground, "test never takes foreground")
                app.quit()
        except Exception as error:
            failures.append(str(error))
            app.quit()

    def tick():
        nonlocal phase, busy, resume_at, network_failure
        try:
            if time.monotonic() - started > 60:
                raise TimeoutError(f"phase {phase}")
            if user32.GetForegroundWindow() == int(window.winId()):
                foreground.append(phase)
                window.lower()
            if busy or time.monotonic() < resume_at:
                return
            if phase == 0 and ready():
                rendered = window.view.grab().toImage()
                colours = {rendered.pixel(x, y) for y in range(0, rendered.height(), 4)
                           for x in range(0, rendered.width(), 4)}
                check(len(colours) > 50, "native form actually renders nonblank pixels")
                snapshot("01-ready.png")
                window.page.runJavaScript("const d=document.getElementById('description');"
                                          "d.value='Crash recovery draft';d.dispatchEvent(new Event('input',{bubbles:true}));")
                window.showMinimized()
                phase = 1
                resume_at = time.monotonic() + 1
            elif phase == 1:
                user32.ShowWindow(int(window.winId()), 4)  # SW_SHOWNOACTIVATE
                window.lower()
                pid = window.page.renderProcessPid()
                renderer = psutil.Process(pid)
                check(renderer.name().lower() == "qtwebengineprocess.exe" and
                      os.getpid() in {parent.pid for parent in renderer.parents()} and
                      "--type=renderer" in renderer.cmdline(), "fault target is this test's renderer")
                owned_children.extend(psutil.Process().children(recursive=True))
                renderer.terminate()
                phase = 2
            elif phase == 2 and window.retry.isVisible():
                check(window.isVisible() and not window.closed, "native reviewer survives renderer termination")
                check(bool(terminations), "actual renderer termination signal received")
                check(window.view.isHidden() and window.browser_button.isVisible() and window.saved_button.isVisible(),
                      "native recovery controls survive a blank renderer")
                observations["renderer_failure_message"] = window.status.text()
                snapshot("02-renderer-failed.png")
                with patch("kfps_ui.support_window.open_browser_url", return_value="failed") as fallback:
                    QTest.mouseClick(window.browser_button, Qt.MouseButton.LeftButton)
                    check("could not open" in window.status.text(), "failed browser launch is explained")
                    check(fallback.call_args.args[0].toString() == window.origin + "/",
                          "browser fallback sends no report contents or credentials")
                with patch("kfps_ui.support_window.open_browser_url", return_value="browser"):
                    QTest.mouseClick(window.browser_button, Qt.MouseButton.LeftButton)
                    check("do not transfer automatically" in window.status.text(),
                          "successful browser fallback explains draft handoff limits")
                with patch("kfps_ui.support_window.QDesktopServices.openUrl", return_value=True) as folder:
                    QTest.mouseClick(window.saved_button, Qt.MouseButton.LeftButton)
                    check(Path(folder.call_args.args[0].toLocalFile()) == fixture / "runtime/support-reports",
                          "saved reports opens only this test installation")
                with patch("kfps_ui.support_window.QDesktopServices.openUrl", return_value=False):
                    QTest.mouseClick(window.saved_button, Qt.MouseButton.LeftButton)
                    check("could not be opened" in window.status.text(), "failed folder launch is explained")
                phase = 3
                window.reload_review()
            elif phase in (3, 5) and ready():
                busy = True
                window.page.runJavaScript("document.getElementById('description')?.value", draft_checked)
            elif phase == 4 and window.retry.isVisible():
                observations["network_failure_message"] = window.status.text()
                snapshot("04-network-failed.png")
                network_failure = False
                phase = 5
                window.reload_review()
            elif phase in (6, 7, 8, 9) and ready():
                busy = True
                window.page.runJavaScript("JSON.stringify({description:document.getElementById('description').value,"
                    "version:document.getElementById('version').value,include:document.getElementById('include').checked,"
                    "pending:!document.getElementById('incoming-report').hidden})",
                    inspect_draft)
        except Exception as error:
            failures.append(f"{type(error).__name__}: {error}")
            app.quit()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(tick)
    timer.start()
    with patch("kfps_ui.support_window.open_browser_url", side_effect=AssertionError("Unexpected browser launch")):
        try:
            app.exec()
        finally:
            timer.stop()
            owned_children.extend(psutil.Process().children(recursive=True))
            window.shutdown()
            window.hide()
            server.shutdown()
            server.server_close()
            thread.join(2)
            handler.flush()
            logger.removeHandler(handler)
            handler.close()
    _, remaining = psutil.wait_procs(owned_children, timeout=3)
    live_children = [{"pid": p.pid, "name": p.name()} for p in remaining if p.is_running()]
    if live_children:
        failures.append("Test renderer children survived cleanup")
    result = {"passed": not failures, "checks": checks, "failures": failures,
              "terminations": terminations, "foreground_violations": foreground,
              "unexpected_posts": requests, "observations": observations,
              "live_test_children": live_children,
              "elapsed_seconds": round(time.monotonic() - started, 2)}
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
