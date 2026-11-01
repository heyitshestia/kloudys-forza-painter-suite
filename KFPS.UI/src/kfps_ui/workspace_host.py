"""Retained native surfaces; document contents and history stay with their owners."""
from html import escape
from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QMainWindow, QMenu, QStackedWidget, QStyle, QTabBar, QToolButton, QVBoxLayout, QWidget
from shiboken6 import isValid
from .workspace_diagnostics import operation, record, surface


class WorkspaceWindow(QMainWindow):
    surfaceRequested = Signal(str)
    geometryChanged = Signal()
    surfaceInstalled = Signal(str, object)
    surfaceRetired = Signal(str, bool)
    sessionClosePreparing = Signal()
    surfaceSelectionChanged = Signal(str, str)
    sessionActivityChanged = Signal()

    def __init__(self, main_window, *, offscreen=False, log=None):
        super().__init__()
        self.log = log
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, offscreen)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, offscreen)
        self.setWindowTitle("KFPS Workspace")
        self.setWindowIcon(main_window.icon())
        self.resize(main_window.width(), main_window.height())
        self.setMinimumSize(1000, 700)
        self.main_window = main_window
        self.tabs = QTabBar(self)
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.stack = QStackedWidget(self)
        self.surfaces = {}
        self.owners = {}
        self._closing = False
        self._approved = False
        self._close_epoch = 0
        self._shutdown = False
        self._operation = None
        self._owner_signals = {}
        self._retiring = {}
        self._selected = "KFPS"
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(15000)
        self._commit_timer.timeout.connect(self._commit_timeout)
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(body)
        self.add_surface("KFPS", QWidget.createWindowContainer(main_window, self))
        self.tabs.currentChanged.connect(self._select)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._tab_context_menu)
        if hasattr(main_window, "workspaceColorsChanged"):
            main_window.workspaceColorsChanged.connect(self.sync_theme)
            self.sync_theme()

    def sync_theme(self):
        value = self.main_window.property("workspaceColors")
        value = value.toVariant() if hasattr(value, "toVariant") else value
        if not isinstance(value, dict):
            return
        colours = {key: QColor(value.get(key, "")) for key in ("background", "surface", "text", "border", "accent")}
        if not all(color.isValid() for color in colours.values()):
            return
        c = {key: color.name(QColor.NameFormat.HexArgb) for key, color in colours.items()}
        self.tabs.setFont(QFont(str(value.get("font", ""))))
        self.setStyleSheet(f"QMainWindow, QStatusBar {{background:{c['background']};color:{c['text']};}}"
            f"QLabel#workspacePlaceholder {{background:{c['background']};color:{c['text']};}}"
            f"QTabBar QToolButton {{background:transparent;color:{c['text']};border:1px solid transparent;}}"
            f"QTabBar QToolButton:hover, QTabBar QToolButton:focus {{border-color:{c['accent']};}}"
            f"QTabBar {{background:{c['background']};}} QTabBar::tab {{background:{c['surface']};color:{c['text']};padding:9px 22px;max-width:280px;border:1px solid {c['border']};}}"
            f"QTabBar::tab:selected {{border-bottom:3px solid {c['accent']};}} QTabBar::tab:hover {{border-color:{c['accent']};}}"
            f"QMenu {{background:{c['surface']};color:{c['text']};border:1px solid {c['border']};}}"
            f"QMenu::item {{padding:7px 20px;}} QMenu::item:selected {{background:{c['background']};border:1px solid {c['accent']};}}"
            f"QMenu::item:disabled {{color:{c['border']};}}")

    def create_tab_menu(self, name):
        """Capture routing identity, not the current index or editable title."""
        menu = QMenu(self)
        menu.setFont(self.tabs.font())
        owner = self.owners.get(name)
        close = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton), "Close current")
        close.setEnabled(self._closable(name) and not self._closing and not self._shutdown)
        close.triggered.connect(lambda: self.close_surface(name) if self.owners.get(name) is owner else None)
        home = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Return to KFPS")
        home.setEnabled(not self._closing and not self._shutdown)
        home.triggered.connect(lambda: self.show_surface("KFPS", background=True))
        return menu

    def _tab_context_menu(self, position):
        index = self.tabs.tabAt(position)
        if index < 0 or self._closing or self._shutdown:
            return
        menu = self.create_tab_menu(self.tabs.tabData(index))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.tabs.mapToGlobal(position))

    def set_session_placeholder(self, name, pending):
        if name not in {"Editor", "Studio"} or name in self.owners:
            return
        widget = self.surfaces.get(name)
        if isinstance(widget, QLabel) and isValid(widget):
            widget.setText(name + ("\nPrevious session ready to reopen" if pending else ""))
            self.tabs.setTabToolTip(self._index(name), "Select to reopen the previous session" if pending else "")

    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometryChanged.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometryChanged.emit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.geometryChanged.emit()
            self.sessionActivityChanged.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.sessionActivityChanged.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.sessionActivityChanged.emit()

    @staticmethod
    def _placeholder(name):
        label = QLabel(name)
        label.setObjectName("workspacePlaceholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def reserve_surface(self, name):
        self.add_surface(name, self._placeholder(name))

    def _check_install(self):
        if self._closing or self._shutdown or self._approved:
            raise RuntimeError("The workspace is closing.")

    def _index(self, name):
        return next((i for i in range(self.tabs.count()) if self.tabs.tabData(i) == name), -1)

    def _closable(self, name):
        return name in self.owners and (name in {"Editor", "Studio"} or name.startswith("Source "))

    def _close_button(self, name):
        index = self._index(name)
        previous = self.tabs.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if previous is not None:
            previous.deleteLater()
        button = None
        if self._closable(name):
            button = QToolButton(self.tabs)
            button.setAutoRaise(True)
            button.setFixedSize(24, 24)
            button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
            button.setToolTip("Close " + name)
            button.setAccessibleName("Close " + name)
            button.clicked.connect(lambda: self.close_surface(name))
        self.tabs.setTabButton(index, QTabBar.ButtonPosition.RightSide, button)

    def _bind_owner(self, name, owner):
        connections = []
        for signal_name, callback in (
            ("closed", lambda: self._owner_closed(name, owner)),
            ("failed", lambda message: self._owner_failed(name, owner, message)),
            ("destroyed", lambda *_: self._owner_destroyed(name, owner)),
        ):
            signal = getattr(owner, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(callback)
                connections.append((signal, callback))
        self._owner_signals[name] = connections
        page = getattr(owner, "page", None)
        signal = getattr(page, "titleChanged", None)
        if signal is not None and hasattr(signal, "connect"):
            callback = lambda title: self._update_title(name, owner, title)
            signal.connect(callback)
            connections.append((signal, callback))

    def _update_title(self, name, owner, title=None):
        if self._shutdown or self.owners.get(name) is not owner:
            return
        index = self._index(name)
        if index < 0:
            return
        if title is None:
            page = getattr(owner, "page", None)
            title = page.title() if callable(getattr(page, "title", None)) else ""
        title = str(title or "").strip()
        source = getattr(owner, "workspace_source_name", None)
        if source is not None:
            translator = getattr(owner, "translator", None)
            label = translator.tr("Source artwork: {0}", source) if translator else "Source artwork: " + str(source)
            title = ("* " if title.startswith("* ") else "") + label
        title = title or name
        self.tabs.setTabText(index, title)
        # Qt tooltips detect rich text, unlike tab labels. Escape user titles.
        self.tabs.setTabToolTip(index, self._title_tooltip(title))
        button = self.tabs.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if button is not None:
            translator = getattr(owner, "translator", None)
            close = translator.tr("Close {0}", title) if translator else "Close " + title
            button.setToolTip(self._title_tooltip(close))
            button.setAccessibleName(close)

    @staticmethod
    def _title_tooltip(text):
        return "<qt>" + escape(text) + "</qt>" if "<" in text else text

    def _unbind_owner(self, name):
        for signal, callback in self._owner_signals.pop(name, []):
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass

    def install_surface(self, name, widget, owner):
        self._check_install()
        if name in self.owners:
            raise RuntimeError("Close the existing workspace owner before replacing it.")
        if name not in self.surfaces:
            self.add_surface(name, widget, owner)
            return
        previous = self.surfaces[name]
        index = self._index(name)
        widget.setParent(self.stack)
        widget.setWindowFlags(Qt.WindowType.Widget)
        self.stack.removeWidget(previous)
        self.stack.insertWidget(index, widget)
        self.surfaces[name], self.owners[name] = widget, owner
        previous.deleteLater()
        self._bind_owner(name, owner)
        self._close_button(name)
        self._update_title(name, owner)
        self._activate(self._selected)
        self.surfaceInstalled.emit(name, owner)
        record(self.log, "workspace.surface", "ready", surface=surface(name), owner_count=len(self.owners))

    def add_surface(self, name, widget, owner=None):
        self._check_install()
        if name in self.surfaces:
            raise ValueError("Workspace surface already exists")
        widget.setParent(self.stack)
        widget.setWindowFlags(Qt.WindowType.Widget)
        self.surfaces[name] = widget
        if owner is not None:
            self.owners[name] = owner
            self._bind_owner(name, owner)
        self.stack.addWidget(widget)
        with QSignalBlocker(self.tabs):
            index = self.tabs.addTab(name)
            self.tabs.setTabData(index, name)
        self._close_button(name)
        if owner is not None:
            self._update_title(name, owner)
        self._activate(self._selected)
        if owner is not None:
            self.surfaceInstalled.emit(name, owner)
            record(self.log, "workspace.surface", "ready", surface=surface(name), owner_count=len(self.owners))

    def show_surface(self, name, *, background=False):
        if self._closing or self._shutdown or self._approved:
            return
        if name not in self.surfaces:
            self.surfaceRequested.emit(name)
            return
        self._activate(name)
        if name != "KFPS" and name not in self.owners:
            self.surfaceRequested.emit(name)
        if not background and not self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
            self.showNormal() if self.isMinimized() else self.show()
            self.raise_()
            self.activateWindow()

    def _select(self, index):
        if self._closing or self._shutdown:
            self._activate(self._selected)
            return
        name = self.tabs.tabData(index)
        if name in self.surfaces:
            self.show_surface(name, background=True)

    def _activate(self, name):
        if name not in self.surfaces:
            name = "KFPS"
        previous = self._selected
        self._selected = name
        with QSignalBlocker(self.tabs):
            self.tabs.setCurrentIndex(self._index(name))
        widget = self.surfaces[name]
        if isValid(widget):
            self.stack.setCurrentWidget(widget)
        if previous != name:
            record(self.log, "workspace.selection", "completed", surface=surface(name))
            self.surfaceSelectionChanged.emit(previous, name)

    def _close_tab(self, index):
        if 0 <= index < self.tabs.count():
            self.close_surface(self.tabs.tabData(index))

    def close_surface(self, name):
        """Start a cancellable tab close; True means started, not yet closed."""
        if self._closing or self._shutdown or self._approved or not self._closable(name):
            return False
        self._start_close([(name, self.owners[name])], whole=False)
        return True

    def closeEvent(self, event):
        if self._approved:
            event.accept()
            return
        event.ignore()
        if self._closing or self._shutdown:
            return
        self._start_close(list(self.owners.items()), whole=True)

    def _start_close(self, owners, *, whole):
        self._closing = True
        self.sessionClosePreparing.emit()
        self._close_epoch += 1
        operation = {"owners": owners, "whole": whole, "selected": self._selected,
                     "enabled": {name: widget.isEnabled() for name, widget in self.surfaces.items() if isValid(widget)},
                     "tabs_enabled": self.tabs.isEnabled(), "waiting": None}
        from .workspace_diagnostics import operation as diagnostic_operation
        operation["diagnostic"] = diagnostic_operation()
        record(self.log, "workspace.close", "started", op=operation["diagnostic"], whole=whole, owner_count=len(owners))
        self._operation = operation
        self.tabs.setEnabled(False)
        self._prepare_next(operation, 0)

    def _active(self, operation):
        return isValid(self) and not self._shutdown and self._operation is operation

    @staticmethod
    def _live(owner):
        return not isinstance(owner, QObject) or isValid(owner)

    def _prepare_next(self, operation, index):
        if not self._active(operation):
            return
        if index == len(operation["owners"]):
            operation["committing"] = sorted(operation["owners"], key=lambda item: not hasattr(item[1], "closed"))
            self._commit_next(operation, 0)
            return
        name, owner = operation["owners"][index]
        if self.owners.get(name) is not owner or not self._live(owner):
            self._recover_close(operation, "A workspace tab is no longer available.")
            return
        self._activate(name)
        waiting = (name, owner, "prepare")
        operation["waiting"] = waiting

        def completed(accepted):
            if not self._active(operation) or operation["waiting"] is not waiting:
                return
            operation["waiting"] = None
            if accepted is not True or self.owners.get(name) is not owner or not self._live(owner):
                self._recover_close(operation)
                return
            widget = self.surfaces[name]
            if not isValid(widget):
                self._recover_close(operation, "A workspace tab is no longer available.")
                return
            widget.setEnabled(False)
            QTimer.singleShot(0, self, lambda: self._prepare_next(operation, index + 1))
        try:
            owner.prepare_close(completed)
        except Exception as exc:
            record(self.log, "workspace.close", "failed", op=operation["diagnostic"], stage="prepare", error=exc)
            self._recover_close(operation, "Could not prepare the tab to close. Try again.")

    def _commit_next(self, operation, index):
        if not self._active(operation):
            return
        if index == len(operation["committing"]):
            self._finish_operation(operation)
            if operation["whole"]:
                self._approved = True
                self.close()
            return
        name, owner = operation["committing"][index]
        operation["waiting"] = (name, owner, "commit")
        operation["commit_index"] = index
        asynchronous = hasattr(owner, "closed")
        if asynchronous:
            self._commit_timer.start()
        try:
            result = owner.commit_close()
        except Exception as exc:
            record(self.log, "workspace.close", "failed", op=operation["diagnostic"], stage="commit", error=exc)
            self._recover_close(operation, "Could not close the tab. Try again.")
            return
        if not self._active(operation):
            return
        if result is False:
            self._recover_close(operation, "The tab could not finish closing. Try again.")
        elif not asynchronous:
            self._committed(operation, name, owner)

    def _committed(self, operation, name, owner):
        if not self._active(operation) or operation["waiting"] != (name, owner, "commit"):
            return
        operation["waiting"] = None
        self._commit_timer.stop()
        if not self._retire_surface(name, owner):
            self._recover_close(operation, "Tab cleanup did not finish. Its owner has been retained.")
            return
        index = operation["commit_index"] + 1
        QTimer.singleShot(0, self, lambda: self._commit_next(operation, index))

    def _owner_closed(self, name, owner):
        if self._shutdown or self.owners.get(name) is not owner or self._retiring.get(name) is owner:
            return
        operation = self._operation
        if operation is not None and operation["waiting"] == (name, owner, "commit"):
            self._committed(operation, name, owner)
        else:
            # A timed-out native close may still finish; retire only that owner.
            self._retire_surface(name, owner)
            if operation is not None:
                self._recover_close(operation, "A tab closed while preparing the workspace.")

    def _owner_failed(self, name, owner, message):
        if self._retiring.get(name) is owner:
            return
        record(self.log, "workspace.owner", "failed", surface=surface(name))
        if self._operation is not None and any(name == key and owner is value for key, value in self._operation["owners"]):
            self._recover_close(self._operation, str(message))

    def _owner_destroyed(self, name, owner):
        if self._shutdown or self.owners.get(name) is not owner or self._retiring.get(name) is owner:
            return
        self._retire_surface(name, owner, destroyed=True)
        if self._operation is not None:
            self._recover_close(self._operation, "A workspace tab was destroyed before closing finished.")

    def _retire_surface(self, name, owner, *, destroyed=False):
        if self.owners.get(name) is not owner:
            return True
        self._retiring[name] = owner
        if not destroyed:
            try:
                if owner.shutdown() is False:
                    record(self.log, "workspace.owner", "failed", surface=surface(name), stage="cleanup")
                    return False
            except Exception as exc:
                record(self.log, "workspace.owner", "failed", surface=surface(name), stage="cleanup", error=exc)
                return False
            finally:
                self._retiring.pop(name, None)
        else:
            self._retiring.pop(name, None)
        self._unbind_owner(name)
        self.owners.pop(name)
        record(self.log, "workspace.surface", "completed", surface=surface(name), stage="cleanup", owner_count=len(self.owners))
        self.surfaceRetired.emit(name, bool(self._operation and self._operation["whole"]))
        previous = self.surfaces[name]
        index = self._index(name)
        if isValid(previous) and not (destroyed and previous is owner):
            self.stack.removeWidget(previous)
            previous.hide()
            previous.deleteLater()
        if name in {"Editor", "Studio"}:
            replacement = self._placeholder(name)
            self.surfaces[name] = replacement
            self.stack.insertWidget(index, replacement)
            self.tabs.setTabText(index, name)
            self.tabs.setTabToolTip(index, "")
            self._close_button(name)
        else:
            self.surfaces.pop(name)
            with QSignalBlocker(self.tabs):
                self.tabs.removeTab(index)
        if self._selected == name:
            self._activate("KFPS")
        else:
            self._activate(self._selected)
        if not destroyed and isinstance(owner, QObject) and owner is not previous and isValid(owner):
            owner.deleteLater()
        return True

    def _finish_operation(self, operation, outcome="completed"):
        record(self.log, "workspace.close", outcome, op=operation.get("diagnostic"), whole=operation["whole"])
        self._operation = None
        self._closing = False
        self._close_epoch += 1
        self._commit_timer.stop()
        self.tabs.setEnabled(operation["tabs_enabled"])
        selected = operation["selected"]
        self._activate(selected if selected in self.owners or selected == "KFPS" else "KFPS")
        self.sessionActivityChanged.emit()

    def _recover_close(self, operation, message=""):
        if not self._active(operation):
            return
        # Invalidate callbacks before cancel_close can synchronously call back.
        self._operation = None
        self._commit_timer.stop()
        for name, owner in operation["owners"]:
            if self.owners.get(name) is not owner or not self._live(owner):
                continue
            try:
                owner.cancel_close()
            except Exception:
                message = message or "Could not cancel the tab's close request."
            if self.owners.get(name) is not owner:
                continue
            widget = self.surfaces[name]
            if isValid(widget):
                widget.setEnabled(operation["enabled"].get(name, True))
        self._finish_operation(operation, "failed" if message else "cancelled")
        if message:
            self.statusBar().showMessage(message, 10000)

    def _commit_timeout(self):
        if self._operation is not None:
            record(self.log, "workspace.close", "timeout", op=self._operation.get("diagnostic"), stage="commit")
            self._recover_close(self._operation, "A tab is taking too long to close. The workspace remains open.")

    def shutdown(self):
        if self._shutdown:
            return self._shutdown_complete
        self._shutdown = True
        diagnostic = operation()
        record(self.log, "workspace.shutdown", "started", op=diagnostic, owner_count=len(self.owners))
        self._shutdown_complete = True
        self._close_epoch += 1
        self._operation = None
        self._closing = False
        self._commit_timer.stop()
        for name, owner in list(self.owners.items()):
            self._unbind_owner(name)
            if self._live(owner):
                try:
                    if owner.shutdown() is False:
                        self._shutdown_complete = False
                except Exception as exc:
                    record(self.log, "workspace.owner", "failed", surface=surface(name), stage="cleanup", error=exc)
                    self._shutdown_complete = False
        # QML's engine owns its root. Detach it before deleting the QWidget shell.
        self.main_window.hide()
        self.main_window.setParent(None)
        record(self.log, "workspace.shutdown", "completed" if self._shutdown_complete else "failed", op=diagnostic)
        return self._shutdown_complete
