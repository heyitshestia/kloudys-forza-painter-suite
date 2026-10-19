"""The native WebEngine backing color must never have fractional alpha."""
from pathlib import Path
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


class LiveryViewerBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        page = (Path(__file__).resolve().parents[1] / "qml/pages/LiveryPage.qml").read_text(encoding="utf-8")
        expressions = re.findall(r"^\s+backgroundColor:\s*(.+)$", page, re.MULTILINE)
        self.assertEqual(len(expressions), 1)
        expression = expressions[0].replace("Theme.previewSurface", "sourceColor")
        self.engine = QQmlEngine()
        self.component = QQmlComponent(self.engine)
        self.component.setData((
            'import QtQuick\nQtObject { property color sourceColor: "#d908050b"; '
            'readonly property color backingColor: ' + expression + ' }'
        ).encode(), QUrl())
        self.item = self.component.create()
        self.assertIsNotNone(self.item, str(self.component.errors()))

    def tearDown(self):
        del self.item
        del self.component
        del self.engine

    def test_crashing_night_blossom_color_keeps_rgb_without_fractional_alpha(self):
        actual = self.item.property("backingColor")
        self.assertEqual(actual.name(), "#08050b")
        self.assertEqual(actual.alpha(), 255)

    def test_runtime_theme_updates_are_safe_for_every_alpha_value(self):
        for alpha in range(256):
            with self.subTest(alpha=alpha):
                source = QColor(83, 154, 217, alpha)
                self.item.setProperty("sourceColor", source)
                actual = self.item.property("backingColor")
                self.assertEqual(actual.getRgb(), (83, 154, 217, 255))


if __name__ == "__main__":
    unittest.main()
