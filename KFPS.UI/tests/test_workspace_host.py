import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCloseEvent, QWindow
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QWidget
from shiboken6 import delete, isValid

from kfps_ui.workspace_host import WorkspaceWindow


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class Owner(QObject):
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.callbacks = []
        self.cancelled = self.committed = self.stopped_count = 0
        self.stopped = False
        self.commit_result = None
        self.prepare_error = self.commit_error = None
        self.shutdown_result = None

    def prepare_close(self, callback):
        if self.prepare_error:
            raise self.prepare_error
        self.callbacks.append(callback)

    def cancel_close(self):
        self.cancelled += 1

    def commit_close(self):
        self.committed += 1
        if self.commit_error:
            raise self.commit_error
        return self.commit_result

    def shutdown(self):
        self.stopped_count += 1
        self.stopped = True
        return self.shutdown_result


class AsyncOwner(Owner):
    closed = Signal()


class WorkspaceTests(unittest.TestCase):
    def test_tab_menu_targets_clicked_owner_and_does_not_close_sequentially(self):
        self.window.show_surface("Studio", background=True)
        menu = self.window.create_tab_menu("Editor")
        self.assertEqual([action.text() for action in menu.actions()], ["Close current", "Return to KFPS"])
        menu.actions()[0].trigger()
        self.assertEqual(len(self.a.callbacks), 1)
        self.assertEqual(self.b.callbacks, [])
        self.a.callbacks[-1](False)
        self.assertIs(self.window.owners["Editor"], self.a)
        self.assertEqual(self.a.stopped_count, 0)
        menu.actions()[1].trigger()
        self.assertEqual(self.window._selected, "KFPS")
        menu.deleteLater()

    def test_tab_menu_does_not_close_replacement_and_placeholder_close_disabled(self):
        menu = self.window.create_tab_menu("Editor")
        self.window.owners["Editor"] = self.b
        menu.actions()[0].trigger()
        self.assertEqual(self.a.callbacks, [])
        self.assertEqual(self.b.callbacks, [])
        self.window.owners["Editor"] = self.a
        home = self.window.create_tab_menu("KFPS")
        self.assertFalse(home.actions()[0].isEnabled())
        self.window._closing = True
        menu.actions()[1].trigger()
        self.assertEqual(self.window._selected, "KFPS")
        self.window._closing = False
        menu.deleteLater()
        home.deleteLater()

    def test_session_lifecycle_signals_and_menu_theme_use_existing_colors(self):
        events = []
        self.window.surfaceRetired.connect(lambda name, whole: events.append((name, whole)))
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.assertEqual(events, [("Editor", False)])
        self.window.set_session_placeholder("Editor", True)
        self.assertIn("Previous session", self.window.surfaces["Editor"].text())
        self.window.set_session_placeholder("Studio", True)
        self.assertIs(self.window.owners["Studio"], self.b)
        self.main.setProperty("workspaceColors", dict(background="#010203", surface="#112233",
            text="#eeeeee", border="#445566", accent="#44aa88", font="Arial"))
        self.window.sync_theme()
        self.assertIn("QMenu", self.window.styleSheet())
        self.assertIn("#ff112233", self.window.styleSheet())

    def test_document_title_updates_label_without_changing_routing_identity(self):
        class Page(QObject):
            titleChanged = Signal(str)

            def title(self):
                return "Design - KFPS Vinyl Editor"

        owner = Owner()
        owner.page = Page(owner)
        self.created.append(owner)
        name = "Source 12345678"
        owner.workspace_source_name = '<b>Body & stripe</b>'
        self.window.add_surface(name, QWidget(), owner)
        index = self.window._index(name)
        self.assertEqual(self.window.tabs.tabText(index), 'Source artwork: <b>Body & stripe</b>')
        owner.page.titleChanged.emit('* Design - KFPS Vinyl Editor')
        self.assertEqual(self.window.tabs.tabText(index), '* Source artwork: <b>Body & stripe</b>')
        self.assertEqual(self.window.tabs.tabData(index), name)
        self.assertNotIn('<b>', self.window.tabs.tabToolTip(index))
        self.assertIn('&lt;b&gt;Body &amp; stripe&lt;/b&gt;', self.window.tabs.tabToolTip(index))
        self.assertNotIn('<b>', self.button(name).toolTip())
        self.window.show_surface(name, background=True)
        self.assertIs(self.window.stack.currentWidget(), self.window.surfaces[name])
        self.window._retire_surface(name, owner)
        owner.page.titleChanged.emit('Late title')
        self.assertEqual(self.window._index(name), -1)

    def test_editor_document_name_and_unsaved_marker_follow_owner(self):
        class Page(QObject):
            titleChanged = Signal(str)

            def title(self):
                return '* My livery - KFPS Vinyl Editor'

        self.window._retire_surface('Editor', self.a)
        owner = Owner()
        owner.page = Page(owner)
        self.created.append(owner)
        self.window.install_surface('Editor', QWidget(), owner)
        index = self.window._index('Editor')
        self.assertEqual(self.window.tabs.tabText(index), '* My livery - KFPS Vinyl Editor')
        owner.page.titleChanged.emit('My livery - KFPS Vinyl Editor')
        self.assertEqual(self.window.tabs.tabText(index), 'My livery - KFPS Vinyl Editor')
        self.assertEqual(self.window.tabs.tabData(index), 'Editor')
        self.window._retire_surface('Editor', owner)
        owner.page.titleChanged.emit('Obsolete title')
        self.assertEqual(self.window.tabs.tabText(index), 'Editor')

    def test_source_title_uses_existing_korean_and_japanese_owner_catalogs(self):
        from kfps_editor.localization import EditorTranslator

        root = Path(__file__).resolve().parents[2]
        prefixes = {'ko': '\uc6d0\ubcf8 \uc544\ud2b8\uc6cc\ud06c: ',
                    'ja': '\u5143\u306e\u30a2\u30fc\u30c8\u30ef\u30fc\u30af: '}
        with tempfile.TemporaryDirectory() as runtime:
            for language, prefix in prefixes.items():
                owner = Owner()
                self.created.append(owner)
                owner.translator = EditorTranslator(root, Path(runtime), language)
                owner.workspace_source_name = '<b>Body {0}</b>'
                name = 'Source ' + language
                self.window.add_surface(name, QWidget(), owner)
                self.window._update_title(name, owner, '* source')
                index = self.window._index(name)
                self.assertEqual(self.window.tabs.tabText(index), '* ' + prefix + '<b>Body {0}</b>')
                self.assertEqual(self.window.tabs.tabData(index), name)
                self.assertIn('&lt;b&gt;Body {0}&lt;/b&gt;', self.window.tabs.tabToolTip(index))

    def test_theme_changes_update_native_controls_without_new_theme_keys(self):
        colors = dict(background='#101112',surface='#202122',text='#f0f1f2',
                      border='#303132',accent='#ff0088',font='Segoe UI')
        self.main.setProperty('workspaceColors',colors)
        self.window.sync_theme()
        style = self.window.styleSheet()
        self.assertIn('#ff101112',style)
        self.assertIn('#ffff0088',style)
        self.assertIn('QLabel#workspacePlaceholder',style)
        self.assertIn('QToolButton:focus',style)
        colors.update(background='#fafafa',text='#101010',accent='#223344')
        self.main.setProperty('workspaceColors',colors)
        self.window.sync_theme()
        self.assertIn('#fffafafa',self.window.styleSheet())
        self.assertNotIn('#ffff0088',self.window.styleSheet())
        previous = self.window.styleSheet()
        self.main.setProperty('workspaceColors',dict(colors,accent='invalid'))
        self.window.sync_theme()
        self.assertEqual(self.window.styleSheet(),previous)

    def setUp(self):
        self.qt_errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, traceback: self.qt_errors.append(value)
        self.main = QWindow()
        self.main.resize(1200, 800)
        self.window = WorkspaceWindow(self.main, offscreen=True)
        self.window.reserve_surface("Editor")
        self.window.reserve_surface("Studio")
        self.a, self.b = Owner(), AsyncOwner()
        self.created = [self.a, self.b]
        self.window.install_surface("Editor", QWidget(), self.a)
        self.window.install_surface("Studio", QWidget(), self.b)

    def tearDown(self):
        try:
            self.window.shutdown()
            delete(self.window)
            delete(self.main)
            for owner in self.created:
                if isValid(owner):
                    delete(owner)
            self.pump()
        finally:
            sys.excepthook = self.previous_hook
        self.assertEqual(self.qt_errors, [], "Unhandled Qt callback exception")

    def pump(self):
        for _ in range(4):
            QCoreApplication.processEvents()

    def source(self, name="Source abcdef12"):
        owner = Owner()
        self.created.append(owner)
        self.window.add_surface(name, QWidget(), owner)
        return owner

    def approve(self, owner):
        owner.callbacks[-1](True)
        self.pump()

    def full_close(self):
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())

    def prepare_all(self):
        self.full_close()
        self.approve(self.a)
        self.approve(self.b)

    def assert_order(self, names):
        self.assertEqual(list(self.window.surfaces), names)
        self.assertEqual(self.window.tabs.count(), len(names))
        self.assertEqual(self.window.stack.count(), len(names))
        for index, name in enumerate(names):
            self.assertEqual(self.window.tabs.tabText(index), name)
            self.assertEqual(self.window.tabs.tabData(index), name)
            self.assertIs(self.window.stack.widget(index), self.window.surfaces[name])
        self.assertIs(self.window.stack.currentWidget(),
                      self.window.surfaces[self.window.tabs.tabData(self.window.tabs.currentIndex())])

    def button(self, name):
        index = list(self.window.surfaces).index(name)
        return self.window.tabs.tabButton(index, self.window.tabs.ButtonPosition.RightSide)

    def test_close_buttons_only_for_owned_editor_studio_and_private_source(self):
        self.source()
        other = Owner()
        self.created.append(other)
        self.window.add_surface("Diagnostics", QWidget(), other)
        self.window.reserve_surface("Empty")
        for name in ("Editor", "Studio", "Source abcdef12"):
            self.assertIsNotNone(self.button(name))
            self.assertEqual(self.button(name).toolTip(), "Close " + name)
        for name in ("KFPS", "Empty", "Diagnostics"):
            self.assertIsNone(self.button(name))
            self.assertFalse(self.window.close_surface(name))
        self.assertFalse(self.window.close_surface("missing"))

    def test_individual_cancel_preserves_owner_document_and_selection(self):
        original = self.window.surfaces["Editor"]
        self.window.show_surface("Studio", background=True)
        self.assertTrue(self.window.close_surface("Editor"))
        self.assertTrue(self.window._closing)
        self.a.callbacks[-1](False)
        self.pump()
        self.assertFalse(self.window._closing)
        self.assertEqual(self.a.cancelled, 1)
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.a.stopped_count, 0)
        self.assertIs(self.window.surfaces["Editor"], original)
        self.assertIs(self.window.stack.currentWidget(), self.window.surfaces["Studio"])

    def test_close_button_retains_reserved_placeholder_and_can_reopen(self):
        self.button("Editor").click()
        self.approve(self.a)
        self.assertNotIn("Editor", self.window.owners)
        self.assertIsInstance(self.window.surfaces["Editor"], QLabel)
        self.assertIsNone(self.button("Editor"))
        self.assertEqual(self.a.stopped_count, 1)
        self.assertFalse(self.window._approved)
        requested = []
        self.window.surfaceRequested.connect(requested.append)
        self.window.show_surface("Editor", background=True)
        replacement = Owner()
        self.created.append(replacement)
        self.window.install_surface("Editor", QWidget(), replacement)
        self.assertEqual(requested, ["Editor"])
        self.assertIs(self.window.stack.currentWidget(), self.window.surfaces["Editor"])
        self.assertIsNotNone(self.button("Editor"))
        self.assert_order(["KFPS", "Editor", "Studio"])

    def test_selected_placeholder_requests_again_on_explicit_open(self):
        self.window.close_surface("Editor")
        self.approve(self.a)
        requested = []
        self.window.surfaceRequested.connect(requested.append)
        self.window.show_surface("Editor", background=True)
        self.window.show_surface("Editor", background=True)
        self.assertEqual(requested, ["Editor", "Editor"])

    def test_async_individual_waits_for_closed_before_shutdown(self):
        self.window.close_surface("Studio")
        self.approve(self.b)
        self.assertEqual(self.b.committed, 1)
        self.assertEqual(self.b.stopped_count, 0)
        self.assertIs(self.window.owners["Studio"], self.b)
        self.assertTrue(self.window._closing)
        self.b.closed.emit()
        self.pump()
        self.assertEqual(self.b.stopped_count, 1)
        self.assertNotIn("Studio", self.window.owners)
        self.assertFalse(self.window._closing)

    def test_source_removal_and_reopen_keep_all_indices_consistent(self):
        first = self.source()
        second = self.source("Source abcdef34")
        self.window.tabs.tabCloseRequested.emit(3)
        self.approve(first)
        self.assert_order(["KFPS", "Editor", "Studio", "Source abcdef34"])
        self.window.show_surface("Source abcdef34", background=True)
        self.window.tabs.tabCloseRequested.emit(3)
        self.approve(second)
        self.source()
        self.assert_order(["KFPS", "Editor", "Studio", "Source abcdef12"])

    def test_tab_switch_and_full_close_are_blocked_during_individual_close(self):
        self.window.close_surface("Studio")
        selected = self.window.stack.currentWidget()
        self.full_close()
        self.assertFalse(self.window.close_surface("Editor"))
        self.window.show_surface("Editor", background=True)
        self.window.tabs.setCurrentIndex(0)
        self.assertIs(self.window.stack.currentWidget(), selected)
        self.assertEqual(self.window.tabs.currentIndex(), self.window.stack.indexOf(selected))
        self.assertEqual(len(self.a.callbacks), 0)
        self.approve(self.b)
        self.full_close()
        self.assertEqual(len(self.a.callbacks), 0)
        self.b.closed.emit()
        self.pump()
        self.full_close()
        self.assertEqual(len(self.a.callbacks), 1)

    def test_cancel_second_preserves_first_and_prior_disabled_state(self):
        self.window.surfaces["Editor"].setEnabled(False)
        self.full_close()
        self.approve(self.a)
        self.b.callbacks[-1](False)
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.a.stopped_count, 0)
        self.assertEqual(self.a.cancelled, 1)
        self.assertEqual(self.b.cancelled, 1)
        self.assertFalse(self.window._closing)
        self.assertFalse(self.window.surfaces["Editor"].isEnabled())
        self.assertTrue(self.window.surfaces["Studio"].isEnabled())

    def test_full_close_commits_async_owner_first_and_waits(self):
        self.prepare_all()
        self.assertEqual(self.b.committed, 1)
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.b.stopped_count, 0)
        self.b.closed.emit()
        self.pump()
        self.assertEqual(self.a.committed, 1)
        self.assertEqual(self.a.stopped_count, 1)
        self.assertEqual(self.b.stopped_count, 1)
        self.assertTrue(self.window._approved)

    def test_async_full_close_failure_restores_survivors_and_allows_retry(self):
        self.prepare_all()
        self.b.failed.emit("renderer stopped")
        self.assertFalse(self.window._closing)
        self.assertFalse(self.window._approved)
        self.assertTrue(self.window.tabs.isEnabled())
        self.assertEqual(self.a.cancelled, 1)
        self.assertEqual(self.b.cancelled, 1)
        self.assertEqual(self.a.committed, 0)
        self.prepare_all()
        self.b.closed.emit()
        self.pump()
        self.assertTrue(self.window._approved)

    def test_failure_after_partial_commit_does_not_revisit_dead_surface(self):
        self.a.commit_result = False
        self.prepare_all()
        delete(self.window.surfaces["Studio"])
        self.b.closed.emit()
        self.pump()
        self.assertFalse(self.window._closing)
        self.assertEqual(self.b.cancelled, 0)
        self.assertNotIn("Studio", self.window.owners)
        self.assertIsInstance(self.window.surfaces["Studio"], QLabel)
        self.a.commit_result = None
        self.full_close()
        self.approve(self.a)
        self.assertTrue(self.window._approved)

    def test_prepare_and_commit_exceptions_recover(self):
        for phase in ("prepare", "commit"):
            with self.subTest(phase=phase):
                setattr(self.a, phase + "_error", RuntimeError("failed"))
                self.window.close_surface("Editor")
                if phase == "commit":
                    self.approve(self.a)
                self.assertFalse(self.window._closing)
                self.assertTrue(self.window.tabs.isEnabled())
                self.assertIs(self.window.owners["Editor"], self.a)
                setattr(self.a, phase + "_error", None)

    def test_async_commit_false_recovers_without_shutdown(self):
        self.b.commit_result = False
        self.prepare_all()
        self.assertFalse(self.window._closing)
        self.assertEqual(self.b.stopped_count, 0)
        self.assertEqual(self.a.committed, 0)

    def test_commit_timeout_recovers_and_late_closed_does_not_close_shell(self):
        self.prepare_all()
        self.window._commit_timer.timeout.emit()
        self.assertFalse(self.window._closing)
        self.b.closed.emit()
        self.pump()
        self.assertNotIn("Studio", self.window.owners)
        self.assertEqual(self.a.committed, 0)
        self.assertFalse(self.window._approved)

    def test_duplicate_and_old_prepare_callbacks_cannot_close_replacement(self):
        self.window.close_surface("Editor")
        callback = self.a.callbacks[-1]
        late_failure = self.window._owner_signals["Editor"][0][1]
        self.approve(self.a)
        replacement = Owner()
        self.created.append(replacement)
        self.window.install_surface("Editor", QWidget(), replacement)
        callback(True)
        callback(False)
        late_failure("late")
        self.pump()
        self.assertIs(self.window.owners["Editor"], replacement)
        self.assertEqual(replacement.committed, 0)
        self.assertEqual(self.a.stopped_count, 1)

    def test_destroyed_owner_invalidates_prepare_and_ignores_late_callback(self):
        self.window.close_surface("Editor")
        callback = self.a.callbacks[-1]
        delete(self.a)
        callback(True)
        self.pump()
        self.assertFalse(self.window._closing)
        self.assertNotIn("Editor", self.window.owners)
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.a.cancelled, 0)
        self.assertEqual(self.a.stopped_count, 0)
        self.assert_order(["KFPS", "Editor", "Studio"])

    def test_destroyed_async_owner_recovers_full_close(self):
        self.prepare_all()
        delete(self.b)
        self.pump()
        self.assertFalse(self.window._closing)
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.a.cancelled, 1)
        self.assertNotIn("Studio", self.window.owners)

    def test_shutdown_invalidates_queued_preparation(self):
        self.window.close_surface("Editor")
        callback = self.a.callbacks[-1]
        self.window.shutdown()
        callback(True)
        self.b.closed.emit()
        self.pump()
        self.assertEqual(self.a.committed, 0)
        self.assertEqual(self.a.stopped_count, 1)
        self.assertEqual(self.b.stopped_count, 1)

    def test_loading_editor_can_close_without_readiness(self):
        self.a._ready = False
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.assertNotIn("Editor", self.window.owners)
        self.assertEqual(self.a.stopped_count, 1)

    def test_install_rejects_replacing_live_owner_and_mutation_during_close(self):
        widget = QWidget()
        try:
            with self.assertRaises(RuntimeError):
                self.window.install_surface("Editor", widget, self.a)
            self.window.close_surface("Editor")
            with self.assertRaises(RuntimeError):
                self.window.add_surface("Source late", widget, self.a)
        finally:
            delete(widget)

    def test_shutdown_failure_retains_owner_and_blocks_reopen(self):
        self.a.shutdown_result = False
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.assertFalse(self.window._closing)
        self.assertIs(self.window.owners["Editor"], self.a)
        self.assertFalse(self.window._approved)

    def test_geometry_signal_for_outer_move_resize_and_state_only(self):
        changed = []
        self.window.geometryChanged.connect(lambda: changed.append(True))
        self.window.show()
        self.pump()
        changed.clear()
        self.window.move(31, 47)
        self.pump()
        self.assertTrue(changed)
        changed.clear()
        self.window.resize(1230, 830)
        self.pump()
        self.assertTrue(changed)
        changed.clear()
        self.window.setWindowState(Qt.WindowState.WindowMaximized)
        self.pump()
        self.assertTrue(changed)
        changed.clear()
        QCoreApplication.sendEvent(self.window, QEvent(QEvent.Type.FontChange))
        self.assertEqual(changed, [])

    def test_modeless_message_box_remains_owned_until_commit(self):
        editor = self.window.surfaces["Editor"]
        box = QMessageBox(editor)
        box.setText("Saving")
        box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        box.show()
        self.window.close_surface("Editor")
        self.a.callbacks[-1](False)
        self.pump()
        self.assertTrue(isValid(box))
        self.assertIs(box.parentWidget(), editor)
        self.assertIs(editor.window(), self.window)
        self.assertIs(box.windowHandle().transientParent(), self.window.windowHandle())
        box.close()

    def test_dialog_created_before_embedding_uses_outer_native_parent(self):
        owner = Owner()
        self.created.append(owner)
        panel = QWidget()
        box = QMessageBox(panel)
        box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.window.add_surface("Source dialog", panel, owner)
        box.show()
        self.pump()
        self.assertIs(box.parentWidget(), panel)
        self.assertIs(box.windowHandle().transientParent(), self.window.windowHandle())
        self.window.close_surface("Source dialog")
        owner.callbacks[-1](False)
        self.assertTrue(isValid(box))
        box.close()

    def test_late_closed_during_new_prepare_recovers_without_global_commit(self):
        self.prepare_all()
        self.window._commit_timer.timeout.emit()
        self.full_close()
        pending = self.a.callbacks[-1]
        self.b.closed.emit()
        pending(True)
        self.pump()
        self.assertFalse(self.window._closing)
        self.assertFalse(self.window._approved)
        self.assertEqual(self.a.committed, 0)
        self.assertNotIn("Studio", self.window.owners)

    def test_duplicate_prepare_reply_is_not_a_second_commit(self):
        self.window.close_surface("Editor")
        callback = self.a.callbacks[-1]
        callback(True)
        callback(True)
        self.pump()
        self.assertEqual(self.a.committed, 1)
        self.assertEqual(self.a.stopped_count, 1)

    def test_destroyed_widget_owner_does_not_leave_stack_or_callback(self):
        widget = QWidget()
        widget.prepare_close = lambda callback: setattr(widget, "prepared", callback)
        widget.cancel_close = lambda: self.fail("Destroyed owner was cancelled")
        widget.commit_close = lambda: self.fail("Destroyed owner was committed")
        widget.shutdown = lambda: self.fail("Destroyed owner was shut down")
        self.window.add_surface("Source widget", widget, widget)
        self.window.close_surface("Source widget")
        callback = widget.prepared
        delete(widget)
        callback(True)
        self.pump()
        self.assertFalse(self.window._closing)
        self.assert_order(["KFPS", "Editor", "Studio"])

    def test_shutdown_that_destroys_owner_does_not_reenter_retirement(self):
        self.a.shutdown = lambda: delete(self.a)
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.assertFalse(self.window._closing)
        self.assertNotIn("Editor", self.window.owners)
        self.assert_order(["KFPS", "Editor", "Studio"])

    def test_synchronous_closed_signal_and_shutdown_signal_are_consumed_once(self):
        def commit():
            self.b.committed += 1
            self.b.closed.emit()
            return True
        def shutdown():
            self.b.stopped_count += 1
            self.b.closed.emit()
        self.b.commit_close = commit
        self.b.shutdown = shutdown
        self.window.close_surface("Studio")
        self.approve(self.b)
        self.assertFalse(self.window._closing)
        self.assertEqual(self.b.committed, 1)
        self.assertEqual(self.b.stopped_count, 1)

    def test_cancellation_keeps_switch_and_close_blocked_until_owners_restore(self):
        attempted = []
        def cancel():
            attempted.append(self.window.close_surface("Studio"))
            self.window.show_surface("Studio", background=True)
            attempted.append(self.window.tabs.currentIndex())
        self.a.cancel_close = cancel
        self.window.close_surface("Editor")
        self.a.callbacks[-1](False)
        self.assertEqual(attempted, [False, 1])
        self.assertFalse(self.window._closing)

    def test_modeless_dialog_is_disposed_only_after_accepted_close(self):
        box = QMessageBox(self.window.surfaces["Editor"])
        box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.window.close_surface("Editor")
        self.assertTrue(isValid(box))
        self.approve(self.a)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(box))

    def test_late_callback_after_shell_destruction_has_no_qt_access(self):
        window = WorkspaceWindow(QWindow(), offscreen=True)
        owner = Owner()
        window.add_surface("Editor", QWidget(), owner)
        window.close_surface("Editor")
        callback = owner.callbacks[-1]
        main = window.main_window
        window.shutdown()
        delete(window)
        callback(True)
        delete(main)
        delete(owner)

    def test_empty_workspace_close_and_invalid_tab_indices(self):
        self.window._close_tab(-1)
        self.window._close_tab(200)
        self.assertFalse(self.a.callbacks)
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.window.close_surface("Studio")
        self.approve(self.b)
        self.b.closed.emit()
        self.pump()
        self.full_close()
        self.assertTrue(self.window._approved)

    def test_owner_destroyed_inside_cancellation_does_not_touch_removed_surface(self):
        owner = self.source()
        owner.cancel_close = lambda: delete(owner)
        self.window.close_surface("Source abcdef12")
        owner.callbacks[-1](False)
        self.assertFalse(self.window._closing)
        self.assert_order(["KFPS", "Editor", "Studio"])

    def test_shutdown_exception_keeps_owner_and_allows_other_cleanup(self):
        def fail():
            raise RuntimeError("shutdown failed")
        self.a.shutdown = fail
        self.window.close_surface("Editor")
        self.approve(self.a)
        self.assertIs(self.window.owners["Editor"], self.a)
        self.assertFalse(self.window._closing)
        self.assertIs(self.window.shutdown(), False)
        self.assertEqual(self.b.stopped_count, 1)
        self.assertIs(self.window.shutdown(), False)

    def test_switch_preserves_widgets(self):
        original = self.window.surfaces["Editor"]
        for name in ("Editor", "Studio", "KFPS", "Editor"):
            self.window.show_surface(name, background=True)
        self.assertIs(self.window.stack.currentWidget(), original)
        self.assertEqual(self.a.stopped_count, 0)
        self.assertEqual(self.b.stopped_count, 0)


if __name__ == "__main__":
    unittest.main()
