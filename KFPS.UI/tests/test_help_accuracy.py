"""Keep user-facing transfer and persistence advice aligned with supported paths."""
import json
from pathlib import Path
import sys
import unittest

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]

from PySide6.QtCore import QCoreApplication
from game_adapters.registry import ADAPTERS
from kfps_ui.help_service import HelpService


class HelpAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.topics = {item["key"]: item for item in json.loads((UI / "help" / "topics.json").read_text(encoding="utf-8"))["topics"]}

    def text(self, key):
        return json.dumps(self.topics[key]).lower()

    def test_transfer_count_and_optional_grouping(self):
        text = self.text("fh6-template")
        for phrase in ("3000", "1842", "for import", "for live export", "recommended", "no longer mandatory", "exact count"):
            self.assertIn(phrase, text)
        self.assertNotIn("cannot be used as 3000", text)
        tooltip = (UI / "qml" / "pages" / "JsonPage.qml").read_text(encoding="utf-8")
        self.assertIn("not the JSON shape count", tooltip)
        self.assertIn("not its group count", tooltip)

    def test_fh5_export_is_not_fh5_import(self):
        self.assertTrue(ADAPTERS["fh5"].capabilities.offline_export)
        self.assertFalse(ADAPTERS["fh5"].capabilities.offline_import)
        self.assertIn("fh5 offline export is available; fh5 offline import is not", self.text("export-games"))
        self.assertIn("microsoft store/xbox wgs", self.text("export-games"))

    def test_editor_storage_and_sharing_boundaries(self):
        source = (ROOT / "KFPS.Editor" / "web" / "editor.js").read_text(encoding="utf-8")
        self.assertIn("EDITOR_PROJECT_MAX_BYTES = 150 * 1024 * 1024", source)
        self.assertIn("EDITOR_REFERENCE_MAX_BYTES = 100 * 1024 * 1024", source)
        for phrase in ("100 mib", "150 mib", "75 mib", "79 mb", "no 16-megapixel"):
            self.assertIn(phrase, self.text("editor-snapping"))
        self.assertIn("cannot preserve editor groups", self.text("editor-export"))
        self.assertIn("kfps editor.exe", self.text("editor-overview"))
        self.assertIn("before a checkpoint finishes", self.text("editor-history"))

    def test_preview_and_report_boundaries(self):
        self.assertIn("export does not launch the 3d preview", self.text("full-livery-packages"))
        self.assertIn("not discarded from the source record", self.text("full-livery-packages"))
        for phrase in ("nothing is sent until", "publicly", "authorized kfps support staff", "not uploaded automatically"):
            self.assertIn(phrase, self.text("reports"))

    def test_actual_help_search_selection_and_related_navigation(self):
        service = HelpService()
        for query, key, phrase in (
            ("1842", "fh6-template", "For live export"),
            ("reference", "editor-snapping", "75 MiB"),
            ("report", "reports", "Nothing is sent until"),
            ("livery", "full-livery-packages", "Export does not launch"),
        ):
            service.setCategory("all")
            service.search(query)
            self.assertTrue(service.hasResults, query)
            service.selectTopic(key)
            self.assertIn(phrase, service.selectedTopicText())
            for related in service.relatedTopics:
                self.assertIn(related["key"], self.topics)
        service.search("no-such-help-topic-9281")
        self.assertFalse(service.hasResults)
        service.selectTopic("editor-overview")
        self.assertTrue(service.hasResults)
        self.assertIn("KFPS Editor.exe", service.selectedTopicText())


if __name__ == "__main__":
    unittest.main()
