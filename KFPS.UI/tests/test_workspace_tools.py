import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QObject, Qt, Signal, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QLineEdit, QListWidget, QPushButton, QLabel
from kfps_ui.app_controller import AppController
from kfps_ui.workspace_tools import WorkspaceTools


class Page(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    def runJavaScript(self, code, callback):
        self.calls.append(code)
        callback({'token': 'document-1', 'commands': [
            {'id': 'save', 'label': 'Save project', 'enabled': True, 'shortcut': 'Alt+S'}
        ]} if '.list()' in code else True)


class Shell(QMainWindow):
    def __init__(self):
        super().__init__()
        self._selected = 'Editor'
        self.owners = {'Editor': SimpleNamespace(page=Page())}

    def show_surface(self, name, **kwargs):
        self._selected = name


class WorkspaceToolTests(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()
        self.shell.setProperty('workspaceColors', dict(background='#202020', surface='#303030',
            text='#ffffff', border='#666666', accent='#ef6ba3', accentText='#000000', font='Segoe UI'))
        self.tools = WorkspaceTools(SimpleNamespace(app_root=Path('.')), AppController(), {})
        self.tools.window = self.tools.shell = self.shell

    def tearDown(self):
        self.tools.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        self.shell.close()
        self.shell.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def command(self):
        self.tools.openCommands()
        dialog = next(iter(self.tools._dialogs))
        search = dialog.findChild(QLineEdit, 'WorkspaceCommandSearch')
        search.setText('Save project')
        return dialog, dialog.findChild(QPushButton)

    def test_current_binding_and_dispatch(self):
        dialog, button = self.command()
        items = dialog.findChild(QListWidget)
        self.assertIn('Alt+S', items.item(0).text())
        page = self.shell.owners['Editor'].page
        button.click()
        self.assertIn('execute("save","document-1")', page.calls[-1])

    def test_stale_owner_cannot_execute(self):
        dialog, button = self.command()
        original = self.shell.owners['Editor'].page
        self.shell.owners['Editor'] = SimpleNamespace(page=Page())
        button.click()
        self.assertEqual(1, len(original.calls))
        self.assertFalse(button.isEnabled())

    def test_stale_active_tab_cannot_execute(self):
        dialog, button = self.command()
        self.shell._selected = 'KFPS'
        button.click()
        self.assertFalse(button.isEnabled())

    def test_settings_navigate_without_mutating_preferences(self):
        seen = []
        self.tools.settingRequested.connect(seen.append)
        row = next(r for r in self.tools._commands() if r['id'] == 'setting:chrome')
        row['action']()
        self.assertEqual(['chrome'], seen)
        self.assertEqual('settings', self.tools.controller.currentPage)

    def test_task_panel_closes_and_reopens_without_duplicate_connection(self):
        self.tools.openTasks()
        first = self.tools._task_dialog
        first.reject()
        self.assertIsNone(self.tools._task_dialog)
        self.tools.openTasks()
        self.assertIsNot(first, self.tools._task_dialog)
        self.tools.journal.changed.emit()

    def test_serialized_web_values_and_invalid_payload(self):
        self.assertEqual({'ok': True}, self.tools._web_value('{"ok":true}'))
        self.assertIsNone(self.tools._web_value('not json'))
        page = self.shell.owners['Editor'].page
        def script(code, callback):
            page.calls.append(code)
            callback(json.dumps({'token': 'one', 'commands': [dict(id='save', label='Save project', enabled=True)]})
                     if '.list()' in code else '{"ok":true}')
        page.runJavaScript = script
        dialog, button = self.command()
        button.click()
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_repeated_command_open_reuses_dialog(self):
        self.tools.openCommands()
        first = self.tools._command_dialog
        self.tools.openCommands()
        self.assertIs(first, self.tools._command_dialog)
        self.assertEqual(1, len(self.tools._dialogs))

    def test_scrollbar_and_progress_follow_live_theme(self):
        self.tools.openTasks()
        dialog = self.tools._task_dialog
        self.assertIn('QScrollBar::handle', dialog.styleSheet())
        self.assertIn('QProgressBar::chunk', dialog.styleSheet())
        colours = dict(self.shell.property('workspaceColors'), accent='#125abc')
        self.shell.setProperty('workspaceColors', colours)
        self.tools._refresh_themes()
        self.assertIn('#ff125abc', dialog.styleSheet())
        self.assertNotIn('#ffef6ba3', dialog.styleSheet())

    def test_task_cancel_error_remains_visible(self):
        class Worker(QObject):
            changed = Signal()
            running = False
            status = 'Working'
        source = Worker()
        def fail():
            raise OSError('Checkpoint is busy; retry later')
        self.tools.journal.watch('test', source, label='Test', page='create', cancel=fail)
        source.running = True
        source.changed.emit()
        self.tools.openTasks()
        dialog = self.tools._task_dialog
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Stop safely').click()
        self.assertTrue(any('Checkpoint is busy' in label.text() for label in dialog.findChildren(QLabel)))
        self.assertTrue(source.running)

    def test_web_activity_does_not_poll_frozen_owner_or_when_panel_closed(self):
        page = self.shell.owners['Editor'].page
        page.lifecycleState = lambda: SimpleNamespace(name='Frozen')
        self.tools._poll_web_activity()
        self.assertEqual([], page.calls)
        self.tools.openTasks()
        self.assertEqual([], page.calls)


if __name__ == '__main__':
    unittest.main()
