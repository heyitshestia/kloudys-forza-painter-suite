"""Real Qt server / pure-stdlib client: no Qt DLLs loaded in the launch client."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtNetwork import QLocalServer

ROOT = Path(__file__).resolve().parents[3]
CLIENT = '''
import json,sys
sys.path.insert(0,sys.argv[1])
from kfps_editor.ipc import forward_before_qt
try:
    result={'accepted':forward_before_qt(sys.argv[2],{'mode':'activate'},timeout=300)}
except Exception as error:
    result={'error':type(error).__name__,'message':str(error)}
result['qtImported']=any(name.startswith(('PySide6','shiboken6')) for name in sys.modules)
print(json.dumps(result))
'''


@unittest.skipUnless(os.name == 'nt', 'Windows named pipe contract')
class PreQtIpcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def exchange(self, reply, *, listening=True, split=False, disconnect=False):
        server = QLocalServer()
        name = 'kfps-editor-' + uuid.uuid4().hex
        sockets, requests = [], []

        def connection():
            socket = server.nextPendingConnection()
            sockets.append(socket)
            pending = bytearray()

            def receive():
                pending.extend(bytes(socket.readAll()))
                if b'\n' not in pending:
                    return
                requests.append(json.loads(bytes(pending)))
                socket.readyRead.disconnect(receive)
                if disconnect:
                    socket.abort()
                elif reply is not None:
                    if split:
                        socket.write(reply[:1]); socket.flush()
                        QTimer.singleShot(15, lambda: (socket.write(reply[1:]), socket.flush()))
                    else:
                        socket.write(reply); socket.flush()
            socket.readyRead.connect(receive)
            if socket.bytesAvailable():
                receive()

        server.newConnection.connect(connection)
        if listening:
            self.assertTrue(server.listen(name), server.errorString())
        child = subprocess.Popen([sys.executable,'-I','-B','-c',CLIENT,str(ROOT/'KFPS.Editor/src'),name],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 4
            while child.poll() is None and time.monotonic() < deadline:
                self.app.processEvents(); time.sleep(.003)
            self.assertIsNotNone(child.poll(), 'Pre-Qt activation did not honor its timeout')
            stdout, stderr = child.communicate(timeout=1)
            self.assertEqual(child.returncode,0,stderr)
            result = json.loads(stdout)
            self.assertFalse(result['qtImported'],result)
            self.assertLessEqual(len(requests),1,'Activation request was replayed')
            return result, requests
        finally:
            if child.poll() is None:
                child.kill(); child.wait()
            for socket in sockets:
                socket.abort()
            server.close()

    def test_absent_instance(self):
        result, requests = self.exchange(None,listening=False)
        self.assertFalse(result['accepted']); self.assertEqual(requests,[])

    def test_accepted_and_fragmented_ack(self):
        for split in (False,True):
            result, requests = self.exchange(b'ok\n',split=split)
            self.assertTrue(result.get('accepted'),result)
            self.assertEqual(requests,[{'project':'','mode':'activate'}])

    def test_busy_bad_and_oversized_replies_are_not_absence(self):
        for reply in (b'busy\n',b'bad\n',b'x'*65,b'ok\nextra'):
            result, _ = self.exchange(reply)
            self.assertEqual(result.get('error'),'EditorConnectionError',result)

    def test_lost_ack_and_disconnect_are_not_absence(self):
        for disconnect in (False,True):
            result, _ = self.exchange(None,disconnect=disconnect)
            self.assertEqual(result.get('error'),'EditorConnectionError',result)


if __name__ == '__main__':
    unittest.main()
