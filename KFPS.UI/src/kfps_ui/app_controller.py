from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class AppController(QObject):
    changed = Signal()

    # Creation-first public navigation. Older routes stay valid so docs,
    # shortcuts, screenshots, and update flows do not break.
    PAGES = {
        "create": "Create",
        "outputs": "Outputs",
        "editor": "Editor",
        "help": "Help",
        "settings": "Settings",
        "dashboard": "Create",
        "generate": "Advanced Generator",
        "json": "Outputs",
        "library": "Outputs",
        "images": "Source Check",
        "tools": "Image Tools",
        "reports": "Reports",
        "update": "Update",
    }

    SUBTITLES = {
        "create": "Source, generation, preview, and next step without page scrolling.",
        "outputs": "Select one JSON, inspect it, then import or export.",
        "editor": "Launch the Fabric editor and manage saved editor projects.",
        "help": "Workflow guides, import notes, and troubleshooting.",
        "settings": "Preferences, folders, maintenance, and diagnostics.",
        "generate": "Full generator controls for advanced/manual runs.",
        "images": "Source image measurements and resize guidance.",
        "tools": "Source preparation links and external image tools.",
        "reports": "Create a local diagnostic report for support.",
        "update": "Check and apply app updates.",
    }

    # Keep the primary workflow free from the bottom log panel so all visible
    # options fit on screen. Advanced/maintenance pages keep the live log.
    LOG_PAGES = {"generate", "images", "reports", "update"}
    ALIASES = {"dashboard": "create", "json": "outputs", "library": "outputs", "learn": "help"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = "create"

    def _canonical(self, page: str) -> str:
        return self.ALIASES.get(str(page or ""), str(page or ""))

    @Property(str, notify=changed)
    def currentPage(self):
        return self._page

    @Property(str, notify=changed)
    def pageTitle(self):
        return self.PAGES.get(self._page, "KFPS")

    @Property(str, notify=changed)
    def pageSubtitle(self):
        return self.SUBTITLES.get(self._page, "Creation-focused KFPS workspace.")

    @Property(str, notify=changed)
    def windowTitle(self):
        return f"KFPS — {self.pageTitle}"

    @Property(bool, notify=changed)
    def showBottomPanel(self):
        return self._page in self.LOG_PAGES

    @Property(str, notify=changed)
    def bottomMode(self):
        return "log"

    @Slot(str)
    def navigate(self, page):
        target = self._canonical(page)
        if target in self.PAGES and target != self._page:
            self._page = target
            self.changed.emit()
