"""User-invoked workspace commands and worker activity, backed by existing owners."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QObject, Property, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QStyle, QToolButton,
    QVBoxLayout, QWidget)
from shiboken6 import isValid
from .workspace_tasks import TaskJournal


class _WebActivity(QObject):
    changed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.running = False
        self.status = self.detail = ""
        self.owner = self.pending = None
        self.name = ""


class WorkspaceTools(QObject):
    changed = Signal()
    settingRequested = Signal(str)

    def __init__(self, paths, controller, services, parent=None):
        super().__init__(parent)
        self.paths, self.controller, self.services = paths, controller, services
        self.window = self.shell = None
        self._dialogs = set()
        self._closed = False
        self._task_dialog = None
        self._command_dialog = None
        self._toolbar = None
        self._session = None
        self._web_tasks = {}
        self.journal = TaskJournal(self)
        self.journal.changed.connect(self.changed)
        self._bind_tasks()
        for key in ("Editor", "Studio", "Source"):
            source = _WebActivity(self)
            self._web_tasks[key] = source
            self.journal.watch("web:"+key, source, label=key+" work", page="editor", detail="detail")

    @Property(int, notify=changed)
    def activeCount(self):
        return self.journal.activeCount

    @Property(QObject, notify=changed)
    def session(self):
        return self._session

    def attach_session(self, session):
        self._session = session
        self.changed.emit()

    def _bind_tasks(self):
        specs = [
            ("generation", "Generation", "create", "running", "status", None),
            ("transfer", "Live game transfer", "outputs", "running", "status", None),
            ("offline", "Offline vinyl transfer", "outputs", "running", "status", "summary"),
            ("liveries", "Livery processing", "liveries", "running", "status", "summary"),
            ("editor", "Opening Editor", "editor", "launching", "status", "lastError"),
            ("studio", "Opening Studio", "editor", "studioLaunching", "studioStatus", None),
            ("upscaler", "Upscaling", "upscaler", "running", "status", "lastError"),
            ("background", "Background removal", "background-remover", "running", "status", "lastError"),
            ("backup", "Library backup", "settings", "running", "status", None),
            ("index", "Output index", "outputs", "indexing", "indexStatus", None),
        ]
        for key, label, page, busy, status, detail in specs:
            source = self.services.get("editor" if key == "studio" else "outputs" if key == "index" else key)
            if source is None:
                continue
            options = {}
            if key == "generation":
                options = dict(cancel=source.cancelQueue,
                    can_cancel=lambda s=source: bool(s.runDirectory),
                    retry=source.retryFailed, can_retry=lambda s=source: s.canRetryFailed,
                    result=lambda: self.navigate("outputs"))
            elif key in {"upscaler", "background"}:
                options = dict(cancel=source.cancel, result=source.openOutputFolder)
            elif key == "offline":
                options = dict(result=lambda s=source: self._open_output(s.lastOutput, 3),
                    can_result=lambda s=source: bool(s.lastOutput and Path(s.lastOutput).is_file()))
            elif key == "transfer":
                options = dict(result=lambda s=source: self._open_output(s.lastOutput, 2),
                    can_result=lambda s=source: bool(s.lastOutput and Path(s.lastOutput).is_file()))
            elif key == "liveries":
                options = dict(result=lambda: self.navigate("liveries"))
            self.journal.watch(key, source, label=label, page=page, busy=busy,
                               status=status, detail=detail, **options)

    def attach(self, window, shell=None):
        self.window, self.shell = window, shell
        signal = getattr(window, "workspaceColorsChanged", None)
        if signal is not None:
            signal.connect(self._refresh_themes)
        if shell is None:
            return
        # Keep the existing tab bar and owners; only add two user-invoked tools.
        layout = shell.centralWidget().layout()
        layout.removeWidget(shell.tabs)
        row = QWidget(shell)
        self._toolbar = row
        bar = QHBoxLayout(row)
        bar.setContentsMargins(0, 0, 4, 0)
        bar.setSpacing(3)
        bar.addWidget(shell.tabs, 1)
        for name, icon, callback in (
            ("Commands and settings", QStyle.StandardPixmap.SP_FileDialogContentsView, self.openCommands),
            ("Background tasks", QStyle.StandardPixmap.SP_FileDialogDetailedView, self.openTasks),
        ):
            button = QToolButton(row)
            button.setObjectName("workspace" + ("Commands" if callback == self.openCommands else "Tasks"))
            button.setIcon(shell.style().standardIcon(icon))
            button.setProperty("workspaceIcon", "terminal" if callback == self.openCommands else "reports")
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setFixedSize(32, 30)
            button.clicked.connect(callback)
            bar.addWidget(button)
            if name == "Background tasks":
                self.changed.connect(lambda b=button: b.setToolTip(
                    f"Background tasks ({self.activeCount} running)"))
        layout.insertWidget(0, row)
        self._theme(row)

    def _refresh_themes(self):
        if self._toolbar is not None and isValid(self._toolbar):
            self._theme(self._toolbar)
        for dialog in self._dialogs:
            if isValid(dialog):
                self._theme(dialog)

    def _theme(self, dialog):
        if self.window is None:
            return
        raw = self.window.property("workspaceColors")
        values = raw.toVariant() if hasattr(raw, "toVariant") else raw
        if not isinstance(values, dict):
            return
        palette = dialog.palette()
        for key, roles in {
            "background": (QPalette.Window, QPalette.Base),
            "surface": (QPalette.Button, QPalette.AlternateBase, QPalette.ToolTipBase),
            "text": (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.ToolTipText),
            "accent": (QPalette.Highlight,),
            "accentText": (QPalette.HighlightedText,),
        }.items():
            color = QColor(values.get(key, ""))
            if color.isValid():
                for role in roles:
                    palette.setColor(role, color)
        dialog.setPalette(palette)
        dialog.setAutoFillBackground(True)
        font = dialog.font()
        if values.get("font"):
            font.setFamily(str(values["font"]))
        font.setPixelSize(max(11, min(32, round(float(values.get("fontSize", 13))))))
        dialog.setFont(font)
        colours = {k: QColor(values.get(k, "")) for k in ("background", "surface", "text", "border", "accent")}
        if all(c.isValid() for c in colours.values()):
            c = {k: v.name(QColor.NameFormat.HexArgb) for k, v in colours.items()}
            selected_text = palette.color(QPalette.ColorRole.HighlightedText).name(QColor.NameFormat.HexArgb)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, colours['border'])
            dialog.setPalette(palette)
            dialog.setStyleSheet(
                f"QDialog {{background:{c['background']};color:{c['text']};}}"
                f"QLabel {{color:{c['text']};}}"
                f"QLineEdit,QListWidget {{background:{c['surface']};color:{c['text']};border:1px solid {c['border']};selection-background-color:{c['accent']};selection-color:{selected_text};}}"
                "QLineEdit {padding:7px;} QListWidget::item {padding:5px 7px;}"
                f"QListWidget::item:selected {{background:{c['accent']};color:{selected_text};}}"
                f"QScrollBar {{background:{c['surface']};border:0;}}"
                "QScrollBar:vertical {width:12px;} QScrollBar:horizontal {height:12px;}"
                f"QScrollBar::handle {{background:{c['border']};min-height:24px;min-width:24px;}}"
                f"QScrollBar::handle:hover {{background:{c['accent']};}}"
                "QScrollBar::add-line,QScrollBar::sub-line {width:0;height:0;}"
                "QScrollBar::add-page,QScrollBar::sub-page {background:transparent;}"
                f"QProgressBar {{background:{c['surface']};border:0;}}"
                f"QProgressBar::chunk {{background:{c['accent']};}}"
                f"QPushButton {{background:{c['surface']};color:{c['text']};padding:6px 12px;border:1px solid {c['border']};}}"
                f"QPushButton:focus,QLineEdit:focus {{border-color:{c['accent']};}}"
                f"QPushButton:disabled {{color:{c['border']};}}"
                f"QToolButton {{background:{c['surface']};color:{c['text']};border:1px solid {c['border']};}}"
                f"QToolButton:hover,QToolButton:focus {{border-color:{c['accent']};}}"
                f"QToolTip {{background:{c['surface']};color:{c['text']};border:1px solid {c['border']};}}")
            for button in dialog.findChildren(QToolButton):
                name = button.property("workspaceIcon")
                if name not in ("terminal", "reports"):
                    continue
                path = self.paths.app_root / "KFPS.UI/assets/icons" / (name + ".svg")
                if path.is_file():
                    pixmap = QIcon(str(path)).pixmap(20, 20)
                    painter = QPainter(pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                    painter.fillRect(pixmap.rect(), colours['text'])
                    painter.end()
                    button.setIcon(QIcon(pixmap))

    def _dialog(self, title):
        dialog = QDialog(self.shell)
        dialog.setWindowTitle(title)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, os.environ.get("QT_QPA_PLATFORM") == "offscreen")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(620, 480)
        dialog.setMinimumSize(380, 300)
        if self.window is not None:
            dialog.resize(min(620, max(380, self.window.width()-80)), min(480, max(300, self.window.height()-80)))
            if self.shell is None and hasattr(self.window, "setTransientParent"):
                dialog.winId()
                dialog.windowHandle().setTransientParent(self.window)
        self._theme(dialog)
        self._dialogs.add(dialog)
        dialog.finished.connect(lambda *_: self._dialogs.discard(dialog))
        return dialog

    def navigate(self, page):
        if self._closed:
            return
        self.controller.navigate(page)
        if self.shell is not None:
            self.shell.show_surface("KFPS", background=True)

    def _open_output(self, path, category):
        outputs = self.services.get("outputs")
        if not path or not Path(path).is_file() or outputs is None:
            self.navigate("outputs")
            return
        outputs.setNavigationConsumer("outputs")
        outputs.setSource(category)
        outputs.selectPath(path)
        self.navigate("outputs")

    def _commands(self):
        rows = []
        editor = self.services.get("editor")
        if editor is not None:
            for key, label, busy, action in (
                ("editor", "Open Vinyl Editor", editor.launching, editor.activate),
                ("studio", "Open Livery Studio", editor.studioLaunching, editor.launchLiveryStudio),
            ):
                rows.append(dict(id="tool:"+key, label=label, shortcut="", enabled=not busy,
                                 reason="Opening already in progress" if busy else "", action=action))
        rows.append(dict(id="tool:tasks", label="Background tasks", shortcut="", enabled=True,
                         reason="", action=self.openTasks))
        for page in ("create", "outputs", "liveries", "community", "editor", "tools", "settings", "help"):
            rows.append(dict(id="page:"+page, label=self.controller.PAGES[page], shortcut="", enabled=True,
                             reason="", action=lambda p=page: self.navigate(p)))
        for key, label in (("theme", "Settings: theme"), ("chrome", "Settings: Editor / Studio in Chrome"),
                           ("motion", "Settings: reduced motion"), ("folders", "Settings: folders and backups"),
                           ("session", "Settings: reopen previous workspace")):
            rows.append(dict(id="setting:"+key, label=label, shortcut="", enabled=True, reason="",
                             action=lambda k=key: (self.navigate("settings"), self.settingRequested.emit(k))))
        return rows

    def _active_web(self):
        if self.shell is None:
            return None
        name = self.shell._selected
        owner = self.shell.owners.get(name)
        page = getattr(owner, "page", None)
        if owner is None or page is None or not isValid(page):
            return None
        return name, owner, page

    def _still_active(self, context):
        return context is not None and self._active_web() == context and not self._closed

    @staticmethod
    def _web_value(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return None
        return value

    def _poll_web_activity(self):
        # Only a user-opened task panel observes web work. Never thaw an idle tab.
        if self.shell is None or self._task_dialog is None or not isValid(self._task_dialog):
            return
        for key, source in self._web_tasks.items():
            name = key
            if key == "Source":
                name = self.shell._selected if self.shell._selected.startswith("Source ") else source.name
            owner = self.shell.owners.get(name)
            page = getattr(owner, "page", None)
            if source.owner is not owner:
                if source.running:
                    source.running = False
                    source.status = "Tool closed or replaced; completion was not confirmed."
                    source.changed.emit()
                source.owner, source.name, source.pending = owner, name, None
            if page is None or not isValid(page) or source.pending is page:
                continue
            state = getattr(page, "lifecycleState", None)
            if state is not None and state().name != "Active":
                continue
            source.pending = page
            def received(value, s=source, p=page, o=owner):
                value = self._web_value(value)
                if s.pending is p:
                    s.pending = None
                if self._closed or self._task_dialog is None or s.owner is not o:
                    return
                if not isinstance(value, dict) or type(value.get("running")) is not bool:
                    return
                s.running = value["running"]
                s.status, s.detail = str(value.get("status") or "")[:2000], str(value.get("detail") or "")[:4000]
                s.changed.emit()
            page.runJavaScript("JSON.stringify(window.kfpsWorkspaceCommands?.activity() || null)", received)

    @Slot()
    def openCommands(self):
        if self._closed:
            return
        if self._command_dialog is not None and isValid(self._command_dialog):
            self._command_dialog.show()
            return
        context = self._active_web()
        dialog = self._dialog("Commands and settings")
        self._command_dialog = dialog
        dialog.finished.connect(lambda *_: setattr(self, "_command_dialog", None))
        dialog.setObjectName("WorkspaceCommandDialog")
        layout = QVBoxLayout(dialog)
        search = QLineEdit(dialog)
        search.setPlaceholderText("Search commands and settings")
        search.setObjectName("WorkspaceCommandSearch")
        items = QListWidget(dialog)
        items.setObjectName("WorkspaceCommandResults")
        detail = QLabel(dialog)
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        run = QPushButton("Open", dialog)
        layout.addWidget(search)
        layout.addWidget(items, 1)
        layout.addWidget(detail)
        layout.addWidget(run)
        rows = self._commands()

        def refresh():
            if not isValid(dialog):
                return
            query = search.text().casefold().strip()
            items.clear()
            for row in rows:
                if query and not all(term in (row["label"]+" "+row.get("shortcut", "")).casefold() for term in query.split()):
                    continue
                item = QListWidgetItem(row["label"] + ("    " + row["shortcut"] if row.get("shortcut") else ""))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setToolTip(row.get("reason") or row["label"])
                if not row.get("enabled", True):
                    item.setForeground(dialog.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
                items.addItem(item)
            items.setCurrentRow(0)
            selected()

        def selected():
            item = items.currentItem()
            row = next((r for r in rows if item and r["id"] == item.data(Qt.ItemDataRole.UserRole)), None)
            run.setEnabled(bool(row and row.get("enabled", True)))
            detail.setText((row.get("reason") or "") if row else "No matching commands")

        def execute():
            item = items.currentItem()
            row = next((r for r in rows if item and r["id"] == item.data(Qt.ItemDataRole.UserRole)), None)
            if row is None or not row.get("enabled", True):
                return
            if row.get("web"):
                if not self._still_active(context):
                    detail.setText("The active document changed. Reopen command search.")
                    run.setEnabled(False)
                    return
                script = "JSON.stringify(window.kfpsWorkspaceCommands?.execute("+json.dumps(row["web"])+","+json.dumps(row["token"])+"))"
                run.setEnabled(False)
                def dispatched(result):
                    result = self._web_value(result)
                    if not isValid(dialog):
                        return
                    if result is True or isinstance(result, dict) and result.get("ok"):
                        dialog.accept()
                    else:
                        detail.setText("The command is no longer available. Reopen command search.")
                context[2].runJavaScript(script, dispatched)
            else:
                dialog.accept()
                row["action"]()

        def receive(value):
            value = self._web_value(value)
            if not isValid(dialog) or dialog not in self._dialogs or not self._still_active(context):
                return
            if not isinstance(value, dict) or not isinstance(value.get("token"), str):
                return
            web_rows = []
            for entry in (value.get("commands") or [])[:200]:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    continue
                web_rows.append(dict(id="web:"+entry["id"], web=entry["id"], token=value["token"],
                    label=str(entry.get("label") or entry["id"])[:200],
                    shortcut=str(entry.get("shortcut") or "")[:100], enabled=entry.get("enabled") is True,
                    reason=str(entry.get("reason") or "")[:1000]))
            rows[:0] = web_rows
            refresh()

        search.textChanged.connect(refresh)
        search.returnPressed.connect(execute)
        items.currentRowChanged.connect(selected)
        items.itemActivated.connect(lambda *_: execute())
        run.clicked.connect(execute)
        refresh()
        dialog.open()
        search.setFocus()
        if context is not None:
            context[2].runJavaScript("JSON.stringify(window.kfpsWorkspaceCommands?.list() || null)", receive)

    @Slot()
    def openTasks(self):
        if self._closed:
            return
        if self._task_dialog is not None and isValid(self._task_dialog):
            self._task_dialog.show()
            return
        dialog = self._dialog("Background tasks")
        self._task_dialog = dialog
        dialog.setObjectName("WorkspaceTaskDialog")
        layout = QVBoxLayout(dialog)
        listing = QListWidget(dialog)
        listing.setObjectName("WorkspaceTaskList")
        detail = QLabel(dialog)
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        progress = QProgressBar(dialog)
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setFixedHeight(4)
        layout.addWidget(listing, 1)
        layout.addWidget(progress)
        layout.addWidget(detail)
        bar = QHBoxLayout()
        buttons = {}
        for key, label in (("cancel", "Stop safely"), ("retry", "Retry failed"), ("result", "Open result"), ("review", "Review")):
            button = QPushButton(label, dialog)
            buttons[key] = button
            bar.addWidget(button)
            button.clicked.connect(lambda _=False, k=key: action(k))
        layout.addLayout(bar)
        clear = QPushButton("Clear finished", dialog)
        clear.clicked.connect(self.journal.clearFinished)
        layout.addWidget(clear)

        def selected():
            item = listing.currentItem()
            row = next((r for r in self.journal.rows if item and r['id'] == item.data(Qt.ItemDataRole.UserRole)), None)
            for key, button in buttons.items():
                reviewable = row and (not row['source'].startswith('web:') or row['running'])
                button.setEnabled(bool(row and (reviewable if key == 'review' else row.get(key))))
            progress.setVisible(bool(row and row['running']))
            detail.setText((row['status']+'\n'+row['detail'] +
                ('\nThis operation cannot be stopped safely here.' if row['running'] and not row['cancel'] else ''))
                if row else 'No background tasks')

        def refresh():
            if not isValid(dialog):
                return
            item = listing.currentItem()
            token = item.data(Qt.ItemDataRole.UserRole) if item else None
            listing.clear()
            for row in self.journal.rows:
                item = QListWidgetItem(row['label']+'\n'+row['status'])
                item.setData(Qt.ItemDataRole.UserRole, row['id'])
                listing.addItem(item)
                if token == row['id']:
                    listing.setCurrentItem(item)
            if listing.currentRow() < 0:
                listing.setCurrentRow(0)
            selected()

        def action(key):
            item = listing.currentItem()
            row = next((r for r in self.journal.rows if item and r['id'] == item.data(Qt.ItemDataRole.UserRole)), None)
            if row is None:
                return
            if key == 'review':
                if row['source'].startswith('web:') and not row['running']:
                    return
                dialog.accept()
                web = self._web_tasks.get(row['source'].removeprefix('web:'))
                if web is not None and self.shell is not None and self.shell.owners.get(web.name) is web.owner and web.owner is not None:
                    self.shell.show_surface(web.name, background=True)
                else:
                    self.navigate(row['page'])
            else:
                if not self.journal.act(row['id'], key):
                    return
                if key == 'result':
                    dialog.accept()
            if isValid(dialog):
                refresh()

        listing.currentRowChanged.connect(selected)
        self.journal.changed.connect(refresh)
        self.journal.actionFailed.connect(detail.setText)
        def cleanup():
            self._task_dialog = None
            self.journal.changed.disconnect(refresh)
            self.journal.actionFailed.disconnect(detail.setText)
        dialog.finished.connect(cleanup)
        timer = QTimer(dialog)
        timer.setInterval(750)
        timer.timeout.connect(self._poll_web_activity)
        dialog.finished.connect(timer.stop)
        refresh()
        dialog.open()
        timer.start()
        self._poll_web_activity()

    def close(self):
        self._closed = True
        self.journal.close()
        for dialog in list(self._dialogs):
            if isValid(dialog):
                dialog.reject()
