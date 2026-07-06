from __future__ import annotations

from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, Signal, Slot

from .app_paths import AppPaths
from .json_service import JsonService
from .log_service import LogService


class TransferService(QObject):
    changed = Signal()
    def __init__(self,paths:AppPaths,log:LogService,jsons:JsonService,parent=None):
        super().__init__(parent);self.paths=paths;self.log=log;self.jsons=jsons;self._running=False;self._status="Ready";self._buffer=b"";self._live_log_lines=[];self._live_log="Import/export log appears here.";self._process=QProcess(self);self._process.setProcessChannelMode(QProcess.MergedChannels);self._process.readyReadStandardOutput.connect(self._read);self._process.finished.connect(self._finished)
    @Property(bool,notify=changed)
    def running(self):return self._running
    @Property(str,notify=changed)
    def status(self):return self._status
    @Property(str,notify=changed)
    def liveLog(self):return self._live_log
    @Slot(str,str,int,bool)
    def importJson(self,game,path,layers,clear_unused):
        if not path or not Path(path).is_file():self.log.append("Select a JSON before importing.","warning");return
        args=["import","--game",self._game(game),"--layer-count",str(layers),"--json",path]
        if clear_unused:args.append("--clear-unused")
        self._start(args,"Importing JSON into game")
    @Slot(str,int)
    def exportJson(self,game,layers):self._start(["export","--game",self._game(game),"--layer-count",str(layers)],"Exporting current game group")
    @staticmethod
    def _game(value):
        value=value.lower();return "fm" if value.startswith("fm") else value
    def _start(self,args,status):
        if self._running:self.log.append("A transfer job is already running.");return
        bridge=self.paths.ui_root/"bridges"/"transfer_bridge.py";self._running=True;self._status=status;self._buffer=b"";self._live_log_lines=[];self._set_live_log([status+"…"]);self.changed.emit();self.log.append(status+"…");env=QProcessEnvironment.systemEnvironment();env.insert("PYTHONUTF8","1");env.insert("KFPS_APP_ROOT",str(self.paths.app_root));self._process.setProcessEnvironment(env);self._process.setWorkingDirectory(str(self.paths.app_root));self._process.start(self.paths.python_executable,["-u",str(bridge),*args])
        if not self._process.waitForStarted(5000):self._running=False;self._status="Failed to start";self.changed.emit()
    def _read(self):
        self._buffer+=bytes(self._process.readAllStandardOutput());parts=self._buffer.split(b"\n");self._buffer=parts.pop() if parts else b""
        live_lines=[]
        for raw in parts:
            line=raw.decode("utf-8","replace").strip()
            if not line:continue
            if line.startswith("KFPS_SELECTED_JSON:") or line.startswith("WPF_SELECTED_JSON:"):
                selected=line.split(":",1)[1].strip();self.jsons.setSource(2);self.jsons.refresh();self.jsons.selectPath(selected);live_lines.append(f"Selected exported JSON: {Path(selected).name}")
            else:
                self.log.append(line,update_status=False);live_lines.append(line)
        self._set_live_log(live_lines)
    def _finished(self,code,_):
        self._running=False;self._status="Complete" if code==0 else f"Failed (exit {code})";self._set_live_log(["Transfer finished." if code==0 else f"Transfer failed with exit code {code}."]);self.changed.emit();self.jsons.refresh();self.jsons.refreshRecent();self.log.append("Transfer finished." if code==0 else f"Transfer failed with exit code {code}.","info" if code==0 else "error")
    def _set_live_log(self,lines):
        clean=[str(line or "").strip() for line in lines if str(line or "").strip()]
        if not clean:return
        self._live_log_lines.extend(clean)
        if len(self._live_log_lines)>400:del self._live_log_lines[:len(self._live_log_lines)-400]
        self._live_log="\n".join(self._live_log_lines);self.changed.emit()
    @Slot()
    def forceStop(self):
        if not self._running:return
        try:
            p=psutil.Process(int(self._process.processId()));[c.kill() for c in p.children(recursive=True)];p.kill()
        except Exception:self._process.kill()
