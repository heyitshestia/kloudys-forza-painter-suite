"""Theme-aware text metrics, using the real QML singleton and controls."""
from pathlib import Path
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


UI = Path(__file__).resolve().parents[1]


class NightCityTypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.font_ids = [QFontDatabase.addApplicationFont(str(path))
                        for path in (UI / "assets/fonts/night-city-2077").glob("*.ttf")]

    def setUp(self):
        self.engine = QQmlEngine()
        self.engine.addImportPath(str(UI / "qml"))
        self.engine.rootContext().setContextProperty("screenshotMode", True)
        self.component = QQmlComponent(self.engine)
        self.component.setData(b'''
import QtQuick
import Kfps.Theme 1.0
import "components"
Item {
    property string selectedTheme: "Night City 2077"
    Binding { target: Theme; property: "themeName"; value: selectedTheme }
    Binding { target: Theme; property: "supporterUnlocked"; value: true }
    Binding { target: Theme; property: "loadedUiFontFamily"; value: "Rajdhani" }
    property var sizes: [8.1, 9.4, 10.5, 12, 13, 14, 21].map(Theme.textSize)
    property var buttonSizes: [8, 12, 13, 14].map(Theme.typeSize)
    property var geometry: [8.1, 12, 21].map(Theme.px)
    property int bodyWeight: Theme.bodyWeight
    property real bodyLineHeight: Theme.bodyLineHeight
    property string family: Theme.fontFamily
    property string activeTheme: Theme.activeThemeName
    Label { objectName: "label"; text: "Theme preset" }
    KfpsSwitch { objectName: "switch"; width: 280; text: "Ambient background motion" }
    QuickActionRow { objectName: "folder"; width: 280; dense: true;
        title: "Editor projects"; subtitle: "C:/Users/Example/Very long project folder" }
}
''', QUrl.fromLocalFile(str(UI / "qml" / "typography-test.qml")))
        self.assertEqual(self.component.status(), QQmlComponent.Ready,
                         "\n".join(error.toString() for error in self.component.errors()))
        self.root = self.component.create()
        self.assertIsNotNone(self.root)
        self.window = QQuickWindow()
        self.root.setParentItem(self.window.contentItem())
        self.window.resize(400, 300)
        self.window.show()
        QTest.qWait(30)

    def tearDown(self):
        self.window.close()
        self.root.deleteLater()
        self.app.processEvents()
        self.window.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    def values(self, name):
        value = self.root.property(name)
        return value.toVariant() if hasattr(value, "toVariant") else value

    def test_small_type_has_readable_floor_without_scaling_geometry(self):
        self.assertEqual(self.values("sizes"), [14, 14, 14, 14, 14, 15, 23])
        self.assertEqual(self.values("buttonSizes"), [14, 14, 14, 15])
        self.assertEqual(self.values("geometry"), [8, 12, 21])

    def test_rajdhani_is_retained_with_a_real_medium_body_face(self):
        self.assertEqual(self.root.property("family"), "Rajdhani")
        self.assertEqual(self.root.property("bodyWeight"), int(QFont.Medium))
        font = QFont("Rajdhani")
        font.setWeight(QFont.Medium)
        font.setPixelSize(14)
        self.assertEqual(QFontInfo(font).family(), "Rajdhani")
        self.assertEqual(QFontInfo(font).styleName(), "Medium")
        self.assertAlmostEqual(self.root.property("bodyLineHeight"), 1.2)

    def test_real_switch_and_folder_labels_use_readable_type_and_fit_vertically(self):
        switch = self.root.findChild(QQuickItem, "switch")
        label = switch.property("contentItem")
        font = label.property("font")
        self.assertEqual(font.pixelSize(), 14)
        self.assertEqual(font.weight(), QFont.Medium)
        self.assertEqual(label.property("lineHeight"), 1.2)
        self.assertGreaterEqual(switch.property("implicitHeight"), label.property("implicitHeight") + 4)
        folder = self.root.findChild(QObject, "folder")
        self.assertIn("C:/Users/Example/Very long project folder", folder.property("effectiveToolTipText"))
        column = next(item for item in folder.childItems()
                      if item.metaObject().className().startswith("QQuickColumn"))
        labels = [item for item in column.childItems() if item.property("text")]
        self.assertEqual(len(labels), 2)
        for item in labels:
            self.assertEqual(item.property("font").pixelSize(), 14)
            self.assertEqual(item.property("font").weight(), QFont.Medium)
        self.assertGreaterEqual(folder.property("implicitHeight"),
                                sum(item.property("implicitHeight") for item in labels) + 9)

    def test_other_themes_keep_original_metrics_and_switching_back_restores_policy(self):
        names = ("Night Blossom", "Command Prompt", "Windows 94", "Patron's Atelier",
                 "Carbon Dark", "Overdrive 200X", "Apex Vector", "RX-93 Psycho-Frame",
                 "Original Xbox", "Original PS2", "NieR Automata")
        for name in names:
            with self.subTest(theme=name):
                self.root.setProperty("selectedTheme", name)
                self.app.processEvents()
                self.assertEqual(self.root.property("activeTheme"), name)
                self.assertEqual(self.values("sizes"), [8, 9, 11, 12, 13, 14, 21])
                self.assertEqual(self.values("buttonSizes"), [12, 12, 13, 14])
                self.assertEqual(self.root.property("bodyWeight"), int(QFont.Normal))
                self.assertEqual(self.root.property("bodyLineHeight"), 1.0)
        self.root.setProperty("selectedTheme", "Night City 2077")
        self.app.processEvents()
        self.assertEqual(self.values("sizes")[0], 14)


if __name__ == "__main__":
    unittest.main()
