import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import delete
from kfps_editor.host import EditorDesktop

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[2]

class WorkspaceEditorCloseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.host=EditorDesktop(ROOT,Path(self.temp.name))
        self.host.page=Mock();self.host.server=Mock();self.host._write_state=Mock()
        self.host._ready=True
        self.host._message_box=Mock(return_value=QMessageBox.StandardButton.Cancel)
        self.host.close=Mock()
    def tearDown(self):
        self.host.page=self.host.server=None
        self.host.shutdown();delete(self.host);self.temp.cleanup()
    def reply(self,value):
        code=self.host.page.runJavaScript.call_args.args[0]
        identifier=json.loads(code.removeprefix('window.KfpsDesktop.execute(...').removesuffix(');'))[0]
        self.host._command_result(identifier,json.dumps({'ok':True,'value':value}))
    def test_prepare_is_not_destructive_and_cancel_restores_admission(self):
        done=Mock();self.host.prepare_close(done)
        self.reply({'dirty':False,'saving':False});self.reply({'ok':True})
        done.assert_called_once_with(True);self.host.close.assert_not_called()
        self.assertFalse(self.host._allow_close);self.assertTrue(self.host._closing)
        self.host.cancel_close();self.assertFalse(self.host._closing)
    def test_user_cancel_completes_callback_once(self):
        done=Mock();self.host.prepare_close(done)
        self.reply({'dirty':True,'saving':False})
        done.assert_called_once_with(False);self.host.close.assert_not_called()
    def test_busy_download_blocks_prepare(self):
        self.host._pending_downloads.add(123)
        done=Mock();self.host.prepare_close(done)
        done.assert_called_once_with(False);self.host.page.runJavaScript.assert_not_called()
    def test_commit_requires_successful_preparation(self):
        with self.assertRaises(RuntimeError):self.host.commit_close()
        done=Mock();self.host.prepare_close(done)
        self.reply({'dirty':False,'saving':False});self.reply({'ok':True})
        self.host.commit_close();self.assertTrue(self.host._allow_close)
